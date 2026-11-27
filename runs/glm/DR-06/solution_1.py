#!/usr/bin/env python3
"""Task DR-06: data review of the SDTM study package for study ALX-932.

Reads the SDTM datasets in ./input/ and writes data-review findings to
./output/findings.csv (columns: CHECK, USUBJID, DOMAIN, SEQ).
"""

import os
import re
from datetime import datetime

import pandas as pd

INPUT_DIR = "input"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "findings.csv")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Seriousness criteria fields on the AE domain.
CRIT_COLS = ["AESCAN", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE", "AESOD"]

CHECK_ORDER = [
    "AE_DATE_ORDER",
    "AE_DUPLICATE",
    "SAE_CRITERIA",
    "DEATH_CONSISTENCY",
    "DOSE_AFTER_DISC",
    "LAB_UNIT",
    "LAB_VISIT_DATE",
]


def read_csv(name):
    """Read an input dataset, keeping every field as a plain string."""
    return pd.read_csv(
        os.path.join(INPUT_DIR, name), dtype=str, keep_default_na=False,
        encoding="utf-8-sig",
    )


def to_date(value):
    """Parse a complete YYYY-MM-DD date (any time part is ignored).

    Returns a datetime.date, or None when blank / partial / invalid.
    """
    if value is None:
        return None
    s = str(value).strip()
    if len(s) < 10:
        return None
    d = s[:10]
    if not DATE_RE.match(d):
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        return None


def as_int(value):
    """Convert a --SEQ value to a plain int (None if not parseable)."""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def is_y(value):
    return str(value).strip().upper() == "Y"


findings = []


def add(check, usubjid, domain, seq=None):
    findings.append((check, str(usubjid), domain, "" if seq is None else str(seq)))


def main():
    dm = read_csv("dm.csv")
    ae = read_csv("ae.csv")
    ex = read_csv("ex.csv")
    ds = read_csv("ds.csv")
    lb = read_csv("lb.csv")

    # ------------------------------------------------------------------
    # AE_DATE_ORDER: AE ends before it starts (complete dates only).
    # ------------------------------------------------------------------
    for _, r in ae.iterrows():
        start = to_date(r["AESTDTC"])
        end = to_date(r["AEENDTC"])
        if start is not None and end is not None and end < start:
            add("AE_DATE_ORDER", r["USUBJID"], "AE", as_int(r["AESEQ"]))

    # ------------------------------------------------------------------
    # AE_DUPLICATE: same AEDECOD with same non-blank AESTDTC entered more
    # than once for a subject; raise on every copy except lowest AESEQ.
    # ------------------------------------------------------------------
    aek = ae.copy()
    aek["_DECOD"] = aek["AEDECOD"].str.strip()
    aek["_STDTC"] = aek["AESTDTC"].str.strip()
    aek["_SEQ"] = aek["AESEQ"].map(as_int)
    for _, g in aek[aek["_STDTC"] != ""].groupby(["USUBJID", "_DECOD", "_STDTC"]):
        if len(g) > 1:
            g = g.sort_values("_SEQ", kind="mergesort")
            for _, r in g.iloc[1:].iterrows():
                add("AE_DUPLICATE", r["USUBJID"], "AE", r["_SEQ"])

    # ------------------------------------------------------------------
    # SAE_CRITERIA: serious flag vs. seriousness criteria disagreement.
    # ------------------------------------------------------------------
    for _, r in ae.iterrows():
        serious = is_y(r["AESER"])
        any_crit = any(is_y(r[c]) for c in CRIT_COLS)
        if serious != any_crit:
            add("SAE_CRITERIA", r["USUBJID"], "AE", as_int(r["AESEQ"]))

    # ------------------------------------------------------------------
    # DEATH_CONSISTENCY
    # ------------------------------------------------------------------
    death_raw = {r["USUBJID"]: str(r["DTHDTC"]).strip() for _, r in dm.iterrows()}
    fatal_subjects = set(
        ae.loc[ae["AEOUT"].str.strip().str.upper() == "FATAL", "USUBJID"]
    )
    for _, r in ae.iterrows():
        subj = r["USUBJID"]
        dth_raw = death_raw.get(subj, "")
        dth_date = to_date(dth_raw)
        start = to_date(r["AESTDTC"])
        # fatal outcome but no death date in DM
        if str(r["AEOUT"]).strip().upper() == "FATAL" and dth_raw == "":
            add("DEATH_CONSISTENCY", subj, "AE", as_int(r["AESEQ"]))
        # complete AE start date after the subject's death date
        if start is not None and dth_date is not None and start > dth_date:
            add("DEATH_CONSISTENCY", subj, "AE", as_int(r["AESEQ"]))
    for _, r in dm.iterrows():
        # death date recorded but no AE with a fatal outcome
        if str(r["DTHDTC"]).strip() != "" and r["USUBJID"] not in fatal_subjects:
            add("DEATH_CONSISTENCY", r["USUBJID"], "DM", None)

    # ------------------------------------------------------------------
    # DOSE_AFTER_DISC: exposure starting after early discontinuation
    # (disposition event other than COMPLETED / SCREEN FAILURE).
    # ------------------------------------------------------------------
    early_disc = {}
    for _, r in ds.iterrows():
        if str(r["DSCAT"]).strip().upper() != "DISPOSITION EVENT":
            continue
        decod = str(r["DSDECOD"]).strip().upper()
        if decod in ("COMPLETED", "SCREEN FAILURE"):
            continue
        d = to_date(r["DSSTDTC"])
        if d is not None:
            early_disc.setdefault(r["USUBJID"], []).append(d)
    for _, r in ex.iterrows():
        start = to_date(r["EXSTDTC"])
        if start is None:
            continue
        disc_dates = early_disc.get(r["USUBJID"])
        if disc_dates and start > min(disc_dates):
            add("DOSE_AFTER_DISC", r["USUBJID"], "EX", as_int(r["EXSEQ"]))

    # ------------------------------------------------------------------
    # LAB_UNIT: numeric result >= 8x or <= 1/8 of the median of the
    # subject's other results for the same test (>= 2 others required).
    # ------------------------------------------------------------------
    lb["_VAL"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")
    lb["_TESTCD"] = lb["LBTESTCD"].str.strip()
    for (subj, _test), g in lb.groupby(["USUBJID", "_TESTCD"]):
        for idx, r in g.iterrows():
            v = r["_VAL"]
            if pd.isna(v):
                continue
            others = g.loc[g.index != idx, "_VAL"].dropna()
            if len(others) < 2:
                continue
            med = float(others.median())
            if med <= 0:
                continue
            if v >= 8.0 * med or v <= med / 8.0:
                add("LAB_UNIT", subj, "LB", as_int(r["LBSEQ"]))

    # ------------------------------------------------------------------
    # LAB_VISIT_DATE: at scheduled visits only, a result dated earlier
    # than the latest date of the same subject/test at earlier scheduled
    # visits (lower VISITNUM). Dates compared without time.
    # ------------------------------------------------------------------
    lb["_DATE"] = lb["LBDTC"].map(to_date)
    lb["_VISITN"] = pd.to_numeric(lb["VISITNUM"], errors="coerce")
    lb["_VISIT_U"] = lb["VISIT"].str.strip().str.upper()
    sched = lb[~lb["_VISIT_U"].str.startswith("UNSCHEDULED")]
    for (subj, _test), g in sched.groupby(["USUBJID", "_TESTCD"]):
        g = g[g["_VISITN"].notna() & g["_DATE"].notna()]
        if g.empty:
            continue
        for _, r in g.iterrows():
            earlier = g[g["_VISITN"] < r["_VISITN"]]
            if earlier.empty:
                continue
            latest = max(earlier["_DATE"])
            if r["_DATE"] < latest:
                add("LAB_VISIT_DATE", subj, "LB", as_int(r["LBSEQ"]))

    # ------------------------------------------------------------------
    # Write findings (deduplicated, stable ordering).
    # ------------------------------------------------------------------
    result = pd.DataFrame(findings, columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])
    result = result.drop_duplicates()
    result["_ORD"] = result["CHECK"].map({c: i for i, c in enumerate(CHECK_ORDER)})
    result["_SEQN"] = pd.to_numeric(result["SEQ"], errors="coerce")
    result = result.sort_values(
        ["_ORD", "USUBJID", "_SEQN"], na_position="first", kind="mergesort"
    )
    result = result[["CHECK", "USUBJID", "DOMAIN", "SEQ"]]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    result.to_csv(OUTPUT_FILE, index=False)
    print(f"Wrote {len(result)} finding(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
