"""
parser_llm.py
=============
Shared document-parsing layer used by invoice_parser.py and proof_parser.py.

Both parsers converge on the same shape:
  PDF   -> PyMuPDF text  -> Morpheus (text LLM) -> structured JSON
  Image -> Tesseract OCR -> Morpheus (text LLM) -> structured JSON

Replaces the old Chutes vision dependency (the Chutes account hit $0 balance).
Morpheus has no usable vision model, so images are OCR'd to text locally first.

System deps:
  - Tesseract binary must be installed for the image path. On Windows set
    TESSERACT_CMD in .env to the tesseract.exe path if it's not on PATH.
    PDFs do NOT need Tesseract.
"""
import io
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MORPHEUS_URL = os.getenv("MORPHEUS_URL")
MORPHEUS_API_KEY = os.getenv("MORPHEUS_API_KEY")
# A confirmed-working Morpheus text model (premium multimodal models 500 on this
# account). Override via env if needed.
MORPHEUS_PARSE_MODEL = os.getenv("MORPHEUS_PARSE_MODEL", "llama-3.3-70b")
TESSERACT_CMD = os.getenv("TESSERACT_CMD")  # optional explicit path on Windows

_client = OpenAI(base_url=MORPHEUS_URL, api_key=MORPHEUS_API_KEY)


def ocr_image(file_bytes: bytes) -> str:
    """Extract text from an image via Tesseract. Raises if the binary is missing."""
    import pytesseract
    from PIL import Image

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    image = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(image)
    if not text.strip():
        raise ValueError("Tesseract found no readable text in the image.")
    return text


def _strip_fences(raw: str) -> str:
    """Remove ```json ... ``` fences a model may wrap around its output."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    return raw


def structure(document_text: str, instruction: str) -> dict:
    """Send extracted text to Morpheus and return the parsed JSON object."""
    response = _client.chat.completions.create(
        model=MORPHEUS_PARSE_MODEL,
        temperature=0.0,
        messages=[
            {
                "role": "system",
                "content": "You are a precise financial parsing API. Return ONLY valid JSON.",
            },
            {
                "role": "user",
                "content": f"{instruction}\n\n### RAW DOCUMENT TEXT:\n{document_text}",
            },
        ],
    )
    raw = _strip_fences(response.choices[0].message.content)
    return json.loads(raw)
