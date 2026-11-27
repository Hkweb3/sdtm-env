import os

import numpy as np
import pandas as pd

IN_DIR = "input"
OUT_DIR = "output"

dm = pd.read_csv(os.path.join(IN_DIR, "dm.csv"), dtype=str).fillna("")
ae = pd.read_csv(os.path.join(IN_DIR, "ae.csv"), dtype=str).fillna("")
ex = pd.read_csv(os.path.join(IN_DIR, "ex.csv"), dtype=str).fillna("")
ds = pd.read_csv(os.path.join(IN_DIR, "ds.csv"), dtype=str).fillna("")
lb = pd.read_csv(os.path.join(IN_DIR, "lb.csv"), dtype=str).fillna("")

findings = []


def add(check, usubjid, domain, seq):
    findings.append((check, usubjid, domain, seq))


def is_complete_date(s):
    s = str(s).strip()
    return len(s) == 10 and s[4] == "-" and s[7] == "-"


# ---- AE_DATE_ORDER: AE ends before it starts (complete dates only) ----
for _, r in ae.iterrows():
    s, e = r["AESTDTC"].strip(), r["AEENDTC"].strip()
    if is_complete_date(s) and is_complete_date(e) and e < s:
        add("AE_DATE_ORDER", r["USUBJID"], "AE", int(r["AESEQ"]))

# ---- AE_DUPLICATE: same AEDECOD + same non-blank AESTDTC ----
ae_d = ae[ae["AESTDTC"].str.strip() != ""]
for (u, dec, dt), g in ae_d.groupby(["USUBJID", "AEDECOD", "AESTDTC"]):
    if len(g) > 1:
        seqs = sorted(int(x) for x in g["AESEQ"])
        for sq in seqs[1:]:  # keep the lowest AESEQ
            add("AE_DUPLICATE", u, "AE", sq)

# ---- SAE_CRITERIA: AESER vs seriousness criteria ----
crit_cols = ["AESCAN", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE", "AESOD"]
for _, r in ae.iterrows():
    any_y = any(r[c].strip().upper() == "Y" for c in crit_cols)
    serious = r["AESER"].strip().upper() == "Y"
    if serious != any_y:
        add("SAE_CRITERIA", r["USUBJID"], "AE", int(r["AESEQ"]))

# ---- DEATH_CONSISTENCY ----
dthdtc = dm.set_index("USUBJID")["DTHDTC"].to_dict()
fatal_subj = set(ae.loc[ae["AEOUT"].str.strip().str.upper() == "FATAL", "USUBJID"])
for _, r in ae.iterrows():
    u = r["USUBJID"]
    d = str(dthdtc.get(u, "")).strip()
    # fatal AE but no death date in DM
    if r["AEOUT"].strip().upper() == "FATAL" and d == "":
        add("DEATH_CONSISTENCY", u, "AE", int(r["AESEQ"]))
    # AE starts after death
    if (d != "" and is_complete_date(d) and is_complete_date(r["AESTDTC"])
            and r["AESTDTC"].strip() > d):
        add("DEATH_CONSISTENCY", u, "AE", int(r["AESEQ"]))
# death date but no fatal AE
for _, r in dm.iterrows():
    if r["DTHDTC"].strip() != "" and r["USUBJID"] not in fatal_subj:
        add("DEATH_CONSISTENCY", r["USUBJID"], "DM", "")

# ---- DOSE_AFTER_DISC: exposure starting after early discontinuation ----
disc = ds[(ds["DSCAT"].str.strip().str.upper() == "DISPOSITION EVENT")
          & (~ds["DSDECOD"].str.strip().str.upper().isin(["COMPLETED", "SCREEN FAILURE"]))]
disc_date = {}
for _, r in disc.iterrows():
    d = r["DSSTDTC"].strip()
    if is_complete_date(d):
        u = r["USUBJID"]
        if u not in disc_date or d < disc_date[u]:
            disc_date[u] = d
for _, r in ex.iterrows():
    u = r["USUBJID"]
    s = r["EXSTDTC"].strip()
    if u in disc_date and is_complete_date(s) and s > disc_date[u]:
        add("DOSE_AFTER_DISC", u, "EX", int(r["EXSEQ"]))

# ---- LAB_UNIT: result >= 8x or <= 1/8 of median of subject's other results ----
lb["_val"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")
for (u, t), g in lb.groupby(["USUBJID", "LBTESTCD"]):
    vals = g["_val"].to_numpy(dtype=float)
    seqs = g["LBSEQ"].to_numpy()
    for i in range(len(g)):
        v = vals[i]
        if np.isnan(v):
            continue
        others = np.delete(vals, i)
        others = others[~np.isnan(others)]
        if len(others) < 2:
            continue
        med = np.median(others)
        if med == 0:
            continue
        if v >= 8 * med or v <= med / 8:
            add("LAB_UNIT", u, "LB", int(seqs[i]))

# ---- LAB_VISIT_DATE: result dated before latest date at earlier scheduled visits ----
lbs = lb[~lb["VISIT"].str.strip().str.upper().str.startswith("UNSCHEDULED")].copy()
lbs["_date"] = lbs["LBDTC"].str.strip().str[:10]
lbs = lbs[lbs["_date"].str.len() == 10]
lbs["_vn"] = pd.to_numeric(lbs["VISITNUM"], errors="coerce")
lbs = lbs.dropna(subset=["_vn"])
for (u, t), g in lbs.groupby(["USUBJID", "LBTESTCD"]):
    max_prior = None
    for vn, gv in g.groupby("_vn"):  # ascending visit number
        if max_prior is not None:
            for _, r in gv.iterrows():
                if r["_date"] < max_prior:
                    add("LAB_VISIT_DATE", u, "LB", int(r["LBSEQ"]))
        cur = gv["_date"].max()
        if max_prior is None or cur > max_prior:
            max_prior = cur

# ---- write output ----
out = pd.DataFrame(findings, columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])
out = out.drop_duplicates()
os.makedirs(OUT_DIR, exist_ok=True)
out.to_csv(os.path.join(OUT_DIR, "findings.csv"), index=False)
