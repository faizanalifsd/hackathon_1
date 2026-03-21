# Physical AI & Humanoid Robotics Textbook — Project Working Documentation

**Hackathon:** Panaversity Hackathon I
**Live Site:** https://faizanalifsd.github.io/hackathon_1/
**Live API:** https://physical-ai-book-api.onrender.com
**GitHub Repo:** https://github.com/faizanalifsd/hackathon_1

---

## What This Project Is

An interactive, AI-powered textbook on **Physical AI & Humanoid Robotics** built as a full-stack web application. Students can read 14 structured chapters AND chat with an AI assistant called **Robo** that answers questions directly from the book content — no hallucinations, no outside knowledge.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│              Student's Browser                      │
│                                                     │
│   ┌──────────────────────┐   ┌──────────────────┐  │
│   │  Docusaurus Website  │   │  Robo Chat Widget│  │
│   │  (14 Chapter Docs)   │◄──│  (React, bottom  │  │
│   │  GitHub Pages        │   │   right corner)  │  │
│   └──────────────────────┘   └────────┬─────────┘  │
└────────────────────────────────────────┼────────────┘
                                         │ POST /chat
                                         ▼
                          ┌──────────────────────────┐
                          │  FastAPI Backend          │
                          │  (Render.com, Python 3.11)│
                          └──────────┬───────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                 ▼
           ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
           │  Jina AI API │  │ Qdrant Cloud │  │  Groq LLM    │
           │  Embeddings  │  │ Vector DB    │  │  (Primary)   │
           │  768-dim     │  │ 79 chunks    │  │              │
           └──────────────┘  └──────────────┘  └──────────────┘
                                                      │ fallback
                                                      ▼
                                               ┌──────────────┐
                                               │ OpenRouter   │
                                               │ DeepSeek LLM │
                                               └──────────────┘
```

---

## Component 1: Docusaurus Website (Frontend)

**Technology:** Docusaurus v3.9.2 (React-based static site generator)
**Hosting:** GitHub Pages (free, auto-deploys via GitHub Actions)
**URL:** https://faizanalifsd.github.io/hackathon_1/

### What It Contains
- **15 Markdown files** in `docusaurus_website/docs/`:
  - `intro.md` — Welcome & overview page
  - `chapter-01-what-is-physical-ai.md` through `chapter-14-capstone-autonomous-humanoid.md`
- Each chapter has:
  - Learning Objectives
  - Introduction
  - Core Concepts (with diagrams/tables)
  - Hands-On Python/ROS 2 Code Examples
  - Common Mistakes section
  - Summary & Review Questions

### Chapter List
| # | Chapter |
|---|---------|
| 1 | What is Physical AI? |
| 2 | Humanoid Robotics Landscape |
| 3 | ROS 2 Architecture |
| 4 | Building ROS 2 Packages |
| 5 | URDF Robot Description |
| 6 | Gazebo Simulation Setup |
| 7 | Unity for Robotics |
| 8 | NVIDIA Isaac Platform |
| 9 | Visual SLAM & Navigation |
| 10 | Sim-to-Real Transfer |
| 11 | Humanoid Kinematics & Dynamics |
| 12 | Manipulation & Grasping |
| 13 | Conversational Robotics & VLA |
| 14 | Capstone: Autonomous Humanoid |

### Auto-Deploy Pipeline
```
git push → GitHub Actions (.github/workflows/deploy.yml)
         → npm run build (Docusaurus builds static HTML)
         → deploys to gh-pages branch
         → GitHub Pages serves the site
