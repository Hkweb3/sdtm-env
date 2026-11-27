import os
import re
from datetime import date

import pandas as pd

STUDYID = "MRN-326"
OUT_COLS = [
    "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM", "AEDECOD",
    "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT", "AESTDTC", "AEENDTC",
    "AESTDY", "AEENDY",
]

SEV_MAP = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
SER_MAP = {"yes": "Y", "no": "N"}
REL_MAP = {
    "not related": "NONE",
    "unlikely related": "REMOTE",
    "possibly related": "POSSIBLE",
    "probably related": "PROBABLE",
}


def clean(val):
    if val is None:
        return ""
    s = str(val).strip()
    if s == "" or s.lower() in ("na", "n/a", "null", "none", "nan", "."):
        return ""
    return s


def to_iso(raw):
    """Convert raw date (MM/DD/YYYY, MM/YYYY, or YYYY) to ISO 8601 (partial allowed)."""
    s = clean(raw)
    if not s:
        return ""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        mm, dd, yy = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            return f"{yy}-{mm:02d}-{dd:02d}"
        return ""
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        mm, yy = int(m.group(1)), m.group(2)
        if 1 <= mm <= 12:
            return f"{yy}-{mm:02d}"
        return ""
    if re.fullmatch(r"\d{4}", s):
        return s
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) or re.fullmatch(r"\d{4}-\d{2}", s):
        return s
    return ""


def parse_full_iso(s):
    """Parse a complete YYYY-MM-DD date; return None for partial/missing."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def study_day(ae_iso, rfst_iso):
    """SDTM --DY: date - RFSTDTC + 1 if on/after RFSTDTC, else date - RFSTDTC."""
    d_ae = parse_full_iso(ae_iso)
    d_rf = parse_full_iso(rfst_iso)
    if d_ae is None or d_rf is None:
        return ""
    delta = (d_ae - d_rf).days
    return str(delta + 1 if delta >= 0 else delta)


# --- Read inputs -------------------------------------------------------------
dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)
rfst_by_usubjid = {
    clean(u): clean(r) for u, r in zip(dm["USUBJID"], dm["RFSTDTC"])
}

ae_raw = pd.read_csv("input/raw_ae.csv", dtype=str, keep_default_na=False)

# --- Map records -------------------------------------------------------------
records = []
for _, row in ae_raw.iterrows():
    subject = clean(row.get("SUBJECT"))
    usubjid = f"{STUDYID}-{subject}" if subject else ""

    ongoing = clean(row.get("AEONGO")).upper() == "Y"
    astdtc = to_iso(row.get("AESTDAT"))
    aendtc = "" if ongoing else to_iso(row.get("AEENDAT"))

    rfstdtc = rfst_by_usubjid.get(usubjid, "")

    sev_raw = clean(row.get("SEVERITY"))
    ser_raw = clean(row.get("SERIOUS")).lower()
    rel_raw = clean(row.get("RELATIONSHIP")).lower()

    records.append({
        "STUDYID": STUDYID,
        "DOMAIN": "AE",
        "USUBJID": usubjid,
        "AESEQ": 0,
        "AESPID": clean(row.get("RECID")),
        "AETERM": clean(row.get("AE_VERBATIM")).upper(),
        "AEDECOD": clean(row.get("CODED_PT")),
        "AEBODSYS": clean(row.get("CODED_SOC")),
        "AESEV": SEV_MAP.get(sev_raw, ""),
        "AESER": SER_MAP.get(ser_raw, ""),
        "AEREL": REL_MAP.get(rel_raw, ""),
        "AEOUT": clean(row.get("OUTCOME")).upper(),
        "AESTDTC": astdtc,
        "AEENDTC": aendtc,
        "AESTDY": study_day(astdtc, rfstdtc),
        "AEENDY": study_day(aendtc, rfstdtc),
    })

ae = pd.DataFrame(records)

# --- AESEQ: sort within subject by AESTDTC (text), AETERM, AESPID ------------
ae = ae.sort_values(
    by=["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort"
).reset_index(drop=True)
ae["AESEQ"] = ae.groupby("USUBJID").cumcount() + 1

# Final deterministic row order: by subject, then sequence number
ae = ae.sort_values(by=["USUBJID", "AESEQ"], kind="mergesort").reset_index(drop=True)
ae = ae[OUT_COLS]

# --- Write output ------------------------------------------------------------
os.makedirs("output", exist_ok=True)
ae.to_csv("output/ae.csv", index=False)
