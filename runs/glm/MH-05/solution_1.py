import os
import re
from datetime import date

import pandas as pd

STUDYID = "ALX-345"
DOMAIN = "MH"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

CATEGORY_MAP = {
    "PD": "PRIMARY DIAGNOSIS",
    "SPC": "SIGNIFICANT PRE-EXISTING CONDITION",
    "HD": "HISTORICAL DIAGNOSIS",
}

FULL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

OUTPUT_COLUMNS = [
    "STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM",
    "MHDECOD", "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY",
]


def parse_visit_date(value):
    """'DD MON YYYY' (day 'UN', month 'UNK') -> ISO 8601 partial date."""
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    year = month = day = None
    for token in text.split():
        token = token.upper()
        if token.isdigit() and len(token) == 4:
            year = token
        elif token in MONTHS:
            month = MONTHS[token]
        elif token.isdigit():
            day = int(token)
    if year is None:
        return ""
    if month is None:
        return year
    if day is None:
        return "%s-%02d" % (year, month)
    return "%s-%02d-%02d" % (year, month, day)


def build_start_date(dd, mm, yyyy):
    """Raw day/month/year parts (blank = unknown) -> ISO 8601 partial date."""
    year = "" if yyyy is None else str(yyyy).strip()
    month = "" if mm is None else str(mm).strip()
    day = "" if dd is None else str(dd).strip()
    if not year.isdigit():
        return ""
    if not month.isdigit():
        return year
    if not day.isdigit():
        return "%s-%02d" % (year, int(month))
    return "%s-%02d-%02d" % (year, int(month), int(day))


def to_complete_date(value):
    """Parse a complete YYYY-MM-DD string into a date, else None."""
    text = "" if value is None else str(value).strip()
    if not FULL_DATE_RE.match(text):
        return None
    year, month, day = text.split("-")
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def study_day(dtc, rfstdtc):
    """SDTM study day relative to RFSTDTC (no day 0); blank if either partial."""
    dt = to_complete_date(dtc)
    rf = to_complete_date(rfstdtc)
    if dt is None or rf is None:
        return ""
    delta = (dt - rf).days
    return delta + 1 if delta >= 0 else delta


def main():
    raw = pd.read_csv(os.path.join("input", "raw_mh.csv"),
                      dtype=str, keep_default_na=False)
    dm = pd.read_csv(os.path.join("input", "dm.csv"),
                     dtype=str, keep_default_na=False)

    # Drop rows flagged as DELETED.
    status = raw["RECORD_STATUS"].astype(str).str.strip().str.upper()
    raw = raw[status != "DELETED"].copy()

    # Identifiers and text/coded variables.
    raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"].astype(str).str.strip()
    raw["MHSPID"] = raw["RECID"].astype(str).str.strip()
    raw["MHTERM"] = raw["MH_VERBATIM"].astype(str)
    raw["MHDECOD"] = raw["CODED_PT"].astype(str)
    raw["MHBODSYS"] = raw["CODED_SOC"].astype(str)
    raw["MHCAT"] = (raw["CATEGORY"].astype(str).str.strip()
                    .str.upper().map(CATEGORY_MAP).fillna(""))

    # Dates: history collection date (MHDTC) and condition start (MHSTDTC).
    raw["MHDTC"] = raw["VISIT_DATE"].map(parse_visit_date)
    raw["MHSTDTC"] = [
        build_start_date(dd, mm, yyyy)
        for dd, mm, yyyy in zip(raw["MHSTDAT_DD"], raw["MHSTDAT_MM"],
                                raw["MHSTDAT_YYYY"])
    ]

    # MHDY: study day of MHDTC relative to the subject's RFSTDTC from DM.
    rfstdtc = (dm.assign(USUBJID=dm["USUBJID"].astype(str).str.strip())
                 .drop_duplicates(subset="USUBJID")
                 .set_index("USUBJID")["RFSTDTC"])
    raw["RFSTDTC"] = raw["USUBJID"].map(rfstdtc).fillna("")
    raw["MHDY"] = [study_day(dtc, rf)
                   for dtc, rf in zip(raw["MHDTC"], raw["RFSTDTC"])]

    # MHSEQ: sort each subject's records by MHCAT, MHSTDTC (as text), MHTERM,
    # MHSPID, then number 1..n within subject.
    raw = raw.sort_values(
        by=["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
        kind="mergesort")
    raw["MHSEQ"] = raw.groupby("USUBJID", sort=False).cumcount() + 1

    out = pd.DataFrame({
        "STUDYID": STUDYID,
        "DOMAIN": DOMAIN,
        "USUBJID": raw["USUBJID"].values,
        "MHSEQ": raw["MHSEQ"].values.astype(int),
        "MHSPID": raw["MHSPID"].values,
        "MHTERM": raw["MHTERM"].values,
        "MHDECOD": raw["MHDECOD"].values,
        "MHCAT": raw["MHCAT"].values,
        "MHBODSYS": raw["MHBODSYS"].values,
        "MHDTC": raw["MHDTC"].values,
        "MHSTDTC": raw["MHSTDTC"].values,
        "MHDY": raw["MHDY"].values,
    })

    os.makedirs("output", exist_ok=True)
    out.to_csv(os.path.join("output", "mh.csv"),
               index=False, columns=OUTPUT_COLUMNS)


if __name__ == "__main__":
    main()
