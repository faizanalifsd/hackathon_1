# execution_plan.md — Physical AI Textbook Project

> **Hackathon I — Panaversity**
> Project: Physical AI & Humanoid Robotics Textbook
> Status: In Progress
> Last Updated: 2026-03-18

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│              GitHub Pages (Frontend)                 │
│                                                      │
│   Docusaurus v3 (React)                              │
│   ├── /docs/          ← 14 chapters (Markdown)       │
│   ├── /src/components/ChatWidget.jsx  ← RAG UI       │
│   └── /src/theme/Root.js             ← Widget inject │
└────────────────────┬────────────────────────────────┘
                     │ HTTP (fetch)
┌────────────────────▼────────────────────────────────┐
│              Render.com (Backend)                    │
│                                                      │
│   FastAPI (Python 3.11)                              │
│   ├── POST /chat      ← RAG chatbot endpoint         │
│   ├── POST /index     ← Re-index book content        │
│   └── GET  /health    ← Health check                 │
└──────────┬──────────────────────┬───────────────────┘
           │                      │
┌──────────▼──────┐    ┌──────────▼──────────────────┐
│  Qdrant Cloud   │    │     Neon Serverless Postgres  │
│  (Embeddings)   │    │     (Chat history / sessions) │
└─────────────────┘    └──────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────┐
│              LLM Layer                               │
│   Primary:  Groq (llama-3.3-70b-versatile)           │
│   Fallback: OpenRouter (deepseek-r1-distill-70b)     │
│   RAG:      OpenAI Agents SDK (gpt-4o-mini)          │
│   Embed:    OpenAI text-embedding-3-small            │
└─────────────────────────────────────────────────────┘
```

---

## Phase 1 — Environment Setup
**Duration: Day 1 | Status: [ ] Not Started**

### Tasks

- [ ] **1.1** Install Node.js v18+, Python 3.11+
  ```bash
  node --version   # must be v18+
  python --version # must be 3.11+
  ```

- [ ] **1.2** Scaffold Docusaurus project
  ```bash
  npx create-docusaurus@latest physical-ai-book classic
  cd physical-ai-book
  npm start
  ```

- [ ] **1.3** Clone Spec-Kit Plus
  ```bash
  git clone https://github.com/panaversity/spec-kit-plus/
  ```

- [ ] **1.4** Create GitHub repo + push initial code
  ```bash
  git init
  git remote add origin https://github.com/YOUR_USER/physical-ai-book.git
  git push -u origin main
  ```

- [ ] **1.5** Enable GitHub Pages
  - Go to Settings → Pages → Source: GitHub Actions
  - Add `.github/workflows/deploy.yml` (see Appendix A)

- [ ] **1.6** Create accounts
  - [ ] neon.tech (free Postgres)
  - [ ] cloud.qdrant.io (free vector DB)
  - [ ] groq.com (free API key)
  - [ ] openrouter.ai (free credits)
  - [ ] openai.com (for embeddings — minimal cost)
  - [ ] render.com (free backend hosting)

- [ ] **1.7** Create `.env` file
  ```env
  GROQ_API_KEY=your_key_here
  OPENROUTER_API_KEY=your_key_here
  OPENAI_API_KEY=your_key_here
  QDRANT_URL=https://xxx.qdrant.io
  QDRANT_API_KEY=your_key_here
  NEON_DATABASE_URL=postgresql://user:pass@host/db
  ```

- [ ] **1.8** Add `.gitignore`
  ```
  .env
  __pycache__/
  node_modules/
  .docusaurus/
  build/
  ```

---

## Phase 2 — Book Content Writing
**Duration: Days 2–5 | Status: [ ] Not Started**

### Chapter Writing Script (Groq-powered)

```python
# scripts/write_chapter.py
import os
from groq import Groq
from openai import OpenAI

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
openrouter_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

CHAPTER_TEMPLATE = """
Write a complete textbook chapter with this structure:
## Chapter {num}: {title}
### Learning Objectives (3-5 bullets)
### Introduction (2-3 paragraphs)
### Core Concepts (subsections with explanations)
### Hands-On: Code Example (working Python/shell code with comments)
### Common Mistakes (3-5 pitfalls)
### Summary (5 bullets)
### Review Questions (3-5 questions)

Topic: {topic}
Audience: Intermediate learners who know Python/JS but are new to robotics.
Include actual ROS 2 / Python code where relevant.
Format: Markdown
"""

