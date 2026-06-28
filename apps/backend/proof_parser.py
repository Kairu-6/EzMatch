import os
import fitz  # PyMuPDF
from supabase import create_client, Client
from dotenv import load_dotenv

from data_contracts import (
    ParseStatus,
    ChutesParserInput,
    ChutesParserOutput,
    ParsedProofData,
)
from parser_llm import ocr_image, structure

load_dotenv()

# ══════════════════════════════════════════════════════════════════
# SUPABASE
# ══════════════════════════════════════════════════════════════════
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

PROOF_INSTRUCTION = """Extract these fields from the payment receipt text below and return ONLY a valid JSON object (no markdown, no commentary):
1. parsed_amount: the total amount paid as a pure float (strip commas and currency symbols).
2. parsed_currency: 3-letter ISO currency code (e.g. MYR, USD, EUR).
3. parsed_date: the payment date in ISO-8601 (YYYY-MM-DD).
4. parsed_reference: the transaction ID, reference, or receipt number.
5. sender_name: who sent the payment, or null.
6. bank_name: the issuing bank, or null.
If a field is absent, return null.

Example: {"parsed_amount":1250.0,"parsed_currency":"MYR","parsed_date":"2026-10-25","parsed_reference":"TRX-998877","sender_name":"John Doe","bank_name":"Maybank"}"""


# ══════════════════════════════════════════════════════════════════
# IMAGE PARSER (Tesseract OCR -> Morpheus)
# ══════════════════════════════════════════════════════════════════
def extract_proof_image(input_data: ChutesParserInput) -> ChutesParserOutput:
    print(f"--> [OCR] Reading proof image: {input_data.file_path}")
    try:
        file_bytes = supabase.storage.from_("proofs").download(input_data.file_path)
        text = ocr_image(file_bytes)
        parsed_dict = structure(text, PROOF_INSTRUCTION)
        validated_data = ParsedProofData(**parsed_dict)
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.COMPLETED,
            parsed_amount=parsed_dict.get("parsed_amount"),
            parsed_currency=parsed_dict.get("parsed_currency"),
            parsed_date=parsed_dict.get("parsed_date"),
            parsed_reference=parsed_dict.get("parsed_reference"),
            parsed_data=validated_data,
            message=None,
        )
    except Exception as e:
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.FAILED,
            message=f"Image OCR/parse error: {str(e)}",
        )


# ══════════════════════════════════════════════════════════════════
# PDF PARSER (PyMuPDF text -> Morpheus)
# ══════════════════════════════════════════════════════════════════
def extract_proof_pdf(input_data: ChutesParserInput) -> ChutesParserOutput:
    print(f"--> [PDF] Extracting proof text: {input_data.file_path}")
    try:
        file_bytes = supabase.storage.from_("proofs").download(input_data.file_path)
        if not file_bytes:
            raise ValueError("Downloaded PDF file is empty.")

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        extracted_text = "".join(page.get_text() for page in doc)
        if not extracted_text.strip():
            raise ValueError("No readable text found in PDF (it may be a scanned image).")

        parsed_dict = structure(extracted_text, PROOF_INSTRUCTION)
        validated_data = ParsedProofData(**parsed_dict)
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.COMPLETED,
            parsed_amount=parsed_dict.get("parsed_amount"),
            parsed_currency=parsed_dict.get("parsed_currency"),
            parsed_date=parsed_dict.get("parsed_date"),
            parsed_reference=parsed_dict.get("parsed_reference"),
            parsed_data=validated_data,
            message=None,
        )
    except Exception as e:
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.FAILED,
            message=f"PDF parse error: {str(e)}",
        )


# ══════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════
def process_payment_proof(proof_id: str, file_path: str, file_type: str):
    """Handle the lifecycle of an uploaded payment proof."""
    print(f"\n--- PROOF ORCHESTRATOR START (id={proof_id}) ---")

    parser_input = ChutesParserInput(
        proof_id=proof_id, file_path=file_path, file_type=file_type
    )

    try:
        if parser_input.file_type == "pdf":
            output = extract_proof_pdf(parser_input)
        elif parser_input.file_type in ["jpg", "jpeg", "png"]:
            output = extract_proof_image(parser_input)
        else:
            raise ValueError(f"Unsupported file type: {parser_input.file_type}")
    except Exception as e:
        output = ChutesParserOutput(
            proof_id=proof_id,
            status=ParseStatus.FAILED,
            message=f"Parser exception: {str(e)}",
        )

    if output.status == ParseStatus.FAILED:
        print(f"[PARSE ERROR]: {output.message}")
    else:
        print(f"[AI Extraction Status]: {output.status.upper()}")

    update_payload = {
        "parse_status": output.status.value,
        "parsed_amount": output.parsed_amount,
        "parsed_currency": output.parsed_currency,
        "parsed_date": output.parsed_date,
        "parsed_reference": output.parsed_reference,
        "error_message": output.message,
        "parsed_data": output.parsed_data.model_dump(exclude_none=True) if output.parsed_data else None,
    }
    update_payload = {k: v for k, v in update_payload.items() if v is not None}

    try:
        response = (
            supabase.table("payment_proof")
            .update(update_payload)
            .eq("proof_id", output.proof_id)
            .execute()
        )
        print(f"Supabase update OK for proof_id: {proof_id}")
        print("--- PROOF ORCHESTRATOR END ---\n")
        return response.data
    except Exception as db_error:
        print(f"[DB ERROR] Failed to update proof {proof_id}: {db_error}")
        print("--- PROOF ORCHESTRATOR END ---\n")
        return None


if __name__ == "__main__":
    import uuid
    test_proof_id = str(uuid.uuid4())
    print(f"[SETUP] Inserting dummy row for proof_id: {test_proof_id}")
    supabase.table("payment_proof").insert(
        {"proof_id": test_proof_id, "parse_status": "pending", "file_type": "pdf", "file_path": "test_proof.pdf"}
    ).execute()
    result = process_payment_proof(proof_id=test_proof_id, file_path="test_proof.pdf", file_type="pdf")
    print("[DB Result]:", result)
