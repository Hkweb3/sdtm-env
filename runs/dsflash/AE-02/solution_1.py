import pandas as pd
import os
import re

STUDYID = "ALX-878"

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_ae.csv", dtype=str)

# Build USUBJID from raw SUBJECT
def make_usubjid(subj):
    parts = subj.split("-")
    return f"{STUDYID}-{parts[0]}-{parts[1]}"

raw["USUBJID"] = raw["SUBJECT"].apply(make_usubjid)

# RFSTDTC lookup
rf_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

def parse_dtc(raw_date):
    """Return (iso_string, is_full) where is_full means YYYY-MM-DD."""
    if raw_date is None or pd.isna(raw_date):
        return "", False
    s = str(raw_date).strip()
    if s == "":
        return "", False
    m = re.match(r"^(\d{2}|UN)([A-Z]{3}|UNK)(\d{4})$", s)
    if not m:
        return "", False
    day, mon, year = m.group(1), m.group(2), m.group(3)
    if mon == "UNK":
        # year only
        return year, False
    mon_num = MONTHS.get(mon)
    if mon_num is None:
        return year, False
    if day == "UN":
        return f"{year}-{mon_num}", False
    return f"{year}-{mon_num}-{day}", True

def to_date(iso):
    if not iso:
        return None
    try:
        return pd.to_datetime(iso, format="%Y-%m-%d")
    except Exception:
        return None

def study_day(iso, is_full, rfstdtc):
    if not is_full or not iso or not rfstdtc:
        return ""
    d = to_date(iso)
    rf = to_date(rfstdtc)
    if d is None or rf is None:
        return ""
    diff = (d - rf).days
    if d >= rf:
        return str(diff + 1)
    else:
        return str(diff)

def map_severity(v):
    if v is None or pd.isna(v):
        return ""
    return str(v).strip().upper()

def map_serious(v):
    if v is None or pd.isna(v):
        return ""
    s = str(v).strip().lower()
    if s == "yes":
        return "Y"
    if s == "no":
        return "N"
    return ""

REL_MAP = {
    "not related": "NONE",
    "unlikely related": "REMOTE",
    "possibly related": "POSSIBLE",
    "probably related": "PROBABLE",
}

def map_rel(v):
    if v is None or pd.isna(v):
        return ""
    return REL_MAP.get(str(v).strip().lower(), "")

def upper(v):
    if v is None or pd.isna(v):
        return ""
    return str(v).strip().upper()

rows = []
for _, r in raw.iterrows():
    usubjid = r["USUBJID"]
    rfstdtc = rf_map.get(usubjid, "")

    aeterm = upper(r.get("AE_VERBATIM"))
    aedecod = r.get("CODED_PT")
    aebodsys = r.get("CODED_SOC")
    aedecod = "" if pd.isna(aedecod) else str(aedecod)
    aebodsys = "" if pd.isna(aebodsys) else str(aebodsys)

    aesev = map_severity(r.get("SEVERITY"))
    aeser = map_serious(r.get("SERIOUS"))
    aerel = map_rel(r.get("RELATIONSHIP"))
    aeout = upper(r.get("OUTCOME"))

    aeon = str(r.get("AEONGO", "")).strip().upper() if not pd.isna(r.get("AEONGO")) else ""

    start_iso, start_full = parse_dtc(r.get("AESTDAT"))
    end_raw = r.get("AEENDAT")
    if aeon == "Y":
        end_iso, end_full = "", False
    else:
        end_iso, end_full = parse_dtc(end_raw)

    aestdy = study_day(start_iso, start_full, rfstdtc)
    aeendy = study_day(end_iso, end_full, rfstdtc)

    rows.append({
        "STUDYID": STUDYID,
        "DOMAIN": "AE",
        "USUBJID": usubjid,
        "AESPID": r.get("RECID", ""),
        "AETERM": aeterm,
        "AEDECOD": aedecod,
        "AEBODSYS": aebodsys,
        "AESEV": aesev,
        "AESER": aeser,
        "AEREL": aerel,
        "AEOUT": aeout,
        "AESTDTC": start_iso,
        "AEENDTC": end_iso,
        "AESTDY": aestdy,
        "AEENDY": aeendy,
    })

ae = pd.DataFrame(rows)

# Sort by USUBJID, AESTDTC (text), AETERM, AESPID
ae = ae.sort_values(
    by=["USUBJID", "AESTDTC", "AETERM", "AESPID"],
    kind="mergesort"
).reset_index(drop=True)

# AESEQ per subject
ae["AESEQ"] = ae.groupby("USUBJID").cumcount() + 1

# Column order
cols = [
    "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
    "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
    "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
]
ae = ae[cols]

os.makedirs("output", exist_ok=True)
ae.to_csv("output/ae.csv", index=False)
