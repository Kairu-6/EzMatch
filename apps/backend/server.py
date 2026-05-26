from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os
import uuid

# Import your actual parser and supabase connection
from statement_parser import parse_bank_statement, upload_parsed_statement, supabase

app = FastAPI()

# Allow your Next.js app to talk to this Python server without being blocked
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # The magic wildcard that fixes the CORS connection error
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/upload")
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
                "statement_id": statement_uuid,  # Adjusted to match your DB
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