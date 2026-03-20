"""
rag.py — RAG pipeline using:
  Embeddings : Jina AI API (free, 768-dim)
  LLM Primary: Groq llama-3.3-70b-versatile
  LLM Fallback: OpenRouter deepseek/deepseek-r1-distill-llama-70b
"""
import os
import time
from dotenv import load_dotenv

load_dotenv()

from qdrant_client import QdrantClient
from groq import Groq
from openai import OpenAI
from embeddings import embed_one

# ── Clients (initialized after load_dotenv) ──────────────────────────────────
qdrant = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
openrouter_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

COLLECTION = "physical_ai_book"

SYSTEM_PROMPT = """You are Robo, a friendly robotics teaching assistant for a Physical AI & Humanoid Robotics textbook.

Rules:
- Answer ONLY based on the provided book context. Do not use outside knowledge.
- Always cite the chapter: "Based on Chapter X..."
- If context is insufficient, say: "I couldn't find that in the book. Try rephrasing or browse a specific chapter."
- Keep answers under 300 words.
- Use clear, encouraging language for learners.
- End every response with: "Want me to explain [related concept]?"
"""


def _call_groq(context: str, question: str) -> str:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context from the book:\n{context}\n\nStudent question: {question}"},
        ],
        max_tokens=500,
        temperature=0.3,
    )
    return response.choices[0].message.content


def _call_openrouter(context: str, question: str) -> str:
    response = openrouter_client.chat.completions.create(
        model="deepseek/deepseek-r1-distill-llama-70b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context from the book:\n{context}\n\nStudent question: {question}"},
        ],
        max_tokens=500,
        temperature=0.3,
    )
    return response.choices[0].message.content


async def answer_question(question: str, selected_text: str = "") -> dict:
    query = f"{selected_text}\n\n{question}".strip() if selected_text else question

    try:
        query_vector = embed_one(query)
    except Exception as e:
        return {"answer": f"Embedding error: {str(e)}"}

    try:
        results = qdrant.query_points(
            collection_name=COLLECTION,
            query=query_vector,
            limit=3,
            score_threshold=0.6,
        ).points
    except Exception as e:
        return {"answer": "I couldn't connect to the knowledge base. Please try again shortly."}

    if not results:
        return {"answer": "I couldn't find that in the book. Try rephrasing or browse a specific chapter."}

    context = "\n\n---\n\n".join([
        f"[{r.payload.get('chapter', 'Unknown Chapter')}]\n{r.payload['text']}"
        for r in results
    ])

    try:
        return {"answer": _call_groq(context, question)}
    except Exception as groq_err:
        print(f"Groq failed: {groq_err} — switching to OpenRouter")
        time.sleep(2)
        try:
            return {"answer": _call_openrouter(context, question)}
        except Exception:
            return {"answer": "Both LLM providers failed. Please try again shortly."}
