import os
import re
from datetime import date
import pandas as pd

STUDYID = "KVT-131"
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

DATE_RE = re.compile(r"^(?P<day>\d{1,2}|UN)(?P<mon>[A-Z]{3}|UNK)(?P<year>\d{4})$")

OUTPUT_COLUMNS = [
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


def parse_raw_date(value):
    if not isinstance(value, str):
        return ""

    value = value.strip().upper()
    if not value:
        return ""

    match = DATE_RE.match(value)
    if not match:
        return ""

    day = match.group("day")
    mon = match.group("mon")
    year = match.group("year")

    if mon == "UNK":
        return year

    mon_num = MONTHS.get(mon)
    if mon_num is None:
        return ""

    if day == "UN":
        return f"{year}-{mon_num:02d}"

    try:
        day_num = int(day)
    except ValueError:
        return ""

    return f"{year}-{mon_num:02d}-{day_num:02d}"


def parse_full_date(value):
    if not isinstance(value, str):
        return None

    value = value.strip()
    if len(value) != 10:
        return None

    parts = value.split("-")
    if len(parts) != 3:
        return None

    try:
        year, month, day = map(int, parts)
        return date(year, month, day)
    except ValueError:
        return None


def study_day(value_date, ref_date):
    if value_date is None or ref_date is None:
        return ""

    delta = (value_date - ref_date).days
    if delta >= 0:
        return str(delta + 1)
    return str(delta)


def main():
    input_dir = "input"
    output_dir = "output"
    dm_path = os.path.join(input_dir, "dm.csv")
    raw_path = os.path.join(input_dir, "raw_mh.csv")
    out_path = os.path.join(output_dir, "mh.csv")

    dm = pd.read_csv(dm_path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8-sig")
    raw = pd.read_csv(raw_path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8-sig")

    for col in ("USUBJID", "SITEID", "SUBJID", "RFSTDTC"):
        if col in dm.columns:
            dm[col] = dm[col].str.strip()

    dm["RAW_SUBJECT"] = dm["SITEID"] + "-" + dm["SUBJID"]
    valid_subjects = set(dm["RAW_SUBJECT"])

    raw["SUBJECT"] = raw["SUBJECT"].str.strip()
    raw = raw[raw["SUBJECT"].isin(valid_subjects)].copy()

    if raw.empty:
        os.makedirs(output_dir, exist_ok=True)
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")
        return

    usubj_map = dict(zip(dm["RAW_SUBJECT"], dm["USUBJID"]))
    rf_map = dict(zip(dm["RAW_SUBJECT"], dm["RFSTDTC"]))

    raw["USUBJID"] = raw["SUBJECT"].map(usubj_map).fillna(
        raw["SUBJECT"].apply(lambda x: f"{STUDYID}-{x}")
    )
    raw["RFSTDTC"] = raw["SUBJECT"].map(rf_map).fillna("")

    for col in ("RECID", "MH_VERBATIM", "CODED_PT", "CODED_SOC", "CATEGORY", "MHSTDAT", "VISIT_DATE"):
        if col in raw.columns:
            raw[col] = raw[col].str.strip()

    cat_map = {
        "PD": "PRIMARY DIAGNOSIS",
        "SPC": "SIGNIFICANT PRE-EXISTING CONDITION",
        "HD": "HISTORICAL DIAGNOSIS",
    }

    raw["MHCAT"] = raw["CATEGORY"].map(lambda x: cat_map.get(x.upper(), ""))
    raw["MHSTDTC"] = raw["MHSTDAT"].apply(parse_raw_date)
    raw["MHDTC"] = raw["VISIT_DATE"].apply(parse_raw_date)

    raw["_MHDTC_DATE"] = raw["MHDTC"].apply(parse_full_date)
    raw["_RFSTDTC_DATE"] = raw["RFSTDTC"].apply(parse_full_date)
    raw["MHDY"] = [study_day(a, b) for a, b in zip(raw["_MHDTC_DATE"], raw["_RFSTDTC_DATE"])]

    out = pd.DataFrame(
        {
            "STUDYID": STUDYID,
            "DOMAIN": DOMAIN,
            "USUBJID": raw["USUBJID"],
            "MHSPID": raw["RECID"],
            "MHTERM": raw["MH_VERBATIM"],
            "MHDECOD": raw["CODED_PT"],
            "MHBODSYS": raw["CODED_SOC"],
            "MHCAT": raw["MHCAT"],
            "MHSTDTC": raw["MHSTDTC"],
            "MHDTC": raw["MHDTC"],
            "MHDY": raw["MHDY"],
        }
    )

    out = out.fillna("")
    out = out.sort_values(
        by=["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
        kind="mergesort",
    ).reset_index(drop=True)

    out["MHSEQ"] = out.groupby("USUBJID", sort=False).cumcount() + 1
    out = out[OUTPUT_COLUMNS]
    out = out.fillna("")

    os.makedirs(output_dir, exist_ok=True)
    out.to_csv(out_path, index=False, encoding="utf-8")


if __name__ == "__main__":
    main()
