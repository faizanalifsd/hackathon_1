"""
indexer.py — Chunk, embed, and upload all 14 chapters to Qdrant.
Run this script once after adding/updating chapters:
    python indexer.py
"""
import os
import glob
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

qdrant = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

COLLECTION = "physical_ai_book"
CHUNK_SIZE = 500  # words per chunk
DOCS_PATH = "../docusaurus_website/docs/*.md"


def chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def index_all_chapters():
    # Recreate collection (clean slate)
    qdrant.recreate_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )
    print(f"Collection '{COLLECTION}' ready.")

    points = []
    chapter_files = sorted(glob.glob(DOCS_PATH))

    if not chapter_files:
        print(f"No markdown files found at: {DOCS_PATH}")
        return

    for path in chapter_files:
        chapter_name = os.path.basename(path).replace(".md", "")
        with open(path, encoding="utf-8") as f:
            content = f.read()

        chunks = chunk_text(content)
        print(f"  {chapter_name}: {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            try:
                embedding = openai_client.embeddings.create(
                    input=chunk,
                    model="text-embedding-3-small",
                ).data[0].embedding

                points.append(PointStruct(
                    id=len(points),
                    vector=embedding,
                    payload={
                        "text": chunk,
                        "chapter": chapter_name,
                        "chunk_index": i,
                    },
                ))
            except Exception as e:
                print(f"    ERROR embedding chunk {i} of {chapter_name}: {e}")

    qdrant.upsert(collection_name=COLLECTION, points=points)
    print(f"\nIndexed {len(points)} chunks from {len(chapter_files)} chapters.")


if __name__ == "__main__":
    index_all_chapters()
