from agents import Agent, Runner
from qdrant_client import QdrantClient
from openai import OpenAI
import os

qdrant = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

COLLECTION = "physical_ai_book"

SYSTEM_PROMPT = """
You are Robo, a friendly and knowledgeable robotics teaching assistant for a Physical AI & Humanoid Robotics textbook.

Rules you must follow:
- Answer ONLY based on the provided book context. Do not use general knowledge outside the book.
- Always cite the chapter your answer comes from: "Based on Chapter X..."
- If the context is insufficient or no results were found, say exactly: "I couldn't find that in the book. Try rephrasing or browse a specific chapter."
- Keep answers under 300 words.
- Use encouraging, clear language suited for learners.
- End every response with a follow-up suggestion: "Want me to explain [related concept]?"
"""

async def answer_question(question: str, selected_text: str = "") -> dict:
    # Build query — prepend selected text if provided
    query = f"{selected_text}\n\n{question}".strip() if selected_text else question

    # Embed the query
    try:
        embedding = openai_client.embeddings.create(
            input=query,
            model="text-embedding-3-small"
        ).data[0].embedding
    except Exception as e:
        return {"answer": f"Embedding error: {str(e)}"}

    # Search Qdrant
    try:
        results = qdrant.search(
            collection_name=COLLECTION,
            query_vector=embedding,
            limit=3,
            score_threshold=0.7,
        )
    except Exception as e:
        return {"answer": "I couldn't connect to the knowledge base. Please try again shortly."}

    if not results:
        return {"answer": "I couldn't find that in the book. Try rephrasing or browse a specific chapter."}

    # Build context from top results
    context = "\n\n---\n\n".join([
        f"[{r.payload.get('chapter', 'Unknown Chapter')}]\n{r.payload['text']}"
        for r in results
    ])

    # Answer via OpenAI Agents SDK
    try:
        agent = Agent(
            name="Robo",
            instructions=SYSTEM_PROMPT,
            model="gpt-4o-mini",
        )
        result = await Runner.run(
            agent,
            f"Context from the book:\n{context}\n\nStudent question: {question}"
        )
        return {"answer": result.final_output}
    except Exception as e:
        return {"answer": f"I encountered an error generating the response: {str(e)}"}
