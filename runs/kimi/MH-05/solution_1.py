import os
from datetime import date

import pandas as pd

STUDYID = "ALX-345"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

CAT_MAP = {
    "PD": "PRIMARY DIAGNOSIS",
    "SPC": "SIGNIFICANT PRE-EXISTING CONDITION",
    "HD": "HISTORICAL DIAGNOSIS",
}


def build_stdtc(dd, mm, yyyy):
    """Build ISO 8601 (possibly partial) date from split day/month/year parts."""
    yyyy = yyyy.strip()
    if yyyy == "":
        return ""
    y = int(yyyy)
    mm = mm.strip()
    if mm == "":
        return f"{y:04d}"
    m = int(mm)
    dd = dd.strip()
    if dd == "":
        return f"{y:04d}-{m:02d}"
    d = int(dd)
    return f"{y:04d}-{m:02d}-{d:02d}"


def parse_visit_date(value):
    """Parse 'DD MON YYYY' with UN/UNK unknowns.

    Returns (iso_string, date_object_or_None). The date object is None
    when the date is partial or missing.
    """
    parts = value.strip().split()
    if len(parts) != 3:
        return "", None
    d_txt, m_txt, y_txt = parts
    if not y_txt.isdigit():
        return "", None
    y = int(y_txt)
    if m_txt.upper() == "UNK":
        return f"{y:04d}", None
    m = MONTHS[m_txt.upper()]
    if d_txt.upper() == "UN":
        return f"{y:04d}-{m:02d}", None
    d = int(d_txt)
    return f"{y:04d}-{m:02d}-{d:02d}", date(y, m, d)


def study_day(dtc_date, rfstdtc):
    """Study day relative to RFSTDTC; no day 0. Blank if either is partial/missing."""
    if dtc_date is None or rfstdtc.strip() == "":
        return ""
    rf = date.fromisoformat(rfstdtc.strip())
    delta = (dtc_date - rf).days
    return str(delta + 1) if delta >= 0 else str(delta)


def main():
    raw = pd.read_csv("input/raw_mh.csv", dtype=str, keep_default_na=False)
    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)

    rfstdtc_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    # Drop deleted records
    raw = raw[raw["RECORD_STATUS"] != "DELETED"].copy()

    raw["STUDYID"] = STUDYID
    raw["DOMAIN"] = "MH"
    raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]
    raw["MHSPID"] = raw["RECID"]
    raw["MHTERM"] = raw["MH_VERBATIM"]
    raw["MHDECOD"] = raw["CODED_PT"]
    raw["MHCAT"] = raw["CATEGORY"].map(CAT_MAP).fillna(raw["CATEGORY"])
    raw["MHBODSYS"] = raw["CODED_SOC"]

    raw["MHSTDTC"] = [
        build_stdtc(dd, mm, yyyy)
        for dd, mm, yyyy in zip(
            raw["MHSTDAT_DD"], raw["MHSTDAT_MM"], raw["MHSTDAT_YYYY"]
        )
    ]

    visit = raw["VISIT_DATE"].map(parse_visit_date)
    raw["MHDTC"] = [v[0] for v in visit]
    raw["_visit_dt"] = [v[1] for v in visit]
    raw["MHDY"] = [
        study_day(d, rfstdtc_map.get(u, ""))
        for d, u in zip(raw["_visit_dt"], raw["USUBJID"])
    ]

    # Sort within subject, then assign MHSEQ
    raw = raw.sort_values(
        by=["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
        kind="mergesort",
    )
    raw["MHSEQ"] = raw.groupby("USUBJID").cumcount() + 1

    out = raw[
        [
            "STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM",
            "MHDECOD", "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY",
        ]
    ]

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/mh.csv", index=False)


if __name__ == "__main__":
    main()
