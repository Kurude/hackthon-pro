"""
ORM models: User, Document, Meeting, ChatMessage, Task
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="owner", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="owner", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="owner", cascade="all, delete-orphan")


class Document(Base):
    """Any uploaded PDF / DOCX / TXT / meeting-notes file that gets embedded into the RAG store."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String, nullable=False)
    doc_type = Column(String, default="document")  # document | meeting_notes
    char_count = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="documents")


class Meeting(Base):
    """Stores meeting transcripts + generated summary/action items.

    Supports two intake modes:
      - Upload mode: a finished PDF/DOCX/TXT/audio file is processed in one shot.
      - Live mode: the meeting is recorded in the browser in short segments while
        it happens; each segment is transcribed and appended to `transcript` in
        real time, and the summary/action items are generated once the meeting
        is ended (`status` moves from "live" -> "completed").
    """
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, default="Untitled Meeting")
    transcript = Column(Text, default="")
    summary = Column(Text, default="")
    action_items = Column(Text, default="")  # stored as JSON string
    status = Column(String, default="completed")  # "live" | "completed"
    source = Column(String, default="upload")  # "upload" | "live"
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="meetings")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String)  # "user" or "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="messages")


class Task(Base):
    """Extracted action items that can be tracked as tasks."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=True)
    description = Column(Text, nullable=False)
    assignee = Column(String, default="Unassigned")
    status = Column(String, default="pending")  # pending | done
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="tasks")
