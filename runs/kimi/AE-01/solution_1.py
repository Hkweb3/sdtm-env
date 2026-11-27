import os
from datetime import date

import pandas as pd

STUDYID = "PLX-785"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

AEREL_MAP = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}

AESER_MAP = {"Yes": "Y", "No": "N"}


def to_dtc(raw):
    """Convert 'DD MON YYYY' (UN day / UNK month unknowns) to ISO 8601,
    keeping only the known parts (YYYY-MM-DD, YYYY-MM or YYYY)."""
    if raw is None or str(raw).strip() == "":
        return ""
    parts = str(raw).split()
    day, mon, year = parts[0], parts[1].upper(), parts[2]
    if mon == "UNK":
        return year
    mm = MONTHS[mon]
    if day == "UN":
        return f"{year}-{mm:02d}"
    return f"{year}-{mm:02d}-{int(day):02d}"


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC (no day 0); blank unless both dates
    are complete."""
    if not dtc or len(dtc) != 10 or not rfstdtc:
        return ""
    d = date.fromisoformat(dtc)
    r = date.fromisoformat(rfstdtc)
    diff = (d - r).days
    return diff + 1 if diff >= 0 else diff


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str).fillna("")
    ae = pd.read_csv("input/raw_ae.csv", dtype=str).fillna("")

    rfstdtc = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    out = pd.DataFrame(index=ae.index)
    out["STUDYID"] = STUDYID
    out["DOMAIN"] = "AE"
    out["USUBJID"] = STUDYID + "-" + ae["SUBJECT"]

    # USUBJID must match DM
    missing = sorted(set(out["USUBJID"]) - set(dm["USUBJID"]))
    if missing:
        raise ValueError(f"USUBJID not found in DM: {missing}")

    out["AESPID"] = ae["RECID"]
    out["AETERM"] = ae["AE_VERBATIM"].str.upper()
    out["AEDECOD"] = ae["CODED_PT"]
    out["AEBODSYS"] = ae["CODED_SOC"]
    out["AESEV"] = ae["SEVERITY"].str.upper()
    out["AESER"] = ae["SERIOUS"].map(AESER_MAP).fillna("")
    out["AEREL"] = ae["RELATIONSHIP"].map(AEREL_MAP).fillna("")
    out["AEOUT"] = ae["OUTCOME"].str.upper()
    out["AESTDTC"] = ae["AESTDAT"].map(to_dtc)
    out["AEENDTC"] = [
        "" if ongoing.strip().upper() == "Y" else to_dtc(end)
        for ongoing, end in zip(ae["AEONGO"], ae["AEENDAT"])
    ]

    # AESEQ: per subject, sorted by AESTDTC (as text), then AETERM, then AESPID
    out = out.sort_values(
        ["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort"
    )
    out["AESEQ"] = out.groupby("USUBJID").cumcount() + 1

    rf = out["USUBJID"].map(rfstdtc)
    out["AESTDY"] = [study_day(s, r) for s, r in zip(out["AESTDTC"], rf)]
    out["AEENDY"] = [study_day(e, r) for e, r in zip(out["AEENDTC"], rf)]

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
