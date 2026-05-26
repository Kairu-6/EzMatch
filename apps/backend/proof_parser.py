import os
from supabase import create_client, Client
from dotenv import load_dotenv
import base64
import json
from openai import OpenAI
from pydantic import ValidationError
import fitz

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_API_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

MORPHEUS_API_KEY = os.environ["MORPHEUS_API_KEY"]
MORPHEUS_URL = os.environ["MORPHEUS_URL"]
morpheus_client = OpenAI(
    base_url=MORPHEUS_URL, 
    api_key=MORPHEUS_API_KEY
)

# 1. Import strictly from your existing data_contracts.py
from data_contracts import (
    ParseStatus,
    ChutesParserInput,
    ChutesParserOutput,
    ParsedProofData
)

# ══════════════════════════════════════════════════════════════════
# 2. SUPABASE SETUP
# ══════════════════════════════════════════════════════════════════
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ══════════════════════════════════════════════════════════════════
# 3. CHUTES AI LOGIC (PLACEHOLDER - FAILING SCENARIO)
# ══════════════════════════════════════════════════════════════════
def extract_data_with_chutes(input_data: ChutesParserInput) -> ChutesParserOutput:
    print(f"--> [Morpheus AI] Analyzing file: {input_data.file_path}")
    
    try:
        # 1. Download file from Supabase
        file_bytes = supabase.storage.from_("proofs").download(input_data.file_path)
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        mime_type = "image/jpeg" if input_data.file_type in ["jpg", "jpeg"] else f"image/{input_data.file_type}"

        # 2. Strict JSON Schema Prompt
        image_instruction = """
        You are a highly precise financial OCR API. Your primary function is to extract data from payment proofs and receipts.
        Your ONLY output must be a valid JSON object. Do not wrap the output in markdown backticks (e.g., ```json) and do not include any conversational text.

        ### FORMAT INSTRUCTIONS & RULES:
        1. parsed_amount: Strip all commas, currency symbols (RM, $, etc.), and text. Return a pure float (e.g., 1500.50).
        2. parsed_currency: Extract or infer the 3-letter ISO currency code (e.g., MYR, USD, SGD). 
        3. parsed_date: Convert ANY date format found on the receipt (e.g., '26 May 2026', '05/26/26') strictly to standard ISO-8601 format: YYYY-MM-DD.
        4. parsed_reference: Extract the primary transaction ID, reference number, or receipt number.
        5. Missing Data: If a specific field is not present on the receipt, return null for that field.

        ### CONFIDENCE GUARDRAILS:
        If the image is completely illegible, completely blank, or clearly NOT a financial document (e.g., a photo of a landscape), you must return null for all fields and set all confidence_scores to 0.0.

        ### FEW-SHOT EXAMPLE:
        If you see a receipt with: "Transfer to Acme Corp on 25-Oct-2026. Total: RM 1,250.00. Ref: TRX-998877. From: John Doe via Maybank."
        You will output exactly:
        {
          "parsed_amount": 1250.0,
          "parsed_currency": "MYR",
          "parsed_date": "2026-10-25",
          "parsed_reference": "TRX-998877",
          "sender_name": "John Doe",
          "bank_name": "Maybank",
          "confidence_scores": {
            "amount": 0.99,
            "date": 0.95
          }
        }
        """

        # 3. Call Morpheus API
        response = morpheus_client.chat.completions.create(
            model="qwen3-5-9b", 
            messages=[
                {
                    # Keep the system prompt tiny, exactly like your working version
                    "role": "system",
                    "content": "You are a precise financial OCR API. Return ONLY valid JSON." 
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": """
                            Analyze the attached payment proof.
                            Your ONLY output must be a valid JSON object matching this schema. Do not use markdown backticks (```json).

                            ### FORMAT INSTRUCTIONS:
                            1. parsed_amount: Strip commas and currency symbols. Return a pure float.
                            2. parsed_currency: 3-letter ISO currency code.
                            3. parsed_date: Convert to standard ISO-8601 format: YYYY-MM-DD.
                            4. parsed_reference: Extract the transaction ID or receipt number.
                            5. Missing Data: Return null if not found.

                            ### CONFIDENCE GUARDRAILS:
                            If the image is completely illegible or not a financial document, return null for all fields and set confidence_scores to 0.0.

                            ### JSON SCHEMA / FEW-SHOT EXAMPLE:
                            {
                              "parsed_amount": 1250.0,
                              "parsed_currency": "MYR",
                              "parsed_date": "2026-10-25",
                              "parsed_reference": "TRX-998877",
                              "sender_name": "John Doe",
                              "bank_name": "Maybank",
                              "confidence_scores": {"amount": 0.99, "date": 0.95}
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
        
        # 4. Parse the output
        raw_output = response.choices[0].message.content.strip()
        
        # Strip hallucinated markdown if present
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:-3].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output[3:-3].strip()
            
        parsed_dict = json.loads(raw_output)
        validated_data = ParsedProofData(**parsed_dict)
        
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.COMPLETED,
            parsed_amount=parsed_dict.get("parsed_amount"),
            parsed_currency=parsed_dict.get("parsed_currency"),
            parsed_date=parsed_dict.get("parsed_date"),
            parsed_reference=parsed_dict.get("parsed_reference"),
            parsed_data=validated_data,
            message=None
        )

    except json.JSONDecodeError:
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.FAILED,
            message="Morpheus failed to return valid JSON."
        )
    except Exception as e:
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.FAILED,
            message=f"Morpheus API Error: {str(e)}"
        )

# ══════════════════════════════════════════════════════════════════
# 3B. PDF PARSER & LLM LOGIC (TEXT-ONLY)
# ══════════════════════════════════════════════════════════════════
def extract_data_from_pdf(input_data: ChutesParserInput) -> ChutesParserOutput:
    print(f"--> [PDF Parser] Extracting text from: {input_data.file_path}")
    
    try:
        # 1. Download file from Supabase
        file_bytes = supabase.storage.from_("proofs").download(input_data.file_path)
        if not file_bytes:
            raise ValueError("Downloaded PDF file is empty.")

        # 2. Extract Raw Text using PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text()
            
        # Failsafe: If the PDF is just a scanned image with no text layer
        if not extracted_text.strip():
            raise ValueError("No readable text found in PDF. It may be a scanned image.")
            
        print(f"--> [PDF Parser] Successfully extracted {len(extracted_text)} characters.")

        # 3. Call Morpheus API (Text-Only Mode)
        response = morpheus_client.chat.completions.create(
            model="qwen3-5-9b", # Can be swapped to a pure text model like llama-3.3-70b
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise financial parsing API. Return ONLY valid JSON."
                },
                {
                    "role": "user",
                    "content": f"""
                    Analyze the following raw text extracted from a payment receipt PDF.
                    Your ONLY output must be a valid JSON object matching the schema below. Do not use markdown backticks (```json).

                    ### FORMAT INSTRUCTIONS:
                    1. parsed_amount: Strip commas and currency symbols. Return a pure float.
                    2. parsed_currency: 3-letter ISO currency code.
                    3. parsed_date: Convert to standard ISO-8601 format: YYYY-MM-DD.
                    4. parsed_reference: Extract the transaction ID or receipt number.
                    5. Missing Data: Return null if not found.

                    ### JSON SCHEMA / FEW-SHOT EXAMPLE:
                    {{
                      "parsed_amount": 1250.0,
                      "parsed_currency": "MYR",
                      "parsed_date": "2026-10-25",
                      "parsed_reference": "TRX-998877",
                      "sender_name": "John Doe",
                      "bank_name": "Maybank",
                      "confidence_scores": {{"amount": 0.99, "date": 0.95}}
                    }}

                    ### RAW PDF TEXT:
                    {extracted_text}
                    """
                }
            ],
            temperature=0.0 
        )
        
        # 4. Parse Output & Strip Markdown
        raw_output = response.choices[0].message.content.strip()
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:-3].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output[3:-3].strip()
            
        parsed_dict = json.loads(raw_output)
        
        # 5. Pydantic Validation Safety Net
        validated_data = ParsedProofData(**parsed_dict)
        
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.COMPLETED,
            parsed_amount=parsed_dict.get("parsed_amount"),
            parsed_currency=parsed_dict.get("parsed_currency"),
            parsed_date=parsed_dict.get("parsed_date"),
            parsed_reference=parsed_dict.get("parsed_reference"),
            parsed_data=validated_data,
            message=None
        )

    except json.JSONDecodeError:
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.FAILED,
            message="Model Hallucination: The AI failed to return valid JSON."
        )
    except ValidationError as val_err:
        error_details = "; ".join([f"{e['loc'][0]}: {e['msg']}" for e in val_err.errors()])
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.FAILED,
            message=f"Data Validation Error: {error_details}"
        )
    except Exception as e:
        return ChutesParserOutput(
            proof_id=input_data.proof_id,
            status=ParseStatus.FAILED,
            message=f"PDF Parsing Error: {str(e)}"
        )

# ══════════════════════════════════════════════════════════════════
# 4. MAIN ORCHESTRATOR FUNCTION
# ══════════════════════════════════════════════════════════════════
def process_payment_proof(proof_id: str, file_path: str, file_type: str):
    """
    Handles the lifecycle of an uploaded payment proof.
    """
    print(f"Starting processing for proof_id: {proof_id}")

    parser_input = ChutesParserInput(
        proof_id=proof_id,
        file_path=file_path,
        file_type=file_type
    )

    try:
        if parser_input.file_type == "pdf":
            output: ChutesParserOutput = extract_data_from_pdf(parser_input)
        elif parser_input.file_type in ["jpg", "jpeg", "png"]:
            output: ChutesParserOutput = extract_data_with_chutes(parser_input)
        else:
            raise ValueError(f"Unsupported file type: {parser_input.file_type}")
    except Exception as e:
        output = ChutesParserOutput(
            proof_id=proof_id,
            status=ParseStatus.FAILED,
            message=f"Parser API exception: {str(e)}"
        )

    # Build the update payload mapping exactly to the Supabase columns
    update_payload = {
        "parse_status": output.status.value,
        "parsed_amount": output.parsed_amount,
        "parsed_currency": output.parsed_currency,
        "parsed_date": output.parsed_date,
        "parsed_reference": output.parsed_reference,
        "error_message": output.message,
        "parsed_data": output.parsed_data.model_dump(exclude_none=True) if output.parsed_data else None
    }

    # Clean payload of None values to avoid overwriting DB defaults with nulls
    update_payload = {k: v for k, v in update_payload.items() if v is not None}

    # Push updates to Supabase
    try:
        response = (
            supabase.table("payment_proof")
            .update(update_payload)
            .eq("proof_id", output.proof_id)
            .execute()
        )
        print(f"Successfully updated Supabase for proof_id: {proof_id}")
        return response.data
    
    except Exception as db_error:
        print(f"Failed to update database for {proof_id}. Error: {db_error}")
        return None

# ══════════════════════════════════════════════════════════════════
# 5. EXECUTION BLOCK FOR TESTING
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    process_payment_proof(
        proof_id="b6066b85-2254-4fed-b468-dc2811edeefe", # Your correct proof_id
        file_path="testpdf2.pdf",                    # Updated to png
        file_type="pdf"                                  # Updated to png
    )
