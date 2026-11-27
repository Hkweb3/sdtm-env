import pandas as pd
import os
import re

STUDYID = "KVT-131"

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_mh.csv", dtype=str)

# Build USUBJID from raw SUBJECT
raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

# Keep only subjects present in DM
dm_usubjids = set(dm["USUBJID"])
raw = raw[raw["USUBJID"].isin(dm_usubjids)].copy()

# Map category
cat_map = {
    "PD": "PRIMARY DIAGNOSIS",
    "SPC": "SIGNIFICANT PRE-EXISTING CONDITION",
    "HD": "HISTORICAL DIAGNOSIS",
}
raw["MHCAT"] = raw["CATEGORY"].map(cat_map)

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

def parse_dtc(val):
    """Convert DDMONYYYY / UNMONYYYY / UNUNKYYYY to ISO 8601 partial date."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    val = str(val).strip()
    if val == "" or val.lower() in ("nan", "na", "null", "."):
        return ""
    m = re.fullmatch(r"([A-Z0-9]{2})([A-Z]{3})(\d{4})", val)
    if not m:
        return ""
    day, mon, year = m.group(1), m.group(2), m.group(3)
    mon_num = MONTHS.get(mon)
    if mon_num is None:
        return ""
    if day == "UN":
        return f"{year}-{mon_num}"
    return f"{year}-{mon_num}-{day}"

def parse_full_date(val):
    """Parse a full ISO date (YYYY-MM-DD) to a date, or None if partial/missing."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    val = str(val).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
        return None
    return pd.Timestamp(val).date()

raw["MHSTDTC"] = raw["MHSTDAT"].apply(parse_dtc)
raw["MHDTC"] = raw["VISIT_DATE"].apply(parse_dtc)

# RFSTDTC lookup
rf_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

def study_day(mhdtc, usubjid):
    d = parse_full_date(mhdtc)
    if d is None:
        return ""
    rf = rf_map.get(usubjid)
    rf_date = parse_full_date(rf)
    if rf_date is None:
        return ""
    delta = (d - rf_date).days
    if delta >= 0:
        return delta + 1
    return delta

raw["MHDY"] = raw.apply(lambda r: study_day(r["MHDTC"], r["USUBJID"]), axis=1)

# Sort and assign MHSEQ
raw = raw.sort_values(
    by=["USUBJID", "MHCAT", "MHSTDTC", "MH_VERBATIM", "RECID"],
    kind="mergesort",
).reset_index(drop=True)

raw["MHSEQ"] = raw.groupby("USUBJID").cumcount() + 1

out = pd.DataFrame({
    "STUDYID": STUDYID,
    "DOMAIN": "MH",
    "USUBJID": raw["USUBJID"],
    "MHSEQ": raw["MHSEQ"],
    "MHSPID": raw["RECID"],
    "MHTERM": raw["MH_VERBATIM"],
    "MHDECOD": raw["CODED_PT"],
    "MHCAT": raw["MHCAT"],
    "MHBODSYS": raw["CODED_SOC"],
    "MHDTC": raw["MHDTC"],
    "MHSTDTC": raw["MHSTDTC"],
    "MHDY": raw["MHDY"],
})

# Clean empty strings -> keep as empty (pandas writes empty for NaN, but we have "")
out = out.fillna("")

os.makedirs("output", exist_ok=True)
out.to_csv("output/mh.csv", index=False)
