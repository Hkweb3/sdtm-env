import os
import pandas as pd
from datetime import datetime


def clean(value):
    if value is None:
        return ""
    s = str(value).strip()
    if s in {"", "NA", "NULL", "None", "nan"}:
        return ""
    return s


def make_dtc(dd, mm, yyyy):
    dd = clean(dd)
    mm = clean(mm)
    yyyy = clean(yyyy)

    if not yyyy:
        return ""

    yyyy = yyyy.zfill(4)

    if not mm:
        return yyyy

    mm = mm.zfill(2)

    if not dd:
        return f"{yyyy}-{mm}"

    dd = dd.zfill(2)
    return f"{yyyy}-{mm}-{dd}"


def parse_full_date(dtc):
    dtc = clean(dtc)
    if len(dtc) != 10:
        return None
    try:
        return datetime.strptime(dtc, "%Y-%m-%d").date()
    except ValueError:
        return None


def study_day(dtc, rfstdtc):
    d = parse_full_date(dtc)
    r = parse_full_date(rfstdtc)

    if d is None or r is None:
        return ""

    delta = (d - r).days
    if delta >= 0:
        return str(delta + 1)
    return str(delta)


def map_serious(value):
    v = clean(value).lower()
    if v in {"yes", "y"}:
        return "Y"
    if v in {"no", "n"}:
        return "N"
    return ""


def map_rel(value):
    v = clean(value).lower()
    return {
        "not related": "NONE",
        "unlikely related": "REMOTE",
        "possibly related": "POSSIBLE",
        "probably related": "PROBABLE",
    }.get(v, "")


def main():
    raw = pd.read_csv("input/raw_ae.csv", dtype=str, keep_default_na=False)
    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)

    dm["USUBJID"] = dm["USUBJID"].map(clean)
    dm["RFSTDTC"] = dm["RFSTDTC"].map(clean)
    dm = dm[["USUBJID", "RFSTDTC"]].drop_duplicates(subset="USUBJID")

    raw["_idx"] = list(range(len(raw)))
    raw["USUBJID"] = raw["SUBJECT"].map(lambda x: f"PLX-326-{clean(x)}")

    df = raw.merge(dm, on="USUBJID", how="left")
    df = df.fillna("")

    df["STUDYID"] = "PLX-326"
    df["DOMAIN"] = "AE"
    df["AESPID"] = df["RECID"].map(clean)
    df["AETERM"] = df["AE_VERBATIM"].map(lambda x: clean(x).upper())
    df["AEDECOD"] = df["CODED_PT"].map(clean)
    df["AEBODSYS"] = df["CODED_SOC"].map(clean)
    df["AESEV"] = df["SEVERITY"].map(lambda x: clean(x).upper())
    df["AESER"] = df["SERIOUS"].map(map_serious)
    df["AEREL"] = df["RELATIONSHIP"].map(map_rel)
    df["AEOUT"] = df["OUTCOME"].map(lambda x: clean(x).upper())

    df["AESTDTC"] = [
        make_dtc(dd, mm, yyyy)
        for dd, mm, yyyy in zip(
            df["AESTDAT_DD"],
            df["AESTDAT_MM"],
            df["AESTDAT_YYYY"],
        )
    ]

    ongoing = df["AEONGO"].map(lambda x: clean(x).lower() in {"y", "yes"})
    df["AEENDTC"] = [
        "" if is_ongoing else make_dtc(dd, mm, yyyy)
        for is_ongoing, dd, mm, yyyy in zip(
            ongoing,
            df["AEENDAT_DD"],
            df["AEENDAT_MM"],
            df["AEENDAT_YYYY"],
        )
    ]

    df["AESTDY"] = [
        study_day(start, rfstdtc)
        for start, rfstdtc in zip(df["AESTDTC"], df["RFSTDTC"])
    ]
    df["AEENDY"] = [
        study_day(end, rfstdtc)
        for end, rfstdtc in zip(df["AEENDTC"], df["RFSTDTC"])
    ]

    df = df.sort_values(
        ["USUBJID", "AESTDTC", "AETERM", "AESPID", "_idx"],
        kind="mergesort",
    )
    df["AESEQ"] = df.groupby("USUBJID", sort=False).cumcount() + 1
    df = df.sort_values(["USUBJID", "AESEQ"], kind="mergesort")

    columns = [
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
    df = df[columns]

    os.makedirs("output", exist_ok=True)
    df.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
