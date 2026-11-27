import os
import pandas as pd
from datetime import datetime

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def parse_iso_date(value):
    s = str(value).strip()
    if not s:
        return ""

    parts = s.split()
    if len(parts) != 3:
        return ""

    day_s, mon_s, year_s = parts

    if not year_s.isdigit():
        return ""

    day = None
    if day_s.upper() not in ("UN", "UNK"):
        if day_s.isdigit():
            day = int(day_s)
        else:
            return ""

    mon = None
    if mon_s.upper() not in ("UN", "UNK"):
        mon = MONTHS.get(mon_s.upper())
        if mon is None:
            return ""

    if day is not None and mon is not None:
        return f"{year_s}-{mon:02d}-{day:02d}"
    if mon is not None:
        return f"{year_s}-{mon:02d}"
    return year_s


def to_full_date(value):
    s = str(value).strip()
    if len(s) != 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def main():
    os.makedirs("output", exist_ok=True)

    raw = pd.read_csv(
        "input/raw_mh.csv",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    dm = pd.read_csv(
        "input/dm.csv",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    raw["SUBJECT"] = raw["SUBJECT"].str.strip()
    raw["USUBJID"] = "DRX-647-" + raw["SUBJECT"]

    dm["USUBJID"] = dm["USUBJID"].str.strip()
    dm["RFSTDTC"] = dm["RFSTDTC"].str.strip()
    rf_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    raw["MHSPID"] = raw["RECID"].str.strip()
    raw["MHTERM"] = raw["MH_VERBATIM"].str.strip()
    raw["MHDECOD"] = raw["CODED_PT"].str.strip()
    raw["MHBODSYS"] = raw["CODED_SOC"].str.strip()
    raw["MHCAT"] = raw["CATEGORY"].str.strip().str.upper()
    raw["MHSTDTC"] = raw["MHSTDAT"].map(parse_iso_date)
    raw["MHDTC"] = raw["VISIT_DATE"].map(parse_iso_date)

    def study_day(row):
        d = to_full_date(row["MHDTC"])
        rf = to_full_date(rf_map.get(row["USUBJID"], ""))
        if d is None or rf is None:
            return ""
        delta = (d - rf).days
        return str(delta + 1 if delta >= 0 else delta)

    raw["MHDY"] = raw.apply(study_day, axis=1)

    out = raw[
        [
            "USUBJID",
            "MHSPID",
            "MHTERM",
            "MHDECOD",
            "MHBODSYS",
            "MHCAT",
            "MHSTDTC",
            "MHDTC",
            "MHDY",
        ]
    ].copy()

    out = out.sort_values(
        by=["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
        kind="mergesort",
    )
    out["MHSEQ"] = out.groupby("USUBJID").cumcount() + 1

    out.insert(0, "DOMAIN", "MH")
    out.insert(0, "STUDYID", "DRX-647")

    out = out[
        [
            "STUDYID",
            "DOMAIN",
            "USUBJID",
            "MHSEQ",
            "MHSPID",
            "MHTERM",
            "MHDECOD",
            "MHBODSYS",
            "MHCAT",
            "MHSTDTC",
            "MHDTC",
            "MHDY",
        ]
    ]

    out.to_csv("output/mh.csv", index=False)


if __name__ == "__main__":
    main()