```

---

## Component 2: Robo Chat Widget (Frontend AI Interface)

**File:** `docusaurus_website/src/components/ChatWidget.jsx`
**Injected via:** `docusaurus_website/src/theme/Root.js` (appears on every page)

### How It Works
1. Floating **🤖 button** appears in bottom-right corner on every page
2. Click opens a chat panel with **Robo** — the Physical AI Book Assistant
3. Student types a question → sent to FastAPI backend via `POST /chat`
4. Response appears in chat with chapter citation

### Special Feature: Selected Text Context
- Student can **highlight any text** on a book page
- A context banner appears: `📌 Context: "highlighted text..."`
- The highlighted text is sent along with the question
- Robo answers specifically about what the student highlighted

### API Call
```javascript
POST https://physical-ai-book-api.onrender.com/chat
Body: {
  "question": "What is a ROS 2 node?",
  "selected_text": "optional highlighted text from page"
}
Response: {
  "answer": "Based on Chapter 3: ROS 2 Architecture, a ROS 2 node is..."
}
```

---

## Component 3: FastAPI Backend (RAG API)

**Technology:** Python 3.11, FastAPI, Uvicorn
**Hosting:** Render.com (Free tier, Web Service)
**URL:** https://physical-ai-book-api.onrender.com

### Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Main Q&A endpoint |
| GET | `/health` | Health check → `{"status":"ok"}` |
| GET | `/` | API info |
| GET | `/docs` | Auto-generated Swagger UI |

### Files
```
backend/
├── main.py          # FastAPI app, routes, CORS middleware
├── rag.py           # RAG pipeline (embed → search → LLM)
├── embeddings.py    # Jina AI HTTP embedding calls
├── indexer.py       # One-time script: chunk chapters → Qdrant
├── db.py            # Neon Postgres chat history (optional)
├── requirements.txt # Python dependencies
└── runtime.txt      # Forces Python 3.11.9 on Render
```

---

## Component 4: RAG Pipeline (The Brain)

RAG = **Retrieval-Augmented Generation** — the technique that makes Robo answer only from the book.

### Step-by-Step Flow

```
Student Question
      │
      ▼
1. EMBED THE QUESTION
   embeddings.py calls Jina AI API
   "What is a ROS 2 node?" → [0.12, -0.45, 0.88, ...] (768 numbers)
      │
      ▼
2. VECTOR SEARCH
   qdrant_client.query_points() searches Qdrant Cloud
   Finds top 3 most similar book chunks (score > 0.6)
   Returns: Chapter 3 text about ROS 2 nodes
      │
      ▼
3. BUILD CONTEXT
   Combines the 3 retrieved chunks:
   "[Chapter 3: ROS 2 Architecture]\n A ROS 2 node is..."
      │
      ▼
4. LLM ANSWER (Groq Primary)
   Sends: System Prompt + Context + Question to Groq
   Model: llama-3.3-70b-versatile
   Returns: "Based on Chapter 3... Want me to explain [X]?"
      │
      ▼  (if Groq fails)
4b. LLM FALLBACK (OpenRouter)
   Same call to deepseek/deepseek-r1-distill-llama-70b
      │
      ▼
5. RETURN ANSWER
   {"answer": "Based on Chapter 3: ROS 2 Architecture..."}
```

### System Prompt (Robo's Personality)
```
You are Robo, a friendly robotics teaching assistant.
- Answer ONLY based on the provided book context
- Always cite the chapter: "Based on Chapter X..."
- If not found: "I couldn't find that in the book..."
- Keep answers under 300 words
- End every response with: "Want me to explain [related concept]?"
```

---

## Component 5: Knowledge Base (Qdrant Vector Database)

**Service:** Qdrant Cloud (Free tier, EU region)
**Collection:** `physical_ai_book`
**Vectors stored:** 79 chunks from 14 chapters
**Embedding model:** Jina AI `jina-embeddings-v2-base-en` (768 dimensions)

### How Indexing Works (run once via `indexer.py`)
```
14 Chapter Markdown Files
         │
         ▼
Chunking: Split into ~500-word chunks
         │ (79 total chunks across 14 chapters)
         ▼
Jina AI API: Convert each chunk → 768-dim vector
         │ (batches of 20 for efficiency)
         ▼
