import logging
import os
from pydantic import BaseModel, field_validator
from enum import Enum
import fitz  # PyMuPDF
from supabase import create_client, Client
from dotenv import load_dotenv

from parser_llm import ocr_image, structure

load_dotenv()
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# 1. SUPABASE
# ══════════════════════════════════════════════════════════════════
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Field-extraction instruction shared by the PDF and image paths.
INVOICE_INSTRUCTION = """Extract these fields from the invoice text below and return ONLY a valid JSON object (no markdown, no commentary):
1. invoice_number: the invoice number or ID.
2. counterparty_name: the vendor/company that issued the invoice.
3. invoice_amount: the TOTAL amount due as a pure float (strip commas and currency symbols).
4. invoice_currency: 3-letter ISO currency code (e.g. USD, MYR, EUR).
5. invoice_date: the issue date in ISO-8601 (YYYY-MM-DD).
6. due_date: the due date in YYYY-MM-DD, or null if not present.

Example: {"invoice_number":"INV-2026-001","counterparty_name":"Acme Corp","invoice_amount":1500.50,"invoice_currency":"USD","invoice_date":"2026-05-20","due_date":"2026-06-20"}"""


# ══════════════════════════════════════════════════════════════════
# 2. LOCAL PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════
class ParseStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"

class InvoiceParserInput(BaseModel):
    invoice_id: str
    file_path: str
    file_type: str

class ParsedInvoiceData(BaseModel):
    invoice_number: str | None = None
    counterparty_name: str | None = None
    invoice_amount: float | None = None
    invoice_currency: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    error_message: str | None = None

    @field_validator("invoice_currency")
    @classmethod
    def currency_uppercase(cls, v: str | None) -> str | None:
        return v.upper() if v else None

class InvoiceParserOutput(BaseModel):
    invoice_id: str
    status: ParseStatus
    parsed_data: ParsedInvoiceData | None = None
    message: str | None = None


# ══════════════════════════════════════════════════════════════════
# 3A. IMAGE PARSER (Tesseract OCR -> Morpheus)
# ══════════════════════════════════════════════════════════════════
def extract_invoice_image(input_data: InvoiceParserInput) -> InvoiceParserOutput:
    logger.info("OCR invoice image: %s", input_data.file_path)
    try:
        file_bytes = supabase.storage.from_("invoices").download(input_data.file_path)
        text = ocr_image(file_bytes)
        parsed_dict = structure(text, INVOICE_INSTRUCTION)
        validated_data = ParsedInvoiceData(**parsed_dict)
        return InvoiceParserOutput(
            invoice_id=input_data.invoice_id,
            status=ParseStatus.COMPLETED,
            parsed_data=validated_data,
            message=None,
        )
    except Exception as e:
        return InvoiceParserOutput(
            invoice_id=input_data.invoice_id,
            status=ParseStatus.FAILED,
            message=f"Image OCR/parse error: {str(e)}",
        )


# ══════════════════════════════════════════════════════════════════
# 3B. PDF PARSER (PyMuPDF text -> Morpheus)
# ══════════════════════════════════════════════════════════════════
def extract_invoice_pdf(input_data: InvoiceParserInput) -> InvoiceParserOutput:
    logger.info("Extract invoice PDF: %s", input_data.file_path)
    try:
        file_bytes = supabase.storage.from_("invoices").download(input_data.file_path)
        if not file_bytes:
            raise ValueError("Downloaded PDF file is empty.")

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        extracted_text = "".join(page.get_text() for page in doc)
        if not extracted_text.strip():
            raise ValueError("No readable text found in PDF (it may be a scanned image).")

        parsed_dict = structure(extracted_text, INVOICE_INSTRUCTION)
        validated_data = ParsedInvoiceData(**parsed_dict)
        return InvoiceParserOutput(
            invoice_id=input_data.invoice_id,
            status=ParseStatus.COMPLETED,
            parsed_data=validated_data,
            message=None,
        )
    except Exception as e:
        return InvoiceParserOutput(
            invoice_id=input_data.invoice_id,
            status=ParseStatus.FAILED,
            message=f"PDF parse error: {str(e)}",
        )


# ══════════════════════════════════════════════════════════════════
# 4. ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════
def process_invoice(invoice_id: str, file_path: str, file_type: str):
    """Handle the lifecycle of an uploaded invoice."""
    parser_input = InvoiceParserInput(
        invoice_id=invoice_id, file_path=file_path, file_type=file_type
    )

    try:
        if parser_input.file_type == "pdf":
            output = extract_invoice_pdf(parser_input)
        elif parser_input.file_type in ["jpg", "jpeg", "png"]:
            output = extract_invoice_image(parser_input)
        else:
            raise ValueError(f"Unsupported file type: {parser_input.file_type}")
    except Exception as e:
        output = InvoiceParserOutput(
            invoice_id=invoice_id,
            status=ParseStatus.FAILED,
            message=f"Parser exception: {str(e)}",
        )

    if output.status == ParseStatus.FAILED:
        logger.warning("Invoice %s parse failed: %s", invoice_id, output.message)

    # 1. Base payload
    update_payload = {"status": "pending"}

    # 2. Inject parsed fields on success
    if output.status == ParseStatus.COMPLETED and output.parsed_data:
        data = output.parsed_data
        update_payload.update({
            "invoice_number": data.invoice_number,
            "counterparty_name": data.counterparty_name,
            "invoice_amount": data.invoice_amount,
            "invoice_currency": data.invoice_currency,
            "invoice_date": data.invoice_date,
            "due_date": data.due_date,
        })
    else:
        # Parse failed — record why so the row doesn't masquerade as "Processing…".
        update_payload["error_message"] = output.message or "Invoice parsing failed."

    # 3. Drop None values so we don't overwrite DB defaults with nulls
    update_payload = {k: v for k, v in update_payload.items() if v is not None}

    # 4. Push to Supabase 'invoice' (retry without error_message if column absent)
    def _do_update(payload):
        return (
            supabase.table("invoice")
            .update(payload)
            .eq("invoice_id", output.invoice_id)
            .execute()
        )

    try:
        try:
            response = _do_update(update_payload)
        except Exception:
            update_payload.pop("error_message", None)
            response = _do_update(update_payload)
        logger.info("Invoice %s updated.", output.invoice_id)
        return response.data
    except Exception as db_error:
        logger.error("Failed to update invoice %s: %s", output.invoice_id, db_error)
        return None
