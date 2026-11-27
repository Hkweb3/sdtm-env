import os
from datetime import date

import pandas as pd

STUDYID = "TQR-448"

SEV_MAP = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
SER_MAP = {"1": "Y", "0": "N"}
REL_MAP = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}


def build_dtc(dd, mm, yyyy):
    yyyy = (yyyy or "").strip()
    mm = (mm or "").strip()
    dd = (dd or "").strip()
    if yyyy == "":
        return ""
    if mm == "":
        return yyyy
    if dd == "":
        return f"{yyyy}-{int(mm):02d}"
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"


def study_day(dtc, rfstdtc):
    # Blank when either date is partial or missing (no imputation, no day 0)
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ""
    d = date.fromisoformat(dtc)
    r = date.fromisoformat(rfstdtc)
    delta = (d - r).days
    return str(delta + 1) if delta >= 0 else str(delta)


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)
    ae = pd.read_csv("input/raw_ae.csv", dtype=str, keep_default_na=False)

    # Keep only the highest VERSION per SUBJECT + RECID
    ae["_ver"] = pd.to_numeric(ae["VERSION"], errors="coerce")
    ae = ae.sort_values(["SUBJECT", "RECID", "_ver"], kind="mergesort")
    ae = ae.drop_duplicates(subset=["SUBJECT", "RECID"], keep="last").copy()

    ae["STUDYID"] = STUDYID
    ae["DOMAIN"] = "AE"
    ae["USUBJID"] = STUDYID + "-" + ae["SUBJECT"].str.strip()
    ae["AESPID"] = ae["RECID"].str.strip()
    ae["AETERM"] = ae["AE_VERBATIM"].str.strip().str.upper()
    ae["AEDECOD"] = ae["CODED_PT"].str.strip()
    ae["AEBODSYS"] = ae["CODED_SOC"].str.strip()
    ae["AESEV"] = ae["SEVERITY"].str.strip().map(SEV_MAP).fillna("")
    ae["AESER"] = ae["SERIOUS"].str.strip().map(SER_MAP).fillna("")
    ae["AEREL"] = ae["RELATIONSHIP"].str.strip().map(REL_MAP).fillna("")
    ae["AEOUT"] = ae["OUTCOME"].str.strip().str.upper()

    ae["AESTDTC"] = [
        build_dtc(d, m, y)
        for d, m, y in zip(ae["AESTDAT_DD"], ae["AESTDAT_MM"], ae["AESTDAT_YYYY"])
    ]
    ongoing = ae["AEONGO"].str.strip().str.upper() == "Y"
    ae["AEENDTC"] = [
        "" if ong else build_dtc(d, m, y)
        for ong, d, m, y in zip(
            ongoing, ae["AEENDAT_DD"], ae["AEENDAT_MM"], ae["AEENDAT_YYYY"]
        )
    ]

    rfstdtc = dm.set_index("USUBJID")["RFSTDTC"]
    ae["_rfstdtc"] = ae["USUBJID"].map(rfstdtc).fillna("")
    ae["AESTDY"] = [study_day(d, r) for d, r in zip(ae["AESTDTC"], ae["_rfstdtc"])]
    ae["AEENDY"] = [study_day(d, r) for d, r in zip(ae["AEENDTC"], ae["_rfstdtc"])]

    # AESEQ: per subject, sorted by AESTDTC (as text), then AETERM, then AESPID
    ae = ae.sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort")
    ae["AESEQ"] = ae.groupby("USUBJID").cumcount() + 1

    cols = [
        "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
        "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
        "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
    ]
    out = ae[cols]

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
