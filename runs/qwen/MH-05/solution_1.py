import os
import pandas as pd
from datetime import date

STUDYID = "ALX-345"
DOMAIN = "MH"

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

CATEGORY_MAP = {
    "PD": "PRIMARY DIAGNOSIS",
    "SPC": "SIGNIFICANT PRE-EXISTING CONDITION",
    "HD": "HISTORICAL DIAGNOSIS",
}


def clean(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def to_int(value):
    s = clean(value)
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_start_date(dd, mm, yyyy):
    y = to_int(yyyy)
    m = to_int(mm)
    d = to_int(dd)

    if y is None:
        return ""
    if m is None:
        return f"{y:04d}"
    if d is None:
        return f"{y:04d}-{m:02d}"
    return f"{y:04d}-{m:02d}-{d:02d}"


def parse_visit_date(value):
    s = clean(value)
    if not s:
        return ""

    parts = s.split()
    if len(parts) != 3:
        return ""

    day_s, mon_s, year_s = parts

    day = None
    if day_s.upper() != "UN":
        day = to_int(day_s)

    mon = None
    if mon_s.upper() != "UNK":
        mon = MONTHS.get(mon_s.upper())

    year = to_int(year_s)

    if year is None:
        return ""
    if mon is None:
        return f"{year:04d}"
    if day is None:
        return f"{year:04d}-{mon:02d}"
    return f"{year:04d}-{mon:02d}-{day:02d}"


def study_day(value, rf_value):
    dtc = clean(value)
    rf = clean(rf_value)

    if len(dtc) != 10 or len(rf) != 10:
        return ""

    try:
        d = date.fromisoformat(dtc)
        r = date.fromisoformat(rf)
    except ValueError:
        return ""

    diff = (d - r).days
    if d >= r:
        return str(diff + 1)
    return str(diff)


def make_usubjid(value):
    s = clean(value)
    if "-" in s:
        site, subj = s.split("-", 1)
    else:
        site, subj = "", s
    return f"{STUDYID}-{site}-{subj}"


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

    for col in raw.columns:
        raw[col] = raw[col].str.strip()
    for col in dm.columns:
        dm[col] = dm[col].str.strip()

    raw = raw[raw["RECORD_STATUS"].str.upper() != "DELETED"].copy()

    raw["USUBJID"] = raw["SUBJECT"].apply(make_usubjid)

    dm = dm[["USUBJID", "RFSTDTC"]].drop_duplicates(subset="USUBJID")
    raw = raw.merge(dm, on="USUBJID", how="inner")

    raw["MHCAT"] = raw["CATEGORY"].str.upper().map(CATEGORY_MAP).fillna("")
    raw["MHSPID"] = raw["RECID"]
    raw["MHTERM"] = raw["MH_VERBATIM"]
    raw["MHDECOD"] = raw["CODED_PT"]
    raw["MHBODSYS"] = raw["CODED_SOC"]

    raw["MHSTDTC"] = raw.apply(
        lambda r: parse_start_date(r["MHSTDAT_DD"], r["MHSTDAT_MM"], r["MHSTDAT_YYYY"]),
        axis=1,
    )
    raw["MHDTC"] = raw["VISIT_DATE"].apply(parse_visit_date)
    raw["MHDY"] = raw.apply(lambda r: study_day(r["MHDTC"], r["RFSTDTC"]), axis=1)

    sort_cols = ["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"]
    raw = raw.sort_values(by=sort_cols, kind="mergesort").reset_index(drop=True)
    raw["MHSEQ"] = raw.groupby("USUBJID", sort=False).cumcount() + 1
    raw = raw.sort_values(by=["USUBJID", "MHSEQ"], kind="mergesort").reset_index(drop=True)

    out = pd.DataFrame(index=raw.index)
    out["STUDYID"] = STUDYID
    out["DOMAIN"] = DOMAIN
    out["USUBJID"] = raw["USUBJID"]
    out["MHSEQ"] = raw["MHSEQ"]
    out["MHSPID"] = raw["MHSPID"]
    out["MHTERM"] = raw["MHTERM"]
    out["MHDECOD"] = raw["MHDECOD"]
    out["MHCAT"] = raw["MHCAT"]
    out["MHBODSYS"] = raw["MHBODSYS"]
    out["MHDTC"] = raw["MHDTC"]
    out["MHSTDTC"] = raw["MHSTDTC"]
    out["MHDY"] = raw["MHDY"]

    out = out.fillna("")
    out.to_csv("output/mh.csv", index=False)


if __name__ == "__main__":
    main()
