import os
import pandas as pd
from datetime import datetime

STUDYID = "PLX-785"
DOMAIN = "AE"

MONTHS = {
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

REL_MAP = {
    "not related": "NONE",
    "unlikely related": "REMOTE",
    "possibly related": "POSSIBLE",
    "probably related": "PROBABLE",
}

SER_MAP = {
    "yes": "Y",
    "no": "N",
}


def clean(value):
    return "" if value is None else str(value).strip()


def parse_raw_date(raw):
    raw = clean(raw)
    if not raw:
        return ""

    parts = raw.split()
    if len(parts) != 3:
        return ""

    day, mon, year = parts

    if not year.isdigit():
        return ""

    mon_upper = mon.upper()
    if mon_upper == "UNK":
        return year

    mm = MONTHS.get(mon_upper)
    if not mm:
        return ""

    if day.upper() == "UN":
        return f"{year}-{mm}"

    if day.isdigit():
        return f"{year}-{mm}-{int(day):02d}"

    return ""


def calc_study_day(dtc, rfstdtc):
    if not dtc or not rfstdtc:
        return ""

    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ""

    try:
        date_value = datetime.strptime(dtc, "%Y-%m-%d").date()
        ref_value = datetime.strptime(rfstdtc, "%Y-%m-%d").date()
    except ValueError:
        return ""

    delta = (date_value - ref_value).days
    if delta >= 0:
        return delta + 1
    return delta


def main():
    dm_df = pd.read_csv("./input/dm.csv", dtype=str, keep_default_na=False)
    dm_dict = {}
    for _, row in dm_df.iterrows():
        usubjid = clean(row.get("USUBJID", ""))
        rfstdtc = clean(row.get("RFSTDTC", ""))
        if usubjid:
            dm_dict[usubjid] = rfstdtc

    raw_df = pd.read_csv("./input/raw_ae.csv", dtype=str, keep_default_na=False)

    records = []
    for _, row in raw_df.iterrows():
        subject = clean(row.get("SUBJECT", ""))
        usubjid = f"{STUDYID}-{subject}" if subject else ""
        rfstdtc = dm_dict.get(usubjid, "")

        aeterm = clean(row.get("AE_VERBATIM", "")).upper()
        aedecod = clean(row.get("CODED_PT", ""))
        aebodsys = clean(row.get("CODED_SOC", ""))
        aesev = clean(row.get("SEVERITY", "")).upper()

        serious_raw = clean(row.get("SERIOUS", "")).lower()
        aeser = SER_MAP.get(serious_raw, "")

        rel_raw = clean(row.get("RELATIONSHIP", "")).lower()
        aerel = REL_MAP.get(rel_raw, "")

        aeout = clean(row.get("OUTCOME", "")).upper()

        aestdtc = parse_raw_date(row.get("AESTDAT", ""))
        aeongo = clean(row.get("AEONGO", "")).upper()

        aeendtc = ""
        if aeongo != "Y":
            aeendtc = parse_raw_date(row.get("AEENDAT", ""))

        aestdy = calc_study_day(aestdtc, rfstdtc)
        aeendy = calc_study_day(aeendtc, rfstdtc)

        records.append(
            {
                "STUDYID": STUDYID,
                "DOMAIN": DOMAIN,
                "USUBJID": usubjid,
                "AESPID": clean(row.get("RECID", "")),
                "AETERM": aeterm,
                "AEDECOD": aedecod,
                "AEBODSYS": aebodsys,
                "AESEV": aesev,
                "AESER": aeser,
                "AEREL": aerel,
                "AEOUT": aeout,
                "AESTDTC": aestdtc,
                "AEENDTC": aeendtc,
                "AESTDY": aestdy,
                "AEENDY": aeendy,
            }
        )

    out_df = pd.DataFrame(records)
    out_df.sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"], inplace=True)
    out_df["AESEQ"] = out_df.groupby("USUBJID").cumcount() + 1

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

    out_df = out_df[columns]

    os.makedirs("./output", exist_ok=True)
    out_df.to_csv("./output/ae.csv", index=False)


if __name__ == "__main__":
    main()
