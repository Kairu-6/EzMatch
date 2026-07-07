import logging
import os
import shutil
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import the parsers and the shared supabase connection.
from statement_parser import parse_bank_statement, upload_parsed_statement, supabase
from proof_parser import process_payment_proof
from invoice_parser import process_invoice
from auth import get_current_sme_id
import myinvois_client
import accounting_client

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI()

# Allow the Next.js frontend to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

        result = parse_bank_statement(file_path=temp_filepath, local_currency=local_currency)
        if result["status"] != "success":
            raise HTTPException(status_code=400, detail=result["message"])

        statement_uuid = str(uuid.uuid4())
        upload_parsed_statement(
            parsed_result=result,
            statement_id=statement_uuid,
            supabase=supabase,
            account_id=account_id,
            sme_id=sme_id,
        )
        logger.info("Statement %s processed (%s).", statement_uuid, local_currency)
        return {"status": "success", "message": "Statement processed and ledger updated."}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Statement upload failed.")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)


@app.post("/api/upload/payment_proof")
async def upload_payment_proof(
    file: UploadFile = File(...),
    sme_id: str = Depends(get_current_sme_id),
):
    try:
        proof_id = str(uuid.uuid4())
        file_ext = file.filename.split(".")[-1].lower()
        storage_path = f"{proof_id}.{file_ext}"

        supabase.table("payment_proof").insert({
            "proof_id": proof_id,
            "sme_id": sme_id,
            "parse_status": "pending",
            "file_type": file_ext,
            "file_path": storage_path,
        }).execute()

        file_bytes = await file.read()
        supabase.storage.from_("proofs").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": file.content_type},
        )

        process_payment_proof(proof_id=proof_id, file_path=storage_path, file_type=file_ext)
        logger.info("Payment proof %s uploaded and parsed.", proof_id)
        return {
            "status": "success",
            "message": "Payment proof uploaded and AI extraction complete.",
            "proof_id": proof_id,
        }
    except Exception as e:
        logger.exception("Payment proof upload failed.")
        raise HTTPException(status_code=500, detail=f"Upload workflow failed: {str(e)}")
    finally:
        file.file.close()


@app.post("/api/upload/invoice")
async def upload_invoice(
    file: UploadFile = File(...),
    sme_id: str = Depends(get_current_sme_id),
):
    try:
        invoice_id = str(uuid.uuid4())
        file_ext = file.filename.split(".")[-1].lower()
        storage_path = f"{invoice_id}.{file_ext}"

        supabase.table("invoice").insert({
            "invoice_id": invoice_id,
            "sme_id": sme_id,
            "status": "pending",
        }).execute()

        file_bytes = await file.read()
        supabase.storage.from_("invoices").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": file.content_type},
        )

        process_invoice(invoice_id=invoice_id, file_path=storage_path, file_type=file_ext)
        logger.info("Invoice %s uploaded and parsed.", invoice_id)
        return {
            "status": "success",
            "message": "Invoice uploaded and AI extraction complete.",
            "invoice_id": invoice_id,
        }
    except Exception as e:
        logger.exception("Invoice upload failed.")
        raise HTTPException(status_code=500, detail=f"Upload workflow failed: {str(e)}")
    finally:
        file.file.close()


@app.post("/api/myinvois/sync")
async def myinvois_sync(sme_id: str = Depends(get_current_sme_id)):
    """Pull VALIDATED e-Invoices (both directions) from MyInvois into the invoice
    table. Idempotent on (sme_id, myinvois_uuid). See myinvois_client."""
    creds = (
        supabase.table("myinvois_credential")
        .select("*").eq("sme_id", sme_id).limit(1).execute().data
    )
    if not creds:
        raise HTTPException(status_code=400, detail="MyInvois is not configured. Add credentials in Settings.")
    creds = creds[0]

    imported, skipped = 0, 0
    by_direction = {"Sent": 0, "Received": 0}
    try:
        for direction in ("Sent", "Received"):
            docs = myinvois_client.get_recent_documents(creds, direction)
            uuids = [d["uuid"] for d in docs if d.get("uuid")]
            if not uuids:
                continue
            # Dedup against already-synced invoices for this tenant.
            existing = (
                supabase.table("invoice")
                .select("myinvois_uuid").eq("sme_id", sme_id)
                .in_("myinvois_uuid", uuids).execute().data
            )
            seen = {r["myinvois_uuid"] for r in existing}
            rows = []
            for uuid_ in uuids:
                if uuid_ in seen:
                    skipped += 1
                    continue
                ubl = myinvois_client.get_document_raw(creds, uuid_)
                row = myinvois_client.map_document(ubl, direction, sme_id, uuid_)
                # Skip half-mapped docs — they'd be dropped by recon anyway.
                if not all(row.get(k) for k in
                           ("invoice_number", "counterparty_name", "invoice_currency",
                            "invoice_amount", "invoice_date")):
                    skipped += 1
                    continue
                rows.append(row)
            if rows:
                supabase.table("invoice").upsert(
                    rows, on_conflict="sme_id,myinvois_uuid"
                ).execute()
                imported += len(rows)
                by_direction[direction] += len(rows)

        logger.info("MyInvois sync for %s: imported=%d skipped=%d", sme_id, imported, skipped)
        return {"status": "success", "imported": imported, "skipped": skipped, "by_direction": by_direction}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("MyInvois sync failed.")
        raise HTTPException(status_code=500, detail=f"MyInvois sync failed: {str(e)}")


@app.post("/api/accounting/sync")
async def accounting_sync(
    provider: str,
    sme_id: str = Depends(get_current_sme_id),
):
    """Pull sales invoices from an accounting system (provider=autocount|sql) into the
    invoice table. Idempotent on (sme_id, source, source_ref). See accounting_client."""
    if provider not in ("autocount", "sql"):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    creds = (
        supabase.table("accounting_credential")
        .select("*").eq("sme_id", sme_id).eq("provider", provider).limit(1).execute().data
    )
    if not creds:
        raise HTTPException(status_code=400, detail=f"{provider} is not configured. Add credentials in Settings.")
    creds = creds[0]

    try:
        docs = accounting_client.get_recent_invoices(creds)
        rows = []
        for doc in docs:
            row = accounting_client.map_invoice(doc, sme_id, provider)
            # Skip half-mapped docs — recon would drop them anyway.
            if not all(row.get(k) for k in
                       ("invoice_number", "counterparty_name", "invoice_currency",
                        "invoice_amount", "invoice_date")):
                continue
            rows.append(row)

        # Dedup against already-synced invoices for this tenant+source.
        refs = [r["source_ref"] for r in rows]
        skipped = 0
        if refs:
            existing = (
                supabase.table("invoice")
                .select("source_ref").eq("sme_id", sme_id).eq("source", provider)
                .in_("source_ref", refs).execute().data
            )
            seen = {r["source_ref"] for r in existing}
            skipped = sum(1 for r in rows if r["source_ref"] in seen)
            rows = [r for r in rows if r["source_ref"] not in seen]

        if rows:
            supabase.table("invoice").upsert(
                rows, on_conflict="sme_id,source,source_ref"
            ).execute()

        logger.info("Accounting sync (%s) for %s: imported=%d skipped=%d", provider, sme_id, len(rows), skipped)
        return {"status": "success", "imported": len(rows), "skipped": skipped, "provider": provider}
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Accounting sync failed.")
        raise HTTPException(status_code=500, detail=f"Accounting sync failed: {str(e)}")
