"""
Backend function catalog extractor. stdlib-only (ast). Walks apps/backend/*.py
and apps/backend/agent/*.py, emits backend_functions.json.

ponytail: single-pass ast walk + dict bookkeeping, no AST-transform framework —
this is a one-shot report generator, not a library.
"""
import ast
import json
import os
import re

REPO = r"C:\Users\user\Desktop\kai's\feldilmi"
BACKEND = os.path.join(REPO, "apps", "backend")

FILES = [
    "main.py", "server.py", "auth.py", "orchestrator.py", "forex_api.py",
    "data_contracts.py", "statement_parser.py", "invoice_parser.py",
    "proof_parser.py", "parser_llm.py", "myinvois_client.py",
    "accounting_client.py", "bank_feed_client.py", "bankfeed_state.py",
    "seed_data.py", "seed_demo.py", "seed_files.py",
    "test_reference_match.py", "test_myinvois_map.py", "test_accounting_map.py",
    os.path.join("agent", "runner.py"), os.path.join("agent", "tools.py"),
    os.path.join("agent", "llm.py"), os.path.join("agent", "memory.py"),
    os.path.join("agent", "gate.py"), os.path.join("agent", "verifier.py"),
    os.path.join("agent", "anomaly.py"), os.path.join("agent", "prompts.py"),
    os.path.join("agent", "__init__.py"),
]

EXTERNAL_HINTS = {
    "httpx": "httpx (HTTP client)",
    "openai": "OpenAI SDK",
    "OpenAI": "OpenAI SDK",
    "pytesseract": "pytesseract (Tesseract OCR)",
    "fitz": "PyMuPDF (fitz)",
    "pymupdf": "PyMuPDF",
    "pandas": "pandas",
    "pd": "pandas",
}

LEGACY_ORCH = {"run_reconciliation", "_build_morpheus_prompt", "_call_morpheus", "_write_recommendation"}
LEGACY_FOREX = {"get_rates_batch"}


def sig_from_args(node: ast.AST) -> str:
    """Reconstruct a readable signature string from a FunctionDef node."""
    a = node.args
    parts = []

    def ann(n):
        return ast.unparse(n) if n is not None else None

    def fmt(arg, default=None):
        s = arg.arg
        if arg.annotation is not None:
            s += f": {ann(arg.annotation)}"
        if default is not None:
            s += f" = {ast.unparse(default)}"
        return s

    posonly = list(a.posonlyargs)
    args = list(a.args)
    all_pos = posonly + args
    defaults = list(a.defaults)
    n_no_default = len(all_pos) - len(defaults)
    for i, arg in enumerate(all_pos):
        default = defaults[i - n_no_default] if i >= n_no_default else None
        parts.append(fmt(arg, default))
        if posonly and i == len(posonly) - 1:
            parts.append("/")
    if a.vararg:
        parts.append("*" + a.vararg.arg + (f": {ann(a.vararg.annotation)}" if a.vararg.annotation else ""))
    elif a.kwonlyargs:
        parts.append("*")
    for i, arg in enumerate(a.kwonlyargs):
        default = a.kw_defaults[i]
        parts.append(fmt(arg, default))
    if a.kwarg:
        parts.append("**" + a.kwarg.arg + (f": {ann(a.kwarg.annotation)}" if a.kwarg.annotation else ""))

    ret = f" -> {ast.unparse(node.returns)}" if getattr(node, "returns", None) else ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(parts)}){ret}"


def first_line(doc: str) -> str:
    """Docstring summary: the first paragraph, unwrapped to one line (some docstrings hard-wrap
    the summary sentence across source lines — splitting on '\\n' alone would cut it mid-word),
    capped at the first sentence so long explanatory paragraphs don't leak into a 'one-line' cell."""
    para = " ".join(doc.strip().split("\n\n", 1)[0].split())
    m = re.search(r"^.*?[.!?](?=\s|$)", para)
    sentence = m.group(0) if m else para
    return sentence if len(sentence) <= 160 else sentence[:157].rstrip() + "..."


def name_hint(fn_name: str) -> str:
    """No docstring: turn the name into a short, non-invented hint (e.g. '_write_match' -> 'write match')."""
    words = re.sub(r"^_+", "", fn_name).replace("_", " ").strip()
    return f"({words})" if words else "(no description)"


