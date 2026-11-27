import os

import pandas as pd

IN_DIR = "input"
OUT_DIR = "output"


def read_domain(name):
    return pd.read_csv(os.path.join(IN_DIR, name), dtype=str, keep_default_na=False)


def complete_date(value):
    """Return the date part of a complete date/datetime string, else NaT."""
    s = str(value).strip()
    if len(s) >= 10:
        return pd.to_datetime(s[:10], format="%Y-%m-%d", errors="coerce")
    return pd.NaT


dm = read_domain("dm.csv")
ae = read_domain("ae.csv")
ex = read_domain("ex.csv")
ds = read_domain("ds.csv")
lb = read_domain("lb.csv")

findings = []


def add(check, usubjid, domain, seq):
    findings.append((check, usubjid, domain, seq))


# ---------------- AE ----------------
ae["AESEQ_i"] = pd.to_numeric(ae["AESEQ"], errors="coerce")
ae["_start"] = ae["AESTDTC"].map(complete_date)
ae["_end"] = ae["AEENDTC"].map(complete_date)

# AE_DATE_ORDER: AE ends before it starts (complete dates only)
mask = ae["_start"].notna() & ae["_end"].notna() & (ae["_end"] < ae["_start"])
for _, row in ae.loc[mask].iterrows():
    add("AE_DATE_ORDER", row["USUBJID"], "AE", int(row["AESEQ_i"]))

# AE_DUPLICATE: same AEDECOD + same non-blank AESTDTC; flag all but lowest AESEQ
dated = ae.loc[ae["AESTDTC"].str.strip() != ""]
for (subj, decod, stdtc), grp in dated.groupby(
    ["USUBJID", "AEDECOD", "AESTDTC"], sort=False
):
    if len(grp) > 1:
        lowest = grp["AESEQ_i"].min()
        for _, row in grp.iterrows():
            if row["AESEQ_i"] != lowest:
                add("AE_DUPLICATE", subj, "AE", int(row["AESEQ_i"]))

# SAE_CRITERIA: AESER vs seriousness criteria mismatch
crit_cols = ["AESCAN", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE", "AESOD"]
any_crit = ae[crit_cols].apply(lambda c: c.str.strip().str.upper() == "Y").any(axis=1)
is_ser = ae["AESER"].str.strip().str.upper() == "Y"
mask = (is_ser & ~any_crit) | (~is_ser & any_crit)
for _, row in ae.loc[mask].iterrows():
    add("SAE_CRITERIA", row["USUBJID"], "AE", int(row["AESEQ_i"]))

# DEATH_CONSISTENCY
dm["_dth"] = dm["DTHDTC"].map(complete_date)
death_dt = dict(zip(dm["USUBJID"], dm["_dth"]))
has_death = dict(zip(dm["USUBJID"], dm["DTHDTC"].str.strip() != ""))
is_fatal = ae["AEOUT"].str.strip().str.upper() == "FATAL"
fatal_subjects = set(ae.loc[is_fatal, "USUBJID"])

for _, row in ae.iterrows():
    subj = row["USUBJID"]
    # fatal AE but no death date in DM
    if row["AEOUT"].strip().upper() == "FATAL" and not has_death.get(subj, False):
        add("DEATH_CONSISTENCY", subj, "AE", int(row["AESEQ_i"]))
    # AE starts after death date
    dd = death_dt.get(subj, pd.NaT)
    if pd.notna(dd) and pd.notna(row["_start"]) and row["_start"] > dd:
        add("DEATH_CONSISTENCY", subj, "AE", int(row["AESEQ_i"]))

# death date but no fatal AE
for _, row in dm.iterrows():
    subj = row["USUBJID"]
    if row["DTHDTC"].strip() != "" and subj not in fatal_subjects:
        add("DEATH_CONSISTENCY", subj, "DM", "")

# ---------------- EX / DS ----------------
ds["_date"] = ds["DSSTDTC"].map(complete_date)
early = ds.loc[
    (ds["DSCAT"].str.strip().str.upper() == "DISPOSITION EVENT")
    & ~ds["DSDECOD"].str.strip().str.upper().isin(["COMPLETED", "SCREEN FAILURE"])
]
disc_date = early.groupby("USUBJID")["_date"].min().to_dict()

ex["EXSEQ_i"] = pd.to_numeric(ex["EXSEQ"], errors="coerce")
ex["_start"] = ex["EXSTDTC"].map(complete_date)

# DOSE_AFTER_DISC: exposure starts after early discontinuation date
for _, row in ex.iterrows():
    dd = disc_date.get(row["USUBJID"])
    if dd is not None and pd.notna(dd) and pd.notna(row["_start"]) and row["_start"] > dd:
        add("DOSE_AFTER_DISC", row["USUBJID"], "EX", int(row["EXSEQ_i"]))

# ---------------- LB ----------------
lb["LBSEQ_i"] = pd.to_numeric(lb["LBSEQ"], errors="coerce")
lb["_val"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")
lb["_date"] = lb["LBDTC"].map(complete_date)
lb["_vn"] = pd.to_numeric(lb["VISITNUM"], errors="coerce")

# LAB_UNIT: value >= 8x or <= 1/8 of median of subject's other results for the test
for (subj, test), grp in lb.groupby(["USUBJID", "LBTESTCD"], sort=False):
    vals = grp["_val"]
    for idx, row in grp.iterrows():
        v = row["_val"]
        if pd.isna(v):
            continue
        others = vals.drop(index=idx).dropna()
        if len(others) < 2:
            continue
        med = others.median()
        if pd.isna(med):
            continue
        if v >= 8 * med or v <= med / 8:
            add("LAB_UNIT", subj, "LB", int(row["LBSEQ_i"]))

# LAB_VISIT_DATE: result dated before latest date at earlier scheduled visits
sched = lb.loc[~lb["VISIT"].str.strip().str.upper().str.startswith("UNSCHEDULED")]
for (subj, test), grp in sched.groupby(["USUBJID", "LBTESTCD"], sort=False):
    grp = grp.dropna(subset=["_vn"])
    threshold = {}
    running = None
    for vn in sorted(grp["_vn"].unique()):
        threshold[vn] = running
        mx = grp.loc[grp["_vn"] == vn, "_date"].max()
        if pd.notna(mx):
            running = mx if running is None else max(running, mx)
    for _, row in grp.iterrows():
        t = threshold.get(row["_vn"])
        if t is not None and pd.notna(row["_date"]) and row["_date"] < t:
            add("LAB_VISIT_DATE", subj, "LB", int(row["LBSEQ_i"]))

# ---------------- output ----------------
out = pd.DataFrame(findings, columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])
out = out.drop_duplicates()
os.makedirs(OUT_DIR, exist_ok=True)
out.to_csv(os.path.join(OUT_DIR, "findings.csv"), index=False)