def write_chapter(num: int, title: str, topic: str) -> str:
    prompt = CHAPTER_TEMPLATE.format(num=num, title=title, topic=topic)
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Groq failed: {e} — switching to OpenRouter")
        response = openrouter_client.chat.completions.create(
            model="deepseek/deepseek-r1-distill-llama-70b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        return response.choices[0].message.content

CHAPTERS = [
    (1,  "What is Physical AI?",             "Embodied intelligence, physical laws, difference from digital AI"),
    (2,  "Humanoid Robotics Landscape",      "Overview of humanoid robots, key players, hardware overview"),
    (3,  "ROS 2 Architecture",               "Nodes, topics, services, actions, rclpy basics"),
    (4,  "Building ROS 2 Packages",          "Package creation, CMakeLists, launch files, parameters"),
    (5,  "URDF & Robot Description",         "URDF format, joints, links, visualisation in RViz"),
    (6,  "Gazebo Simulation Setup",          "Gazebo install, SDF format, physics simulation, sensors"),
    (7,  "Unity for Robotics",               "Unity Robotics Hub, importing URDF, human-robot interaction"),
    (8,  "NVIDIA Isaac SDK Overview",        "Isaac Sim, Isaac ROS, synthetic data generation"),
    (9,  "Visual SLAM & Navigation",         "VSLAM, Nav2, path planning for bipedal robots"),
    (10, "Sim-to-Real Transfer",             "Techniques for deploying sim-trained models to real robots"),
    (11, "Humanoid Kinematics & Dynamics",   "Forward/inverse kinematics, bipedal balance, ZMP"),
    (12, "Manipulation & Grasping",          "Gripper control, grasp planning, force feedback"),
    (13, "Conversational Robotics (VLA)",    "Whisper voice input, LLM to ROS 2 action translation"),
    (14, "Capstone: Autonomous Humanoid",    "Full pipeline: voice → plan → navigate → grasp"),
]

if __name__ == "__main__":
    import sys
    ch_num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    num, title, topic = CHAPTERS[ch_num - 1]
    content = write_chapter(num, title, topic)
    path = f"physical-ai-book/docs/chapter-{num:02d}-{title.lower().replace(' ', '-')[:30]}.md"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"Chapter {num} written → {path}")
```

### Chapter Status Tracker

| # | Title | Written | Indexed | Review |
|---|---|---|---|---|
| 1 | What is Physical AI? | [ ] | [ ] | [ ] |
| 2 | Humanoid Robotics Landscape | [ ] | [ ] | [ ] |
| 3 | ROS 2 Architecture | [ ] | [ ] | [ ] |
| 4 | Building ROS 2 Packages | [ ] | [ ] | [ ] |
| 5 | URDF & Robot Description | [ ] | [ ] | [ ] |
| 6 | Gazebo Simulation Setup | [ ] | [ ] | [ ] |
| 7 | Unity for Robotics | [ ] | [ ] | [ ] |
| 8 | NVIDIA Isaac SDK Overview | [ ] | [ ] | [ ] |
| 9 | Visual SLAM & Navigation | [ ] | [ ] | [ ] |
| 10 | Sim-to-Real Transfer | [ ] | [ ] | [ ] |
| 11 | Humanoid Kinematics & Dynamics | [ ] | [ ] | [ ] |
| 12 | Manipulation & Grasping | [ ] | [ ] | [ ] |
| 13 | Conversational Robotics (VLA) | [ ] | [ ] | [ ] |
| 14 | Capstone Project | [ ] | [ ] | [ ] |

---

## Phase 3 — RAG Backend (FastAPI)
**Duration: Days 5–7 | Status: [ ] Not Started**

### File Structure
```
backend/
├── main.py          ← FastAPI app
├── rag.py           ← RAG pipeline (OpenAI Agents SDK)
├── indexer.py       ← Chunk + embed + upload to Qdrant
├── db.py            ← Neon Postgres connection
├── requirements.txt
└── .env
```

### Key Endpoints

```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rag import answer_question

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

@app.post("/chat")
async def chat(payload: dict):
    question = payload.get("question", "")
    selected_text = payload.get("selected_text", "")
    return await answer_question(question, selected_text)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

### RAG Pipeline (OpenAI Agents SDK)

