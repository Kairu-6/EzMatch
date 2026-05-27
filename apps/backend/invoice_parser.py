import os
import base64
import json
from openai import OpenAI
from pydantic import BaseModel, field_validator, ValidationError
from typing import Optional
from enum import Enum
import fitz  # PyMuPDF
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════
# 1. SETUP CLIENTS
# ══════════════════════════════════════════════════════════════════
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

CHUTES_API_KEY = os.environ.get("CHUTES_API_KEY")
CHUTES_URL = os.environ.get("CHUTES_URL")
chutes_client = OpenAI(
    base_url=CHUTES_URL, 
    api_key=CHUTES_API_KEY
)

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
# 3A. IMAGE PARSER (CHUTES VISION)
# ══════════════════════════════════════════════════════════════════
def extract_invoice_image(input_data: InvoiceParserInput) -> InvoiceParserOutput:
    print(f"--> [Chutes Vision] Analyzing invoice image: {input_data.file_path}")
    
    try:
        file_bytes = supabase.storage.from_("invoices").download(input_data.file_path)
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        mime_type = "image/jpeg" if input_data.file_type in ["jpg", "jpeg"] else f"image/{input_data.file_type}"

        response = chutes_client.chat.completions.create(
            model="Qwen/Qwen3.6-27B-TEE", 
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise financial OCR API. Return ONLY valid JSON." 
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": """
                            Analyze the attached invoice.
                            Your ONLY output must be a valid JSON object matching this schema. Do not use markdown backticks (```json).

                            ### FORMAT INSTRUCTIONS:
                            1. invoice_number: Extract the invoice number or ID.
                            2. counterparty_name: Extract the name of the vendor/company billing the user.
                            3. invoice_amount: Strip commas and currency symbols. Return a pure float of the TOTAL amount due.
                            4. invoice_currency: 3-letter ISO currency code (e.g., USD, MYR).
                            5. invoice_date: Convert the issue date to standard ISO-8601 format: YYYY-MM-DD.
                            6. due_date: Convert the due date to YYYY-MM-DD. Return null if not found.

                            ### FEW-SHOT EXAMPLE:
                            {
                              "invoice_number": "INV-2026-001",
                              "counterparty_name": "Acme Corp",
                              "invoice_amount": 1500.50,
                              "invoice_currency": "USD",
                              "invoice_date": "2026-05-20",
                              "due_date": "2026-06-20"
                            }
                            """
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                        }
                    ]
                }
            ],
            temperature=0.0 
        )
        
        raw_output = response.choices[0].message.content.strip()
        
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:-3].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output[3:-3].strip()
            
        parsed_dict = json.loads(raw_output)
        validated_data = ParsedInvoiceData(**parsed_dict)
        
        return InvoiceParserOutput(
            invoice_id=input_data.invoice_id,
            status=ParseStatus.COMPLETED,
            parsed_data=validated_data,
            message=None
        )

    except Exception as e:
        return InvoiceParserOutput(
            invoice_id=input_data.invoice_id,
            status=ParseStatus.FAILED,
            message=f"Chutes Vision Error: {str(e)}"
        )


# ══════════════════════════════════════════════════════════════════
# 3B. PDF PARSER (TEXT-ONLY)
# ══════════════════════════════════════════════════════════════════
def extract_invoice_pdf(input_data: InvoiceParserInput) -> InvoiceParserOutput:
    print(f"--> [PDF Parser] Extracting text from invoice: {input_data.file_path}")
    
    try:
        file_bytes = supabase.storage.from_("invoices").download(input_data.file_path)
        if not file_bytes:
            raise ValueError("Downloaded PDF file is empty.")

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text()
            
        if not extracted_text.strip():
            raise ValueError("No readable text found in PDF. It may be a scanned image.")

        response = chutes_client.chat.completions.create(
            model="Qwen/Qwen3.6-27B-TEE",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise financial parsing API. Return ONLY valid JSON."
                },
                {
                    "role": "user",
                    "content": f"""
                    Analyze the following raw text extracted from an invoice PDF.
                    Your ONLY output must be a valid JSON object matching the schema below. Do not use markdown backticks (```json).

                    ### FORMAT INSTRUCTIONS:
                    1. invoice_number: Extract the invoice number or ID.
                    2. counterparty_name: Extract the name of the vendor/company billing the user.
                    3. invoice_amount: Strip commas and currency symbols. Return a pure float of the TOTAL amount due.
                    4. invoice_currency: 3-letter ISO currency code.
                    5. invoice_date: Convert to standard ISO-8601 format: YYYY-MM-DD.
                    6. due_date: Convert to YYYY-MM-DD. Return null if not found.

                    ### JSON SCHEMA / FEW-SHOT EXAMPLE:
                    {{
                      "invoice_number": "INV-2026-001",
                      "counterparty_name": "Acme Corp",
                      "invoice_amount": 1500.50,
                      "invoice_currency": "USD",
                      "invoice_date": "2026-05-20",
                      "due_date": "2026-06-20"
                    }}

                    ### RAW PDF TEXT:
                    {extracted_text}
                    """
                }
            ],
            temperature=0.0 
        )
        
        raw_output = response.choices[0].message.content.strip()
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:-3].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output[3:-3].strip()
            
        parsed_dict = json.loads(raw_output)
        validated_data = ParsedInvoiceData(**parsed_dict)
        
        return InvoiceParserOutput(
            invoice_id=input_data.invoice_id,
            status=ParseStatus.COMPLETED,
            parsed_data=validated_data,
            message=None
        )

    except Exception as e:
        return InvoiceParserOutput(
            invoice_id=input_data.invoice_id,
            status=ParseStatus.FAILED,
            message=f"PDF Parsing Error: {str(e)}"
        )


# ══════════════════════════════════════════════════════════════════
# 4. MAIN ORCHESTRATOR FUNCTION
# ══════════════════════════════════════════════════════════════════
def process_invoice(invoice_id: str, file_path: str, file_type: str):
    """
    Handles the lifecycle of an uploaded invoice.
    """
    print(f"\n--- 🔍 INVOICE ORCHESTRATOR START ---")
    print(f"⚙️ Target invoice_id: {invoice_id}")

    parser_input = InvoiceParserInput(
        invoice_id=invoice_id,
        file_path=file_path,
        file_type=file_type
    )

    try:
        if parser_input.file_type == "pdf":
            output: InvoiceParserOutput = extract_invoice_pdf(parser_input)
        elif parser_input.file_type in ["jpg", "jpeg", "png"]:
            output: InvoiceParserOutput = extract_invoice_image(parser_input)
        else:
            raise ValueError(f"Unsupported file type: {parser_input.file_type}")
    except Exception as e:
        output = InvoiceParserOutput(
            invoice_id=invoice_id,
            status=ParseStatus.FAILED,
            message=f"Parser exception: {str(e)}"
        )

    # 🔥 DEBUG CATCH: Reveal the hidden error!
    print(f"\n🧠 [AI Extraction Status]: {output.status.upper()}")
    if output.status == ParseStatus.FAILED:
        print(f"🚨 [CRITICAL AI ERROR]: {output.message}")

    # 1. Base update payload (Top-level table columns)
    update_payload = {
        "status": "pending"  # The only status column that actually exists on this table
    }

    # 2. Inject parsed data directly into the top-level columns if successful
    if output.status == ParseStatus.COMPLETED and output.parsed_data:
        data = output.parsed_data
        update_payload.update({
            "invoice_number": data.invoice_number,
            "counterparty_name": data.counterparty_name,
            "invoice_amount": data.invoice_amount,
            "invoice_currency": data.invoice_currency,
            "invoice_date": data.invoice_date,
            "due_date": data.due_date
        })

    # 3. Clean payload of None values so we don't overwrite DB defaults with nulls
    update_payload = {k: v for k, v in update_payload.items() if v is not None}

    print("\n📦 [DEBUG] Payload heading to Supabase 'invoice' table:")
    print(json.dumps(update_payload, indent=2, default=str))

    # 4. Push updates to Supabase 'invoice' table
    try:
        response = (
            supabase.table("invoice")
            .update(update_payload)
            .eq("invoice_id", output.invoice_id)
            .execute()
        )
        print("✅ Supabase Update Success!")
        print("--- INVOICE ORCHESTRATOR END ---\n")
        return response.data
    
    except Exception as db_error:
        print(f"\n❌ [DB ERROR] Failed to update invoice database. Error: {db_error}")
        print("--- INVOICE ORCHESTRATOR END ---\n")
        return None
    

if __name__ == "__main__":
    import uuid

    # 1. Generate a dummy UUID for the test
    test_invoice_id = str(uuid.uuid4())
    
    # ⚠️ For this test to succeed, we must insert the dummy row FIRST
    # otherwise the .update() function in Supabase will return [] silently.
    print(f"\n🟡 [SETUP] Inserting dummy row into DB for invoice_id: {test_invoice_id}")
    supabase.table("invoice").insert({
        "invoice_id": test_invoice_id,
        "status": "pending"
    }).execute()
    
    # ⚠️ IMPORTANT: For this local test to work, you MUST manually upload 
    # a file named "test_invoice.pdf" into your Supabase 'invoices' bucket first!
    test_file_path = "test_invoice.pdf" 
    test_file_type = "pdf"
    
    print("\n" + "="*50)
    print(f"🧪 INITIATING LOCAL INVOICE TEST")
    print("="*50)

    # 2. Fire the orchestrator
    result = process_invoice(
        invoice_id=test_invoice_id,
        file_path=test_file_path,
        file_type=test_file_type
    )
    print(result)
    
    # 3. Print the final outcome returned from Supabase
    if result:
        print("\n🎉 Test Complete! Check your Supabase database for the updated row.")
    else:
        print("\n❌ Test Failed. Check the logs above for errors.")