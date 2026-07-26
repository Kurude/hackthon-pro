# 🧠 AI Business & Meeting Copilot

**AI Hackathon 2026 — Problem Statement 3**

An AI-powered assistant that stores company documents and meeting notes, answers employee
questions via a RAG-grounded chatbot and voice assistant, summarizes meetings, extracts action
items, and drafts follow-up emails automatically.

---

## ✨ Features

| Feature | Status | Implementation |
|---|---|---|
| LLM Integration | ✅ | Groq (`llama-3.3-70b-versatile`) — free & very fast |
| RAG Integration | ✅ | ChromaDB (vector store) + Sentence-Transformers (local embeddings) |
| AI Chatbot | ✅ | RAG-grounded conversational agent with chat history |
| Voice Assistant | ✅ | Full voice pipeline: record → transcribe → RAG answer → spoken reply |
| Speech-to-Text | ✅ | Groq-hosted Whisper (`whisper-large-v3`) |
| Text-to-Speech | ✅ | gTTS (Google Text-to-Speech) |
| PDF / Meeting Notes Upload | ✅ | PDF, DOCX, TXT parsing → auto-ingested into knowledge base |
| Audio Upload | ✅ | Meeting audio recordings are transcribed automatically |
| **Live Business Meeting** | ✅ | Browser records the meeting in ~10s segments in real time; each segment is transcribed as it happens so the transcript builds live on screen; ending the meeting auto-generates the summary + action items |
| Meeting Summary | ✅ | LLM-generated: key points, decisions, open questions |
| Task Extraction | ✅ | Structured JSON action items with assignees, tracked as tasks |
| Email Generator | ✅ | Auto-drafted follow-up email per meeting |
| Conversation History | ✅ | Persisted in SQLite, viewable in the UI |
| Authentication | ✅ | JWT-based login/register (secure password hashing via bcrypt) |
| Responsive Web UI | ✅ | Custom HTML/CSS/JS dashboard, mobile-friendly |
| API Documentation | ✅ | Auto-generated OpenAPI/Swagger at `/docs` |

---

## 🏗️ Architecture

```
┌────────────────┐        ┌─────────────────────────────┐
│   Frontend      │  HTTP  │        FastAPI Backend       │
│ (HTML/CSS/JS)   │◄──────►│                               │
│  - Auth screens  │       │  ┌─────────┐   ┌───────────┐ │
│  - Chat UI       │       │  │ auth.py │   │ models.py │ │
│  - Voice UI      │       │  └─────────┘   └───────────┘ │
│  - Docs/Meetings │       │  ┌─────────┐   ┌───────────┐ │
│  - Tasks         │       │  │ rag.py  │   │llm_service│ │
└────────────────┘        │  └────┬────┘   └─────┬─────┘ │
                            │       │              │        │
                            │  ┌────▼────┐   ┌─────▼─────┐ │
                            │  │ChromaDB │   │   Groq    │ │
                            │  │ (vectors)│   │  (LLM +   │ │
                            │  └─────────┘   │  Whisper) │ │
                            │                └───────────┘ │
                            │  ┌─────────────────────────┐ │
                            │  │   SQLite (users, chats,  │ │
                            │  │   meetings, tasks, docs) │ │
                            │  └─────────────────────────┘ │
                            └─────────────────────────────┘
```

**Flow for RAG chat:** user message → embed query → retrieve top-k relevant chunks from
ChromaDB (scoped to that user) → inject as context into the LLM prompt → grounded answer
returned with cited source filenames.

**Flow for voice:** browser records mic audio (MediaRecorder API) → sent to backend →
Groq Whisper transcribes → same RAG pipeline generates a reply → gTTS converts reply to
speech → mp3 streamed back and auto-played in browser.

**Flow for meeting upload:** PDF/DOCX/TXT or audio file → text extracted (or transcribed) →
ingested into RAG store + saved as `Meeting.transcript` → LLM generates summary → LLM
extracts structured action items (JSON) → each item becomes a trackable `Task` row.

**Flow for a live business meeting:** clicking "Start Live Meeting" creates a `Meeting` row
with `status="live"`. The browser then records the microphone in independent ~10-second
segments (`POST /meetings/live/{id}/chunk`); each segment is transcribed the moment it
arrives and appended to `Meeting.transcript`, so the on-screen transcript grows in real time
while the meeting is still happening. Clicking "End Meeting" (`POST /meetings/live/{id}/end`)
uploads the final in-progress segment, then runs the exact same summarize + extract-action-items
+ RAG-ingest pipeline used for uploaded recordings, moving `status` to `"completed"`.

---

## 🚀 Setup & Run Locally

### 1. Get a free Groq API key
Sign up at **https://console.groq.com/keys** — it's free and takes 30 seconds.

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# open .env and paste your GROQ_API_KEY

