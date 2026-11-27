import pandas as pd
import os
import re

os.makedirs("output", exist_ok=True)

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_ae.csv", dtype=str)

# Build USUBJID
raw["USUBJID"] = "PLX-785-" + raw["SUBJECT"]

# Map RFSTDTC
rf_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

def parse_date(s):
    """Return (iso_string, is_full) where iso_string is YYYY, YYYY-MM, or YYYY-MM-DD."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return "", False
    s = str(s).strip()
    if s == "" or s.lower() == "nan":
        return "", False
    parts = s.split()
    if len(parts) != 3:
        return "", False
    d, m, y = parts
    d_known = d.upper() != "UN"
    m_known = m.upper() != "UNK"
    if not y.isdigit():
        return "", False
    if m_known and d_known:
        return f"{y}-{MONTHS[m.upper()]}-{d.zfill(2)}", True
    if m_known:
        return f"{y}-{MONTHS[m.upper()]}", False
    return y, False

def study_day(iso, is_full, rfstdtc):
    if not is_full or not iso or not rfstdtc:
        return ""
    try:
        d = pd.Timestamp(iso)
        r = pd.Timestamp(rfstdtc)
    except Exception:
        return ""
    delta = (d - r).days
    if d >= r:
        return str(delta + 1)
    return str(delta)

sev_map = {"Mild": "MILD", "Moderate": "MODERATE", "Severe": "SEVERE"}
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

    aeterm = str(r["AE_VERBATIM"]).upper() if pd.notna(r["AE_VERBATIM"]) else ""

    sev_raw = str(r["SEVERITY"]).strip() if pd.notna(r["SEVERITY"]) else ""
    aesev = sev_map.get(sev_raw, sev_raw.upper())

    ser_raw = str(r["SERIOUS"]).strip() if pd.notna(r["SERIOUS"]) else ""
    aeser = "Y" if ser_raw == "Yes" else ("N" if ser_raw == "No" else "")

    rel_raw = str(r["RELATIONSHIP"]).strip() if pd.notna(r["RELATIONSHIP"]) else ""
    aerel = rel_map.get(rel_raw, "")

    out_raw = str(r["OUTCOME"]).strip() if pd.notna(r["OUTCOME"]) else ""
    aeout = out_raw.upper()

    ongo = str(r["AEONGO"]).strip() if pd.notna(r["AEONGO"]) else ""

    stdtc, st_full = parse_date(r["AESTDAT"])
    if ongo == "Y":
        enddtc, en_full = "", False
    else:
        enddtc, en_full = parse_date(r["AEENDAT"])

    aestdy = study_day(stdtc, st_full, rfstdtc)
    aeendy = study_day(enddtc, en_full, rfstdtc)

    rows.append({
        "STUDYID": "PLX-785",
        "DOMAIN": "AE",
        "USUBJID": usubjid,
        "AESPID": r["RECID"],
        "AETERM": aeterm,
        "AEDECOD": r["CODED_PT"],
        "AEBODSYS": r["CODED_SOC"],
        "AESEV": aesev,
        "AESER": aeser,
        "AEREL": aerel,
        "AEOUT": aeout,
        "AESTDTC": stdtc,
        "AEENDTC": enddtc,
        "AESTDY": aestdy,
        "AEENDY": aeendy,
    })

ae = pd.DataFrame(rows)

# Sort for AESEQ
ae = ae.sort_values(
    by=["USUBJID", "AESTDTC", "AETERM", "AESPID"],
    kind="mergesort"
).reset_index(drop=True)

ae["AESEQ"] = ae.groupby("USUBJID").cumcount() + 1
ae["AESEQ"] = ae["AESEQ"].astype(int)

cols = ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM", "AEDECOD",
        "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT", "AESTDTC", "AEENDTC",
        "AESTDY", "AEENDY"]

ae = ae[cols]

ae.to_csv("output/ae.csv", index=False)
