"""
evaluator.py
------------
Ye file "LLM-as-a-judge" logic implement karti hai.

Idea simple hai: RAG bot ne jo answer diya, wo answer un chunks se
"grounded" hai ya nahi (i.e., kya answer document me actually likha
hai, ya LLM ne khud se kuch bana diya / hallucinate kiya)?

Isko check karne ke liye hum ek DUSRA LLM call karte hain (Groq) jisme
usse "judge" bana dete hain -- usse answer + source chunks dono dete
hain aur JSON format me verdict maangte hain.
"""

import json
import re
from rag_core import _generate_with_retry

# 12 generic test questions -- ye kisi bhi policy/informational/govt
# scheme type document ke saath kaam karenge. User apna custom question
# bhi add kar sakta hai UI se.
DEFAULT_TEST_QUESTIONS = [
    "What is the eligibility criteria mentioned in this document?",
    "What is the process to apply or register?",
    "What documents are required for the application?",
    "What is the deadline or last date mentioned, if any?",
    "What benefits or entitlements does this document describe?",
    "Who is the target audience or beneficiary of this document?",
    "What fees or charges, if any, are mentioned?",
    "What is the validity period or duration mentioned?",
    "What are the penalties or consequences of non-compliance mentioned?",
    "Which authority or department issued or is responsible for this?",
    "What is the contact information or helpline mentioned, if any?",
    "What supporting evidence or proof is required, if any?",
]

JUDGE_PROMPT_TEMPLATE = """You are a strict fact-checking judge. Your job is to determine whether
a GENERATED ANSWER is fully supported by the given SOURCE CHUNKS, or whether it contains
information that is not present in the source (hallucination).

SOURCE CHUNKS:
{context}

GENERATED ANSWER:
{answer}

Evaluate the GENERATED ANSWER strictly against the SOURCE CHUNKS only. Do not use any outside
knowledge. Respond with ONLY a valid JSON object (no markdown, no code fences, no extra text)
in exactly this format:

{{
  "verdict": "Yes" or "Partially" or "No",
  "unsupported_part": "the specific phrase or claim from the answer that is NOT supported by the source, or empty string if verdict is Yes",
  "score": integer from 0 to 100 representing how well grounded the answer is,
  "reasoning": "one short sentence explaining the verdict"
}}

Verdict meaning:
- "Yes": every claim in the answer is directly supported by the source chunks.
- "Partially": most of the answer is supported, but some part is added/inferred/not explicitly present.
- "No": the answer is largely or entirely not supported by the source (hallucinated)."""


def _extract_json(raw_text: str) -> dict:
    """
    LLM kabhi kabhi JSON ke around ```json fences ya thoda extra text
    daal deta hai. Ye function safely JSON object nikaal ke parse karta hai.
    """
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned.strip(), flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned.strip()).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # fallback: pehla { se lekar last } tak ka substring nikaal lo
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def judge_answer(question: str, answer: str, context_chunks: list) -> dict:
    """
    Answer ko source chunks ke against evaluate karta hai.
    Returns dict: {verdict, unsupported_part, score, reasoning}
    """
    context_text = "\n\n---\n\n".join(context_chunks) if context_chunks else "(no context retrieved)"
    prompt = JUDGE_PROMPT_TEMPLATE.format(context=context_text, answer=answer)

    response_text = _generate_with_retry(prompt, json_mode=True)

    try:
        result = _extract_json(response_text)
    except (json.JSONDecodeError, AttributeError):
        # Agar judge ka output parse na ho paaye, safe fallback de do
        result = {
            "verdict": "Partially",
            "unsupported_part": "Judge response could not be parsed.",
            "score": 50,
            "reasoning": "Could not parse judge model output; defaulting to neutral verdict.",
        }

    # Basic sanitation so the frontend never breaks on missing keys
    result.setdefault("verdict", "Partially")
    result.setdefault("unsupported_part", "")
    result.setdefault("score", 50)
    result.setdefault("reasoning", "")

    if result["verdict"] not in ("Yes", "Partially", "No"):
        result["verdict"] = "Partially"

    try:
        result["score"] = max(0, min(100, int(result["score"])))
    except (ValueError, TypeError):
        result["score"] = 50

    result["question"] = question
    return result