from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os
import uuid

# Import your actual parser and supabase connection
from statement_parser import parse_bank_statement, upload_parsed_statement, supabase
from proof_parser import process_payment_proof
from invoice_parser import process_invoice

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
async def process_statement(file: UploadFile = File(...)):
    print(f"📥 Incoming file from frontend: {file.filename}")
    
    # 1. Securely save the uploaded file temporarily
    temp_filepath = f"temp_{file.filename}"
    try:
        with open(temp_filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print("⚙️ Running Parser and AI Engine...")
        
        # 2. Feed the file into your existing logic
        result = parse_bank_statement(file_path=temp_filepath, local_currency="MYR")
        
        if result["status"] != "success":
            raise HTTPException(status_code=400, detail=result["message"])
            
        # 3. Generate a mathematically valid UUID for this specific upload
        statement_uuid = str(uuid.uuid4())
        
        # 4. Create the parent "Statement" folder in Supabase first
        # BARE MINIMUM: Only sending what we absolutely know it needs
        try:
            supabase.table("bank_statement").insert({
                "statement_id": statement_uuid,           
                "file_type": "text/csv"         
            }).execute()
            print("📁 Parent statement record created successfully.")
        except Exception as e:
            print(f"⚠️ Parent creation bypassed/failed: {e}")

        # 5. Push the parsed transactions straight to your Supabase database
        upload_parsed_statement(
            parsed_result=result,
            statement_id=statement_uuid,
            supabase=supabase
        )
        
        print("✅ Success! Database updated.")
        return {"status": "success", "message": "Statement processed and ledger updated."}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # 6. Clean up the temp file so your server stays clean
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)

@app.post("/api/upload/payment_proof")
async def upload_payment_proof(file: UploadFile = File(...)):
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
async def upload_invoice(file: UploadFile = File(...)):
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
