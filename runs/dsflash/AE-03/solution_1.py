import pandas as pd
import os

STUDYID = "PLX-326"

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_ae.csv", dtype=str)

# Build USUBJID from SUBJECT
raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

# RFSTDTC lookup
rf_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

def make_dtc(dd, mm, yyyy):
    if pd.isna(yyyy) or str(yyyy).strip() == "":
        return ""
    y = str(int(float(yyyy)))
    if pd.isna(mm) or str(mm).strip() == "":
        return y
    m = str(int(float(mm))).zfill(2)
    if pd.isna(dd) or str(dd).strip() == "":
        return f"{y}-{m}"
    d = str(int(float(dd))).zfill(2)
    return f"{y}-{m}-{d}"

def study_day(dtc, rfstdtc):
    if not dtc or not rfstdtc:
        return ""
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ""
    d = pd.Timestamp(dtc)
    r = pd.Timestamp(rfstdtc)
    diff = (d - r).days
    if d >= r:
        return str(diff + 1)
    else:
        return str(diff)

sev_map = {
    "mild": "MILD",
    "moderate": "MODERATE",
    "severe": "SEVERE",
}

rel_map = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}

rows = []
for _, r in raw.iterrows():
    usubjid = r["USUBJID"]
    rfstdtc = rf_map.get(usubjid, "")

    aestdtc = make_dtc(r.get("AESTDAT_DD"), r.get("AESTDAT_MM"), r.get("AESTDAT_YYYY"))
    aeendtc = make_dtc(r.get("AEENDAT_DD"), r.get("AEENDAT_MM"), r.get("AEENDAT_YYYY"))

    ongo = str(r.get("AEONGO", "")).strip().upper()
    if ongo == "Y":
        aeendtc = ""

    aestdy = study_day(aestdtc, rfstdtc)
    aeendy = study_day(aeendtc, rfstdtc)

    sev = str(r.get("SEVERITY", "")).strip()
    sev_out = sev_map.get(sev.lower(), sev.upper())

    ser = str(r.get("SERIOUS", "")).strip()
    if ser == "Yes":
        aeser = "Y"
    elif ser == "No":
        aeser = "N"
    else:
        aeser = ""

    rel = str(r.get("RELATIONSHIP", "")).strip()
    aerel = rel_map.get(rel, "")

    rows.append({
        "STUDYID": STUDYID,
        "DOMAIN": "AE",
        "USUBJID": usubjid,
        "AESPID": r.get("RECID", ""),
        "AETERM": str(r.get("AE_VERBATIM", "")).upper(),
        "AEDECOD": r.get("CODED_PT", ""),
        "AEBODSYS": r.get("CODED_SOC", ""),
        "AESEV": sev_out,
        "AESER": aeser,
        "AEREL": aerel,
        "AEOUT": str(r.get("OUTCOME", "")).upper(),
        "AESTDTC": aestdtc,
        "AEENDTC": aeendtc,
        "AESTDY": aestdy,
        "AEENDY": aeendy,
    })

ae = pd.DataFrame(rows)

# Sort for AESEQ
ae = ae.sort_values(by=["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort").reset_index(drop=True)
ae["AESEQ"] = ae.groupby("USUBJID").cumcount() + 1
ae["AESEQ"] = ae["AESEQ"].astype(str)

cols = ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM", "AEDECOD",
        "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT", "AESTDTC", "AEENDTC",
        "AESTDY", "AEENDY"]
ae = ae[cols]

os.makedirs("output", exist_ok=True)
ae.to_csv("output/ae.csv", index=False)
