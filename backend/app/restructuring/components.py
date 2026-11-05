"""Stage 2-3: tender understanding -> work items -> capability components.

Works on real tender bundles (NIT / RFP / Scope of Work / Technical Specifications PDFs) and,
when supplied, a Bill of Quantities (CSV / XLSX). Every item keeps its provenance: document,
page and the exact source text, so the auditor can check what the system read.

Values are never invented. Order of preference for a component's value:
  1. BOQ amounts (``value_basis = "boq"``)
  2. amounts written next to the item in the tender text (``"document"``)
  3. a share of the tender's stated estimated value by number of scope items
     (``"assumed_item_share"`` - shown as an assumption and editable by the user)
  4. otherwise ``None`` (``"unknown"``)
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict

from .classifier import classify, label
from .taxonomy import OTHER

ITEM_START = re.compile(r"^\s*(?:\(?\d{1,3}(?:\.\d{1,3}){0,3}[.)]?|\(?[a-z][.)]|\(?[ivx]{1,5}[.)]|[•●▪\-–*])\s+", re.I)
WORK_VERBS = re.compile(
    r"\b(supply(?:ing)?|install(?:ation|ing)?|provid(?:e|ing)|lay(?:ing)?|construct(?:ion|ing)?|commission(?:ing)?|"
    r"erect(?:ion|ing)?|fabricat(?:e|ion|ing)|design(?:ing)?|develop(?:ment|ing)?|testing|maintenance|"
    r"operat(?:e|ion)|dismantl(?:e|ing)|excavat(?:e|ion|ing)|implement(?:ation|ing)?|integrat(?:e|ion|ing)|"
    r"deploy(?:ment|ing)?|upgrad(?:e|ation)|augment(?:ation)?|repair(?:ing|s)?|painting|replacement|"
    r"retrofit(?:ting)?|survey(?:ing)?|calibrat(?:e|ion)|establish(?:ment|ing)?|improvement|marking|"
    r"setting up|creation|provision|procurement of|strengthening|rehabilitation|widening|modernisation|modernization)\b", re.I)
SCOPE_SECTION = re.compile(r"\b(scope of (?:work|supply|services)|schedule of (?:quantities|requirements)|bill of quantities|"
                           r"\bboq\b|technical specifications?|work components?|description of works?|project components?|"
                           r"terms of reference)\b", re.I)
HEADING = re.compile(r"^(?:(?:section|part|chapter)\s+[\divxlc]+[.:\-]?\s*|\d{1,2}\.?\s+)?[A-Z][A-Za-z ,&/()\-]{3,80}$")
BOILERPLATE = re.compile(
    r"\b(turnover|earnest money|emd\b|bid security|performance security|penalt(?:y|ies)|liquidated damages|"
    r"arbitration|jurisdiction|blacklist|debarr|power of attorney|affidavit|eligib|pre-?qualification|"
    r"bank guarantee|tender fee|document fee|signature|seal|net worth|solvency|pan card|integrity pact|"
    r"force majeure|termination|similar work|bid validity|corrigend|online bid|e-?procurement portal|"
    r"digital signature|dsc\b|undertaking|declaration|indemnit|insurance|notice inviting tender|nit no|tender no)\b", re.I)
PAGE_NOISE = re.compile(r"^(page \d+( of \d+)?|\d+|-\s*\d+\s*-)$", re.I)

MONEY = re.compile(
    r"(?:(?:rs\.?|inr|₹)\s*)(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crores?|cr\.?|lakhs?|lacs?|lakh)?"
    r"|(?P<num2>\d[\d,]*(?:\.\d+)?)\s*(?P<unit2>crores?|lakhs?|lacs?)\b", re.I)
ESTIMATE = re.compile(r"(estimated (?:cost|value)|tender value|cost of (?:the )?work|project cost|contract value)", re.I)


def parse_money_cr(text: str) -> float | None:
    """First money amount in ``text`` converted to ₹ crore, or None."""
    m = MONEY.search(text)
    if not m:
        return None
    num = (m.group("num") or m.group("num2") or "").replace(",", "")
    unit = (m.group("unit") or m.group("unit2") or "").lower()
    try:
        value = float(num)
    except ValueError:
        return None
    if unit.startswith("cr"):
        return value
    if unit.startswith(("lakh", "lac")):
        return value / 100
    return value / 1e7  # plain rupees


def stated_estimate_cr(pages: list[tuple[str, int, str]]) -> tuple[float | None, dict | None]:
    for doc, page, text in pages:
        for line in text.splitlines():
            if ESTIMATE.search(line):
                v = parse_money_cr(line)
                if v and v >= 0.01:
                    return round(v, 4), {"document_id": doc, "page": page, "quote": line.strip()[:240]}
    return None, None


def segment_blocks(pages: list[tuple[str, int, str]]) -> list[dict]:
    """Group lines into candidate scope blocks with page provenance."""
    blocks: list[dict] = []
    cur: dict | None = None
    section = ""
    for doc, page, text in pages:
        for raw in text.splitlines():
            line = raw.strip()
            if not line or PAGE_NOISE.match(line):
                continue
            if HEADING.match(line) and not line.endswith((".", ";")) and len(line.split()) <= 10:
                section = line
                cur = None
                continue
            starts = bool(ITEM_START.match(line))
            ends_prev = cur is not None and cur["text"].rstrip().endswith((".", ":", ";"))
            if cur is None or starts or (ends_prev and line[:1].isupper()) or cur["doc"] != doc or len(cur["text"]) > 700:
                cur = {"doc": doc, "page": page, "text": line, "section": section}
                blocks.append(cur)
            else:
                cur["text"] = f"{cur['text']} {line}"
    return blocks


def is_scope_text(text: str, section: str = "") -> bool:
    t = text.strip()
    if not 30 <= len(t) <= 900 or BOILERPLATE.search(t):
        return False
    return bool(WORK_VERBS.search(t)) or (bool(SCOPE_SECTION.search(section)) and bool(ITEM_START.match(t)))


def items_from_documents(pages: list[tuple[str, int, str]], min_conf: float = 0.35) -> tuple[list[dict], list[dict]]:
    blocks = [b for b in segment_blocks(pages) if is_scope_text(b["text"], b.get("section", ""))]
    seen, unique = set(), []
    for b in blocks:
        key = re.sub(r"\W+", " ", b["text"].lower())[:160]
        if key not in seen:
            seen.add(key)
            unique.append(b)
    preds = classify([ITEM_START.sub("", b["text"]) for b in unique])
    items, unassigned = [], []
    for b, (cap, conf, dist, hits) in zip(unique, preds):
        item = {"text": b["text"][:600], "document_id": b["doc"], "page": b["page"], "section": b.get("section") or None,
                "capability": cap,
                "confidence": round(conf, 3), "alternatives": dist, "keywords": sorted({k for v in hits.values() for k in v}),
                "amount_inr_cr": None if ESTIMATE.search(b["text"]) else parse_money_cr(b["text"]), "source": "document"}
        (items if cap != OTHER and conf >= min_conf else unassigned).append(item)
    return items, unassigned


BOQ_DESC = ("description", "item description", "description of item", "particulars", "item", "work description")
BOQ_AMOUNT = ("amount", "total amount", "amount (rs)", "amount in rs", "total", "value", "estimated amount")
BOQ_QTY = ("quantity", "qty")
BOQ_UNIT = ("unit", "units", "uom")
BOQ_RATE = ("rate", "unit rate", "rate (rs)", "estimated rate")


def _find_col(header: list[str], names: tuple[str, ...]) -> int | None:
    norm = [re.sub(r"[^a-z ()]", "", (h or "").lower()).strip() for h in header]
    for n in names:
        if n in norm:
            return norm.index(n)
    for i, h in enumerate(norm):
        if any(h.startswith(n) for n in names):
            return i
    return None


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def parse_boq(content: bytes, filename: str) -> list[dict]:
    """Rows of a BOQ (CSV or XLSX). Finds the header row by its 'description' column."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        table = [[c for c in r] for ws in wb.worksheets for r in ws.iter_rows(values_only=True)]
    elif filename.lower().endswith(".xls"):
        try:
            import xlrd  # CPPP BOQs are often legacy .xls
        except ImportError as exc:
            raise ValueError("Legacy .xls BOQ needs the 'xlrd' package - or save the sheet as .xlsx/.csv") from exc
        book = xlrd.open_workbook(file_contents=content)
        table = [sh.row_values(i) for sh in book.sheets() for i in range(sh.nrows)]
    else:
        table = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace"))))
    header_idx = next((i for i, r in enumerate(table[:60]) if _find_col([str(c or "") for c in r], BOQ_DESC) is not None), None)
    if header_idx is None:
        raise ValueError("Could not find a BOQ header row with a 'Description' column")
    header = [str(c or "") for c in table[header_idx]]
    d, a, q, u, r_ = (_find_col(header, BOQ_DESC), _find_col(header, BOQ_AMOUNT), _find_col(header, BOQ_QTY),
                      _find_col(header, BOQ_UNIT), _find_col(header, BOQ_RATE))
    rows = []
    for n, r in enumerate(table[header_idx + 1:], start=header_idx + 2):
        desc = str(r[d] or "").strip() if d is not None and d < len(r) else ""
        if len(desc) < 8:
            continue
        amount = _num(r[a]) if a is not None and a < len(r) else None
        qty = _num(r[q]) if q is not None and q < len(r) else None
        rate = _num(r[r_]) if r_ is not None and r_ < len(r) else None
        if amount is None and qty is not None and rate is not None:
            amount = qty * rate
        rows.append({"row": n, "description": desc, "quantity": qty, "unit": str(r[u]).strip() if u is not None and u < len(r) and r[u] else None,
                     "rate": rate, "amount_inr": amount})
    return rows


