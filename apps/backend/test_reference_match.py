"""
test_reference_match.py
=======================
Self-check for the DuitNow/FPX exact-reference recon key. No framework:
    ./venv/Scripts/python.exe test_reference_match.py

Covers the pure logic that decides an exact-reference match, independent of the
DB/LLM: _reference_pairs (invoice-number and proof-reference keys, normalisation,
one-txn-per-invoice), _extract_reference (narrative token / None), and the gate
verdict for the wrong-amount-same-reference case.
"""
from datetime import date

from data_contracts import InvoiceForMatching, TransactionForMatching, ProofForMatching
from orchestrator import _reference_pairs, _norm_ref
from statement_parser import _extract_reference
from agent.gate import decide, Verdict


def _inv(num, amount, iid=None, currency="MYR"):
    return InvoiceForMatching(
        invoice_id=iid or f"inv-{num}", invoice_number=num, counterparty_name="Acme",
        invoice_currency=currency, invoice_amount=amount, invoice_date=date(2026, 7, 1),
    )


def _txn(ref, credit, tid=None, currency="MYR"):
    return TransactionForMatching(
        transaction_id=tid or f"txn-{ref}", transaction_date=date(2026, 7, 1),
        description="DUITNOW TRANSFER", description_normalised="DUITNOW TRANSFER",
        reference_number=ref, debit_amount=None, credit_amount=credit, currency_code=currency,
    )


def _proof(ref, amount, pid="p1"):
    return ProofForMatching(proof_id=pid, parsed_amount=amount, parsed_currency="MYR",
                            parsed_date="2026-07-01", parsed_reference=ref, parsed_data=None)


def main():
    # 1. Exact match on invoice number, formatting differences ignored.
    inv = _inv("INV-2026-001", 1000.0)
    txn = _txn("inv 2026 001", 1000.0)            # spaces vs dashes, lower-case
    pairs = _reference_pairs([inv], [txn], [])
    assert len(pairs) == 1 and pairs[0][0] is inv and pairs[0][1] is txn, "invoice-number key failed"

    # 2. Match via the proof reference when the invoice number differs from the ref.
    inv2 = _inv("BILL-42", 500.0)
    txn2 = _txn("DN99887766", 500.0)
    proof2 = _proof("DN99887766", 500.0)
    pairs = _reference_pairs([inv2], [txn2], [proof2])
    assert len(pairs) == 1 and pairs[0][2] is proof2, "proof-reference key failed"

    # 3. No reference overlap -> no pair (left for the fuzzy matcher).
    assert _reference_pairs([_inv("INV-A", 10.0)], [_txn("INV-B", 10.0)], []) == [], "false positive"

    # 4. One transaction is claimed by only one invoice.
    a, b = _inv("INV-X", 10.0, "ia"), _inv("INV-X", 10.0, "ib")   # same ref, two invoices
    t = _txn("INV-X", 10.0)
    pairs = _reference_pairs([a, b], [t], [])
    assert len(pairs) == 1, "a transaction was matched to two invoices"

    # 5. Missing/blank references never match.
    assert _reference_pairs([_inv("", 10.0)], [_txn(None, 10.0)], []) == [], "blank ref matched"

    # 6. Wrong-amount-same-reference -> gate routes to human, not auto-commit.
    #    (The pair is still found; the gate is what protects the amount.)
    inv6, txn6 = _inv("INV-777", 1000.0), _txn("INV-777", 850.0)   # 15% short
    assert len(_reference_pairs([inv6], [txn6], [])) == 1, "ref pair should still form"
    verdict, _ = decide(0.99, variance_pct=-15.0, converted_amount=1000.0, auto_count=0)
    assert verdict == Verdict.ROUTE_TO_HUMAN, f"expected human review, got {verdict}"
    # And a clean amount auto-commits.
    v_ok, _ = decide(0.99, variance_pct=-1.0, converted_amount=1000.0, auto_count=0)
    assert v_ok == Verdict.AUTO_COMMIT, f"clean ref match should auto-commit, got {v_ok}"

    # 7. _extract_reference pulls the token from a narrative, None when absent.
    assert _extract_reference("DUITNOW TRANSFER REF INV-2026-001") == "INV-2026-001"
    assert _extract_reference("FPX PAYMENT TXN: DN12345") == "DN12345"
    assert _extract_reference("MONTHLY SERVICE CHARGE") is None

    # 8. _norm_ref sanity.
    assert _norm_ref(" inv-2026 001 ") == "INV2026001"
    assert _norm_ref(None) is None and _norm_ref("   ") is None

    print("OK — reference pairing, gate protection, extraction, normalisation all pass.")


if __name__ == "__main__":
    main()
