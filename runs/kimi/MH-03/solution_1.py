import os
from datetime import date

import pandas as pd

STUDYID = "CTN-248"

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def clean(v):
    if pd.isna(v):
        return ""
    return str(v).strip()


def build_stdtc(dd, mm, yyyy):
    """Build ISO 8601 (possibly partial) date from raw DD/MM/YYYY parts."""
    y = clean(yyyy)
    if not y:
        return ""
    m = clean(mm)
    d = clean(dd)
    if not m:
        return y
    if not d:
        return f"{y}-{int(m):02d}"
    return f"{y}-{int(m):02d}-{int(d):02d}"


def parse_visit_date(s):
    """Parse 'DD MON YYYY' with UN/UNK unknown parts into ISO 8601."""
    s = clean(s)
    if not s:
        return ""
    parts = s.split()
    if len(parts) != 3:
        return ""
    d, m, y = parts[0], parts[1].upper(), parts[2]
    if y.upper() in ("UN", "UNK"):
        return ""
    mm = MONTHS.get(m)
    if mm is None:
        return y
    if d.upper() in ("UN", "UNK"):
        return f"{y}-{mm}"
    return f"{y}-{mm}-{int(d):02d}"


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC; blank if either date is partial/missing."""
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ""
    d = date.fromisoformat(dtc)
    r = date.fromisoformat(rfstdtc)
    delta = (d - r).days
    return str(delta + 1) if delta >= 0 else str(delta)


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str)
    mh = pd.read_csv("input/raw_mh.csv", dtype=str)

    rfstdtc = {clean(u): clean(r) for u, r in zip(dm["USUBJID"], dm["RFSTDTC"])}

    out = pd.DataFrame()
    out["STUDYID"] = STUDYID
    out["DOMAIN"] = "MH"
    out["USUBJID"] = mh["SUBJECT"].map(lambda v: f"{STUDYID}-{clean(v)}")
    out["MHSPID"] = mh["RECID"].map(clean)
    out["MHTERM"] = mh["MH_VERBATIM"].map(clean)
    out["MHDECOD"] = mh["CODED_PT"].map(clean)
    out["MHCAT"] = mh["CATEGORY"].map(lambda v: clean(v).upper())
    out["MHBODSYS"] = mh["CODED_SOC"].map(clean)
    out["MHDTC"] = mh["VISIT_DATE"].map(parse_visit_date)
    out["MHSTDTC"] = [
        build_stdtc(d, m, y)
        for d, m, y in zip(mh["MHSTDAT_DD"], mh["MHSTDAT_MM"], mh["MHSTDAT_YYYY"])
    ]
    out["MHDY"] = [
        study_day(dtc, rfstdtc.get(usubjid, ""))
        for dtc, usubjid in zip(out["MHDTC"], out["USUBJID"])
    ]

    out = out.sort_values(
        ["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"], kind="mergesort"
    )
    out["MHSEQ"] = out.groupby("USUBJID").cumcount() + 1

    cols = [
        "STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM", "MHDECOD",
        "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY",
    ]
    out = out[cols].fillna("")

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/mh.csv", index=False)


if __name__ == "__main__":
    main()
