import os
import re
import pandas as pd

STUDYID = "TQR-883"
DOMAIN = "MH"

FULL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

COLS = [
    "STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM",
    "MHDECOD", "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY",
]


def main():
    os.makedirs("output", exist_ok=True)

    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)
    raw = pd.read_csv("input/raw_mh.csv", dtype=str, keep_default_na=False)

    # Normalize whitespace on fields used for keys/dates
    for c in ["SUBJECT", "RECID", "MHSTDAT", "VISIT_DATE", "RECORD_STATUS"]:
        raw[c] = raw[c].str.strip()
    dm["USUBJID"] = dm["USUBJID"].str.strip()
    dm["RFSTDTC"] = dm["RFSTDTC"].str.strip()

    # Drop deleted records
    raw = raw[raw["RECORD_STATUS"].str.upper() != "DELETED"].copy()

    # USUBJID: raw SUBJECT is <site>-<subject> -> STUDYID-SITE-SUBJECT
    raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

    # RFSTDTC lookup from finished DM domain
    rfstdtc = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    def study_day(dtc, usubjid):
        """Study day relative to RFSTDTC; blank if either date is partial/missing."""
        if not FULL_DATE.match(dtc):
            return ""
        ref = rfstdtc.get(usubjid, "")
        if not FULL_DATE.match(ref):
            return ""
        delta = (pd.Timestamp(dtc) - pd.Timestamp(ref)).days
        return delta + 1 if delta >= 0 else delta  # no day 0

    out = pd.DataFrame()
    out["STUDYID"] = STUDYID
    out["DOMAIN"] = DOMAIN
    out["USUBJID"] = raw["USUBJID"]
    out["MHSPID"] = raw["RECID"]
    out["MHTERM"] = raw["MH_VERBATIM"]
    out["MHDECOD"] = raw["CODED_PT"]
    out["MHCAT"] = raw["CATEGORY"].str.strip().str.upper()
    out["MHBODSYS"] = raw["CODED_SOC"]
    out["MHDTC"] = raw["VISIT_DATE"]
    out["MHSTDTC"] = raw["MHSTDAT"]
    out["MHDY"] = [
        study_day(d, u) for d, u in zip(raw["VISIT_DATE"], raw["USUBJID"])
    ]

    # MHSEQ: within each subject, sort by MHCAT, MHSTDTC (as text), MHTERM, MHSPID
    out = out.sort_values(
        ["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
        kind="mergesort",
    ).reset_index(drop=True)
    out["MHSEQ"] = out.groupby("USUBJID").cumcount() + 1

    out = out[COLS]
    out.to_csv("output/mh.csv", index=False)


if __name__ == "__main__":
    main()
