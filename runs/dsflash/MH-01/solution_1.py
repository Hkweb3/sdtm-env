import pandas as pd
import numpy as np
import os

STUDYID = "DRX-647"

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_mh.csv", dtype=str)

# Build USUBJID from raw SUBJECT
raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

# Validate against DM
valid_ids = set(dm["USUBJID"])
raw = raw[raw["USUBJID"].isin(valid_ids)].copy()

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

def to_iso(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    s = str(val).strip()
    if s == "" or s.upper() in ("NA", "NULL", "."):
        return ""
    parts = s.split()
    if len(parts) != 3:
        return ""
    d, m, y = parts[0].upper(), parts[1].upper(), parts[2]
    if not y.isdigit():
        return ""
    if m == "UNK":
        return y
    mm = MONTHS.get(m)
    if mm is None:
        return ""
    if d == "UN":
        return f"{y}-{mm}"
    if d.isdigit():
        return f"{y}-{mm}-{int(d):02d}"
    return ""

def parse_full_date(val):
    """Return a datetime.date only if fully specified, else None."""
    iso = to_iso(val)
    if len(iso) == 10:
        try:
            return pd.Timestamp(iso).date()
        except Exception:
            return None
    return None

raw["MHSTDTC"] = raw["MHSTDAT"].apply(to_iso)
raw["MHDTC"] = raw["VISIT_DATE"].apply(to_iso)

# RFSTDTC lookup
rf_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

def study_day(usubjid, dtc):
    if not dtc or len(dtc) != 10:
        return ""
    rf = rf_map.get(usubjid)
    if not rf or len(rf) != 10:
        return ""
    try:
        d = pd.Timestamp(dtc).date()
        r = pd.Timestamp(rf).date()
    except Exception:
        return ""
    if d >= r:
        return str((d - r).days + 1)
    else:
        return str((d - r).days)

raw["MHDY"] = [study_day(u, d) for u, d in zip(raw["USUBJID"], raw["MHDTC"])]

out = pd.DataFrame()
out["STUDYID"] = STUDYID
out["DOMAIN"] = "MH"
out["USUBJID"] = raw["USUBJID"]
out["MHSPID"] = raw["RECID"]
out["MHTERM"] = raw["MH_VERBATIM"]
out["MHDECOD"] = raw["CODED_PT"].fillna("")
out["MHCAT"] = raw["CATEGORY"].fillna("").str.upper()
out["MHBODSYS"] = raw["CODED_SOC"].fillna("")
out["MHDTC"] = raw["MHDTC"]
out["MHSTDTC"] = raw["MHSTDTC"]
out["MHDY"] = raw["MHDY"]

# Sort for MHSEQ
out = out.sort_values(
    by=["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
    kind="mergesort"
).reset_index(drop=True)

out["MHSEQ"] = out.groupby("USUBJID").cumcount() + 1

out = out[[
    "STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM",
    "MHDECOD", "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY"
]]

# Clean empty strings
for c in out.columns:
    out[c] = out[c].fillna("").astype(str)

os.makedirs("output", exist_ok=True)
out.to_csv("output/mh.csv", index=False)
