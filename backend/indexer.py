"""
indexer.py — Chunk all 14 chapters and upload to Qdrant.
Uses Jina AI embeddings API (free, 768-dim, works on any Python version).

Run once after chapters are written:
    python indexer.py
"""
import os
import glob
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from embeddings import embed, VECTOR_DIM
from dotenv import load_dotenv

load_dotenv()

qdrant = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)

COLLECTION = "physical_ai_book"
CHUNK_SIZE = 500
DOCS_PATH = "../docusaurus_website/docs/*.md"


def chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def index_all_chapters():
    # Recreate collection
    qdrant.recreate_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    print(f"Collection '{COLLECTION}' ready (dim={VECTOR_DIM}).")

    chapter_files = sorted(glob.glob(DOCS_PATH))
    if not chapter_files:
        print(f"No markdown files found at: {DOCS_PATH}")
        return

    all_chunks = []
    chunk_meta = []

    for path in chapter_files:
        chapter_name = os.path.basename(path).replace(".md", "")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        chunks = chunk_text(content)
        print(f"  {chapter_name}: {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                all_chunks.append(chunk)
                chunk_meta.append({"chapter": chapter_name, "chunk_index": i, "text": chunk})

    # Embed in batches of 20 (Jina API limit per request)
    print(f"\nEmbedding {len(all_chunks)} chunks via Jina AI...")
    all_vectors = []
    batch_size = 20
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        vectors = embed(batch)
        all_vectors.extend(vectors)
        print(f"  Embedded {min(i + batch_size, len(all_chunks))}/{len(all_chunks)}")

    # Build and upload Qdrant points
    points = [
        PointStruct(id=i, vector=all_vectors[i], payload=chunk_meta[i])
        for i in range(len(all_chunks))
    ]

    for i in range(0, len(points), 100):
        qdrant.upsert(collection_name=COLLECTION, points=points[i:i + 100])

    print(f"\nDone! Indexed {len(points)} chunks from {len(chapter_files)} chapters.")


if __name__ == "__main__":
    index_all_chapters()
