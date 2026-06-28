from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os
import uuid
from dotenv import load_dotenv

# Import your actual parser and supabase connection
from statement_parser import parse_bank_statement, upload_parsed_statement, supabase
from proof_parser import process_payment_proof
from invoice_parser import process_invoice
from auth import get_current_sme_id

load_dotenv()

app = FastAPI()

# Allow your Next.js app to talk to this Python server without being blocked
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # The magic wildcard that fixes the CORS connection error
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/upload/statement")
async def process_statement(
    file: UploadFile = File(...),
    account_id: str | None = Form(None),
    sme_id: str = Depends(get_current_sme_id),
):
    print(f"📥 Incoming file from frontend: {file.filename} (account_id={account_id})")

    # 1. Securely save the uploaded file temporarily
    temp_filepath = f"temp_{file.filename}"
    try:
        with open(temp_filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Parse in the target account's currency (falls back to MYR).
        local_currency = "MYR"
        if account_id:
            acct = (
                supabase.table("bank_account")
                .select("currency_code, sme_id")
                .eq("account_id", account_id)
                .limit(1)
                .execute()
                .data
            )
            # The posted account must belong to the authenticated tenant.
            if not acct or acct[0].get("sme_id") != sme_id:
                raise HTTPException(
                    status_code=403,
                    detail="Account does not belong to your workspace.",
                )
            if acct[0].get("currency_code"):
                local_currency = acct[0]["currency_code"]

        print(f"⚙️ Running parser (currency={local_currency})...")

        # 2. Feed the file into the existing logic
        result = parse_bank_statement(file_path=temp_filepath, local_currency=local_currency)

        if result["status"] != "success":
            raise HTTPException(status_code=400, detail=result["message"])

        # 3. Generate a UUID for this upload
        statement_uuid = str(uuid.uuid4())

        # 4. Push the parsed transactions to Supabase, linked to the chosen
        #    account (upload_parsed_statement creates the bank_statement row).
        upload_parsed_statement(
            parsed_result=result,
            statement_id=statement_uuid,
            supabase=supabase,
            account_id=account_id,
            sme_id=sme_id,
        )

        print("✅ Success! Database updated.")
        return {"status": "success", "message": "Statement processed and ledger updated."}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # 6. Clean up the temp file so your server stays clean
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)

@app.post("/api/upload/payment_proof")
async def upload_payment_proof(
    file: UploadFile = File(...),
    sme_id: str = Depends(get_current_sme_id),
):
    print("\n" + "="*50)
    print("🚀 [API START] NEW PAYMENT PROOF UPLOAD")
    print("="*50)
    print(f"📦 Received File: {file.filename} | Type: {file.content_type}")
    
    try:
        proof_id = str(uuid.uuid4())
        file_ext = file.filename.split(".")[-1].lower()
        storage_path = f"{proof_id}.{file_ext}" 
        
        print(f"🔑 Generated proof_id: {proof_id}")
        
        # ---------------------------------------------------------
        # STEP 1: INSERT PENDING ROW
        # ---------------------------------------------------------
        print("\n🟡 [STEP 1] Inserting PENDING row into Supabase 'payment_proof' table...")
        insert_response = supabase.table("payment_proof").insert({
            "proof_id": proof_id,
            "sme_id": sme_id,
            "parse_status": "pending",
            "file_type": file_ext,
            "file_path": storage_path
        }).execute()
        
        print(f"✅ DB Insert Success! Inserted Data: {insert_response.data}")

        # ---------------------------------------------------------
        # STEP 2: UPLOAD TO BUCKET
        # ---------------------------------------------------------
        print(f"\n☁️ [STEP 2] Uploading {file_ext.upper()} to Supabase Storage bucket 'proofs'...")
        file_bytes = await file.read()
        
        storage_response = supabase.storage.from_("proofs").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": file.content_type}
        )
        print(f"✅ Storage Upload Success! Path in bucket: {storage_path}")

        # ---------------------------------------------------------
        # STEP 3: TRIGGER AI PARSER
        # ---------------------------------------------------------
        print("\n🤖 [STEP 3] Handing off to AI Orchestrator (proof_parser.py)...")
        
        # This calls your untouched parser function
        process_payment_proof(
            proof_id=proof_id,
            file_path=storage_path,
            file_type=file_ext
        )

        print("\n🎉 [DONE] Full pipeline executed successfully. Returning 200 OK to frontend.\n")
        return {
            "status": "success",
            "message": "Payment proof uploaded and AI extraction complete.",
            "proof_id": proof_id
        }

    except Exception as e:
        print(f"\n❌ [CRITICAL ERROR] Pipeline failed at some point: {str(e)}\n")
        raise HTTPException(status_code=500, detail=f"Upload workflow failed: {str(e)}")
        
    finally:
        # Prevent memory leaks
        file.file.close()

@app.post("/api/upload/invoice")
async def upload_invoice(
    file: UploadFile = File(...),
    sme_id: str = Depends(get_current_sme_id),
):
    print("\n" + "="*50)
    print("🚀 [API START] NEW INVOICE UPLOAD")
    print("="*50)
    print(f"📦 Received File: {file.filename} | Type: {file.content_type}")
    
    try:
        invoice_id = str(uuid.uuid4())
        file_ext = file.filename.split(".")[-1].lower()
        storage_path = f"{invoice_id}.{file_ext}" 
        
        print(f"🔑 Generated invoice_id: {invoice_id}")
        
        # ---------------------------------------------------------
        # STEP 1: INSERT PENDING ROW
        # ---------------------------------------------------------
        print("\n🟡 [STEP 1] Inserting PENDING row into Supabase 'invoice' table...")
        insert_response = supabase.table("invoice").insert({
            "invoice_id": invoice_id,
            "sme_id": sme_id,
            "status": "pending"
        }).execute()
        
        print(f"✅ DB Insert Success! Inserted Data: {insert_response.data}")

        # ---------------------------------------------------------
        # STEP 2: UPLOAD TO BUCKET
        # ---------------------------------------------------------
        print(f"\n☁️ [STEP 2] Uploading {file_ext.upper()} to Supabase Storage bucket 'invoices'...")
        file_bytes = await file.read()
        
        storage_response = supabase.storage.from_("invoices").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": file.content_type}
        )
        print(f"✅ Storage Upload Success! Path in bucket: {storage_path}")

        # ---------------------------------------------------------
        # STEP 3: TRIGGER AI PARSER
        # ---------------------------------------------------------
        print("\n🤖 [STEP 3] Handing off to AI Orchestrator (invoice_parser.py)...")
        
        process_invoice(
            invoice_id=invoice_id,
            file_path=storage_path,
            file_type=file_ext
        )

        print("\n🎉 [DONE] Full pipeline executed successfully. Returning 200 OK to frontend.\n")
        return {
            "status": "success",
            "message": "Invoice uploaded and AI extraction complete.",
            "invoice_id": invoice_id
        }

    except Exception as e:
        print(f"\n❌ [CRITICAL ERROR] Pipeline failed: {str(e)}\n")
        raise HTTPException(status_code=500, detail=f"Upload workflow failed: {str(e)}")
        
    finally:
        file.file.close()
