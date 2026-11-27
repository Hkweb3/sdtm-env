import os
from datetime import date

import pandas as pd

STUDYID = "MRN-326"

SEV_MAP = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
SER_MAP = {"Yes": "Y", "No": "N"}
REL_MAP = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}


def parse_date(value):
    """Convert a raw MM/DD/YYYY date (possibly partial) to ISO 8601.

    Partial dates keep only the known parts (YYYY-MM or YYYY);
    missing components are never imputed.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    parts = [p.strip() for p in s.split("/")]
    mm = dd = yyyy = ""
    if len(parts) == 3:
        mm, dd, yyyy = parts
    elif len(parts) == 2:
        mm, yyyy = parts
    elif len(parts) == 1:
        yyyy = parts[0]
    else:
        return ""
    if not yyyy:
        return ""
    try:
        y = int(yyyy)
        if not mm:
            return f"{y:04d}"
        m = int(mm)
        if not dd:
            return f"{y:04d}-{m:02d}"
        d = int(dd)
        return f"{y:04d}-{m:02d}-{d:02d}"
    except ValueError:
        return ""


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC (no day 0).

    Blank when either date is partial or missing.
    """
    if not dtc or not rfstdtc:
        return ""
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ""
    try:
        d = date.fromisoformat(dtc)
        r = date.fromisoformat(rfstdtc)
    except ValueError:
        return ""
    delta = (d - r).days
    return str(delta + 1) if delta >= 0 else str(delta)


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str).fillna("")
    raw = pd.read_csv("input/raw_ae.csv", dtype=str).fillna("")

    rfstdtc = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    out = pd.DataFrame()
    out["STUDYID"] = STUDYID
    out["DOMAIN"] = "AE"
    out["USUBJID"] = STUDYID + "-" + raw["SUBJECT"].str.strip()
    out["AESPID"] = raw["RECID"].str.strip()
    out["AETERM"] = raw["AE_VERBATIM"].str.upper()
    out["AEDECOD"] = raw["CODED_PT"]
    out["AEBODSYS"] = raw["CODED_SOC"]
    out["AESEV"] = raw["SEVERITY"].str.strip().map(SEV_MAP).fillna("")
    out["AESER"] = raw["SERIOUS"].str.strip().map(SER_MAP).fillna("")
    out["AEREL"] = raw["RELATIONSHIP"].str.strip().map(REL_MAP).fillna("")
    out["AEOUT"] = raw["OUTCOME"].str.upper()
    out["AESTDTC"] = raw["AESTDAT"].map(parse_date)

    ongoing = raw["AEONGO"].str.strip().str.upper() == "Y"
    endtc = raw["AEENDAT"].map(parse_date)
    endtc[ongoing] = ""
    out["AEENDTC"] = endtc

    rf = out["USUBJID"].map(rfstdtc).fillna("")
    out["AESTDY"] = [study_day(d, r) for d, r in zip(out["AESTDTC"], rf)]
    out["AEENDY"] = [study_day(d, r) for d, r in zip(out["AEENDTC"], rf)]

    out = out.sort_values(
        ["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort"
    ).reset_index(drop=True)
    out.insert(3, "AESEQ", out.groupby("USUBJID").cumcount() + 1)

    columns = [
        "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
        "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
        "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
    ]
    out = out[columns]

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
