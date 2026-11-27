import os
import calendar
from datetime import date, timedelta

import pandas as pd


def clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("nan", "nat", "", "<na>"):
        return ""
    return text


def parse_complete_date(text):
    text = clean_text(text)
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            return date(int(text[:4]), int(text[5:7]), int(text[8:10]))
        except ValueError:
            return None
    return None


def impute_end(aeendtc):
    text = clean_text(aeendtc)
    if text == "":
        return None, ""

    if len(text) == 10:
        dt = parse_complete_date(text)
        if dt is not None:
            return dt, ""
    elif len(text) == 7 and text[4] == "-":
        try:
            y = int(text[:4])
            m = int(text[5:7])
            return date(y, m, calendar.monthrange(y, m)[1]), "D"
        except (ValueError, IndexError):
            pass
    elif len(text) == 4:
        try:
            y = int(text)
            return date(y, 12, 31), "M"
        except ValueError:
            pass

    return None, ""


def impute_start(aestdtc, trtsdt, aendt, aendtf):
    if trtsdt is None:
        return None, ""

    text = clean_text(aestdtc)

    if text == "":
        dt = trtsdt
        flag = "Y"
    elif len(text) == 10:
        dt = parse_complete_date(text)
        if dt is None:
            return None, ""
        return dt, ""
    elif len(text) == 7 and text[4] == "-":
        try:
            y = int(text[:4])
            m = int(text[5:7])
        except ValueError:
            return None, ""

        if trtsdt.year == y and trtsdt.month == m:
            dt = trtsdt
        else:
            dt = date(y, m, 1)
        flag = "D"
    elif len(text) == 4:
        try:
            y = int(text)
        except ValueError:
            return None, ""

        if trtsdt.year == y:
            dt = trtsdt
        else:
            dt = date(y, 1, 1)
        flag = "M"
    else:
        return None, ""

    if flag != "" and aendt is not None and aendtf == "" and dt > aendt:
        dt = aendt

    return dt, flag


def study_day(dt, trtsdt):
    if dt is None or trtsdt is None:
        return None
    delta = (dt - trtsdt).days
    if delta >= 0:
        return delta + 1
    return delta


def duration_days(start_dt, end_dt):
    if start_dt is None or end_dt is None:
        return None
    return (end_dt - start_dt).days + 1


def trtem_flag(row):
    if row.ASTDT is None or row.TRTSDT is None or row.TRTEDT is None:
        return ""
    upper = row.TRTEDT + timedelta(days=7)
    if row.ASTDT >= row.TRTSDT and row.ASTDT <= upper:
        return "Y"
    return ""


def main():
    os.makedirs("output", exist_ok=True)

    adsl = pd.read_csv("input/adsl.csv", keep_default_na=False)
    adsl["TRTSDT"] = pd.to_datetime(
        adsl["TRTSDT"].str.strip(), format="%Y-%m-%d", errors="coerce"
    )
    adsl["TRTSDT"] = adsl["TRTSDT"].apply(
        lambda x: x.date() if pd.notna(x) else None
    )
    adsl["TRTEDT"] = pd.to_datetime(
        adsl["TRTEDT"].str.strip(), format="%Y-%m-%d", errors="coerce"
    )
    adsl["TRTEDT"] = adsl["TRTEDT"].apply(
        lambda x: x.date() if pd.notna(x) else None
    )

    ae = pd.read_csv("input/ae.csv", keep_default_na=False)
    ae["AESEQ"] = ae["AESEQ"].astype(int)

    df = ae[
        [
            "STUDYID",
            "USUBJID",
            "AESEQ",
            "AETERM",
            "AEDECOD",
            "AEBODSYS",
            "AESTDTC",
            "AEENDTC",
        ]
    ].merge(adsl[["USUBJID", "TRTSDT", "TRTEDT"]], on="USUBJID", how="left")

    end_results = [impute_end(x) for x in df["AEENDTC"]]
    df["AENDT"] = [r[0] for r in end_results]
    df["AENDTF"] = [r[1] for r in end_results]

    start_results = [
        impute_start(row.AESTDTC, row.TRTSDT, row.AENDT, row.AENDTF)
        for row in df.itertuples(index=False)
    ]
    df["ASTDT"] = [r[0] for r in start_results]
    df["ASTDTF"] = [r[1] for r in start_results]

    df["ASTDY"] = [study_day(row.ASTDT, row.TRTSDT) for row in df.itertuples(index=False)]
    df["AENDY"] = [study_day(row.AENDT, row.TRTSDT) for row in df.itertuples(index=False)]
    df["ADURN"] = [duration_days(row.ASTDT, row.AENDT) for row in df.itertuples(index=False)]

    df["TRTEMFL"] = [trtem_flag(row) for row in df.itertuples(index=False)]

    df["AOCCFL"] = ""
    df["AOCCPFL"] = ""

    trt = df[df["TRTEMFL"] == "Y"].sort_values(["USUBJID", "ASTDT", "AESEQ"]).copy()
    trt["AOCCFL"] = ""
    trt["AOCCPFL"] = ""

    first_subj = ~trt.duplicated("USUBJID", keep="first")
    trt.loc[first_subj, "AOCCFL"] = "Y"

    first_term = ~trt.duplicated(["USUBJID", "AEDECOD"], keep="first")
    trt.loc[first_term, "AOCCPFL"] = "Y"

    df.loc[trt.index, "AOCCFL"] = trt["AOCCFL"]
    df.loc[trt.index, "AOCCPFL"] = trt["AOCCPFL"]

    out_cols = [
        "STUDYID",
        "USUBJID",
        "AESEQ",
        "AETERM",
        "AEDECOD",
        "AEBODSYS",
        "TRTSDT",
        "TRTEDT",
        "ASTDT",
        "ASTDTF",
        "AENDT",
        "AENDTF",
        "ASTDY",
        "AENDY",
        "ADURN",
        "TRTEMFL",
        "AOCCFL",
        "AOCCPFL",
    ]

    df = df[out_cols]
    df = df.sort_values(["USUBJID", "AESEQ"], kind="stable").reset_index(drop=True)

    for col in ["TRTSDT", "TRTEDT", "ASTDT", "AENDT"]:
        df[col] = df[col].apply(lambda x: x.strftime("%Y-%m-%d") if x is not None else "")

    df.to_csv("output/adae.csv", index=False, na_rep="")


if __name__ == "__main__":
    main()
