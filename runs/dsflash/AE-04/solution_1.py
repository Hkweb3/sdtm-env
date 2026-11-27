import pandas as pd
import os

STUDYID = "MRN-326"

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_ae.csv", dtype=str)

# Build USUBJID from raw SUBJECT
raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

# Keep only subjects present in DM
dm_usubjids = set(dm["USUBJID"])
raw = raw[raw["USUBJID"].isin(dm_usubjids)].copy()

# RFSTDTC lookup
rfstdtc_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

def to_iso(datestr):
    if pd.isna(datestr) or datestr is None:
        return ""
    datestr = str(datestr).strip()
    if datestr == "":
        return ""
    parts = datestr.split("/")
    if len(parts) == 3:
        mm, dd, yyyy = parts
        if mm and dd and yyyy:
            return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
        elif mm and yyyy:
            return f"{yyyy}-{mm.zfill(2)}"
        elif yyyy:
            return f"{yyyy}"
    return ""

def is_full_date(iso):
    return len(iso) == 10

def study_day(iso_date, rfstdtc):
    if not iso_date or not rfstdtc:
        return ""
    if not is_full_date(iso_date) or not is_full_date(rfstdtc):
        return ""
    d = pd.to_datetime(iso_date)
    r = pd.to_datetime(rfstdtc)
    diff = (d - r).days
    if diff >= 0:
        return diff + 1
    else:
        return diff

sev_map = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
ser_map = {"Yes": "Y", "No": "N"}
rel_map = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}

rows = []
for _, r in raw.iterrows():
    usubjid = r["USUBJID"]
    rfstdtc = rfstdtc_map.get(usubjid, "")

    aeterm = str(r["AE_VERBATIM"]).upper() if pd.notna(r["AE_VERBATIM"]) else ""
    aedecod = str(r["CODED_PT"]).upper() if pd.notna(r["CODED_PT"]) else ""
    aebodsys = str(r["CODED_SOC"]).upper() if pd.notna(r["CODED_SOC"]) else ""

    sev_raw = str(r["SEVERITY"]).strip() if pd.notna(r["SEVERITY"]) else ""
    aesev = sev_map.get(sev_raw, "")

    ser_raw = str(r["SERIOUS"]).strip() if pd.notna(r["SERIOUS"]) else ""
    aeser = ser_map.get(ser_raw, "")

    rel_raw = str(r["RELATIONSHIP"]).strip() if pd.notna(r["RELATIONSHIP"]) else ""
    aerel = rel_map.get(rel_raw, "")

    aeout = str(r["OUTCOME"]).upper() if pd.notna(r["OUTCOME"]) else ""

    aestdtc = to_iso(r["AESTDAT"])
    aongo = str(r["AEONGO"]).strip() if pd.notna(r["AEONGO"]) else ""
    if aongo == "Y":
        aeendtc = ""
    else:
        aeendtc = to_iso(r["AEENDAT"])

    aestdy = study_day(aestdtc, rfstdtc)
    aeendy = study_day(aeendtc, rfstdtc)

    rows.append({
        "STUDYID": STUDYID,
        "DOMAIN": "AE",
        "USUBJID": usubjid,
        "AESPID": r["RECID"],
        "AETERM": aeterm,
        "AEDECOD": aedecod,
        "AEBODSYS": aebodsys,
        "AESEV": aesev,
        "AESER": aeser,
        "AEREL": aerel,
        "AEOUT": aeout,
        "AESTDTC": aestdtc,
        "AEENDTC": aeendtc,
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

# Order columns
cols = [
    "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
    "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
    "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
]
ae = ae[cols]

os.makedirs("output", exist_ok=True)
ae.to_csv("output/ae.csv", index=False)