```python
# rag.py
from agents import Agent, Runner
from qdrant_client import QdrantClient
from openai import OpenAI
import os

qdrant = QdrantClient(url=os.getenv("QDRANT_URL"),
                      api_key=os.getenv("QDRANT_API_KEY"))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are Robo, a friendly robotics teaching assistant for a Physical AI textbook.
Answer ONLY based on the provided book context.
Always cite which chapter your answer comes from.
If context is insufficient, say: "I couldn't find that in the book."
Keep answers under 300 words.
End with a follow-up suggestion.
"""

async def answer_question(question: str, selected_text: str = "") -> dict:
    # 1. Embed the question
    query = f"{selected_text}\n\n{question}".strip() if selected_text else question
    embedding = openai_client.embeddings.create(
        input=query, model="text-embedding-3-small"
    ).data[0].embedding

    # 2. Search Qdrant
    results = qdrant.search(
        collection_name="physical_ai_book",
        query_vector=embedding,
        limit=3,
        score_threshold=0.7
    )

    if not results:
        return {"answer": "I couldn't find that in the book. Try rephrasing or browse a specific chapter."}

    # 3. Build context
    context = "\n\n---\n\n".join([
        f"[{r.payload.get('chapter', 'Unknown Chapter')}]\n{r.payload['text']}"
        for r in results
    ])

    # 4. Answer via OpenAI Agents SDK
    agent = Agent(
        name="Robo",
        instructions=SYSTEM_PROMPT,
        model="gpt-4o-mini"
    )
    result = await Runner.run(agent, f"Context:\n{context}\n\nQuestion: {question}")
    return {"answer": result.final_output}
```

### Book Indexer

```python
# indexer.py
import os, glob
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from openai import OpenAI

qdrant = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
COLLECTION = "physical_ai_book"

def chunk_text(text: str, size: int = 500) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i+size]) for i in range(0, len(words), size)]

def index_all_chapters():
    qdrant.recreate_collection(COLLECTION,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE))
    points = []
    for path in sorted(glob.glob("physical-ai-book/docs/*.md")):
        chapter_name = os.path.basename(path).replace(".md", "")
        with open(path) as f:
            content = f.read()
        for i, chunk in enumerate(chunk_text(content)):
            embedding = openai_client.embeddings.create(
                input=chunk, model="text-embedding-3-small"
            ).data[0].embedding
            points.append(PointStruct(
                id=len(points),
                vector=embedding,
                payload={"text": chunk, "chapter": chapter_name, "chunk_index": i}
            ))
    qdrant.upsert(collection_name=COLLECTION, points=points)
    print(f"Indexed {len(points)} chunks from {len(glob.glob('physical-ai-book/docs/*.md'))} chapters")

if __name__ == "__main__":
    index_all_chapters()
```

---

## Phase 4 — React Chatbot Widget
**Duration: Day 8 | Status: [ ] Not Started**

### Files to create:
- `src/components/ChatWidget.jsx` — floating chat UI
- `src/theme/Root.js` — injects widget into every page
- `src/css/chat.css` — widget styles

### Widget behaviour:
- Floating button (bottom-right corner)
- Opens chat panel when clicked
- Sends selected text automatically if user highlights content
- Connects to FastAPI `/chat` endpoint
- Shows "Robo" avatar and name in header

---

## Phase 5 — Deployment
**Duration: Day 9 | Status: [ ] Not Started**

- [ ] Run `npm run build` — verify no errors
- [ ] Push to GitHub → GitHub Actions auto-deploys to Pages
- [ ] Deploy FastAPI to Render.com (connect GitHub repo)
- [ ] Set environment variables in Render dashboard
- [ ] Run `python indexer.py` to index all chapters into Qdrant
- [ ] Test chatbot on live URL — ask 5 questions from the book
- [ ] Update `BACKEND_URL` in `ChatWidget.jsx` to Render URL

---

## Phase 6 — Demo Video
**Duration: Day 10 | Status: [ ] Not Started**

Script (90 seconds):
1. 0:00–0:15 — Show live book URL, navigate chapters
2. 0:15–0:40 — Click chatbot, ask: *"What is a ROS 2 node?"*
3. 0:40–0:65 — Highlight text in a chapter → ask a follow-up question
4. 0:65–0:90 — Show correct answer with chapter citation

---

## Appendix A — GitHub Actions Deploy Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy to GitHub Pages
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 18
      - name: Install & Build
        working-directory: physical-ai-book
        run: |
          npm ci
          npm run build
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./physical-ai-book/build
```

---

## Risk Log

| Risk | Likelihood | Mitigation |
|---|---|---|
| Groq rate limit during chapter gen | Medium | OpenRouter fallback in write_chapter.py |
| Qdrant free tier storage limit | Low | 500-word chunks keep total size small |
| Render.com cold starts | Medium | Add `/health` ping on chatbot open |
| GitHub Pages build failure | Low | Always test `npm run build` locally first |
| OpenAI embedding cost overrun | Very Low | ~1500 chunks × $0.00002 = $0.03 total |
