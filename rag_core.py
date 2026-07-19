"""
rag_core.py
-----------
Ye file "source of truth" document ko process karke ek simple RAG
(Retrieval-Augmented Generation) pipeline banati hai:

1. PDF/text se raw text nikalna (pypdf)
2. Text ko chhote chunks me todna (overlap ke saath)
3. Har chunk ka embedding banana (Gemini embedding model)
4. ChromaDB me store karna
5. Kisi bhi question ke liye top-k relevant chunks retrieve karna
6. Un chunks ke context ke saath Groq se answer generate karna

Is module ka poora purpose hai ek "answer + jin chunks se wo answer
banaya gaya" dono return karna, kyunki evaluator.py ko dono cheezein
chahiye grounding check karne ke liye.
"""

import os
import time
import uuid
import chromadb
from groq import Groq
import google.generativeai as genai
from pypdf import PdfReader

EMBEDDING_MODEL = "models/gemini-embedding-001"          # Gemini used ONLY for embeddings
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")  # Groq used for all text generation

CHUNK_SIZE = 1000   # characters per chunk
CHUNK_OVERLAP = 150 # overlap between consecutive chunks
TOP_K = 4           # number of chunks retrieved per question

# Free-tier Gemini embedding quota is limited requests/minute. This delay
# between embedding calls plus retry-with-backoff keeps us under that limit
# instead of firing all chunks back-to-back and hitting a 429.
EMBED_CALL_DELAY_SECONDS = 1.0
EMBED_MAX_RETRIES = 5


def _embed_with_retry(content: str, task_type: str):
    """Calls Gemini embed_content with retry + exponential backoff on 429s."""
    delay = 5
    for attempt in range(EMBED_MAX_RETRIES):
        try:
            result = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=content,
                task_type=task_type,
            )
            return result["embedding"]
        except Exception as e:
            is_rate_limit = "429" in str(e) or "quota" in str(e).lower()
            if is_rate_limit and attempt < EMBED_MAX_RETRIES - 1:
                time.sleep(delay)
                delay *= 2  # exponential backoff: 5s, 10s, 20s, 40s...
                continue
            raise


# Groq's free tier is much more generous than Gemini's, so all answer
# generation + judge calls go through Groq. Client is created lazily so we
# don't need GROQ_API_KEY present at import time (only when actually used).
GENERATE_CALL_DELAY_SECONDS = 0.5
GENERATE_MAX_RETRIES = 5

_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set. Add it to your .env file.")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def _generate_with_retry(prompt: str, json_mode: bool = False) -> str:
    """Calls Groq chat completion with retry + exponential backoff on rate limits.

    Returns the plain text content of the model's reply (a string).
    """
    client = _get_groq_client()
    delay = 5
    for attempt in range(GENERATE_MAX_RETRIES):
        try:
            kwargs = {}
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=1024,
                **kwargs,
            )
            time.sleep(GENERATE_CALL_DELAY_SECONDS)  # stay comfortably under rate limits
            return response.choices[0].message.content
        except Exception as e:
            error_text = str(e)
            is_daily_limit = "per day" in error_text.lower() or "daily" in error_text.lower()
            is_rate_limit = "429" in error_text or "rate_limit" in error_text.lower()

            if is_daily_limit:
                raise RuntimeError(
                    "Groq free-tier DAILY quota exhausted. "
                    "Wait for it to reset, or use a different API key. "
                    f"Original error: {error_text}"
                ) from e

            if is_rate_limit and attempt < GENERATE_MAX_RETRIES - 1:
                time.sleep(delay)
                delay *= 2  # exponential backoff: 5s, 10s, 20s, 40s...
                continue
            raise


class RagPipeline:
    """
    Ek object = ek uploaded document ka RAG pipeline.
    Har naye upload par naya RagPipeline instance banega (app.py isko
    global state me hold karega for the current session/document).
    """

    def __init__(self):
        # In-memory ChromaDB client -> restart hone par data clear ho jaata hai.
        # Ye evaluation tool ke liye theek hai, hume persistence ki zaroorat nahi.
        self._client = chromadb.Client()
        collection_name = f"doc_{uuid.uuid4().hex[:8]}"
        self.collection = self._client.create_collection(name=collection_name)
        self.chunk_count = 0
        self.source_filename = None

    # ------------------------------------------------------------------
    # STEP 1: Text extraction
    # ------------------------------------------------------------------
    @staticmethod
    def extract_text(filepath: str) -> str:
        """PDF ya .txt file se plain text nikalta hai."""
        if filepath.lower().endswith(".pdf"):
            reader = PdfReader(filepath)
            pages_text = []
            for page in reader.pages:
                pages_text.append(page.extract_text() or "")
            return "\n".join(pages_text)
        else:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

    # ------------------------------------------------------------------
    # STEP 2: Chunking
    # ------------------------------------------------------------------
    @staticmethod
    def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        """
        Simple sliding-window character chunking with overlap.
        Overlap isliye rakha hai taaki chunk boundary par koi important
        sentence beech me na kat jaaye aur context na toote.
        """
        text = " ".join(text.split())  # normalize whitespace
        if not text:
            return []

        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == text_len:
                break
            start = end - overlap  # step back for overlap
        return chunks

    # ------------------------------------------------------------------
    # STEP 3 & 4: Embed + Store
    # ------------------------------------------------------------------
    def ingest(self, filepath: str):
        """Poora document process karke ChromaDB me daal deta hai."""
        self.source_filename = os.path.basename(filepath)
        raw_text = self.extract_text(filepath)
        chunks = self.chunk_text(raw_text)

        if not chunks:
            raise ValueError("Document se koi text nahi nikal paaya. File check karo.")

        ids, embeddings, documents = [], [], []
        for i, chunk in enumerate(chunks):
            embedding = _embed_with_retry(chunk, task_type="retrieval_document")
            ids.append(f"chunk_{i}")
            embeddings.append(embedding)
            documents.append(chunk)
            time.sleep(EMBED_CALL_DELAY_SECONDS)  # stay under free-tier requests/minute limit

        self.collection.add(ids=ids, embeddings=embeddings, documents=documents)
        self.chunk_count = len(chunks)
        return self.chunk_count

    # ------------------------------------------------------------------
    # STEP 5: Retrieve
    # ------------------------------------------------------------------
    def retrieve(self, question: str, top_k: int = TOP_K):
        """Question ke embedding se top-k most relevant chunks nikalta hai."""
        query_embedding = _embed_with_retry(question, task_type="retrieval_query")

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(self.chunk_count, 1)),
        )
        return results["documents"][0] if results["documents"] else []

    # ------------------------------------------------------------------
    # STEP 6: Generate answer using retrieved context
    # ------------------------------------------------------------------
    @staticmethod
    def generate_answer(question: str, context_chunks: list):
        context_text = "\n\n---\n\n".join(context_chunks)
        prompt = f"""You are a helpful assistant answering questions strictly using the
provided document context below. Only use information present in the context.
If the context does not contain the answer, say so honestly instead of guessing.

CONTEXT:
{context_text}

QUESTION:
{question}

Give a clear, concise answer (2-4 sentences) based only on the context above."""

        answer_text = _generate_with_retry(prompt)
        return answer_text.strip()

    def answer_question(self, question: str):
        """Full retrieve + generate flow. Returns (answer, retrieved_chunks)."""
        chunks = self.retrieve(question)
        if not chunks:
            return "No relevant context found in the document.", []
        answer = self.generate_answer(question, chunks)
        return answer, chunks