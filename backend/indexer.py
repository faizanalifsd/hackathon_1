"""
indexer.py — Chunk all 14 chapters and upload to Qdrant using fastembed.
No API key needed for embeddings (runs locally).

Run once:
    python indexer.py
"""
import os
import glob
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding
from dotenv import load_dotenv

load_dotenv()

qdrant = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)

# BAAI/bge-small-en-v1.5 → 384 dimensions, ~25 MB, runs on CPU
embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

COLLECTION = "physical_ai_book"
VECTOR_DIM = 384       # matches BAAI/bge-small-en-v1.5
CHUNK_SIZE = 500       # words per chunk
DOCS_PATH = "../docusaurus_website/docs/*.md"


def chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def index_all_chapters():
    # Recreate collection with correct vector size
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

    # Batch embed all chunks at once (fastembed is fast in batch mode)
    print(f"\nEmbedding {len(all_chunks)} chunks (this may take a minute)...")
    embeddings = list(embedder.embed(all_chunks))

    # Build Qdrant points
    points = [
        PointStruct(
            id=i,
            vector=embeddings[i].tolist(),
            payload=chunk_meta[i],
        )
        for i in range(len(all_chunks))
    ]

    # Upload in batches of 100
    batch_size = 100
    for i in range(0, len(points), batch_size):
        qdrant.upsert(collection_name=COLLECTION, points=points[i:i + batch_size])
        print(f"  Uploaded {min(i + batch_size, len(points))}/{len(points)} points")

    print(f"\nDone! Indexed {len(points)} chunks from {len(chapter_files)} chapters.")


if __name__ == "__main__":
    index_all_chapters()
