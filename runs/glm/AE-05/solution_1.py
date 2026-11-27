import datetime
import os
import re

import pandas as pd

STUDYID = "BRV-836"
RAW_PATH = os.path.join("input", "raw_ae.csv")
DM_PATH = os.path.join("input", "dm.csv")
OUT_PATH = os.path.join("output", "ae.csv")

OUTPUT_COLS = [
    "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM", "AEDECOD",
    "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT", "AESTDTC", "AEENDTC",
    "AESTDY", "AEENDY",
]

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

SER_MAP = {"yes": "Y", "no": "N"}

REL_MAP = {
    "not related": "NONE",
    "unlikely related": "REMOTE",
    "possibly related": "POSSIBLE",
    "probably related": "PROBABLE",
}


def to_iso(value):
    """'DD MON YYYY' (unknown day 'UN', unknown month 'UNK') -> ISO 8601 partial date."""
    s = "" if value is None else str(value).strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):  # already ISO
        return s
    parts = s.split()
    if len(parts) != 3:
        return ""
    day, mon, year = (p.strip().upper() for p in parts)
    if year in ("UN", "UNK", ""):
        return ""
    month = MONTHS.get(mon[:3], "")
    day_part = "" if day in ("UN", "UNK", "") else day.zfill(2)
    if not month:
        return year
    if not day_part:
        return "{}-{}".format(year, month)
    return "{}-{}-{}".format(year, month, day_part)


def study_day(dtc, rfstdtc):
    """--DY relative to RFSTDTC: date - RFSTDTC + 1 on/after ref, else date - RFSTDTC (no day 0)."""
    if not dtc or not rfstdtc or len(dtc) != 10 or len(rfstdtc) != 10:
        return ""
    try:
        d = datetime.date.fromisoformat(dtc)
        r = datetime.date.fromisoformat(rfstdtc)
    except ValueError:
        return ""
    delta = (d - r).days
    return delta + 1 if delta >= 0 else delta


def main():
    raw = pd.read_csv(RAW_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    dm = pd.read_csv(DM_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")

    raw.columns = [c.strip() for c in raw.columns]
    dm.columns = [c.strip() for c in dm.columns]
    for df in (raw, dm):
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # Exclusions: deleted records and "no adverse events" placeholder pages.
    raw = raw[raw["RECORD_STATUS"].str.upper() != "DELETED"]
    raw = raw[raw["AEYN"].str.upper() != "NO"].copy()

    # USUBJID = STUDYID-SITE-SUBJECT (raw SUBJECT is <site>-<subject>).
    raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

    # Reference start date per subject from the finished DM domain.
    rfst = dm.drop_duplicates(subset=["USUBJID"])[["USUBJID", "RFSTDTC"]].copy()
    raw = raw.merge(rfst, on="USUBJID", how="left")
    raw["RFSTDTC"] = raw["RFSTDTC"].fillna("")

    # ISO 8601 dates; an ongoing event has no end date.
    raw["AESTDTC"] = raw["AESTDAT"].map(to_iso)
    raw["AEENDTC"] = raw["AEENDAT"].map(to_iso)
    raw.loc[raw["AEONGO"].str.upper() == "Y", "AEENDTC"] = ""

    # Study days relative to RFSTDTC (blank when either date is partial or missing).
    raw["AESTDY"] = [study_day(a, b) for a, b in zip(raw["AESTDTC"], raw["RFSTDTC"])]
    raw["AEENDY"] = [study_day(a, b) for a, b in zip(raw["AEENDTC"], raw["RFSTDTC"])]

    # AESEQ: 1..n per subject after sorting by AESTDTC, AETERM, AESPID (as text).
    raw["AESPID"] = raw["RECID"]
    raw["AETERM"] = raw["AE_VERBATIM"].str.upper()
    raw = raw.sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort")
    raw["AESEQ"] = raw.groupby("USUBJID").cumcount() + 1

    out = pd.DataFrame({
        "STUDYID": STUDYID,
        "DOMAIN": "AE",
        "USUBJID": raw["USUBJID"],
        "AESEQ": raw["AESEQ"].astype(int),
        "AESPID": raw["AESPID"],
        "AETERM": raw["AETERM"],
        "AEDECOD": raw["CODED_PT"],
        "AEBODSYS": raw["CODED_SOC"],
        "AESEV": raw["SEVERITY"].str.upper(),
        "AESER": raw["SERIOUS"].str.lower().map(SER_MAP).fillna(""),
        "AEREL": raw["RELATIONSHIP"].str.lower().map(REL_MAP).fillna(""),
        "AEOUT": raw["OUTCOME"].str.upper(),
        "AESTDTC": raw["AESTDTC"],
        "AEENDTC": raw["AEENDTC"],
        "AESTDY": raw["AESTDY"],
        "AEENDY": raw["AEENDY"],
    })

    out = out[OUTPUT_COLS].sort_values(["USUBJID", "AESEQ"], kind="mergesort").reset_index(drop=True)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out.to_csv(OUT_PATH, index=False)


if __name__ == "__main__":
    main()
