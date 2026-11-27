import os

import numpy as np
import pandas as pd

INPUT_DIR = "input"
OUTPUT_DIR = "output"

dm = pd.read_csv(os.path.join(INPUT_DIR, "dm.csv"), dtype=str).fillna("")
ae = pd.read_csv(os.path.join(INPUT_DIR, "ae.csv"), dtype=str).fillna("")
ex = pd.read_csv(os.path.join(INPUT_DIR, "ex.csv"), dtype=str).fillna("")
ds = pd.read_csv(os.path.join(INPUT_DIR, "ds.csv"), dtype=str).fillna("")
lb = pd.read_csv(os.path.join(INPUT_DIR, "lb.csv"), dtype=str).fillna("")

ae["AESEQ"] = ae["AESEQ"].astype(int)
ex["EXSEQ"] = ex["EXSEQ"].astype(int)
lb["LBSEQ"] = lb["LBSEQ"].astype(int)

findings = []


def add(check, usubjid, domain, seq):
    findings.append({"CHECK": check, "USUBJID": usubjid, "DOMAIN": domain, "SEQ": seq})


def complete_date_mask(s):
    # complete date = YYYY-MM-DD (optionally followed by a time part)
    return s.str.match(r"^\d{4}-\d{2}-\d{2}") & pd.to_datetime(
        s.str[:10], errors="coerce"
    ).notna()


def as_date(s):
    # date part only, ignoring any time component
    return pd.to_datetime(s.str[:10], errors="coerce")


# ---------------- AE_DATE_ORDER ----------------
m = complete_date_mask(ae["AESTDTC"]) & complete_date_mask(ae["AEENDTC"])
sub = ae[m]
bad = sub[as_date(sub["AEENDTC"]) < as_date(sub["AESTDTC"])]
for _, r in bad.iterrows():
    add("AE_DATE_ORDER", r["USUBJID"], "AE", int(r["AESEQ"]))

# ---------------- AE_DUPLICATE ----------------
sub = ae[ae["AESTDTC"] != ""]
for (usubjid, _decod, _stdtc), grp in sub.groupby(["USUBJID", "AEDECOD", "AESTDTC"]):
    seqs = sorted(int(s) for s in grp["AESEQ"])
    for s in seqs[1:]:  # every copy except the lowest AESEQ
        add("AE_DUPLICATE", usubjid, "AE", s)

# ---------------- SAE_CRITERIA ----------------
crit_cols = ["AESCAN", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE", "AESOD"]
any_crit = ae[crit_cols].apply(lambda c: c.str.strip().str.upper()).eq("Y").any(axis=1)
serious = ae["AESER"].str.strip().str.upper() == "Y"
bad = ae[(serious & ~any_crit) | (~serious & any_crit)]
for _, r in bad.iterrows():
    add("SAE_CRITERIA", r["USUBJID"], "AE", int(r["AESEQ"]))

# ---------------- DEATH_CONSISTENCY ----------------
dthdtc = dm.set_index("USUBJID")["DTHDTC"]
dth_date = as_date(dthdtc)

fatal = ae[ae["AEOUT"].str.strip().str.upper() == "FATAL"]
fatal_subjects = set(fatal["USUBJID"])

# fatal AE but no death date in DM
for _, r in fatal.iterrows():
    if dthdtc.get(r["USUBJID"], "") == "":
        add("DEATH_CONSISTENCY", r["USUBJID"], "AE", int(r["AESEQ"]))

# AE with complete start date after the death date
sub = ae[complete_date_mask(ae["AESTDTC"])]
starts = as_date(sub["AESTDTC"])
for idx, r in sub.iterrows():
    dd = dth_date.get(r["USUBJID"])
    if pd.notna(dd) and pd.notna(starts[idx]) and starts[idx] > dd:
        add("DEATH_CONSISTENCY", r["USUBJID"], "AE", int(r["AESEQ"]))

# death date but no AE with fatal outcome
for _, r in dm.iterrows():
    if r["DTHDTC"] != "" and r["USUBJID"] not in fatal_subjects:
        add("DEATH_CONSISTENCY", r["USUBJID"], "DM", "")

# ---------------- DOSE_AFTER_DISC ----------------
disc = ds[
    (ds["DSCAT"].str.strip().str.upper() == "DISPOSITION EVENT")
    & (~ds["DSDECOD"].str.strip().str.upper().isin(["COMPLETED", "SCREEN FAILURE"]))
].copy()
disc["disc_date"] = as_date(disc["DSSTDTC"])
disc_date = disc.groupby("USUBJID")["disc_date"].min()

ex_start = as_date(ex["EXSTDTC"])
for idx, r in ex.iterrows():
    dd = disc_date.get(r["USUBJID"])
    if pd.notna(dd) and pd.notna(ex_start[idx]) and ex_start[idx] > dd:
        add("DOSE_AFTER_DISC", r["USUBJID"], "EX", int(r["EXSEQ"]))

# ---------------- LAB_UNIT ----------------
lb["_num"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")
for (usubjid, testcd), grp in lb[lb["_num"].notna()].groupby(["USUBJID", "LBTESTCD"]):
    vals = grp["_num"].to_numpy(dtype=float)
    if len(vals) < 3:  # need at least two other results
        continue
    seqs = grp["LBSEQ"].to_numpy()
    for i in range(len(vals)):
        med = float(np.median(np.delete(vals, i)))
        if med > 0 and (vals[i] >= 8 * med or vals[i] <= med / 8):
            add("LAB_UNIT", usubjid, "LB", int(seqs[i]))

# ---------------- LAB_VISIT_DATE ----------------
lb["_date"] = as_date(lb["LBDTC"])
lb["_visitnum"] = pd.to_numeric(lb["VISITNUM"], errors="coerce")
sched = lb[
    (~lb["VISIT"].str.strip().str.upper().str.startswith("UNSCHEDULED"))
    & lb["_date"].notna()
    & lb["_visitnum"].notna()
]
for (usubjid, testcd), grp in sched.groupby(["USUBJID", "LBTESTCD"]):
    by_visit = grp.groupby("_visitnum")["_date"].max().sort_index()
    prev_max = by_visit.cummax().shift()  # latest date at earlier scheduled visits
    pm = grp["_visitnum"].map(prev_max)
    bad = grp[grp["_date"] < pm]
    for _, r in bad.iterrows():
        add("LAB_VISIT_DATE", usubjid, "LB", int(r["LBSEQ"]))

# ---------------- output ----------------
out = pd.DataFrame(findings, columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])
out = out.drop_duplicates()

check_order = [
    "AE_DATE_ORDER",
    "AE_DUPLICATE",
    "SAE_CRITERIA",
    "DEATH_CONSISTENCY",
    "DOSE_AFTER_DISC",
    "LAB_UNIT",
    "LAB_VISIT_DATE",
]
out["_c"] = out["CHECK"].map({c: i for i, c in enumerate(check_order)})
out["_s"] = pd.to_numeric(out["SEQ"], errors="coerce").fillna(-1)
out = out.sort_values(["_c", "USUBJID", "DOMAIN", "_s"]).drop(columns=["_c", "_s"])

os.makedirs(OUTPUT_DIR, exist_ok=True)
out.to_csv(os.path.join(OUTPUT_DIR, "findings.csv"), index=False)