uvicorn main:app --reload --port 8000
```

The first run will download the local embedding model (`all-MiniLM-L6-v2`, ~90MB) —
this needs an internet connection once, after which it's fully cached.

### 3. Open the app
Visit **http://localhost:8000** — the FastAPI backend serves the frontend directly, so
there's no separate frontend server needed.

API docs (Swagger UI): **http://localhost:8000/docs**

---

## 📁 Project Structure

```
ai-meeting-copilot/
├── backend/
│   ├── main.py            # FastAPI app & all API routes
│   ├── database.py        # SQLAlchemy engine/session
│   ├── models.py          # ORM models (User, Document, Meeting, ChatMessage, Task)
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── auth.py             # JWT auth + password hashing
│   ├── rag.py              # Chunking, embedding, ChromaDB retrieval
│   ├── llm_service.py     # Groq LLM calls (chat, summary, tasks, email)
│   ├── voice_service.py   # Whisper STT + gTTS TTS
│   ├── file_utils.py      # PDF/DOCX/TXT text extraction
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── README.md
```

---

## 🛠️ Windows Troubleshooting

**"Program 'pip.exe' failed to run: An Application Control policy has blocked this file"**
This is a Windows security policy blocking `pip.exe` directly, not a bug in this project.
Fix, in order:
1. Use `python -m pip install -r requirements.txt` instead of calling `pip` directly.
2. If that's also blocked, check **Windows Security → App & browser control → Smart App
   Control** and turn it off, then restart your PC.
3. Run your terminal / VS Code **as Administrator**.
4. On a locked-down college or office laptop, this policy is often enforced by IT and can't
   be bypassed — use a personal machine, or a cloud dev environment (GitHub Codespaces,
   Google Colab, Replit) instead.

**Package install is slow, fails, or tries to build from source (`pydantic-core`, etc.)**
This almost always means your Python version is too new for some packages to have
pre-built wheels yet. Check your version:
```powershell
python --version
```
This project is tested against **Python 3.11 or 3.12**. If you're on Python 3.13+ (including
3.14), install 3.11/3.12 from https://www.python.org/downloads/ alongside your existing
version, then create the virtual environment with it explicitly:
```powershell
py -3.11 -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
```

**Microphone doesn't work for Voice Assistant / Live Meeting**
Browsers only allow microphone access on `https://` or `http://localhost` — this is why the
app should be opened as `http://localhost:8000`, not via a raw file path or a plain IP address.

---

## ☁️ Deployment

Any of these work well for this stack (single FastAPI process serving both API + static frontend):

- **Render** — connect the GitHub repo, set build command `pip install -r backend/requirements.txt`,
  start command `uvicorn main:app --host 0.0.0.0 --port $PORT` (run from `backend/` dir), add
  `GROQ_API_KEY` and `SECRET_KEY` as environment variables.
- **Railway** — similar setup, auto-detects Python; add the same env vars.
- **Hugging Face Spaces** — use the Docker SDK with a simple Dockerfile wrapping the uvicorn command.

---

## 🎯 Hackathon Evaluation Mapping

| Criteria (50 marks) | How this project addresses it |
|---|---|
| Problem Understanding & Innovation (10) | Solves real org pain: scattered meeting knowledge, forgotten action items, manual follow-up emails |
| Solution Design (10) | Clean modular backend, proper error handling on uploads/transcription, per-user data isolation in RAG store |
| Technical Stack & AI Implementation (10) | FastAPI + real RAG (ChromaDB + embeddings) + Groq LLM + Whisper STT + gTTS TTS, all wired end-to-end |
| UI/UX (10) | Custom-designed responsive dashboard, no default Bootstrap look, clear navigation |
| Demo/Deploy/GitHub/Docs (10) | Auto Swagger docs, full README, ready to deploy to Render/Railway/HF Spaces |

**Bonus features included:** Feedback-ready task status tracking, citation-aware chat
(source filenames returned with every RAG answer), persistent chat history.

**Possible extensions for extra bonus marks:** streaming responses (SSE), RBAC (admin vs
employee roles), analytics dashboard for query volume, OCR for scanned PDFs.

---

## ⚠️ Notes

- This project uses **Groq** for both the LLM and Whisper STT because it's free, extremely
  fast, and needs only one API key — ideal for a hackathon demo. Swap `llm_service.py` /
  `voice_service.py` to OpenAI/Gemini/HuggingFace if your team prefers a different provider.
- Database is SQLite by default for zero-config setup. Point `SQLALCHEMY_DATABASE_URL` in
  `database.py` to a Postgres/MongoDB connection string for production use.
- Uploaded files and generated audio are stored under `backend/uploads/` (gitignored).
