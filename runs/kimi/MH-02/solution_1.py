import os
from datetime import date

import pandas as pd

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

CAT_MAP = {
    "PD": "PRIMARY DIAGNOSIS",
    "SPC": "SIGNIFICANT PRE-EXISTING CONDITION",
    "HD": "HISTORICAL DIAGNOSIS",
}


def parse_dtc(val):
    """Convert DDMONYYYY (UN day / UNK month) to ISO 8601, keeping partials."""
    if pd.isna(val):
        return ""
    s = str(val).strip().upper()
    if not s:
        return ""
    day, mon, year = s[0:2], s[2:5], s[5:9]
    if mon == "UNK" or mon not in MONTHS:
        return year
    iso = f"{year}-{MONTHS[mon]}"
    if day == "UN":
        return iso
    return f"{iso}-{day}"


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC; blank if either date is partial/missing."""
    if not dtc or not rfstdtc or len(dtc) < 10 or len(rfstdtc) < 10:
        return ""
    delta = (date.fromisoformat(dtc) - date.fromisoformat(rfstdtc)).days
    return str(delta + 1) if delta >= 0 else str(delta)


dm = pd.read_csv("input/dm.csv", dtype=str)
mh = pd.read_csv("input/raw_mh.csv", dtype=str)

rfstdtc_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"].fillna("")))

mh["STUDYID"] = "KVT-131"
mh["DOMAIN"] = "MH"
mh["USUBJID"] = "KVT-131-" + mh["SUBJECT"].fillna("").str.strip()
mh["MHSPID"] = mh["RECID"].fillna("")
mh["MHTERM"] = mh["MH_VERBATIM"].fillna("")
mh["MHDECOD"] = mh["CODED_PT"].fillna("")
mh["MHCAT"] = mh["CATEGORY"].map(CAT_MAP).fillna("")
mh["MHBODSYS"] = mh["CODED_SOC"].fillna("")
mh["MHDTC"] = mh["VISIT_DATE"].apply(parse_dtc)
mh["MHSTDTC"] = mh["MHSTDAT"].apply(parse_dtc)
mh["MHDY"] = [
    study_day(dtc, rfstdtc_map.get(usubjid, ""))
    for dtc, usubjid in zip(mh["MHDTC"], mh["USUBJID"])
]

mh = mh.sort_values(
    ["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
    kind="mergesort",
)
mh["MHSEQ"] = mh.groupby("USUBJID").cumcount() + 1

out = mh[
    [
        "STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM",
        "MHDECOD", "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY",
    ]
]

os.makedirs("output", exist_ok=True)
out.to_csv("output/mh.csv", index=False)
