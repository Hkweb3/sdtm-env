import os
import datetime
import pandas as pd

STUDYID = "PLX-785"

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

REL_MAP = {
    "not related": "NONE",
    "unlikely related": "REMOTE",
    "possibly related": "POSSIBLE",
    "probably related": "PROBABLE",
}


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def parse_raw_date(value):
    s = clean(value)
    if not s:
        return None

    parts = s.split()
    if len(parts) != 3:
        return None

    day_s, month_s, year_s = parts

    try:
        year = int(year_s)
    except ValueError:
        return None

    month = MONTHS.get(month_s.upper())
    if month_s.upper() == "UNK":
        month = None

    day = None
    if day_s.upper() != "UN":
        try:
            day = int(day_s)
        except ValueError:
            day = None

    if day is not None and (day < 1 or day > 31):
        day = None
    if month is not None and (month < 1 or month > 12):
        month = None

    return year, month, day


def format_iso_date(year, month, day):
    if year is None:
        return ""
    if month is None:
        return f"{year:04d}"
    if day is None:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}-{month:02d}-{day:02d}"


def make_date(year, month, day):
    if year is None or month is None or day is None:
        return None
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def parse_iso_date(value):
    s = clean(value)
    if not s:
        return None

    parts = s.split("-")
    if len(parts) != 3:
        return None

    try:
        year, month, day = map(int, parts)
    except ValueError:
        return None

    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def study_day(event_date, rfstdtc):
    if event_date is None:
        return ""

    ref_date = parse_iso_date(rfstdtc)
    if ref_date is None:
        return ""

    delta = (event_date - ref_date).days
    if delta >= 0:
        delta += 1

    return str(delta)


def map_serious(value):
    v = clean(value).lower()
    if v == "yes":
        return "Y"
    if v == "no":
        return "N"
    return ""


def map_rel(value):
    return REL_MAP.get(clean(value).lower(), "")


def main():
    os.makedirs("output", exist_ok=True)

    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    ae = pd.read_csv("input/raw_ae.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")

    for df in (dm, ae):
        for col in df.columns:
            df[col] = df[col].str.strip()

    rfstdtc_map = {}
    if "USUBJID" in dm.columns and "RFSTDTC" in dm.columns:
        rfstdtc_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    ae["USUBJID"] = ae["SUBJECT"].apply(lambda x: f"{STUDYID}-{x}" if x else "")
    ae["AESPID"] = ae["RECID"].str.strip()

    if "RECORD_STATUS" in ae.columns:
        status = ae["RECORD_STATUS"].str.upper()
        ae = ae[status.isin(["ACTIVE", ""])].copy()

    if "VERSION" in ae.columns:
        ae["VERSION_NUM"] = pd.to_numeric(ae["VERSION"], errors="coerce").fillna(0)
        ae = ae.sort_values(
            ["USUBJID", "AESPID", "VERSION_NUM"],
            ascending=[True, True, False],
            kind="mergesort",
        )
        ae = ae.drop_duplicates(subset=["USUBJID", "AESPID"], keep="first").drop(columns=["VERSION_NUM"])

    n = len(ae)

    start_parsed = ae["AESTDAT"].apply(parse_raw_date).tolist()
    end_parsed = ae["AEENDAT"].apply(parse_raw_date).tolist()
    ongoing = ae["AEONGO"].str.upper().eq("Y")

    start_iso = []
    start_dt = []
    for p in start_parsed:
        if p is None:
            start_iso.append("")
            start_dt.append(None)
        else:
            year, month, day = p
            start_iso.append(format_iso_date(year, month, day))
            start_dt.append(make_date(year, month, day))

    end_iso = []
    end_dt = []
    for p, is_ongoing in zip(end_parsed, ongoing):
        if p is None or is_ongoing:
            end_iso.append("")
            end_dt.append(None)
        else:
            year, month, day = p
            end_iso.append(format_iso_date(year, month, day))
            end_dt.append(make_date(year, month, day))

    rf = ae["USUBJID"].map(rfstdtc_map).fillna("")

    out = pd.DataFrame(
        {
            "STUDYID": [STUDYID] * n,
            "DOMAIN": ["AE"] * n,
            "USUBJID": ae["USUBJID"].tolist(),
            "AESPID": ae["AESPID"].tolist(),
            "AETERM": ae["AE_VERBATIM"].str.upper().tolist(),
            "AEDECOD": ae["CODED_PT"].str.upper().tolist(),
            "AEBODSYS": ae["CODED_SOC"].str.upper().tolist(),
            "AESEV": ae["SEVERITY"].str.upper().tolist(),
            "AESER": ae["SERIOUS"].apply(map_serious).tolist(),
            "AEREL": ae["RELATIONSHIP"].apply(map_rel).tolist(),
            "AEOUT": ae["OUTCOME"].str.upper().tolist(),
            "AESTDTC": start_iso,
            "AEENDTC": end_iso,
            "AESTDY": [study_day(d, r) for d, r in zip(start_dt, rf)],
            "AEENDY": [study_day(d, r) for d, r in zip(end_dt, rf)],
        }
    )

    out = out.sort_values(
        ["USUBJID", "AESTDTC", "AETERM", "AESPID"],
        kind="mergesort",
    ).reset_index(drop=True)

    out["AESEQ"] = out.groupby("USUBJID", sort=False).cumcount() + 1

    out = out.sort_values(["USUBJID", "AESEQ"], kind="mergesort").reset_index(drop=True)

    cols = [
        "STUDYID",
        "DOMAIN",
        "USUBJID",
        "AESEQ",
        "AESPID",
        "AETERM",
        "AEDECOD",
        "AEBODSYS",
        "AESEV",
        "AESER",
        "AEREL",
        "AEOUT",
        "AESTDTC",
        "AEENDTC",
        "AESTDY",
        "AEENDY",
    ]

    out = out[cols].fillna("")
    out.to_csv("output/ae.csv", index=False, na_rep="")


if __name__ == "__main__":
    main()
