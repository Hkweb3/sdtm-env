import os
import re
from datetime import datetime

import pandas as pd

STUDYID = "KVT-131"
DOMAIN = "MH"

CATEGORY_MAP = {
    "PD": "PRIMARY DIAGNOSIS",
    "SPC": "SIGNIFICANT PRE-EXISTING CONDITION",
    "HD": "HISTORICAL DIAGNOSIS",
}

MONTH_MAP = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


def parse_dtc(value):
    """Convert DDMONYYYY to ISO 8601. Day may be UN; month may be UNK."""
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s == "":
        return ""

    m = re.match(
        r"^(UN|\d{2})(UNK|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{4})$",
        s,
        re.IGNORECASE,
    )
    if not m:
        return ""

    day = m.group(1).upper()
    mon = m.group(2).upper()
    year = m.group(3)

    if mon == "UNK":
        return year

    mm = MONTH_MAP.get(mon)
    if mm is None:
        return ""

    if day == "UN":
        return f"{year}-{mm}"

    return f"{year}-{mm}-{day}"


def compute_dy(mhdtc, rfstdtc):
    """Compute study day of MHDTC relative to RFSTDTC."""
    if not mhdtc or not rfstdtc:
        return ""
    if len(mhdtc) != 10 or len(rfstdtc) != 10:
        return ""

    try:
        d = datetime.strptime(mhdtc, "%Y-%m-%d").date()
        r = datetime.strptime(rfstdtc, "%Y-%m-%d").date()
    except ValueError:
        return ""

    delta = (d - r).days
    if delta >= 0:
        return delta + 1
    return delta


def main():
    os.makedirs("output", exist_ok=True)

    raw = pd.read_csv("input/raw_mh.csv", dtype=str)
    dm = pd.read_csv("input/dm.csv", dtype=str)

    rfstdtc_by_usubjid = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    rows = []

    for _, r in raw.iterrows():
        raw_subject = str(r["SUBJECT"]).strip()
        if "-" in raw_subject:
            site, subject = raw_subject.split("-", 1)
        else:
            site, subject = raw_subject, raw_subject

        usubjid = f"{STUDYID}-{site}-{subject}"

        cat_code = (
            str(r["CATEGORY"]).strip().upper()
            if pd.notna(r["CATEGORY"])
            else ""
        )
        mhcat = CATEGORY_MAP.get(cat_code, cat_code)

        def clean(value):
            return str(value).strip() if pd.notna(value) else ""

        mhspid = clean(r["RECID"])
        mhterm = clean(r["MH_VERBATIM"])
        mhdecod = clean(r["CODED_PT"])
        mhbodsys = clean(r["CODED_SOC"])

        mhstdtc = parse_dtc(r["MHSTDAT"])
        mhdtc = parse_dtc(r["VISIT_DATE"])

        rfstdtc = rfstdtc_by_usubjid.get(usubjid, "")
        mhdy = compute_dy(mhdtc, rfstdtc)

        rows.append(
            {
                "STUDYID": STUDYID,
                "DOMAIN": DOMAIN,
                "USUBJID": usubjid,
                "MHSPID": mhspid,
                "MHTERM": mhterm,
                "MHDECOD": mhdecod,
                "MHCAT": mhcat,
                "MHBODSYS": mhbodsys,
                "MHDTC": mhdtc,
                "MHSTDTC": mhstdtc,
                "MHDY": mhdy,
            }
        )

    df = pd.DataFrame(rows)

    df = df.sort_values(
        ["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"]
    ).reset_index(drop=True)

    df["MHSEQ"] = df.groupby("USUBJID", sort=False).cumcount() + 1

    df = df[
        [
            "STUDYID",
            "DOMAIN",
            "USUBJID",
            "MHSEQ",
            "MHSPID",
            "MHTERM",
            "MHDECOD",
            "MHCAT",
            "MHBODSYS",
            "MHDTC",
            "MHSTDTC",
            "MHDY",
        ]
    ]

    df.to_csv("output/mh.csv", index=False)


if __name__ == "__main__":
    main()
