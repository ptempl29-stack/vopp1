import io
import os
import re
import json
import uuid

from core.db import logger

MODEL = ("anthropic", "claude-sonnet-5-5")
PROMPT = (
    "This is a scan of VA Form 10-7959f-2 (Foreign Medical Program Claim Cover Sheet). "
    "Find the checkbox that says who should receive payment: 'Provider' or 'Veteran'. "
    "Reply with ONLY this JSON: {\"selection\": \"provider\" | \"veteran\" | \"unclear\", \"evidence\": \"<short reason>\"}. "
    "Answer 'unclear' if no box is marked, both are marked, the mark is ambiguous or illegible, "
    "or this is not that form. Never guess.")


def _page_images(data: bytes, is_pdf: bool) -> list:
    import base64
    if is_pdf:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        try:
            return [base64.b64encode(doc[i].get_pixmap(dpi=130).tobytes("png")).decode() for i in range(min(2, len(doc)))]
        finally:
            doc.close()
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img.seek(0)
    img = img.convert("RGB")
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return [base64.b64encode(buf.getvalue()).decode()]


async def _ask_vision(images: list) -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone
    chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"paybox-{uuid.uuid4()}",
                   system_message="You read scanned medical claim forms precisely and never guess.").with_model(*MODEL)
    text = ""
    async for ev in chat.stream_message(UserMessage(text=PROMPT, file_contents=[ImageContent(image_base64=b) for b in images])):
        if isinstance(ev, TextDelta):
            text += ev.content
        elif isinstance(ev, StreamDone):
            break
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


async def detect_payment_box(data: bytes, content_type: str, filename: str) -> dict:
    """Read which payment box is checked on an uploaded cover sheet. Read-only on the scan.
    Returns payment_to = 'provider' | 'veteran' | None (None => staff review)."""
    is_pdf = (content_type or "").endswith("pdf") or (filename or "").lower().endswith(".pdf")
    if is_pdf:
        from routers.fmp import _read_payment_recipient
        try:
            found = _read_payment_recipient(data)
        except Exception as e:
            logger.warning(f"payment box text read failed: {e}")
            found = None
        if found:
            return {"payment_to": found, "source": "cover_sheet_text", "reason": "Read from the PDF's form field / printed mark"}
    try:
        res = await _ask_vision(_page_images(data, is_pdf))
    except Exception as e:
        logger.error(f"payment box vision read failed: {e}")
        return {"payment_to": None, "source": None, "reason": "The scan could not be read automatically"}
    sel = str(res.get("selection") or "").lower()
    if sel in ("provider", "veteran"):
        return {"payment_to": sel, "source": "cover_sheet_ai", "reason": str(res.get("evidence") or "")[:200]}
    return {"payment_to": None, "source": None,
            "reason": str(res.get("evidence") or "No clear payment box mark was found")[:200]}