def dotted(node: ast.AST):
    """Best-effort dotted-name string for a Call's func (Name or Attribute chain)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        if base is None:
            return node.attr
        return f"{base}.{node.attr}"
    if isinstance(node, ast.Call):
        return dotted(node.func)
    return None


def route_info(decorators):
    """If decorator is app.get/post/... return (METHOD, path-expr-string)."""
    for d in decorators:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
            method = d.func.attr.upper()
            if method in {"GET", "POST", "PUT", "DELETE", "PATCH"} and d.args:
                try:
                    path = ast.literal_eval(d.args[0]) if isinstance(d.args[0], ast.Constant) else ast.unparse(d.args[0])
                except Exception:
                    path = ast.unparse(d.args[0])
                return method, path
    return None


def extract_calls_and_tables(body_nodes):
    """Walk a function body once, collecting call targets + db table read/write."""
    calls = set()
    tables_read = set()
    tables_write = set()
    for n in body_nodes:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Call):
                name = dotted(sub.func)
                if name:
                    calls.add(name)
                # background_tasks.add_task(fn, ...) / asyncio.create_task(fn(...)) pass the
                # real callee as a bare arg, not sub.func — pick it up so the dep edge isn't lost.
                if isinstance(sub.func, ast.Attribute) and sub.func.attr == "add_task" and sub.args:
                    ref = dotted(sub.args[0])
                    if ref:
                        calls.add(ref)
                # X.table("NAME") / X.from_("NAME") -> db table; also storage.from_("bucket")
                if isinstance(sub.func, ast.Attribute) and sub.func.attr in ("table", "from_") and sub.args:
                    arg0 = sub.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                        tbl = arg0.value
                        # walk up the call chain on the SAME statement to see if insert/update/upsert/delete follows
                        write = False
                        parent_chain = dotted(sub) or ""
                        # crude heuristic: search siblings in same top-level statement text via unparse
                        try:
                            stmt_src = ast.unparse(n)
                        except Exception:
                            stmt_src = ""
                        if any(op in stmt_src for op in (".insert(", ".update(", ".upsert(", ".delete(")):
                            write = True
                        is_storage = isinstance(sub.func.value, ast.Attribute) and sub.func.value.attr == "storage"
                        label = f"storage:{tbl}" if is_storage else tbl
                        (tables_write if write else tables_read).add(label)
    return calls, tables_read, tables_write


def process_file(relpath):
    path = os.path.join(BACKEND, relpath)
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    try:
        tree = ast.parse(src, filename=relpath)
    except SyntaxError as e:
        print(f"PARSE FAILED: {relpath}: {e}")
        return []

    module = relpath.replace(os.sep, "/")
    entries = []

    def handle_func(node, cls_name):
        decorators = [ast.unparse(d) for d in node.decorator_list]
        deco_nodes = node.decorator_list
        r = route_info(deco_nodes)
        doc = ast.get_docstring(node)
        desc = first_line(doc) if doc else name_hint(node.name)
        calls, treads, twrites = extract_calls_and_tables(node.body)
        entry = {
            "module": module,
            "class": cls_name,
            "name": node.name,
            "lineno": node.lineno,
            "signature": sig_from_args(node),
            "decorators": decorators,
            "endpoint": f"{r[0]} {r[1]}" if r else None,
            "description": desc,
            "calls": sorted(calls),
            "tables_read": sorted(treads),
            "tables_write": sorted(twrites),
        }
        entries.append(entry)

    def walk_defs(node, cls_ctx):
        """Recurse into every scope so nested/closure defs are caught too
        (matches grep's plain line-count baseline, which doesn't care about nesting)."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                for c2 in ast.iter_child_nodes(child):
                    if isinstance(c2, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        handle_func(c2, child.name)
                        walk_defs(c2, None)
                    else:
                        walk_defs(c2, cls_ctx)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                handle_func(child, cls_ctx)
                walk_defs(child, None)
            else:
                walk_defs(child, cls_ctx)

    walk_defs(tree, None)

    # module-level aliases: `_reconcile_task = run_agent` (incl. inside if/else branches) —
    # ponytail: one heuristic pass for the one real case (main.py's engine-select alias),
    # not a general alias-tracking system.
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            ref = dotted(node.value) if isinstance(node.value, (ast.Name, ast.Attribute)) else None
            if ref:
                aliases.setdefault(target, set()).add(ref)

    return entries, aliases


def main():
    all_entries = []
    grep_mismatch = []
    aliases_by_module = {}
    for relpath in FILES:
        entries, aliases = process_file(relpath)
        module = relpath.replace(os.sep, "/")
        aliases_by_module[module] = aliases
        all_entries.extend(entries)
        path = os.path.join(BACKEND, relpath)
        with open(path, "r", encoding="utf-8") as f:
            grep_count = sum(1 for line in f if line.lstrip().startswith(("def ", "async def ")))
        print(f"{relpath}: {len(entries)} (grep-ish: {grep_count})")
        if len(entries) != grep_count:
            grep_mismatch.append((relpath, len(entries), grep_count))

    print(f"\nTOTAL: {len(all_entries)}")
    if grep_mismatch:
        print("MISMATCHES:", grep_mismatch)

    # build module-qualified def-name set for DEPENDS_ON / AFFECTS resolution
    # key: bare name -> list of (module, class, qualname)
    by_bare_name = {}
    for e in all_entries:
        qual = f"{e['module']}::{e['class']+'.' if e['class'] else ''}{e['name']}"
        by_bare_name.setdefault(e["name"], []).append((e["module"], e["class"], qual))

    # index entries by qualname for reverse-edge (AFFECTS) building
    qualname_of = {}
    for e in all_entries:
        qual = f"{e['module']}::{e['class']+'.' if e['class'] else ''}{e['name']}"
        e["qualname"] = qual
        qualname_of[qual] = e

    # resolve each entry's calls -> intra-repo qualnames it depends on, preferring same-module
    for e in all_entries:
        depends_intra = []
        depends_ext = set()
        for c in e["calls"]:
            last = c.split(".")[-1]
            base = c.split(".")[0]
            if base in EXTERNAL_HINTS:
                depends_ext.add(EXTERNAL_HINTS[base])
                continue
            candidate_groups = [by_bare_name.get(last)] if by_bare_name.get(last) else []
            if not candidate_groups:
                # try resolving through same-module aliases, e.g. `_reconcile_task = run_agent`
                # (may be multiple, e.g. one per if/else branch) — collect all, not just first.
                for aliased in aliases_by_module.get(e["module"], {}).get(last, ()):
                    cands = by_bare_name.get(aliased.split(".")[-1])
                    if cands:
                        candidate_groups.append(cands)
            for candidates in candidate_groups:
                # prefer same-module match, else first
                same_mod = [cand for cand in candidates if cand[0] == e["module"]]
                pick = same_mod[0] if same_mod else candidates[0]
                if pick[2] != e["qualname"]:
                    depends_intra.append(pick[2])
        e["depends_intra"] = sorted(set(depends_intra))
        e["depends_ext"] = sorted(depends_ext)

    # reverse edges: who calls me
    reverse = {}
    for e in all_entries:
        for dep in e["depends_intra"]:
            reverse.setdefault(dep, set()).add(e["qualname"])
    for e in all_entries:
        e["called_by"] = sorted(reverse.get(e["qualname"], []))

    # tags
    for e in all_entries:
        tags = []
        fname = e["module"].split("/")[-1]
        if e["endpoint"]:
            tags.append("endpoint")
        if fname == "orchestrator.py" and e["name"] in LEGACY_ORCH:
            tags.append("legacy")
        if fname == "forex_api.py" and e["name"] in LEGACY_FOREX:
            tags.append("legacy")
        if fname == "accounting_client.py":
            # mock-only: function body raises NotImplementedError somewhere (real path stubbed)
            pass  # refined below using source text
        e["tags"] = tags

    # accounting_client mock-only detection: re-scan source for NotImplementedError per function
    acc_path = os.path.join(BACKEND, "accounting_client.py")
    with open(acc_path, "r", encoding="utf-8") as f:
        acc_src = f.read()
    acc_tree = ast.parse(acc_src)
    for node in ast.walk(acc_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_src = ast.unparse(node)
            if "NotImplementedError" in body_src:
                for e in all_entries:
                    if e["module"] == "accounting_client.py" and e["name"] == node.name:
                        e["tags"].append("mock-only")

    out_path = os.path.join(os.path.dirname(__file__), "backend_functions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2)
    print(f"\nWrote {out_path} ({len(all_entries)} entries)")


if __name__ == "__main__":
    main()
