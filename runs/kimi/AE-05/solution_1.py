import os
from datetime import date

import pandas as pd

STUDYID = "BRV-836"

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

REL_MAP = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}

SER_MAP = {"Yes": "Y", "No": "N"}


def parse_dtc(raw):
    """Convert 'DD MON YYYY' (with UN/UNK unknowns) to ISO 8601, keeping
    only known parts (YYYY-MM-DD, YYYY-MM or YYYY)."""
    s = (raw or "").strip()
    if not s:
        return ""
    parts = s.split()
    if len(parts) != 3:
        return ""
    day, mon, year = parts[0], parts[1].upper(), parts[2]
    if not year.isdigit():
        return ""
    dtc = year
    if mon == "UNK" or mon not in MONTHS:
        return dtc
    dtc += "-" + MONTHS[mon]
    if day.upper() == "UN" or not day.isdigit():
        return dtc
    return dtc + "-" + day.zfill(2)


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC; blank if either date is partial/missing."""
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ""
    try:
        d = date.fromisoformat(dtc)
        r = date.fromisoformat(rfstdtc)
    except ValueError:
        return ""
    diff = (d - r).days
    return str(diff + 1) if diff >= 0 else str(diff)


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)
    raw = pd.read_csv("input/raw_ae.csv", dtype=str, keep_default_na=False)

    rfstdtc = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    # Drop deleted records and "no adverse events" placeholder rows.
    raw = raw[raw["RECORD_STATUS"].str.strip() != "DELETED"]
    raw = raw[raw["AEYN"].str.strip() != "No"]
    raw = raw.copy()

    raw["STUDYID"] = STUDYID
    raw["DOMAIN"] = "AE"
    raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"].str.strip()
    raw["AESPID"] = raw["RECID"].str.strip()
    raw["AETERM"] = raw["AE_VERBATIM"].str.strip().str.upper()
    raw["AEDECOD"] = raw["CODED_PT"].str.strip()
    raw["AEBODSYS"] = raw["CODED_SOC"].str.strip()
    raw["AESEV"] = raw["SEVERITY"].str.strip().str.upper()
    raw["AESER"] = raw["SERIOUS"].str.strip().map(SER_MAP).fillna("")
    raw["AEREL"] = raw["RELATIONSHIP"].str.strip().map(REL_MAP).fillna("")
    raw["AEOUT"] = raw["OUTCOME"].str.strip().str.upper()
    raw["AESTDTC"] = raw["AESTDAT"].map(parse_dtc)
    raw["AEENDTC"] = [
        "" if ongoing.strip().upper() == "Y" else parse_dtc(end)
        for ongoing, end in zip(raw["AEONGO"], raw["AEENDAT"])
    ]
    raw["AESTDY"] = [
        study_day(dtc, rfstdtc.get(subj, ""))
        for dtc, subj in zip(raw["AESTDTC"], raw["USUBJID"])
    ]
    raw["AEENDY"] = [
        study_day(dtc, rfstdtc.get(subj, ""))
        for dtc, subj in zip(raw["AEENDTC"], raw["USUBJID"])
    ]

    # AESEQ: per subject, sorted by AESTDTC (as text), AETERM, AESPID.
    raw = raw.sort_values(
        by=["USUBJID", "AESTDTC", "AETERM", "AESPID"],
        kind="mergesort",
    )
    raw["AESEQ"] = raw.groupby("USUBJID").cumcount() + 1

    out = raw[[
        "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
        "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
        "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
    ]]

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
