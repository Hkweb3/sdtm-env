import os
from datetime import datetime

import pandas as pd

INPUT_DIR = "input"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "findings.csv")

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


def read_raw(name):
    df = pd.read_csv(
        os.path.join(INPUT_DIR, name),
        dtype=str,
        keep_default_na=False,
        na_values=[],
        encoding="utf-8-sig",
    )
    df.columns = [c.strip() for c in df.columns]
    return df


def complete_date(value):
    """Return the YYYY-MM-DD part if value holds a complete date, else None."""
    if value is None:
        return None
    s = str(value).strip()
    if len(s) < 10:
        return None
    candidate = s[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def to_int(value):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


findings = []


def add(check, usubjid, domain, seq=None):
    findings.append({"CHECK": check, "USUBJID": usubjid, "DOMAIN": domain, "SEQ": seq})


def main():
    dm = read_raw("dm.csv")
    ae = read_raw("ae.csv")
    ex = read_raw("ex.csv")
    ds = read_raw("ds.csv")
    lb = read_raw("lb.csv")

    # ---------------- AE_DATE_ORDER ----------------
    for _, r in ae.iterrows():
        start = complete_date(r["AESTDTC"])
        end = complete_date(r["AEENDTC"])
        if start and end and end < start:
            add("AE_DATE_ORDER", r["USUBJID"], "AE", to_int(r["AESEQ"]))

    # ---------------- AE_DUPLICATE ----------------
    ae_dup = ae.copy()
    ae_dup["_start"] = ae_dup["AESTDTC"].astype(str).str.strip()
    ae_dup["_seq"] = ae_dup["AESEQ"].map(to_int)
    for subj, g in ae_dup[ae_dup["_start"] != ""].groupby(
        ["USUBJID", "AEDECOD", "_start"], sort=False
    ):
        if len(g) < 2:
            continue
        min_seq = g["_seq"].min()
        for _, r in g.iterrows():
            if r["_seq"] != min_seq:
                add("AE_DUPLICATE", subj[0], "AE", r["_seq"])

    # ---------------- SAE_CRITERIA ----------------
    for _, r in ae.iterrows():
        ser = str(r["AESER"]).strip().upper()
        any_y = any(str(r[c]).strip().upper() == "Y" for c in CRIT_COLS)
        if (ser == "Y" and not any_y) or (ser != "Y" and any_y):
            add("SAE_CRITERIA", r["USUBJID"], "AE", to_int(r["AESEQ"]))

    # ---------------- DEATH_CONSISTENCY ----------------
    dth_raw = {}
    dth_complete = {}
    for _, r in dm.iterrows():
        subj = r["USUBJID"]
        raw = str(r["DTHDTC"]).strip()
        dth_raw[subj] = raw
        dth_complete[subj] = complete_date(raw)

    fatal_subjects = set(
        ae.loc[ae["AEOUT"].astype(str).str.strip().str.upper() == "FATAL", "USUBJID"]
    )

    for _, r in ae.iterrows():
        subj = r["USUBJID"]
        seq = to_int(r["AESEQ"])
        # fatal AE but no death date in DM
        if str(r["AEOUT"]).strip().upper() == "FATAL" and not dth_raw.get(subj, ""):
            add("DEATH_CONSISTENCY", subj, "AE", seq)
        # AE with complete start date after the death date
        start = complete_date(r["AESTDTC"])
        death = dth_complete.get(subj)
        if start and death and start > death:
            add("DEATH_CONSISTENCY", subj, "AE", seq)

    for _, r in dm.iterrows():
        subj = r["USUBJID"]
        if dth_raw.get(subj, "") and subj not in fatal_subjects:
            add("DEATH_CONSISTENCY", subj, "DM", None)

    # ---------------- DOSE_AFTER_DISC ----------------
    early_disc = {}
    for _, r in ds.iterrows():
        if str(r["DSCAT"]).strip().upper() != "DISPOSITION EVENT":
            continue
        if str(r["DSDECOD"]).strip().upper() in ("COMPLETED", "SCREEN FAILURE"):
            continue
        d = complete_date(r["DSSTDTC"])
        if d:
            early_disc.setdefault(r["USUBJID"], []).append(d)

    for _, r in ex.iterrows():
        start = complete_date(r["EXSTDTC"])
        dates = early_disc.get(r["USUBJID"], [])
        if start and dates and start > min(dates):
            add("DOSE_AFTER_DISC", r["USUBJID"], "EX", to_int(r["EXSEQ"]))

    # ---------------- LAB_UNIT ----------------
    lb["_val"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")
    lb["_seq"] = lb["LBSEQ"].map(to_int)
    for (subj, _test), g in lb.groupby(["USUBJID", "LBTESTCD"], sort=False):
        numeric = g[g["_val"].notna()]
        if len(numeric) < 3:
            continue
        for idx, r in numeric.iterrows():
            others = numeric["_val"].drop(idx)
            if len(others) < 2:
                continue
            med = others.median()
            if pd.isna(med) or med == 0:
                continue
            v = r["_val"]
            if v >= 8 * med or v <= med / 8:
                add("LAB_UNIT", subj, "LB", r["_seq"])

    # ---------------- LAB_VISIT_DATE ----------------
    lb["_visitnum"] = pd.to_numeric(lb["VISITNUM"], errors="coerce")
    lb["_date"] = lb["LBDTC"].map(complete_date)
    visit_up = lb["VISIT"].astype(str).str.strip().str.upper()
    lb["_sched"] = ~visit_up.str.startswith("UNSCHEDULED")

    for (subj, _test), g in lb.groupby(["USUBJID", "LBTESTCD"], sort=False):
        sched = g[g["_sched"] & g["_date"].notna() & g["_visitnum"].notna()]
        if sched.empty:
            continue
        for idx, r in sched.iterrows():
            earlier = sched[sched["_visitnum"] < r["_visitnum"]]
            if earlier.empty:
                continue
            latest = earlier["_date"].max()
            if r["_date"] < latest:
                add("LAB_VISIT_DATE", subj, "LB", r["_seq"])

    # ---------------- write output ----------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    res = pd.DataFrame(findings, columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])
    res = res.drop_duplicates(subset=["CHECK", "USUBJID", "DOMAIN", "SEQ"])
    order_map = {c: i for i, c in enumerate(CHECK_ORDER)}
    res["_order"] = res["CHECK"].map(order_map)
    res["_seqsort"] = res["SEQ"].map(lambda x: -1 if x is None else int(x))
    res = res.sort_values(["_order", "USUBJID", "DOMAIN", "_seqsort"], kind="mergesort")
    res = res[["CHECK", "USUBJID", "DOMAIN", "SEQ"]].copy()
    res["SEQ"] = res["SEQ"].map(lambda x: "" if x is None else str(int(x)))
    res.to_csv(OUTPUT_FILE, index=False)
    print("Wrote %d finding(s) to %s" % (len(res), OUTPUT_FILE))


main()