Qdrant Cloud: Store vector + payload
         │ payload = {text, chapter, source_file}
         ▼
Collection "physical_ai_book" ready for search
```

---

## Component 6: AI Services Used

| Service | Purpose | Model | Cost |
|---------|---------|-------|------|
| Jina AI | Text embeddings | jina-embeddings-v2-base-en | Free tier |
| Groq | Primary LLM | llama-3.3-70b-versatile | Free tier |
| OpenRouter | Fallback LLM | deepseek/deepseek-r1-distill-llama-70b | Pay-per-use |
| Qdrant Cloud | Vector database | — | Free tier |
| Render.com | Backend hosting | — | Free tier |
| GitHub Pages | Frontend hosting | — | Free |

---

## Environment Variables (Backend)

```bash
GROQ_API_KEY=...          # Groq LLM access
OPENROUTER_API_KEY=...    # Fallback LLM access
QDRANT_URL=...            # Qdrant Cloud cluster URL
QDRANT_API_KEY=...        # Qdrant authentication
JINA_API_KEY=...          # Jina AI embeddings
NEON_DATABASE_URL=...     # Neon Postgres (chat history)
PYTHON_VERSION=3.11.9     # Forces Python 3.11 on Render
```

---

## Deployment Architecture

```
Developer Machine (Windows)
        │
        │ git push
        ▼
GitHub Repository (faizanalifsd/hackathon_1)
        │
        ├──► GitHub Actions (deploy.yml)
        │         │ npm run build
        │         ▼
        │    gh-pages branch
        │         │
        │         ▼
        │    GitHub Pages
        │    faizanalifsd.github.io/hackathon_1/
        │
        └──► Render.com (Auto-deploy on push)
                  │ pip install -r requirements.txt
                  │ uvicorn main:app --host 0.0.0.0 --port $PORT
                  ▼
             physical-ai-book-api.onrender.com
```

---

## Key Technical Decisions & Why

| Decision | Reason |
|----------|--------|
| Jina AI instead of OpenAI embeddings | No OpenAI API key; Jina free tier gives 1M tokens/month |
| Groq instead of OpenAI for LLM | Free tier, extremely fast (500 tokens/sec), llama-3.3-70b is powerful |
| OpenRouter as fallback | Reliability — if Groq rate-limits, DeepSeek handles overflow |
| Qdrant Cloud instead of local | Free hosted vector DB, no server management |
| Docusaurus for textbook | Built-in search, versioning, sidebar navigation, React extensibility |
| GitHub Pages for hosting | Free, reliable, auto-deploys via GitHub Actions |
| Render.com for backend | Free Python hosting with auto-deploy from GitHub |
| `httpx==0.27.2` pinned | groq 0.11.0 incompatible with httpx 0.28+ (removed `proxies` param) |
| `qdrant-client==1.11.1` pinned | v1.17+ removed `.search()` method; using `.query_points()` instead |
| Python 3.11.9 via runtime.txt + PYTHON_VERSION | Render defaults to Python 3.14 which can't build pydantic-core wheels |

---

## How to Run Locally

### Backend
```bash
cd backend
pip install -r requirements.txt
# Create .env with all API keys
uvicorn main:app --reload --port 8002
# API available at http://localhost:8002
```

### Frontend
```bash
cd docusaurus_website
npm install
npm start
# Site available at http://localhost:3000/hackathon_1/
```

### Test the Chat
```bash
curl -X POST http://localhost:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Physical AI?", "selected_text": ""}'
```

---

## Project Stats

- **14 chapters** of textbook content
- **79 vector chunks** indexed in Qdrant
- **~500 words** per chunk average
- **768-dimensional** embedding vectors
- **Top 3 chunks** retrieved per query (score threshold: 0.6)
- **300 word** max response length
- **3 files** changed to fix Python/dependency issues on Render

---

*Built for Panaversity Hackathon I — Physical AI & Humanoid Robotics Textbook with RAG-powered AI Assistant*
