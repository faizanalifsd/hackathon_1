"""
embeddings.py — Free embeddings via Jina AI API.
Model: jina-embeddings-v2-base-en (768-dim)
Free tier: 1M tokens/month — no credit card needed.
Get key at: https://jina.ai (sign up → API key)
"""
import os
import requests

JINA_API_KEY = os.getenv("JINA_API_KEY")
JINA_MODEL = "jina-embeddings-v2-base-en"
VECTOR_DIM = 768


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Returns list of 768-dim vectors."""
    response = requests.post(
        "https://api.jina.ai/v1/embeddings",
        headers={
            "Authorization": f"Bearer {JINA_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": JINA_MODEL, "input": texts},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return [item["embedding"] for item in data["data"]]


def embed_one(text: str) -> list[float]:
    """Embed a single string."""
    return embed([text])[0]
