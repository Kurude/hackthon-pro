from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ---------- Auth ----------
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Chat ----------
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    sources: List[str] = []


class ChatHistoryItem(BaseModel):
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Documents ----------
class DocumentOut(BaseModel):
    id: int
    filename: str
    doc_type: str
    char_count: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


# ---------- Meetings ----------
class MeetingOut(BaseModel):
    id: int
    title: str
    transcript: str
    summary: str
    action_items: str
    status: str
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class LiveMeetingStartRequest(BaseModel):
    title: str = "Untitled Meeting"


class LiveMeetingChunkResponse(BaseModel):
    chunk_transcript: str
    full_transcript: str


class EmailGenerateRequest(BaseModel):
    meeting_id: int
    tone: Optional[str] = "professional"
    recipient_context: Optional[str] = ""


class EmailGenerateResponse(BaseModel):
    subject: str
    body: str


# ---------- Tasks ----------
class TaskOut(BaseModel):
    id: int
    description: str
    assignee: str
    status: str
    meeting_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    status: str
