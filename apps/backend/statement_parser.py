import os
import re
import hashlib
import logging
from datetime import datetime, date
from typing import Any

import pandas as pd
from pydantic import BaseModel, field_validator, ValidationError

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

# Schema

class TransactionSchema(BaseModel):
    transaction_id:        str
    date:                  str
    description:           str
    description_normalised: str
    amount:                float
    currency:              str
    running_balance:       float | None

    @field_validator("currency")
    @classmethod
    def currency_must_be_iso(cls, v: str) -> str:
        if not v or not v.isalpha() or len(v) != 3:
            raise ValueError(f"Currency '{v}' is not a valid 3-letter ISO 4217 code.")
        return v.upper()

    @field_validator("date")
    @classmethod
    def date_must_be_iso(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date '{v}' is not in ISO 8601 format (YYYY-MM-DD).")
        return v

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
    # occurrence = how many times this exact (date, description, amount) combo
    # has already appeared in this file. Two coffees bought on the same day
    # for the same price get occurrence=0 and occurrence=1 — different hashes.
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
            txn = TransactionSchema(
                transaction_id=txn_id,
                date=date_iso,
                description=description,
                description_normalised=description_normalised,
                amount=amount,
                currency=local_currency,
                running_balance=running_balance,
            )
            transactions.append(txn.model_dump())
        except ValidationError as exc:
            logger.warning("Row %d failed schema validation — %s", idx, exc)
            skipped += 1
            continue

    if not transactions:
        return {"status": "error", "message": "No valid transactions found in file."}

    # Build metadata
    amounts = [t["amount"] for t in transactions]
    dates   = [t["date"] for t in transactions]
    meta = {
        "total_transactions": len(transactions),
        "skipped_rows":       skipped,
        "date_range":         {"from": min(dates), "to": max(dates)},
        "total_credits":      round(sum(a for a in amounts if a > 0), 2),
        "total_debits":       round(sum(a for a in amounts if a < 0), 2),
        "net":                round(sum(amounts), 2),
        "currency":           local_currency.upper(),
    }

    logger.info(
        "Parsed %d transactions (%d skipped). Net: %s %.2f",
        len(transactions), skipped, meta["currency"], meta["net"],
    )

    return {"status": "success", "data": transactions, "meta": meta}