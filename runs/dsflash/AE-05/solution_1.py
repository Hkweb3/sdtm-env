import pandas as pd
import os

STUDYID = "BRV-836"

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_ae.csv", dtype=str)

# Build USUBJID lookup from DM
dm["USUBJID"] = dm["USUBJID"].str.strip()

# Filter raw
raw = raw[raw["RECORD_STATUS"].str.strip().str.upper() != "DELETED"].copy()
raw = raw[~raw["AEYN"].fillna("").str.strip().str.upper().eq("NO")].copy()

# Build USUBJID
raw["SUBJECT"] = raw["SUBJECT"].str.strip()
parts = raw["SUBJECT"].str.split("-", n=1, expand=True)
raw["SITE"] = parts[0]
raw["SUBJ"] = parts[1]
raw["USUBJID"] = STUDYID + "-" + raw["SITE"] + "-" + raw["SUBJ"]

# Validate against DM
valid_ids = set(dm["USUBJID"])
raw = raw[raw["USUBJID"].isin(valid_ids)].copy()

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
}

def parse_date(s):
    """Return (iso_string, is_complete) or (None, False) if missing."""
    if s is None:
        return None, False
    s = str(s).strip()
    if s == "" or s.upper() == "NAN":
        return None, False
    parts = s.split()
    if len(parts) != 3:
        return None, False
    d, m, y = parts[0].upper(), parts[1].upper(), parts[2]
    if not y.isdigit():
        return None, False
    if m == "UNK":
        return y, False
    if m not in MONTHS:
        return None, False
    mm = MONTHS[m]
    if d == "UN":
        return f"{y}-{mm}", False
    if not d.isdigit():
        return None, False
    return f"{y}-{mm}-{d.zfill(2)}", True

def to_iso(s):
    iso, _ = parse_date(s)
    return iso if iso else ""

def to_date(s):
    iso, complete = parse_date(s)
    if not complete:
        return None
    return pd.Timestamp(iso)

# RFSTDTC lookup
rf_map = {}
for _, row in dm.iterrows():
    rf = row["RFSTDTC"]
    if pd.notna(rf) and str(rf).strip():
        try:
            rf_map[row["USUBJID"]] = pd.Timestamp(str(rf).strip())
        except Exception:
            pass

def study_day(dtc_str, usubjid):
    d = to_date(dtc_str)
    if d is None:
        return ""
    rf = rf_map.get(usubjid)
    if rf is None:
        return ""
    diff = (d - rf).days
    if diff >= 0:
        return str(diff + 1)
    else:
        return str(diff)

# Map columns
raw["AESPID"] = raw["RECID"].fillna("").str.strip()
raw["AETERM"] = raw["AE_VERBATIM"].fillna("").str.strip().str.upper()
raw["AEDECOD"] = raw["CODED_PT"].fillna("").str.strip()
raw["AEBODSYS"] = raw["CODED_SOC"].fillna("").str.strip()

raw["AESEV"] = raw["SEVERITY"].fillna("").str.strip().str.upper()

def map_serious(v):
    v = str(v).strip().upper()
    if v == "YES":
        return "Y"
    if v == "NO":
        return "N"
    return ""

raw["AESER"] = raw["SERIOUS"].apply(map_serious)

REL_MAP = {
    "NOT RELATED": "NONE",
    "UNLIKELY RELATED": "REMOTE",
    "POSSIBLY RELATED": "POSSIBLE",
    "PROBABLY RELATED": "PROBABLE",
}
def map_rel(v):
    return REL_MAP.get(str(v).strip().upper(), "")

raw["AEREL"] = raw["RELATIONSHIP"].apply(map_rel)
raw["AEOUT"] = raw["OUTCOME"].fillna("").str.strip().str.upper()

raw["AESTDTC"] = raw["AESTDAT"].apply(to_iso)

def end_dtc(row):
    ongo = str(row.get("AEONGO", "")).strip().upper()
    if ongo == "Y":
        return ""
    return to_iso(row.get("AEENDAT"))

raw["AEENDTC"] = raw.apply(end_dtc, axis=1)

raw["AESTDY"] = raw.apply(lambda r: study_day(r["AESTDAT"], r["USUBJID"]), axis=1)
raw["AEENDY"] = raw.apply(
    lambda r: "" if str(r.get("AEONGO", "")).strip().upper() == "Y"
    else study_day(r.get("AEENDAT"), r["USUBJID"]),
    axis=1
)

# Sort for AESEQ
raw = raw.sort_values(
    by=["USUBJID", "AESTDTC", "AETERM", "AESPID"],
    kind="mergesort"
).reset_index(drop=True)

raw["AESEQ"] = raw.groupby("USUBJID").cumcount() + 1
raw["AESEQ"] = raw["AESEQ"].astype(str)

raw["STUDYID"] = STUDYID
raw["DOMAIN"] = "AE"

out_cols = [
    "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
    "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
    "AESTDTC", "AEENDTC", "AESTDY", "AEENDY"
]

out = raw[out_cols].copy()
for c in out.columns:
    out[c] = out[c].fillna("").astype(str)

os.makedirs("output", exist_ok=True)
out.to_csv("output/ae.csv", index=False)
