import os
import sys
from datetime import datetime

import pandas as pd

STUDYID = "PLX-326"
RAW_PATH = os.path.join("input", "raw_ae.csv")
DM_PATH = os.path.join("input", "dm.csv")
OUT_PATH = os.path.join("output", "ae.csv")

REL_MAP = {
    "not related": "NONE",
    "unlikely related": "REMOTE",
    "possibly related": "POSSIBLE",
    "probably related": "PROBABLE",
}

COLUMNS = [
    "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM", "AEDECOD",
    "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
    "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
]


def clean(value):
    """Return value as a stripped string; missing -> ''."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def part_int(value):
    """Parse an unpadded numeric date part; blank/invalid -> None."""
    text = clean(value)
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def build_dtc(year, month, day):
    """Assemble ISO 8601 date from parts; keep only known parts, never impute."""
    y = part_int(year)
    if y is None:
        return ""
    m = part_int(month)
    if m is None:
        return f"{y:04d}"
    d = part_int(day)
    if d is None:
        return f"{y:04d}-{m:02d}"
    return f"{y:04d}-{m:02d}-{d:02d}"


def study_day(dtc, rfstdtc):
    """SDTM --DY relative to RFSTDTC; blank unless both are complete dates."""
    if not dtc or len(dtc) != 10 or not rfstdtc or len(rfstdtc) != 10:
        return None
    try:
        d = datetime.strptime(dtc, "%Y-%m-%d").date()
        rf = datetime.strptime(rfstdtc, "%Y-%m-%d").date()
    except ValueError:
        return None
    diff = (d - rf).days
    return diff + 1 if diff >= 0 else diff


def main():
    raw = pd.read_csv(RAW_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    dm = pd.read_csv(DM_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    raw.columns = [c.strip() for c in raw.columns]
    dm.columns = [c.strip() for c in dm.columns]

    # USUBJID = STUDYID-SITE-SUBJECT (raw SUBJECT is "<site>-<subject>")
    parts = raw["SUBJECT"].map(clean).str.split("-", n=1, expand=True)
    if parts.shape[1] < 2:
        parts[1] = ""
    site = parts[0].fillna("")
    subj = parts[1].fillna("")
    raw["USUBJID"] = STUDYID + "-" + site + "-" + subj

    # RFSTDTC from the finished DM domain
    dm_rf = dm[["USUBJID", "RFSTDTC"]].copy()
    dm_rf["USUBJID"] = dm_rf["USUBJID"].map(clean)
    dm_rf["RFSTDTC"] = dm_rf["RFSTDTC"].map(clean)
    dm_rf = dm_rf.drop_duplicates(subset="USUBJID")
    df = raw.merge(dm_rf, on="USUBJID", how="left")
    df["RFSTDTC"] = df["RFSTDTC"].fillna("")

    unmatched = sorted(set(df["USUBJID"]) - set(dm_rf["USUBJID"]))
    if unmatched:
        print("WARNING: no DM record for USUBJID: " + ", ".join(unmatched), file=sys.stderr)

    # Direct mappings
    df["STUDYID"] = STUDYID
    df["DOMAIN"] = "AE"
    df["AESPID"] = df["RECID"].map(clean)
    df["AETERM"] = df["AE_VERBATIM"].map(lambda v: clean(v).upper())
    df["AEDECOD"] = df["CODED_PT"].map(clean)
    df["AEBODSYS"] = df["CODED_SOC"].map(clean)
    df["AESEV"] = df["SEVERITY"].map(lambda v: clean(v).upper())
    df["AESER"] = df["SERIOUS"].map(lambda v: {"yes": "Y", "no": "N"}.get(clean(v).lower(), ""))
    df["AEREL"] = df["RELATIONSHIP"].map(lambda v: REL_MAP.get(clean(v).lower(), ""))
    df["AEOUT"] = df["OUTCOME"].map(lambda v: clean(v).upper())

    # ISO 8601 dates (partials keep only known parts; no imputation)
    df["AESTDTC"] = [
        build_dtc(y, m, d)
        for y, m, d in zip(df["AESTDAT_YYYY"], df["AESTDAT_MM"], df["AESTDAT_DD"])
    ]
    end_dtc = [
        build_dtc(y, m, d)
        for y, m, d in zip(df["AEENDAT_YYYY"], df["AEENDAT_MM"], df["AEENDAT_DD"])
    ]
    ongoing = df["AEONGO"].map(lambda v: clean(v).upper() == "Y")
    df["AEENDTC"] = ["" if og else dtc for og, dtc in zip(ongoing, end_dtc)]

    # Study days relative to RFSTDTC (blank when either date is partial or missing)
    df["AESTDY"] = pd.Series(
        [study_day(s, rf) for s, rf in zip(df["AESTDTC"], df["RFSTDTC"])],
        index=df.index,
        dtype=object,
    )
    df["AEENDY"] = pd.Series(
        [study_day(e, rf) for e, rf in zip(df["AEENDTC"], df["RFSTDTC"])],
        index=df.index,
        dtype=object,
    )

    # AESEQ: within each subject, sort by AESTDTC (as text), AETERM, AESPID -> 1..n
    df = df.sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort")
    df = df.reset_index(drop=True)
    df["AESEQ"] = df.groupby("USUBJID").cumcount() + 1

    out = df[COLUMNS]
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {OUT_PATH} ({len(out)} records)")


if __name__ == "__main__":
    main()
