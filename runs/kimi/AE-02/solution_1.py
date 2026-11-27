import os
from datetime import datetime

import pandas as pd

STUDYID = "ALX-878"

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

AEREL_MAP = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}

AESER_MAP = {"Yes": "Y", "No": "N"}


def parse_raw_date(raw):
    """Parse DDMONYYYY (UN = unknown day, UNK = unknown month).

    Returns (ISO 8601 string, date object or None if partial/missing).
    """
    if raw is None or pd.isna(raw) or str(raw).strip() == "":
        return "", None
    s = str(raw).strip().upper()
    day, mon, year = s[0:2], s[2:5], s[5:9]
    if mon == "UNK" or mon not in MONTHS:
        return year, None
    mm = MONTHS[mon]
    if day == "UN":
        return f"{year}-{mm}", None
    d = datetime(int(year), int(mm), int(day)).date()
    return f"{year}-{mm}-{day}", d


def study_day(d, rfstdtc):
    """Study day relative to RFSTDTC; blank if date is partial/missing."""
    if d is None or rfstdtc is None or pd.isna(rfstdtc) or str(rfstdtc).strip() == "":
        return ""
    rf = datetime.strptime(str(rfstdtc).strip(), "%Y-%m-%d").date()
    delta = (d - rf).days
    return str(delta + 1) if delta >= 0 else str(delta)


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str)
    raw = pd.read_csv("input/raw_ae.csv", dtype=str).fillna("")

    rfstdtc = dm.set_index("USUBJID")["RFSTDTC"].to_dict()

    records = []
    for _, row in raw.iterrows():
        usubjid = f"{STUDYID}-{row['SUBJECT'].strip()}"

        aestdtc, st_date = parse_raw_date(row["AESTDAT"])
        if row["AEONGO"].strip().upper() == "Y":
            aeendtc, en_date = "", None
        else:
            aeendtc, en_date = parse_raw_date(row["AEENDAT"])

        rf = rfstdtc.get(usubjid, "")

        records.append({
            "STUDYID": STUDYID,
            "DOMAIN": "AE",
            "USUBJID": usubjid,
            "AESPID": row["RECID"].strip(),
            "AETERM": row["AE_VERBATIM"].strip().upper(),
            "AEDECOD": row["CODED_PT"].strip(),
            "AEBODSYS": row["CODED_SOC"].strip(),
            "AESEV": row["SEVERITY"].strip().upper(),
            "AESER": AESER_MAP.get(row["SERIOUS"].strip(), ""),
            "AEREL": AEREL_MAP.get(row["RELATIONSHIP"].strip(), ""),
            "AEOUT": row["OUTCOME"].strip().upper(),
            "AESTDTC": aestdtc,
            "AEENDTC": aeendtc,
            "AESTDY": study_day(st_date, rf),
            "AEENDY": study_day(en_date, rf),
        })

    out = pd.DataFrame(records)
    out = out.sort_values(
        ["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort"
    )
    out.insert(3, "AESEQ", out.groupby("USUBJID").cumcount() + 1)

    cols = [
        "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
        "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
        "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
    ]
    out = out[cols]

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
