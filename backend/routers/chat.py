import os
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from emergentintegrations.llm.chat import LlmChat, UserMessage

from core.db import logger

router = APIRouter()

CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_SYSTEM = (
    "You are the Veterans of Puerto Plata clinic assistant. Reply in the same language "
    "the user writes in (English or Spanish). Be concise, professional and accurate."
)


def _flatten(content) -> str:
    """Content may be a plain string or a list of blocks like [{'type':'text','text':...}]."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    return str(content)


def _extract(body: dict):
    """Return (system_message, history_lines, last_user_text) from a flexible request body."""
    # 1) explicit chat-style messages (OpenAI / Anthropic)
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        system_parts, turns = [], []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = (m.get("role") or "user").lower()
            text = _flatten(m.get("content"))
            if role == "system":
                system_parts.append(text)
            else:
                turns.append((role, text))
        # a top-level "system" field (Anthropic) too
        if isinstance(body.get("system"), (str, list)):
            system_parts.insert(0, _flatten(body.get("system")))
        system = "\n".join(p for p in system_parts if p) or DEFAULT_SYSTEM
        if not turns:
            raise HTTPException(status_code=400, detail="No user message provided")
        last_text = turns[-1][1]
        history = [f"{'User' if r == 'user' else 'Assistant'}: {t}" for r, t in turns[:-1]]
        return system, history, last_text
    # 2) simple single-field shapes
    for key in ("message", "prompt", "input", "text", "query", "q"):
        if body.get(key):
            return DEFAULT_SYSTEM, [], _flatten(body[key])
    raise HTTPException(status_code=400, detail="Request must include 'messages' or a 'message'/'prompt' field")


def _check_key(request: Request):
    expected = os.environ.get("CHAT_API_KEY")
    if not expected:
        return  # endpoint is open until a key is configured
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    provided = token or request.headers.get("x-api-key", "")
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def _handle(request: Request):
    _check_key(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    system, history, last_text = _extract(body)
    if not (last_text or "").strip():
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(last_text) > 12000:
        raise HTTPException(status_code=400, detail="Message too long")

    system_msg = system
    if history:
        system_msg = system + "\n\nConversation so far:\n" + "\n".join(history)

    try:
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=str(uuid.uuid4()),
                       system_message=system_msg).with_model("anthropic", CLAUDE_MODEL)
        reply = await chat.send_message(UserMessage(text=last_text))
    except Exception:
        logger.exception("/api/chat failed")
        raise HTTPException(status_code=502, detail="The assistant is unavailable right now. Please try again later.")

    reply = reply or ""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": CLAUDE_MODEL,
        "provider": "anthropic",
        "role": "assistant",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": reply}}],
        "content": [{"type": "text", "text": reply}],
        "text": reply,
        "reply": reply,
    }


@router.post("/chat")
async def chat_endpoint(request: Request):
    return await _handle(request)


@router.post("/chat/completions")
async def chat_completions_endpoint(request: Request):
    return await _handle(request)
