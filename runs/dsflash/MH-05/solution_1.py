import pandas as pd
import numpy as np
import os

STUDYID = "ALX-345"

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_mh.csv", dtype=str)

# Drop deleted
raw = raw[raw["RECORD_STATUS"] != "DELETED"].copy()

# Build USUBJID
raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

# Validate against DM
valid_ids = set(dm["USUBJID"])
raw = raw[raw["USUBJID"].isin(valid_ids)].copy()

# RFSTDTC lookup
rf_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

# Category mapping
cat_map = {
    "PD": "PRIMARY DIAGNOSIS",
    "SPC": "SIGNIFICANT PRE-EXISTING CONDITION",
    "HD": "HISTORICAL DIAGNOSIS",
}

def build_stdtc(row):
    y = row.get("MHSTDAT_YYYY")
    m = row.get("MHSTDAT_MM")
    d = row.get("MHSTDAT_DD")
    def blank(v):
        return v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "" or str(v).lower() == "nan"
    if blank(y):
        return ""
    y = str(int(float(y)))
    if blank(m):
        return y
    m = str(int(float(m))).zfill(2)
    if blank(d):
        return f"{y}-{m}"
    d = str(int(float(d))).zfill(2)
    return f"{y}-{m}-{d}"

def build_dtc(visit):
    if visit is None or (isinstance(visit, float) and np.isnan(visit)):
        return ""
    parts = str(visit).strip().split()
    if len(parts) != 3:
        return ""
    dd, mon, yyyy = parts
    months = {"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06",
              "JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12"}
    # year
    if yyyy.upper() == "UNK" or yyyy == "":
        return ""
    y = yyyy
    # month
    if mon.upper() == "UNK":
        return y
    mm = months.get(mon.upper())
    if mm is None:
        return y
    # day
    if dd.upper() == "UN":
        return f"{y}-{mm}"
    try:
        d = str(int(dd)).zfill(2)
    except ValueError:
        return f"{y}-{mm}"
    return f"{y}-{mm}-{d}"

def study_day(dtc, rfstdtc):
    if not dtc or not rfstdtc:
        return ""
    # both must be full dates
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ""
    try:
        d = pd.Timestamp(dtc)
        r = pd.Timestamp(rfstdtc)
    except Exception:
        return ""
    delta = (d - r).days
    if delta >= 0:
        return str(delta + 1)
    else:
        return str(delta)

rows = []
for _, r in raw.iterrows():
    usubjid = r["USUBJID"]
    rf = rf_map.get(usubjid, "")
    mhstdtc = build_stdtc(r)
    mhdtc = build_dtc(r["VISIT_DATE"])
    mhdy = study_day(mhdtc, rf)
    cat_code = r.get("CATEGORY", "")
    mhcat = cat_map.get(cat_code, "")
    rows.append({
        "STUDYID": STUDYID,
        "DOMAIN": "MH",
        "USUBJID": usubjid,
        "MHSPID": r["RECID"],
        "MHTERM": r["MH_VERBATIM"],
        "MHDECOD": r.get("CODED_PT", "") if pd.notna(r.get("CODED_PT")) else "",
        "MHCAT": mhcat,
        "MHBODSYS": r.get("CODED_SOC", "") if pd.notna(r.get("CODED_SOC")) else "",
        "MHDTC": mhdtc,
        "MHSTDTC": mhstdtc,
        "MHDY": mhdy,
    })

out = pd.DataFrame(rows)

# Clean NaN to empty
out = out.fillna("")

# Sort for MHSEQ
out = out.sort_values(
    by=["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
    kind="mergesort"
).reset_index(drop=True)

out["MHSEQ"] = out.groupby("USUBJID").cumcount() + 1

# Final column order
cols = ["STUDYID","DOMAIN","USUBJID","MHSEQ","MHSPID","MHTERM","MHDECOD",
        "MHCAT","MHBODSYS","MHDTC","MHSTDTC","MHDY"]
out = out[cols]

os.makedirs("output", exist_ok=True)
out.to_csv("output/mh.csv", index=False)
