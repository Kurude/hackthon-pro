"""
AI Business & Meeting Copilot - FastAPI Backend
=================================================
Mandatory features implemented:
  - LLM Integration (Groq / llama-3.3-70b)
  - RAG over uploaded PDFs / meeting notes (ChromaDB + Sentence-Transformers)
  - AI Chatbot (RAG-grounded)
  - Voice Assistant (STT via Groq Whisper, TTS via gTTS)
  - Image/File Upload Support (PDF, DOCX, TXT, Audio)
  - Conversation History (persisted in SQLite)
  - Auth (JWT login/register)
  - Meeting Summary, Email Generator, Task Extraction
  - OpenAPI / Swagger docs (auto-generated at /docs)
"""
import os
import shutil
import uuid
import json

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

import models
import schemas
import rag
import llm_service
import voice_service
from database import engine, get_db
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from file_utils import extract_text

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Business & Meeting Copilot",
    description="Multimodal AI assistant that stores company documents and meeting notes, "
                "answers employee questions, summarizes meetings, and generates action items.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ============================================================
# AUTH
# ============================================================
@app.post("/auth/register", response_model=schemas.Token, tags=["Auth"])
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        name=user_in.name,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        {"sub": str(user.id)}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": token, "user": user}


@app.post("/auth/login", response_model=schemas.Token, tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # form_data.username is used as the email field (OAuth2 spec requires 'username')
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token(
        {"sub": str(user.id)}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": token, "user": user}


@app.get("/auth/me", response_model=schemas.UserOut, tags=["Auth"])
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ============================================================
# DOCUMENT UPLOAD (PDF / DOCX / TXT) -> ingested into RAG store
# ============================================================
@app.post("/documents/upload", response_model=schemas.DocumentOut, tags=["Documents"])
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".txt"]:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files are supported")

    save_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{ext}")
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    text = extract_text(save_path)
    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract any text from this file")

    rag.ingest_text(text, current_user.id, source_name=file.filename, doc_type="document")

    doc = models.Document(
        user_id=current_user.id,
        filename=file.filename,
        doc_type="document",
        char_count=len(text),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@app.get("/documents", response_model=list[schemas.DocumentOut], tags=["Documents"])
def list_documents(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.Document)
        .filter(models.Document.user_id == current_user.id)
        .order_by(models.Document.uploaded_at.desc())
        .all()
    )


# ============================================================
# AI CHATBOT (RAG-grounded)
# ============================================================
@app.post("/chat", response_model=schemas.ChatResponse, tags=["Chatbot"])
def chat(
    req: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    context_chunks = rag.retrieve(req.message, current_user.id, top_k=4)

    history_rows = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == current_user.id)
        .order_by(models.ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]

    reply = llm_service.rag_chat_reply(req.message, context_chunks, history)

    db.add(models.ChatMessage(user_id=current_user.id, role="user", content=req.message))
    db.add(models.ChatMessage(user_id=current_user.id, role="assistant", content=reply))
    db.commit()

    sources = list({c["source"] for c in context_chunks})
    return {"reply": reply, "sources": sources}


@app.get("/chat/history", response_model=list[schemas.ChatHistoryItem], tags=["Chatbot"])
def chat_history(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == current_user.id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )


# ============================================================
# VOICE ASSISTANT (Audio in -> transcript -> RAG chat -> Audio out)
# ============================================================
@app.post("/voice/transcribe", tags=["Voice"])
def voice_transcribe(
    file: UploadFile = File(...), current_user: models.User = Depends(get_current_user)
):
    ext = os.path.splitext(file.filename)[1].lower() or ".wav"
    save_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{ext}")
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    text = voice_service.transcribe_audio(save_path)
    return {"transcript": text}


@app.post("/voice/chat", tags=["Voice"])
def voice_chat(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Full voice pipeline: audio question in -> transcript -> RAG-grounded LLM reply -> spoken mp3 out."""
    ext = os.path.splitext(file.filename)[1].lower() or ".wav"
    save_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{ext}")
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    transcript = voice_service.transcribe_audio(save_path)

    context_chunks = rag.retrieve(transcript, current_user.id, top_k=4)
    history_rows = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.user_id == current_user.id)
        .order_by(models.ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]
    reply = llm_service.rag_chat_reply(transcript, context_chunks, history)

    db.add(models.ChatMessage(user_id=current_user.id, role="user", content=transcript))
    db.add(models.ChatMessage(user_id=current_user.id, role="assistant", content=reply))
    db.commit()

    audio_path = voice_service.text_to_speech(reply)
    audio_filename = os.path.basename(audio_path)

    return {
        "transcript": transcript,
        "reply": reply,
        "audio_url": f"/voice/audio/{audio_filename}",
    }


@app.get("/voice/audio/{filename}", tags=["Voice"])
def get_audio(filename: str):
    path = os.path.join(voice_service.AUDIO_OUT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, media_type="audio/mpeg")


# ============================================================
# MEETINGS: upload notes/audio -> transcript -> summary + action items
# ============================================================
@app.post("/meetings/upload-notes", response_model=schemas.MeetingOut, tags=["Meetings"])
def upload_meeting_notes(
    title: str = "Untitled Meeting",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Accepts meeting notes as PDF/DOCX/TXT, or a meeting audio recording."""
    ext = os.path.splitext(file.filename)[1].lower()
    save_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{ext}")
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    if ext in [".pdf", ".docx", ".txt"]:
        transcript = extract_text(save_path)
    elif ext in [".mp3", ".wav", ".m4a", ".webm", ".ogg"]:
        transcript = voice_service.transcribe_audio(save_path)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type for meeting upload")

    if not transcript.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from this file")

    rag.ingest_text(transcript, current_user.id, source_name=file.filename, doc_type="meeting_notes")

    summary = llm_service.summarize_meeting(transcript)
    action_items = llm_service.extract_action_items(transcript)

    meeting = models.Meeting(
        user_id=current_user.id,
        title=title,
        transcript=transcript,
        summary=summary,
        action_items=json.dumps(action_items),
        status="completed",
        source="upload",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    for item in action_items:
        db.add(
            models.Task(
                user_id=current_user.id,
                meeting_id=meeting.id,
                description=item.get("description", "Untitled task"),
                assignee=item.get("assignee", "Unassigned"),
            )
        )
    db.commit()

    doc = models.Document(
        user_id=current_user.id,
        filename=file.filename,
        doc_type="meeting_notes",
        char_count=len(transcript),
    )
    db.add(doc)
    db.commit()

    return meeting


@app.get("/meetings", response_model=list[schemas.MeetingOut], tags=["Meetings"])
def list_meetings(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.Meeting)
        .filter(models.Meeting.user_id == current_user.id)
        .order_by(models.Meeting.created_at.desc())
        .all()
    )


@app.get("/meetings/{meeting_id}", response_model=schemas.MeetingOut, tags=["Meetings"])
def get_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    meeting = (
        db.query(models.Meeting)
        .filter(models.Meeting.id == meeting_id, models.Meeting.user_id == current_user.id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


# ============================================================
# LIVE BUSINESS MEETING
# ============================================================
# Real-time meeting capture: the browser records short audio segments while
# the meeting is happening. Each segment is transcribed immediately and
# appended to the meeting's running transcript, so the transcript grows live
# on screen. When the organiser ends the meeting, the full transcript is
# summarised and action items are extracted automatically - exactly like the
# upload flow, just built up incrementally instead of all at once.

@app.post("/meetings/live/start", response_model=schemas.MeetingOut, tags=["Live Meeting"])
def start_live_meeting(
    req: schemas.LiveMeetingStartRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    meeting = models.Meeting(
        user_id=current_user.id,
        title=req.title or "Untitled Meeting",
        transcript="",
        summary="",
        action_items="[]",
        status="live",
        source="live",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


@app.post(
    "/meetings/live/{meeting_id}/chunk",
    response_model=schemas.LiveMeetingChunkResponse,
    tags=["Live Meeting"],
)
def push_live_meeting_chunk(
    meeting_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Accepts one short audio segment (~8-15s), transcribes it, and appends
    the text to the meeting's running transcript."""
    meeting = (
        db.query(models.Meeting)
        .filter(models.Meeting.id == meeting_id, models.Meeting.user_id == current_user.id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.status != "live":
        raise HTTPException(status_code=400, detail="This meeting has already ended")

    ext = os.path.splitext(file.filename)[1].lower() or ".webm"
    save_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{ext}")
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        chunk_text = voice_service.transcribe_audio(save_path).strip()
    finally:
        # segment files are short-lived; clean up once transcribed
        if os.path.exists(save_path):
            os.remove(save_path)

    if chunk_text:
        meeting.transcript = (meeting.transcript + " " + chunk_text).strip()
        db.commit()
        db.refresh(meeting)

    return {"chunk_transcript": chunk_text, "full_transcript": meeting.transcript}


@app.post("/meetings/live/{meeting_id}/end", response_model=schemas.MeetingOut, tags=["Live Meeting"])
def end_live_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Finalizes a live meeting: generates the summary, extracts action items,
    ingests the transcript into the RAG knowledge base, and creates Task rows -
    the same treatment an uploaded meeting recording gets."""
    meeting = (
        db.query(models.Meeting)
        .filter(models.Meeting.id == meeting_id, models.Meeting.user_id == current_user.id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.status != "live":
        raise HTTPException(status_code=400, detail="This meeting has already ended")

    if not meeting.transcript.strip():
        meeting.status = "completed"
        meeting.summary = "No speech was captured during this meeting."
        db.commit()
        db.refresh(meeting)
        return meeting

    summary = llm_service.summarize_meeting(meeting.transcript)
    action_items = llm_service.extract_action_items(meeting.transcript)

    rag.ingest_text(
        meeting.transcript, current_user.id, source_name=f"{meeting.title} (live)", doc_type="meeting_notes"
    )

    meeting.summary = summary
    meeting.action_items = json.dumps(action_items)
    meeting.status = "completed"
    db.commit()

    for item in action_items:
        db.add(
            models.Task(
                user_id=current_user.id,
                meeting_id=meeting.id,
                description=item.get("description", "Untitled task"),
                assignee=item.get("assignee", "Unassigned"),
            )
        )

    db.add(
        models.Document(
            user_id=current_user.id,
            filename=f"{meeting.title} (live meeting)",
            doc_type="meeting_notes",
            char_count=len(meeting.transcript),
        )
    )
    db.commit()
    db.refresh(meeting)
    return meeting


@app.get("/meetings/live/{meeting_id}", response_model=schemas.MeetingOut, tags=["Live Meeting"])
def get_live_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lets the frontend poll the running transcript if it needs to resync."""
    meeting = (
        db.query(models.Meeting)
        .filter(models.Meeting.id == meeting_id, models.Meeting.user_id == current_user.id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


# ============================================================
# EMAIL GENERATOR
# ============================================================
@app.post("/meetings/generate-email", response_model=schemas.EmailGenerateResponse, tags=["Meetings"])
def generate_email(
    req: schemas.EmailGenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    meeting = (
        db.query(models.Meeting)
        .filter(models.Meeting.id == req.meeting_id, models.Meeting.user_id == current_user.id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    result = llm_service.generate_followup_email(
        meeting.summary, meeting.action_items, req.tone, req.recipient_context
    )
    return result


# ============================================================
# TASKS (action items extracted from meetings)
# ============================================================
@app.get("/tasks", response_model=list[schemas.TaskOut], tags=["Tasks"])
def list_tasks(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.Task)
        .filter(models.Task.user_id == current_user.id)
        .order_by(models.Task.created_at.desc())
        .all()
    )


@app.patch("/tasks/{task_id}", response_model=schemas.TaskOut, tags=["Tasks"])
def update_task(
    task_id: int,
    update: schemas.TaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    task = (
        db.query(models.Task)
        .filter(models.Task.id == task_id, models.Task.user_id == current_user.id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = update.status
    db.commit()
    db.refresh(task)
    return task


# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok", "message": "AI Business & Meeting Copilot backend is running"}


# ============================================================
# SERVE FRONTEND (static files)
# ============================================================
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
