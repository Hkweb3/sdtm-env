import os
import pandas as pd

INPUT_DIR = "input"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

dm = pd.read_csv(os.path.join(INPUT_DIR, "dm.csv"), dtype=str).fillna("")
ae = pd.read_csv(os.path.join(INPUT_DIR, "ae.csv"), dtype=str).fillna("")
ex = pd.read_csv(os.path.join(INPUT_DIR, "ex.csv"), dtype=str).fillna("")
ds = pd.read_csv(os.path.join(INPUT_DIR, "ds.csv"), dtype=str).fillna("")
lb = pd.read_csv(os.path.join(INPUT_DIR, "lb.csv"), dtype=str).fillna("")

ae["AESEQ"] = ae["AESEQ"].astype(int)
ex["EXSEQ"] = ex["EXSEQ"].astype(int)
lb["LBSEQ"] = lb["LBSEQ"].astype(int)
lb["LBSTRESN"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")
lb["VISITNUM"] = pd.to_numeric(lb["VISITNUM"], errors="coerce")

findings = set()

def add(check, usubjid, domain, seq):
    findings.add((check, usubjid, domain, "" if seq == "" else str(int(seq))))

def complete(d):
    return isinstance(d, str) and len(d.strip()) >= 10

# AE_DATE_ORDER: AE ends before it starts (complete dates only)
for _, r in ae.iterrows():
    if complete(r["AESTDTC"]) and complete(r["AEENDTC"]) and r["AEENDTC"][:10] < r["AESTDTC"][:10]:
        add("AE_DATE_ORDER", r["USUBJID"], "AE", r["AESEQ"])

# AE_DUPLICATE: same AEDECOD + same non-blank AESTDTC for a subject; flag all but lowest AESEQ
for (subj, decod, stdtc), g in ae[ae["AESTDTC"] != ""].groupby(["USUBJID", "AEDECOD", "AESTDTC"]):
    if len(g) > 1:
        keep = g["AESEQ"].min()
        for s in g["AESEQ"]:
            if s != keep:
                add("AE_DUPLICATE", subj, "AE", s)

# SAE_CRITERIA: AESER vs seriousness criteria mismatch
crit_cols = ["AESCAN", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE", "AESOD"]
for _, r in ae.iterrows():
    any_y = any(r[c] == "Y" for c in crit_cols)
    if (r["AESER"] == "Y") != any_y:
        add("SAE_CRITERIA", r["USUBJID"], "AE", r["AESEQ"])

# DEATH_CONSISTENCY
dth = dict(zip(dm["USUBJID"], dm["DTHDTC"]))
fatal_subj = set(ae.loc[ae["AEOUT"] == "FATAL", "USUBJID"])
for _, r in ae.iterrows():
    subj = r["USUBJID"]
    d = dth.get(subj, "")
    if r["AEOUT"] == "FATAL" and d == "":
        add("DEATH_CONSISTENCY", subj, "AE", r["AESEQ"])
    if complete(d) and complete(r["AESTDTC"]) and r["AESTDTC"][:10] > d[:10]:
        add("DEATH_CONSISTENCY", subj, "AE", r["AESEQ"])
for subj, d in dth.items():
    if d != "" and subj not in fatal_subj:
        add("DEATH_CONSISTENCY", subj, "DM", "")

# DOSE_AFTER_DISC: exposure starting after early discontinuation
disc = ds[(ds["DSCAT"] == "DISPOSITION EVENT") & (~ds["DSDECOD"].isin(["COMPLETED", "SCREEN FAILURE"]))]
disc_date = {}
for _, r in disc.iterrows():
    if complete(r["DSSTDTC"]):
        d = r["DSSTDTC"][:10]
        if r["USUBJID"] not in disc_date or d < disc_date[r["USUBJID"]]:
            disc_date[r["USUBJID"]] = d
for _, r in ex.iterrows():
    d = disc_date.get(r["USUBJID"])
    if d and complete(r["EXSTDTC"]) and r["EXSTDTC"][:10] > d:
        add("DOSE_AFTER_DISC", r["USUBJID"], "EX", r["EXSEQ"])

# LAB_UNIT: result >= 8x or <= 1/8 of median of subject's other results for the test
for (subj, test), g in lb.groupby(["USUBJID", "LBTESTCD"]):
    vals = g["LBSTRESN"]
    for idx, v in vals.items():
        if pd.isna(v):
            continue
        others = vals.drop(idx).dropna()
        if len(others) >= 2:
            med = others.median()
            if v >= 8 * med or v <= med / 8:
                add("LAB_UNIT", subj, "LB", g.loc[idx, "LBSEQ"])

# LAB_VISIT_DATE: scheduled visits only; date earlier than latest date at earlier scheduled visits
sched = lb[~lb["VISIT"].str.startswith("UNSCHEDULED")].copy()
sched["LBDATE"] = sched["LBDTC"].str[:10]
for (subj, test), g in sched.groupby(["USUBJID", "LBTESTCD"]):
    for idx, r in g.iterrows():
        if r["LBDATE"] == "" or pd.isna(r["VISITNUM"]):
            continue
        earlier = g[(g["VISITNUM"] < r["VISITNUM"]) & (g["LBDATE"] != "")]
        if len(earlier) and r["LBDATE"] < earlier["LBDATE"].max():
            add("LAB_VISIT_DATE", subj, "LB", r["LBSEQ"])

# Output
order = ["AE_DATE_ORDER", "AE_DUPLICATE", "SAE_CRITERIA", "DEATH_CONSISTENCY",
         "DOSE_AFTER_DISC", "LAB_UNIT", "LAB_VISIT_DATE"]
rows = sorted(findings, key=lambda t: (order.index(t[0]), t[1], t[2],
                                       int(t[3]) if t[3] != "" else -1))
out = pd.DataFrame(rows, columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])
out.to_csv(os.path.join(OUTPUT_DIR, "findings.csv"), index=False)
