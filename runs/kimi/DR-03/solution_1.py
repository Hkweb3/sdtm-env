import os

import numpy as np
import pandas as pd

IN_DIR = "input"
OUT_DIR = "output"

ae = pd.read_csv(os.path.join(IN_DIR, "ae.csv"), dtype=str)
dm = pd.read_csv(os.path.join(IN_DIR, "dm.csv"), dtype=str)
ds = pd.read_csv(os.path.join(IN_DIR, "ds.csv"), dtype=str)
ex = pd.read_csv(os.path.join(IN_DIR, "ex.csv"), dtype=str)
lb = pd.read_csv(os.path.join(IN_DIR, "lb.csv"), dtype=str)

ae["AESEQ"] = pd.to_numeric(ae["AESEQ"], errors="coerce")
ex["EXSEQ"] = pd.to_numeric(ex["EXSEQ"], errors="coerce")
lb["LBSEQ"] = pd.to_numeric(lb["LBSEQ"], errors="coerce")
lb["VISITNUM"] = pd.to_numeric(lb["VISITNUM"], errors="coerce")
lb["LBSTRESN"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")


def complete_date(s):
    """Parse only complete YYYY-MM-DD dates; anything else becomes NaT."""
    s = s.fillna("")
    return pd.to_datetime(s.where(s.str.len() == 10),
                          format="%Y-%m-%d", errors="coerce")


ae["_start"] = complete_date(ae["AESTDTC"])
ae["_end"] = complete_date(ae["AEENDTC"])
dm["_dth"] = complete_date(dm["DTHDTC"])
ex["_start"] = complete_date(ex["EXSTDTC"])
ds["_dt"] = complete_date(ds["DSSTDTC"])
lb["_date"] = pd.to_datetime(lb["LBDTC"].fillna("").str.slice(0, 10),
                             format="%Y-%m-%d", errors="coerce")

findings = []


def add(check, usubjid, domain, seq):
    findings.append({"CHECK": check, "USUBJID": usubjid,
                     "DOMAIN": domain, "SEQ": seq})


# --- AE_DATE_ORDER: AE ends before it starts (complete dates only) -------
m = ae["_start"].notna() & ae["_end"].notna() & (ae["_end"] < ae["_start"])
for _, r in ae.loc[m].iterrows():
    add("AE_DATE_ORDER", r["USUBJID"], "AE", int(r["AESEQ"]))

# --- AE_DUPLICATE: same AEDECOD + same non-blank AESTDTC -----------------
d = ae.loc[ae["AESTDTC"].fillna("") != ""]
for _, g in d.groupby(["USUBJID", "AEDECOD", "AESTDTC"]):
    if len(g) > 1:
        for _, r in g.sort_values("AESEQ").iloc[1:].iterrows():
            add("AE_DUPLICATE", r["USUBJID"], "AE", int(r["AESEQ"]))

# --- SAE_CRITERIA: AESER disagrees with seriousness criteria -------------
crit_cols = ["AESCAN", "AESCONG", "AESDISAB", "AESDTH",
             "AESHOSP", "AESLIFE", "AESOD"]
any_crit = ae[crit_cols].fillna("").eq("Y").any(axis=1)
serious = ae["AESER"].fillna("").eq("Y")
for _, r in ae.loc[serious != any_crit].iterrows():
    add("SAE_CRITERIA", r["USUBJID"], "AE", int(r["AESEQ"]))

# --- DEATH_CONSISTENCY ----------------------------------------------------
dth_raw = dm.set_index("USUBJID")["DTHDTC"].fillna("")
dth_dt = dm.set_index("USUBJID")["_dth"]
for _, r in ae.iterrows():
    subj = r["USUBJID"]
    raw = dth_raw.get(subj, "")
    dd = dth_dt.get(subj, pd.NaT)
    if r["AEOUT"] == "FATAL" and raw == "":
        add("DEATH_CONSISTENCY", subj, "AE", int(r["AESEQ"]))
    if pd.notna(r["_start"]) and pd.notna(dd) and r["_start"] > dd:
        add("DEATH_CONSISTENCY", subj, "AE", int(r["AESEQ"]))
fatal_subj = set(ae.loc[ae["AEOUT"].fillna("") == "FATAL", "USUBJID"])
for _, r in dm.iterrows():
    v = r["DTHDTC"]
    if pd.notna(v) and str(v).strip() != "" and r["USUBJID"] not in fatal_subj:
        add("DEATH_CONSISTENCY", r["USUBJID"], "DM", "")

# --- DOSE_AFTER_DISC: EX starts after early discontinuation --------------
disp = ds.loc[ds["DSCAT"].fillna("") == "DISPOSITION EVENT"]
early = disp.loc[~disp["DSDECOD"].fillna("").isin(["COMPLETED", "SCREEN FAILURE"])]
disc = early.groupby("USUBJID")["_dt"].min()
for _, r in ex.iterrows():
    dd = disc.get(r["USUBJID"], pd.NaT)
    if pd.notna(r["_start"]) and pd.notna(dd) and r["_start"] > dd:
        add("DOSE_AFTER_DISC", r["USUBJID"], "EX", int(r["EXSEQ"]))

# --- LAB_UNIT: result >= 8x or <= 1/8 of median of subject's other results
ln = lb.dropna(subset=["LBSTRESN"])
for (subj, test), g in ln.groupby(["USUBJID", "LBTESTCD"]):
    if len(g) < 3:  # need at least two other results
        continue
    vals = g["LBSTRESN"].to_numpy(dtype=float)
    seqs = g["LBSEQ"].to_numpy()
    for i in range(len(g)):
        med = float(np.median(np.delete(vals, i)))
        if med <= 0:
            continue
        if vals[i] >= 8 * med or vals[i] <= med / 8:
            add("LAB_UNIT", subj, "LB", int(seqs[i]))

# --- LAB_VISIT_DATE: result dated before latest date at earlier visits ---
unsched = lb["VISIT"].fillna("").str.upper().str.startswith("UNSCHEDULED")
sched = lb.loc[~unsched & lb["_date"].notna() & lb["VISITNUM"].notna()]
for (subj, test), g in sched.groupby(["USUBJID", "LBTESTCD"]):
    vns = g["VISITNUM"].to_numpy()
    dates = g["_date"].to_numpy()
    seqs = g["LBSEQ"].to_numpy()
    for i in range(len(g)):
        earlier = dates[vns < vns[i]]
        if earlier.size and dates[i] < earlier.max():
            add("LAB_VISIT_DATE", subj, "LB", int(seqs[i]))

# --- write findings -------------------------------------------------------
os.makedirs(OUT_DIR, exist_ok=True)
out = pd.DataFrame(findings, columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])
out = out.drop_duplicates()
k = pd.to_numeric(out["SEQ"], errors="coerce").fillna(-1)
out = out.assign(_k=k).sort_values(["CHECK", "USUBJID", "DOMAIN", "_k"])
out = out.drop(columns="_k")
out.to_csv(os.path.join(OUT_DIR, "findings.csv"), index=False)
