import os
from datetime import date

import pandas as pd

STUDYID = "TQR-883"

dm = pd.read_csv("input/dm.csv", dtype=str).fillna("")
mh = pd.read_csv("input/raw_mh.csv", dtype=str).fillna("")

# Drop deleted records
mh = mh[mh["RECORD_STATUS"] != "DELETED"].copy()

# USUBJID = STUDYID-SITE-SUBJECT (raw SUBJECT is already <site>-<subject>)
mh["USUBJID"] = STUDYID + "-" + mh["SUBJECT"]

rfstdtc = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))


def study_day(dtc, ref):
    # Blank when either date is partial or missing
    if len(dtc) != 10 or len(ref) != 10:
        return ""
    try:
        d = date.fromisoformat(dtc)
        r = date.fromisoformat(ref)
    except ValueError:
        return ""
    delta = (d - r).days
    return str(delta + 1) if delta >= 0 else str(delta)


mh["STUDYID"] = STUDYID
mh["DOMAIN"] = "MH"
mh["MHSPID"] = mh["RECID"]
mh["MHTERM"] = mh["MH_VERBATIM"]
mh["MHDECOD"] = mh["CODED_PT"]
mh["MHCAT"] = mh["CATEGORY"].str.upper()
mh["MHBODSYS"] = mh["CODED_SOC"]
mh["MHDTC"] = mh["VISIT_DATE"]
mh["MHSTDTC"] = mh["MHSTDAT"]
mh["MHDY"] = [
    study_day(dtc, rfstdtc.get(usubjid, ""))
    for dtc, usubjid in zip(mh["MHDTC"], mh["USUBJID"])
]

# Sort within subject, then sequence 1..n per subject
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
