import pandas as pd
import numpy as np
import os
import re

STUDYID = "ALX-919"

# Read inputs
dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_ae.csv", dtype=str)

# Build DM lookup: USUBJID -> RFSTDTC
dm["USUBJID"] = dm["USUBJID"].str.strip()
rfstdtc_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

# Filter raw
raw = raw[raw["RECORD_STATUS"].str.strip().str.upper() != "DELETED"].copy()
raw = raw[raw["AEYN"].fillna("").str.strip().str.upper() != "NO"].copy()

# Keep highest VERSION per SUBJECT + RECID
raw["VERSION_NUM"] = pd.to_numeric(raw["VERSION"], errors="coerce")
raw = raw.sort_values(["SUBJECT", "RECID", "VERSION_NUM"])
raw = raw.drop_duplicates(subset=["SUBJECT", "RECID"], keep="last").copy()

# Build USUBJID
def make_usubjid(subj):
    subj = str(subj).strip()
    parts = subj.split("-")
    if len(parts) >= 2:
        site = parts[0]
        subject = parts[1]
        return f"{STUDYID}-{site}-{subject}"
    return None

raw["USUBJID"] = raw["SUBJECT"].apply(make_usubjid)

# Keep only subjects present in DM
raw = raw[raw["USUBJID"].isin(rfstdtc_map.keys())].copy()

# Date parsing
MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
}

def parse_date(d):
    if d is None or (isinstance(d, float) and np.isnan(d)):
        return None, None
    s = str(d).strip().upper()
    if s == "" or s == "NAN":
        return None, None
    m = re.fullmatch(r"(\w{2})(\w{3})(\d{4})", s)
    if not m:
        return None, None
    day, mon, year = m.group(1), m.group(2), m.group(3)
    day_known = day != "UN"
    mon_known = mon != "UNK"
    if not mon_known:
        # month unknown -> only year
        return year, False
    mm = MONTHS.get(mon)
    if mm is None:
        return year, False
    if not day_known:
        return f"{year}-{mm}", False
    return f"{year}-{mm}-{day}", True

def to_iso(d):
    iso, complete = parse_date(d)
    return iso if iso else ""

raw["AESTDTC"] = raw["AESTDAT"].apply(to_iso)
raw["AEENDTC"] = raw["AEENDAT"].apply(to_iso)

# Ongoing -> no end date
ongoing = raw["AEONGO"].fillna("").str.strip().str.upper() == "Y"
raw.loc[ongoing, "AEENDTC"] = ""

# Severity
sev_map = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
raw["AESEV"] = raw["SEVERITY"].astype(str).str.strip().map(sev_map).fillna("")

# Serious
ser_map = {"YES": "Y", "NO": "N"}
raw["AESER"] = raw["SERIOUS"].astype(str).str.strip().str.upper().map(ser_map).fillna("")

# Relationship
rel_map = {
    "NOT RELATED": "NONE",
    "UNLIKELY RELATED": "REMOTE",
    "POSSIBLY RELATED": "POSSIBLE",
    "PROBABLY RELATED": "PROBABLE",
}
raw["AEREL"] = raw["RELATIONSHIP"].astype(str).str.strip().str.upper().map(rel_map).fillna("")

# Outcome
raw["AEOUT"] = raw["OUTCOME"].astype(str).str.strip().str.upper().replace({"NAN": ""})

# AETERM upper
raw["AETERM"] = raw["AE_VERBATIM"].astype(str).str.strip().str.upper()

# AEDECOD, AEBODSYS
raw["AEDECOD"] = raw["CODED_PT"].astype(str).str.strip().replace({"NAN": ""})
raw["AEBODSYS"] = raw["CODED_SOC"].astype(str).str.strip().replace({"NAN": ""})

# AESPID
raw["AESPID"] = raw["RECID"].astype(str).str.strip()

# Sort for AESEQ
raw = raw.sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort").reset_index(drop=True)
raw["AESEQ"] = raw.groupby("USUBJID").cumcount() + 1

# Study day calculation
def study_day(dtc, rfstdtc):
    if not dtc or not rfstdtc:
        return ""
    # both must be complete dates YYYY-MM-DD
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dtc):
        return ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", rfstdtc):
        return ""
    try:
        d = pd.Timestamp(dtc)
        r = pd.Timestamp(rfstdtc)
    except Exception:
        return ""
    delta = (d - r).days
    if delta >= 0:
        return delta + 1
    else:
        return delta

raw["AESTDY"] = raw.apply(lambda r: study_day(r["AESTDTC"], rfstdtc_map.get(r["USUBJID"], "")), axis=1)
raw["AEENDY"] = raw.apply(lambda r: study_day(r["AEENDTC"], rfstdtc_map.get(r["USUBJID"], "")), axis=1)

# Build output
out = pd.DataFrame({
    "STUDYID": STUDYID,
    "DOMAIN": "AE",
    "USUBJID": raw["USUBJID"],
    "AESEQ": raw["AESEQ"],
    "AESPID": raw["AESPID"],
    "AETERM": raw["AETERM"],
    "AEDECOD": raw["AEDECOD"],
    "AEBODSYS": raw["AEBODSYS"],
    "AESEV": raw["AESEV"],
    "AESER": raw["AESER"],
    "AEREL": raw["AEREL"],
    "AEOUT": raw["AEOUT"],
    "AESTDTC": raw["AESTDTC"],
    "AEENDTC": raw["AEENDTC"],
    "AESTDY": raw["AESTDY"],
    "AEENDY": raw["AEENDY"],
})

# Ensure output dir
os.makedirs("output", exist_ok=True)

# Write CSV
out.to_csv("output/ae.csv", index=False)
