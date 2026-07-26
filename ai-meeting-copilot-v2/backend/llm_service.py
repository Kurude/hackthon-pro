"""
LLM service powered by Groq (free, extremely fast inference).
Get a free API key at https://console.groq.com/keys

Handles:
- RAG-grounded chatbot replies
- Meeting summarization
- Action item / task extraction (structured JSON)
- Follow-up email generation
"""
import os
import json
from typing import List, Dict

from groq import Groq

_client = None
CHAT_MODEL = "llama-3.3-70b-versatile"


def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file. "
                "Get a free key at https://console.groq.com/keys"
            )
        _client = Groq(api_key=api_key)
    return _client


def _chat(messages: List[Dict], temperature: float = 0.4) -> str:
    client = get_client()
    completion = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return completion.choices[0].message.content.strip()


def rag_chat_reply(user_message: str, context_chunks: List[Dict], history: List[Dict]) -> str:
    """Generate a chatbot reply grounded in retrieved document/meeting context."""
    context_text = "\n\n".join(
        f"[Source: {c['source']}]\n{c['text']}" for c in context_chunks
    ) or "No relevant context found in the knowledge base."

    system_prompt = (
        "You are an AI Business & Meeting Copilot. You help employees quickly find answers "
        "from company documents, meeting notes and reports. Answer ONLY using the provided "
        "context when it is relevant. If the context doesn't contain the answer, say so clearly "
        "and answer from general knowledge, noting that it isn't from the company's documents. "
        "Be concise, professional, and structure longer answers with bullet points.\n\n"
        f"CONTEXT:\n{context_text}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    return _chat(messages)


def summarize_meeting(transcript: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert meeting summarizer. Summarize the meeting transcript into "
                "clear sections: Key Discussion Points, Decisions Made, and Open Questions. "
                "Use concise bullet points. Do not invent information not present in the transcript."
            ),
        },
        {"role": "user", "content": transcript},
    ]
    return _chat(messages, temperature=0.2)


def extract_action_items(transcript: str) -> List[Dict]:
    """Extract structured action items as a JSON list of {description, assignee}."""
    messages = [
        {
            "role": "system",
            "content": (
                "Extract all action items / tasks from this meeting transcript. "
                "Respond ONLY with a valid JSON array, no markdown, no commentary, in this exact format: "
                '[{"description": "task description", "assignee": "person name or Unassigned"}]. '
                "If there are no clear action items, return an empty array []."
            ),
        },
        {"role": "user", "content": transcript},
    ]
    raw = _chat(messages, temperature=0.1)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return []


def generate_followup_email(summary: str, action_items: str, tone: str, recipient_context: str) -> Dict:
    messages = [
        {
            "role": "system",
            "content": (
                f"You write clear, {tone} follow-up emails after business meetings. "
                "Respond ONLY with valid JSON in the format: "
                '{"subject": "...", "body": "..."}. '
                "The body should reference the summary and list action items with assignees."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Meeting Summary:\n{summary}\n\nAction Items:\n{action_items}\n\n"
                f"Additional context about recipients: {recipient_context or 'general team'}"
            ),
        },
    ]
    raw = _chat(messages, temperature=0.5)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(raw)
        return {"subject": parsed.get("subject", "Meeting Follow-up"), "body": parsed.get("body", raw)}
    except json.JSONDecodeError:
        return {"subject": "Meeting Follow-up", "body": raw}
