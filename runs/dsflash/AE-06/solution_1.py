import pandas as pd
import os
import re

os.makedirs("output", exist_ok=True)

dm = pd.read_csv("input/dm.csv")
raw = pd.read_csv("input/raw_ae.csv")

# Keep highest VERSION per SUBJECT + RECID
raw["VERSION"] = pd.to_numeric(raw["VERSION"], errors="coerce")
raw = raw.sort_values("VERSION").drop_duplicates(subset=["SUBJECT", "RECID"], keep="last")

# Build USUBJID
def make_usubjid(subject):
    parts = str(subject).split("-")
    return "PLX-650-" + parts[0] + "-" + parts[1]

raw["USUBJID"] = raw["SUBJECT"].apply(make_usubjid)

# Validate against DM
valid_ids = set(dm["USUBJID"])
raw = raw[raw["USUBJID"].isin(valid_ids)].copy()

# Date parsing
MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
}

def parse_dtc(val):
    if pd.isna(val) or str(val).strip() == "":
        return None
    s = str(val).strip().upper()
    m = re.match(r"^(\w{2})(\w{3})(\d{4})$", s)
    if not m:
        return None
    day, mon, year = m.group(1), m.group(2), m.group(3)
    if mon == "UNK":
        return year
    mon_num = MONTHS.get(mon)
    if mon_num is None:
        return year
    if day == "UN":
        return f"{year}-{mon_num}"
    return f"{year}-{mon_num}-{day}"

raw["AESTDTC"] = raw["AESTDAT"].apply(parse_dtc)
raw["AEENDTC"] = raw["AEENDAT"].apply(parse_dtc)

# Ongoing events have no end date
raw.loc[raw["AEONGO"].astype(str).str.upper() == "Y", "AEENDTC"] = None

# Study day
rfstdtc_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

def to_date(dtc):
    if dtc is None:
        return None
    parts = dtc.split("-")
    if len(parts) != 3:
        return None
    try:
        return pd.Timestamp(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return None

def study_day(dtc, usubjid):
    d = to_date(dtc)
    if d is None:
        return None
    rf = rfstdtc_map.get(usubjid)
    if rf is None or pd.isna(rf):
        return None
    rf_date = to_date(str(rf))
    if rf_date is None:
        return None
    if d >= rf_date:
        return (d - rf_date).days + 1
    else:
        return (d - rf_date).days

raw["AESTDY"] = raw.apply(lambda r: study_day(r["AESTDTC"], r["USUBJID"]), axis=1)
raw["AEENDY"] = raw.apply(lambda r: study_day(r["AEENDTC"], r["USUBJID"]), axis=1)

# Mappings
sev_map = {"mild": "MILD", "moderate": "MODERATE", "severe": "SEVERE"}
raw["AESEV"] = raw["SEVERITY"].astype(str).str.strip().str.lower().map(sev_map)

ser_map = {"yes": "Y", "no": "N"}
raw["AESER"] = raw["SERIOUS"].astype(str).str.strip().str.lower().map(ser_map)

rel_map = {
    "not related": "NONE",
    "unlikely related": "REMOTE",
    "possibly related": "POSSIBLE",
    "probably related": "PROBABLE",
}
raw["AEREL"] = raw["RELATIONSHIP"].astype(str).str.strip().str.lower().map(rel_map)

raw["AEOUT"] = raw["OUTCOME"].astype(str).str.upper()

raw["AETERM"] = raw["AE_VERBATIM"].astype(str).str.upper()
raw["AEDECOD"] = raw["CODED_PT"]
raw["AEBODSYS"] = raw["CODED_SOC"]
raw["AESPID"] = raw["RECID"]
raw["STUDYID"] = "PLX-650"
raw["DOMAIN"] = "AE"

# Sort and sequence
raw = raw.sort_values(
    by=["USUBJID", "AESTDTC", "AETERM", "AESPID"],
    key=lambda col: col.fillna("") if col.name == "AESTDTC" else col,
    na_position="last"
)
raw["AESEQ"] = raw.groupby("USUBJID").cumcount() + 1

out_cols = [
    "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM", "AEDECOD",
    "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT", "AESTDTC", "AEENDTC",
    "AESTDY", "AEENDY"
]

out = raw[out_cols].copy()

# Format study days as integers where present
for c in ["AESTDY", "AEENDY"]:
    out[c] = out[c].apply(lambda x: "" if x is None or pd.isna(x) else int(x))

out.to_csv("output/ae.csv", index=False)
