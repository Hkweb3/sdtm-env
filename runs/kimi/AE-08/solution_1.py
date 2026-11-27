import os
from datetime import date

import pandas as pd

STUDYID = "ALX-919"

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

SEV_MAP = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
SER_MAP = {"YES": "Y", "NO": "N"}
REL_MAP = {
    "NOT RELATED": "NONE",
    "UNLIKELY RELATED": "REMOTE",
    "POSSIBLY RELATED": "POSSIBLE",
    "PROBABLY RELATED": "PROBABLE",
}


def to_dtc(raw):
    """Convert DDMONYYYY (UN = unknown day, UNK = unknown month) to ISO 8601,
    keeping only the known parts (YYYY-MM-DD, YYYY-MM or YYYY)."""
    if pd.isna(raw):
        return ""
    s = str(raw).strip().upper()
    if not s:
        return ""
    day, mon, year = s[:2], s[2:5], s[5:9]
    if mon not in MONTHS:          # UNK month (or unparseable) -> year only
        return year
    if day == "UN":                # unknown day -> year-month
        return f"{year}-{MONTHS[mon]}"
    return f"{year}-{MONTHS[mon]}-{day}"


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC (no day 0). Blank if either date is
    partial or missing."""
    if not isinstance(dtc, str) or not isinstance(rfstdtc, str):
        return ""
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ""
    delta = (date.fromisoformat(dtc) - date.fromisoformat(rfstdtc)).days
    return delta + 1 if delta >= 0 else delta


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str)
    raw = pd.read_csv("input/raw_ae.csv", dtype=str)

    # Keep only the highest VERSION of each SUBJECT + RECID record.
    raw["_ver"] = pd.to_numeric(raw["VERSION"], errors="coerce")
    raw = raw.sort_values("_ver", kind="mergesort")
    raw = raw.drop_duplicates(subset=["SUBJECT", "RECID"], keep="last")

    # Drop deleted records and "no adverse events" placeholder rows.
    status = raw["RECORD_STATUS"].fillna("").str.strip().str.upper()
    aeyn = raw["AEYN"].fillna("").str.strip().str.upper()
    raw = raw[(status != "DELETED") & (aeyn != "NO")]

    out = pd.DataFrame(index=raw.index)
    out["STUDYID"] = STUDYID
    out["DOMAIN"] = "AE"
    out["USUBJID"] = STUDYID + "-" + raw["SUBJECT"].str.strip()
    out["AESPID"] = raw["RECID"].fillna("")
    out["AETERM"] = raw["AE_VERBATIM"].fillna("").str.upper()
    out["AEDECOD"] = raw["CODED_PT"].fillna("")
    out["AEBODSYS"] = raw["CODED_SOC"].fillna("")
    out["AESEV"] = raw["SEVERITY"].str.strip().map(SEV_MAP).fillna("")
    out["AESER"] = raw["SERIOUS"].str.strip().str.upper().map(SER_MAP).fillna("")
    out["AEREL"] = raw["RELATIONSHIP"].str.strip().str.upper().map(REL_MAP).fillna("")
    out["AEOUT"] = raw["OUTCOME"].fillna("").str.upper()
    out["AESTDTC"] = raw["AESTDAT"].map(to_dtc)
    out["AEENDTC"] = [
        "" if str(ongo).strip().upper() == "Y" else to_dtc(end)
        for ongo, end in zip(raw["AEONGO"], raw["AEENDAT"])
    ]

    # Attach RFSTDTC from DM and derive study days.
    out = out.merge(dm[["USUBJID", "RFSTDTC"]], on="USUBJID", how="left")
    out["AESTDY"] = [study_day(d, r) for d, r in zip(out["AESTDTC"], out["RFSTDTC"])]
    out["AEENDY"] = [study_day(d, r) for d, r in zip(out["AEENDTC"], out["RFSTDTC"])]

    # AESEQ: per subject, ordered by AESTDTC (as text), AETERM, AESPID.
    out = out.sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort")
    out["AESEQ"] = out.groupby("USUBJID").cumcount() + 1

    cols = ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
            "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
            "AESTDTC", "AEENDTC", "AESTDY", "AEENDY"]
    out = out[cols]

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
