"""
Voice service:
- Speech-to-Text via Groq's hosted Whisper (whisper-large-v3) - fast + free tier, no local model needed
- Text-to-Speech via gTTS (Google Text-to-Speech) - no API key required
"""
import os
import uuid

from gtts import gTTS

from llm_service import get_client

AUDIO_OUT_DIR = os.path.join(os.path.dirname(__file__), "uploads", "tts")
os.makedirs(AUDIO_OUT_DIR, exist_ok=True)


def transcribe_audio(file_path: str) -> str:
    """Send an audio file to Groq's Whisper endpoint and return the transcript text."""
    client = get_client()
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(file_path), f.read()),
            model="whisper-large-v3",
            response_format="text",
        )
    # Groq SDK returns either a string or an object depending on response_format
    return transcription if isinstance(transcription, str) else str(transcription)


def text_to_speech(text: str) -> str:
    """Convert text to an mp3 file and return its path."""
    filename = f"{uuid.uuid4()}.mp3"
    output_path = os.path.join(AUDIO_OUT_DIR, filename)
    tts = gTTS(text=text, lang="en")
    tts.save(output_path)
    return output_path
