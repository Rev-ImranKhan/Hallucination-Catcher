"""
app.py
------
Flask server jo poore "Hallucination Catcher" ko chalata hai.

Routes:
  GET  /                          -> main UI
  POST /upload                    -> document upload + RAG ingestion
  POST /run-evaluation            -> batch evaluation start karta hai (background thread)
  GET  /run-evaluation/status/<job_id> -> polling endpoint for progress + final results

Design note: batch evaluation me multiple Gemini calls lagte hain (RAG answer +
judge, har question ke liye = 2 calls x N questions), isliye ye kaam background
thread me chalta hai aur frontend progress bar ke liye status poll karta hai.
"""

import os
import uuid
import threading
import traceback

from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import google.generativeai as genai

from rag_core import RagPipeline
from evaluator import DEFAULT_TEST_QUESTIONS, judge_answer

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not set. Add it to your .env file before using the app.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB upload limit

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# In-memory "session" state. Ek time me ek document active rehta hai.
# Production me ye per-user session/DB hona chahiye, lekin is portfolio
# project ke liye single global state kaafi hai.
# ---------------------------------------------------------------------------
STATE = {
    "pipeline": None,          # RagPipeline instance
    "filename": None,
}

# Background evaluation jobs, job_id -> job dict
JOBS = {}


@app.route("/")
def index():
    return render_template("index.html", default_questions=DEFAULT_TEST_QUESTIONS)


@app.route("/upload", methods=["POST"])
def upload():
    if "document" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files["document"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    allowed_ext = (".pdf", ".txt")
    if not file.filename.lower().endswith(allowed_ext):
        return jsonify({"error": "Only PDF or TXT files are supported."}), 400

    save_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(save_path)

    try:
        pipeline = RagPipeline()
        chunk_count = pipeline.ingest(save_path)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to process document: {str(e)}"}), 500

    STATE["pipeline"] = pipeline
    STATE["filename"] = file.filename

    return jsonify({
        "message": "Document processed successfully.",
        "filename": file.filename,
        "chunk_count": chunk_count,
        "default_questions": DEFAULT_TEST_QUESTIONS,
    })


def _run_evaluation_job(job_id, questions):
    job = JOBS[job_id]
    pipeline = STATE["pipeline"]
    results = []
    summary = {"Yes": 0, "Partially": 0, "No": 0, "Error": 0}

    for i, question in enumerate(questions):
        try:
            answer, chunks = pipeline.answer_question(question)
            verdict = judge_answer(question, answer, chunks)
            verdict["answer"] = answer
            verdict["source_chunks"] = chunks
            summary[verdict["verdict"]] += 1
            results.append(verdict)
        except Exception as e:
            # IMPORTANT: this is a processing ERROR (e.g. API rate limit,
            # network issue) -- NOT a real "hallucinated" judge verdict.
            # We keep it in its own bucket so the summary dashboard doesn't
            # misleadingly report these as hallucinations.
            traceback.print_exc()
            error_message = str(e)
            is_rate_limit = "429" in error_message or "quota" in error_message.lower()
            results.append({
                "question": question,
                "answer": "",
                "verdict": "Error",
                "unsupported_part": "",
                "score": 0,
                "reasoning": (
                    "Rate limit hit while calling Gemini API. Try again in a minute, "
                    "or reduce the number of questions per run."
                ) if is_rate_limit else f"An error occurred while processing this question: {error_message}",
                "source_chunks": [],
            })
            summary["Error"] += 1

        job["completed"] = i + 1
        job["total"] = len(questions)

    job["status"] = "done"
    job["results"] = results
    job["summary"] = summary


@app.route("/run-evaluation", methods=["POST"])
def run_evaluation():
    if STATE["pipeline"] is None:
        return jsonify({"error": "No document uploaded yet."}), 400

    data = request.get_json(force=True) or {}
    questions = data.get("questions", [])
    questions = [q.strip() for q in questions if q and q.strip()]

    if not questions:
        return jsonify({"error": "No questions provided."}), 400

    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "status": "running",
        "completed": 0,
        "total": len(questions),
        "results": None,
        "summary": None,
    }

    thread = threading.Thread(target=_run_evaluation_job, args=(job_id, questions), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/run-evaluation/status/<job_id>")
def evaluation_status(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown job id."}), 404

    response = {
        "status": job["status"],
        "completed": job["completed"],
        "total": job["total"],
    }
    if job["status"] == "done":
        response["results"] = job["results"]
        response["summary"] = job["summary"]

    return jsonify(response)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
