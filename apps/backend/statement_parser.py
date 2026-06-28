import os
import re
import hashlib
import logging
from datetime import datetime, date
from supabase import create_client, Client
from typing import Any
from dotenv import load_dotenv
import json

import pandas as pd
from pydantic import ValidationError

# We only need the one schema now!
from data_contracts import TransactionSchema

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_API_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
DATE_ALIASES    = {"date", "transaction date", "value date", "txn date", "posting date", "trans. date"}
DESC_ALIASES    = {"description", "details", "particulars", "narration", "transaction details", "remarks"}
AMOUNT_ALIASES  = {"amount", "value", "sum", "net amount"}
DEBIT_ALIASES   = {"debit", "withdrawal", "dr", "dr amount", "debit amount"}
CREDIT_ALIASES  = {"credit", "deposit", "cr", "cr amount", "credit amount"}
BALANCE_ALIASES = {"balance", "running balance", "closing balance", "bal", "ledger balance", "available balance"}

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y%m%d",
]

_REF_NOISE  = re.compile(r"\b(ref|ref#|txn|trx|id|no\.?)\s*[#:]?\s*[\w\-]+", flags=re.IGNORECASE)
_WHITESPACE = re.compile(r"\s{2,}")

# Helpers
def _detect_encoding(file_path: str) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(file_path, encoding=enc) as f:
                f.read(1024)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _resolve_column(columns: list[str], aliases: set[str]) -> str | None:
    for col in columns:
        if col.strip().lower() in aliases:
            return col
    return None


def _clean_amount(raw: Any) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)

    s = str(raw).strip()
    is_debit    = bool(re.search(r"\bdr\.?\b", s, re.IGNORECASE))
    is_negative = s.startswith("(") and s.endswith(")")

    s = re.sub(r"[^\d.\-]", "", s).strip(".")

    if not s:
        raise ValueError(f"Cannot parse amount from '{raw}'.")

    value = float(s)
    if is_debit or is_negative:
        value = -abs(value)

    return value


def _parse_date(raw: Any) -> str:
    s = str(raw).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date '{s}' with any known format.")


def _normalise_description(raw: str) -> str:
    s = _REF_NOISE.sub("", raw)
    s = re.sub(r"\b\d{4,}\b", "", s)
    s = _WHITESPACE.sub(" ", s).strip(" -+/")
    return s.upper()


def _fingerprint(date_iso: str, description: str, amount: float, occurrence: int) -> str:
    payload = f"{date_iso}|{description.upper()}|{round(amount, 2)}|{occurrence}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _merge_debit_credit(df: pd.DataFrame) -> pd.DataFrame:
    cols       = df.columns.tolist()
    debit_col  = _resolve_column(cols, DEBIT_ALIASES)
    credit_col = _resolve_column(cols, CREDIT_ALIASES)

    if debit_col and credit_col:
        logger.info("Split debit/credit columns detected — merging into signed 'amount'.")
        debit  = df[debit_col].apply(lambda x: -abs(_clean_amount(x)) if pd.notna(x) and str(x).strip() else 0.0)
        credit = df[credit_col].apply(lambda x: abs(_clean_amount(x)) if pd.notna(x) and str(x).strip() else 0.0)
        df["amount"] = debit + credit
        df.drop(columns=[debit_col, credit_col], inplace=True)

    return df