def items_from_boq(rows: list[dict], document_id: str) -> tuple[list[dict], list[dict]]:
    preds = classify([r["description"] for r in rows])
    items, unassigned = [], []
    for r, (cap, conf, dist, hits) in zip(rows, preds):
        item = {"text": r["description"][:600], "document_id": document_id, "page": None, "row": r["row"],
                "capability": cap, "confidence": round(conf, 3), "alternatives": dist,
                "keywords": sorted({k for v in hits.values() for k in v}),
                "amount_inr_cr": round(r["amount_inr"] / 1e7, 6) if r["amount_inr"] else None,
                "quantity": r["quantity"], "unit": r["unit"], "source": "boq"}
        (items if cap != OTHER else unassigned).append(item)
    return items, unassigned


def build_components(items: list[dict], estimate_cr: float | None, overrides: dict[str, float] | None = None) -> list[dict]:
    by_cap: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_cap[it["capability"]].append(it)
    comps = []
    for cap, its in sorted(by_cap.items(), key=lambda kv: -len(kv[1])):
        boq_vals = [i["amount_inr_cr"] for i in its if i["source"] == "boq" and i["amount_inr_cr"]]
        doc_vals = [i["amount_inr_cr"] for i in its if i["source"] == "document" and i["amount_inr_cr"]]
        if boq_vals:
            value, basis = sum(boq_vals), "boq"
        elif doc_vals:
            value, basis = sum(doc_vals), "document"
        else:
            value, basis = None, "unknown"
        comps.append({"capability": cap, "label": label(cap), "items": sorted(its, key=lambda i: -i["confidence"]),
                      "n_items": len(its), "value_inr_cr": round(value, 4) if value else None, "value_basis": basis,
                      "pages": sorted({i["page"] for i in its if i["page"]}),
                      "mean_confidence": round(sum(i["confidence"] for i in its) / len(its), 3)})
    # Allocate the remainder of the stated estimate across components without a value.
    known = sum(c["value_inr_cr"] or 0 for c in comps)
    missing = [c for c in comps if c["value_inr_cr"] is None]
    if estimate_cr and missing and estimate_cr > known:
        remainder = estimate_cr - known
        total_items = sum(c["n_items"] for c in missing)
        for c in missing:
            c["value_inr_cr"] = round(remainder * c["n_items"] / total_items, 4)
            c["value_basis"] = "assumed_item_share"
    for c in comps:
        if overrides and c["capability"] in overrides:
            c["value_inr_cr"], c["value_basis"] = float(overrides[c["capability"]]), "user_override"
    for i, c in enumerate(comps, start=1):
        c["component_id"] = f"C{i}"
    return comps
