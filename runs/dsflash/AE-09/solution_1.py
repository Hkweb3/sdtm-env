import pandas as pd
import numpy as np
import os

STUDYID = "TQR-448"

raw = pd.read_csv("input/raw_ae.csv", dtype=str)
dm = pd.read_csv("input/dm.csv", dtype=str)

# Keep highest VERSION per SUBJECT + RECID
raw["VERSION"] = pd.to_numeric(raw["VERSION"], errors="coerce")
raw = raw.sort_values("VERSION")
raw = raw.drop_duplicates(subset=["SUBJECT", "RECID"], keep="last")

# USUBJID
raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

# Build DTC from split date parts
def build_dtc(dd, mm, yyyy):
    dd = str(dd).strip() if pd.notna(dd) else ""
    mm = str(mm).strip() if pd.notna(mm) else ""
    yyyy = str(yyyy).strip() if pd.notna(yyyy) else ""
    if dd in ("", "nan"):
        dd = ""
    if mm in ("", "nan"):
        mm = ""
    if yyyy in ("", "nan"):
        yyyy = ""
    if yyyy == "":
        return ""
    if mm == "":
        return yyyy
    if dd == "":
        return f"{yyyy}-{int(mm):02d}"
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"

raw["AESTDTC"] = raw.apply(
    lambda r: build_dtc(r["AESTDAT_DD"], r["AESTDAT_MM"], r["AESTDAT_YYYY"]), axis=1
)
raw["AEENDTC"] = raw.apply(
    lambda r: build_dtc(r["AEENDAT_DD"], r["AEENDAT_MM"], r["AEENDAT_YYYY"]), axis=1
)

# Ongoing -> no end date
raw.loc[raw["AEONGO"].astype(str).str.strip().str.upper() == "Y", "AEENDTC"] = ""

# AETERM upper
raw["AETERM"] = raw["AE_VERBATIM"].astype(str).str.upper()

# Severity
sev_map = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
raw["AESEV"] = raw["SEVERITY"].astype(str).str.strip().map(sev_map)

# Serious
ser_map = {"1": "Y", "0": "N"}
raw["AESER"] = raw["SERIOUS"].astype(str).str.strip().map(ser_map)

# Relationship
rel_map = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}
raw["AEREL"] = raw["RELATIONSHIP"].astype(str).str.strip().map(rel_map)

# Outcome
raw["AEOUT"] = raw["OUTCOME"].astype(str).str.upper()

# Sort for AESEQ
raw = raw.sort_values(
    by=["USUBJID", "AESTDTC", "AETERM", "RECID"],
    kind="mergesort",
).reset_index(drop=True)
raw["AESEQ"] = raw.groupby("USUBJID").cumcount() + 1

# Study day
dm_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

def study_day(dtc, rfstdtc):
    if not dtc or not rfstdtc:
        return ""
    # only full dates
    if len(dtc) != 10 or len(rfstdtc) != 10:
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

raw["AESTDY"] = raw.apply(
    lambda r: study_day(r["AESTDTC"], dm_map.get(r["USUBJID"], "")), axis=1
)
raw["AEENDY"] = raw.apply(
    lambda r: study_day(r["AEENDTC"], dm_map.get(r["USUBJID"], "")), axis=1
)

out = pd.DataFrame({
    "STUDYID": STUDYID,
    "DOMAIN": "AE",
    "USUBJID": raw["USUBJID"],
    "AESEQ": raw["AESEQ"],
    "AESPID": raw["RECID"],
    "AETERM": raw["AETERM"],
    "AEDECOD": raw["CODED_PT"],
    "AEBODSYS": raw["CODED_SOC"],
    "AESEV": raw["AESEV"],
    "AESER": raw["AESER"],
    "AEREL": raw["AEREL"],
    "AEOUT": raw["AEOUT"],
    "AESTDTC": raw["AESTDTC"],
    "AEENDTC": raw["AEENDTC"],
    "AESTDY": raw["AESTDY"],
    "AEENDY": raw["AEENDY"],
})

os.makedirs("output", exist_ok=True)
out.to_csv("output/ae.csv", index=False)