# Public API
def parse_bank_statement(
    file_path: str,
    local_currency: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        return {"status": "error", "message": f"File not found: {file_path}"}

    # Load
    ext = os.path.splitext(file_path)[-1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            logger.info("Reading '%s' as Excel workbook.", file_path)
            df = pd.read_excel(file_path, engine="openpyxl")
        else:
            encoding = _detect_encoding(file_path)
            logger.info("Reading '%s' as CSV with encoding '%s'.", file_path, encoding)
            df = pd.read_csv(file_path, encoding=encoding, skip_blank_lines=True)
    except pd.errors.EmptyDataError:
        return {"status": "error", "message": "File is empty."}
    except Exception as exc:
        logger.exception("Failed to read file.")
        return {"status": "error", "message": str(exc)}

    # Normalise headers
    df.dropna(how="all", inplace=True)
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Resolve columns
    cols        = df.columns.tolist()
    date_col    = _resolve_column(cols, DATE_ALIASES)
    desc_col    = _resolve_column(cols, DESC_ALIASES)
    amount_col  = _resolve_column(cols, AMOUNT_ALIASES)
    balance_col = _resolve_column(cols, BALANCE_ALIASES)

    df = _merge_debit_credit(df)
    if not amount_col:
        amount_col = _resolve_column(df.columns.tolist(), {"amount"})

    missing = [name for name, col in [("date", date_col), ("description", desc_col), ("amount", amount_col)] if not col]
    if missing:
        msg = f"CSV is missing required columns: {missing}. Found: {cols}"
        logger.warning(msg)
        return {"status": "error", "message": msg}

    # Parse rows
    transactions: list[dict] = []
    skipped = 0
    _seen: dict[str, int] = {}  # tracks occurrence count per (date|desc|amount) key

    for idx, row in df.iterrows():
        if pd.isna(row[desc_col]) and pd.isna(row[amount_col]):
            continue

        try:
            date_iso = _parse_date(row[date_col])
        except ValueError as exc:
            logger.warning("Row %d skipped — %s", idx, exc)
            skipped += 1
            continue

        txn_date = date.fromisoformat(date_iso)
        if date_from and txn_date < date_from:
            continue
        if date_to and txn_date > date_to:
            continue

        try:
            amount = _clean_amount(row[amount_col])
        except ValueError as exc:
            logger.warning("Row %d skipped — %s", idx, exc)
            skipped += 1
            continue

        description           = str(row[desc_col]).strip()
        description_normalised = _normalise_description(description)

        running_balance: float | None = None
        if balance_col and pd.notna(row.get(balance_col)):
            try:
                running_balance = abs(_clean_amount(row[balance_col]))
            except ValueError:
                pass

        _key        = f"{date_iso}|{description.upper()}|{round(amount, 2)}"
        occurrence  = _seen.get(_key, 0)
        _seen[_key] = occurrence + 1
        txn_id      = _fingerprint(date_iso, description, amount, occurrence)

        try:
            # Splitting debit and credit immediately using the new schema
            txn = TransactionSchema(
                transaction_id=txn_id,
                transaction_date=date_iso,
                description=description,
                description_normalised=description_normalised,
                reference_number=None,
                debit_amount=round(abs(amount), 2) if amount < 0 else None,
                credit_amount=round(amount, 2)     if amount >= 0 else None,
                currency_code=local_currency,
                running_balance=running_balance,
                is_matched=False,
            )
            transactions.append(txn.model_dump())
        except ValidationError as exc:
            logger.warning("Row %d failed schema validation — %s", idx, exc)
            skipped += 1
            continue

    if not transactions:
        return {"status": "error", "message": "No valid transactions found in file."}

    # Build metadata using the newly split columns
    credits = [t["credit_amount"] for t in transactions if t["credit_amount"] is not None]
    debits  = [t["debit_amount"]  for t in transactions if t["debit_amount"]  is not None]
    dates   = [t["transaction_date"] for t in transactions]
    meta = {
        "total_transactions": len(transactions),
        "skipped_rows":       skipped,
        "date_range":         {"from": min(dates), "to": max(dates)},
        "total_credits":      round(sum(credits), 2),
        "total_debits":       round(sum(debits), 2),
        "net":                round(sum(credits) - sum(debits), 2),
        "currency":           local_currency.upper(),
    }

    logger.info(
        "Parsed %d transactions (%d skipped). Net: %s %.2f",
        len(transactions), skipped, meta["currency"], meta["net"],
    )

    return {"status": "success", "data": transactions, "meta": meta}


def upload_parsed_statement(
    parsed_result: dict[str, Any],
    statement_id: str,
    supabase: Any,
    account_id: str | None = None,
    sme_id: str | None = None,
):
    if parsed_result.get("status") != "success":
        logger.error("Cannot upload: parsing was not successful.")
        return None

    # --- STEP 1: Resolve the target account ---
    # Use the explicitly chosen account if provided; otherwise fall back to the
    # tenant's primary/first account (single-tenant MVP).
    if not account_id:
        # Fall back to the tenant's primary/first account. sme_id comes from the
        # verified JWT (server.py); env DEFAULT_SME_ID is a legacy last resort.
        owner_sme_id = sme_id or os.getenv("DEFAULT_SME_ID")
        account_query = supabase.table("bank_account").select("account_id")
        if owner_sme_id:
            account_query = account_query.eq("sme_id", owner_sme_id)
        # Prefer the primary account when falling back.
        account_res = account_query.order("is_primary", desc=True).limit(1).execute()
        if not account_res.data:
            account_res = supabase.table("bank_account").select("account_id").limit(1).execute()
        if not account_res.data:
            logger.error("No bank accounts found! Cannot link statement.")
            return None
        account_id = account_res.data[0]["account_id"]

    # --- FIX STEP 2: Create the Parent Statement Record First ---
    meta = parsed_result["meta"]
    statement_payload = {
        "statement_id": statement_id,
        "account_id": account_id,
        "file_type": "csv",
        "file_path": f"/{statement_id}.csv", # giving it a clean path just in case
        "period_start": meta["date_range"]["from"],
        "period_end": meta["date_range"]["to"],
    }
    
    try:
        supabase.table("bank_statement").upsert(statement_payload).execute()
        logger.info(f"Created parent statement {statement_id} successfully.")
    except Exception as exc:
        logger.exception("Failed to create parent bank_statement record.")
        raise

    # --- FIX STEP 3: Insert the Transactions ---
    db_ready_rows = []

    for raw_row in parsed_result["data"]:
        raw_row["statement_id"] = statement_id
        # The parser's transaction_id is a content hash (date|desc|amount|n), so
        # the SAME statement uploaded under two different accounts/tenants would
        # produce identical ids and collide on the upsert below — silently
        # reassigning one tenant's transactions to another. Scope the id to the
        # account. Re-uploading to the SAME account stays idempotent.
        base_id = raw_row.get("transaction_id")
        if base_id:
            raw_row["transaction_id"] = hashlib.sha256(
                f"{account_id}|{base_id}".encode()
            ).hexdigest()
        db_ready_rows.append(raw_row)

    if not db_ready_rows:
        logger.warning("No valid rows to upload.")
        return None

    try:
        response = (
            supabase.table("bank_transaction")
            .upsert(db_ready_rows, on_conflict="transaction_id")
            .execute()
        )
        logger.info(f"Successfully upserted {len(response.data)} transactions to DB.")
        return response.data
        
    except Exception as exc:
        logger.exception("Failed to upload transactions to Supabase.")
        raise

# --- TESTING EXECUTION ---
if __name__ == "__main__":
    print("--- STARTING PARSE ---")
    result = parse_bank_statement(
        file_path="statement2.csv", 
        local_currency="MYR"
    )

    print(json.dumps(result, indent=2))

    print("--- STARTING UPLOAD ---")

    # Generating a fresh UUID so the test script won't crash on duplicates
    import uuid
    test_id = str(uuid.uuid4())
    
    upload_result = upload_parsed_statement(
        parsed_result=result, 
        statement_id=test_id, 
        supabase=supabase
    )

    print("Upload complete!")