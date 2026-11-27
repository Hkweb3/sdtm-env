import csv
import os
from collections import defaultdict
from datetime import datetime
from statistics import median

import pandas as pd

INPUT_DIR = "input"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "findings.csv")

SERIOUSNESS_CRITERIA_COLS = [
    "AESCAN", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE", "AESOD",
]


def read_csv(name):
    df = pd.read_csv(
        os.path.join(INPUT_DIR, name),
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    df.columns = [str(c).strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    return df


def full_date(value):
    """Return datetime.date if value starts with a complete YYYY-MM-DD date, else None."""
    if value is None:
        return None
    s = str(value).strip()
    if len(s) < 10:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def to_int(value):
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def to_float(value):
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def main():
    dm = read_csv("dm.csv")
    ae = read_csv("ae.csv")
    ex = read_csv("ex.csv")
    ds = read_csv("ds.csv")
    lb = read_csv("lb.csv")

    findings = []

    def add(check, usubjid, domain, seq=""):
        seq = "" if seq is None else str(seq).strip()
        if seq:
            n = to_int(seq)
            if n is not None:
                seq = str(n)
        findings.append((check, str(usubjid), domain, seq))

    # ------------------------------------------------------------------
    # AE_DATE_ORDER: AE ends before it starts (complete dates only).
    # ------------------------------------------------------------------
    for _, r in ae.iterrows():
        start = full_date(r["AESTDTC"])
        end = full_date(r["AEENDTC"])
        if start is not None and end is not None and end < start:
            add("AE_DATE_ORDER", r["USUBJID"], "AE", r["AESEQ"])

    # ------------------------------------------------------------------
    # AE_DUPLICATE: same AEDECOD + same non-blank AESTDTC for a subject;
    # raise on every copy except the one with the lowest AESEQ.
    # ------------------------------------------------------------------
    dup_groups = defaultdict(list)
    for _, r in ae.iterrows():
        if r["AESTDTC"] != "":
            dup_groups[(r["USUBJID"], r["AEDECOD"], r["AESTDTC"])].append(r)
    for rows in dup_groups.values():
        if len(rows) > 1:
            ordered = sorted(
                rows,
                key=lambda x: (to_int(x["AESEQ"]) is None, to_int(x["AESEQ"]) or 0),
            )
            for r in ordered[1:]:
                add("AE_DUPLICATE", r["USUBJID"], "AE", r["AESEQ"])

    # ------------------------------------------------------------------
    # SAE_CRITERIA: serious flag vs seriousness criteria mismatch.
    # ------------------------------------------------------------------
    for _, r in ae.iterrows():
        serious = r["AESER"].upper() == "Y"
        any_criterion = any(r[c].upper() == "Y" for c in SERIOUSNESS_CRITERIA_COLS)
        if serious != any_criterion:
            add("SAE_CRITERIA", r["USUBJID"], "AE", r["AESEQ"])

    # ------------------------------------------------------------------
    # DEATH_CONSISTENCY
    # ------------------------------------------------------------------
    dthdtc = {r["USUBJID"]: r["DTHDTC"] for _, r in dm.iterrows()}
    subjects_with_fatal_ae = set()

    for _, r in ae.iterrows():
        usubjid = r["USUBJID"]
        death = dthdtc.get(usubjid, "")
        start = full_date(r["AESTDTC"])

        # fatal outcome but no death date recorded in DM
        if r["AEOUT"].upper() == "FATAL":
            subjects_with_fatal_ae.add(usubjid)
            if death == "":
                add("DEATH_CONSISTENCY", usubjid, "AE", r["AESEQ"])

        # complete AE start date after the subject's death date
        if start is not None and death != "":
            death_date = full_date(death)
            if death_date is not None:
                if start > death_date:
                    add("DEATH_CONSISTENCY", usubjid, "AE", r["AESEQ"])
            elif len(death) >= 7 and r["AESTDTC"][:7] > death[:7]:
                add("DEATH_CONSISTENCY", usubjid, "AE", r["AESEQ"])

    # death date recorded but no AE with a fatal outcome
    for _, r in dm.iterrows():
        if r["DTHDTC"] != "" and r["USUBJID"] not in subjects_with_fatal_ae:
            add("DEATH_CONSISTENCY", r["USUBJID"], "DM", "")

    # ------------------------------------------------------------------
    # DOSE_AFTER_DISC: exposure starting after early discontinuation.
    # ------------------------------------------------------------------
    early_disc_date = {}
    for _, r in ds.iterrows():
        if r["DSCAT"].upper() != "DISPOSITION EVENT":
            continue
        if r["DSDECOD"].upper() in ("COMPLETED", "SCREEN FAILURE"):
            continue
        d = full_date(r["DSSTDTC"])
        if d is None:
            continue
        usubjid = r["USUBJID"]
        if usubjid not in early_disc_date or d < early_disc_date[usubjid]:
            early_disc_date[usubjid] = d

    for _, r in ex.iterrows():
        usubjid = r["USUBJID"]
        if usubjid in early_disc_date:
            start = full_date(r["EXSTDTC"])
            if start is not None and start > early_disc_date[usubjid]:
                add("DOSE_AFTER_DISC", usubjid, "EX", r["EXSEQ"])

    # ------------------------------------------------------------------
    # LAB_UNIT: numeric result >= 8x or <= 1/8 of the median of the
    # subject's other results for the same test (needs >= 2 others).
    # ------------------------------------------------------------------
    lb_by_subject_test = defaultdict(list)
    for _, r in lb.iterrows():
        lb_by_subject_test[(r["USUBJID"], r["LBTESTCD"])].append(
            (r, to_float(r["LBSTRESN"]))
        )

    for (usubjid, _test), items in lb_by_subject_test.items():
        for i, (rec, value) in enumerate(items):
            if value is None:
                continue
            others = [v for j, (_, v) in enumerate(items) if j != i and v is not None]
            if len(others) < 2:
                continue
            med = median(others)
            if med <= 0:
                continue
            ratio = value / med
            if ratio >= 8 - 1e-9 or ratio <= 0.125 + 1e-9:
                add("LAB_UNIT", usubjid, "LB", rec["LBSEQ"])

    # ------------------------------------------------------------------
    # LAB_VISIT_DATE: at scheduled visits only, a result dated earlier
    # than the latest date of the same subject/test at lower VISITNUMs.
    # ------------------------------------------------------------------
    sched_by_subject_test = defaultdict(list)
    for _, r in lb.iterrows():
        if r["VISIT"].upper().startswith("UNSCHEDULED"):
            continue
        sched_by_subject_test[(r["USUBJID"], r["LBTESTCD"])].append(
            (to_float(r["VISITNUM"]), full_date(r["LBDTC"]), r)
        )

    for (usubjid, _test), items in sched_by_subject_test.items():
        for visitnum, res_date, rec in items:
            if visitnum is None or res_date is None:
                continue
            earlier_dates = [
                d for v, d, _ in items
                if v is not None and v < visitnum and d is not None
            ]
            if earlier_dates and res_date < max(earlier_dates):
                add("LAB_VISIT_DATE", usubjid, "LB", rec["LBSEQ"])

    # ------------------------------------------------------------------
    # Write findings (deduplicated).
    # ------------------------------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    seen = set()
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["CHECK", "USUBJID", "DOMAIN", "SEQ"])
        for row in findings:
            if row in seen:
                continue
            seen.add(row)
            writer.writerow(row)


if __name__ == "__main__":
    main()
