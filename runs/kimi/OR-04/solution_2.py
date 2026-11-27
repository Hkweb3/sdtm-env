import os
import re
import pandas as pd
import numpy as np

IN_DIR = "input"
OUT_DIR = "output"
OUT_FILE = os.path.join(OUT_DIR, "findings.csv")
CUTOFF = pd.Timestamp("2013-10-05")

# The earlier failure was almost certainly a missing output directory and/or
# a conditional write. Create the directory up front and always write the file.
os.makedirs(OUT_DIR, exist_ok=True)


def read(name):
    return pd.read_csv(os.path.join(IN_DIR, name), dtype=str)


dm = read("dm.csv")
ae = read("ae.csv")
ex = read("ex.csv")
ds = read("ds.csv")
lb = read("lb.csv")


def to_dt(s):
    return pd.to_datetime(s, errors="coerce")


def to_num(s):
    return pd.to_numeric(s, errors="coerce")


findings = []


def add(priority, usubjid, domain, seq, issue):
    if seq is None or pd.isna(seq):
        seq_out, seq_sort = "", -1
    else:
        seq_out, seq_sort = int(seq), int(seq)
    findings.append({
        "priority": priority,
        "USUBJID": usubjid,
        "DOMAIN": domain,
        "SEQ": seq_out,
        "seq_sort": seq_sort,
        "ISSUE": " ".join(str(issue).split()),
    })


# ---------------- DM ----------------
for c in ["BRTHDTC", "RFSTDTC", "RFENDTC", "DTHDTC"]:
    dm[c + "_dt"] = to_dt(dm[c])
dm["AGE_n"] = to_num(dm["AGE"])

VALID_ARMS = {"Placebo", "Xanomeline Low Dose", "Xanomeline High Dose"}

for _, r in dm.iterrows():
    subj = r["USUBJID"]
    age = r["AGE_n"]
    br, rf, rfe, dth = r["BRTHDTC_dt"], r["RFSTDTC_dt"], r["RFENDTC_dt"], r["DTHDTC_dt"]
    dthfl = str(r["DTHFL"]).strip().upper() if pd.notna(r["DTHFL"]) else ""

    if str(r["ARM"]).strip() not in VALID_ARMS:
        add(40, subj, "DM", None, f"ARM '{r['ARM']}' is not a valid protocol arm")
    if pd.notna(age) and age < 50:
        add(40, subj, "DM", None,
            f"AGE {int(age)} at entry violates key inclusion criterion (age >= 50)")
    if pd.notna(br) and pd.notna(rf) and pd.notna(age):
        calc = rf.year - br.year - ((rf.month, rf.day) < (br.month, br.day))
        if calc != int(age):
            add(45, subj, "DM", None,
                f"AGE {int(age)} inconsistent with BRTHDTC {r['BRTHDTC']} at RFSTDTC {r['RFSTDTC']} (computed {calc})")
    if dthfl == "Y" and pd.isna(dth):
        add(60, subj, "DM", None, "DTHFL is Y but DTHDTC is missing")
    if dthfl != "Y" and pd.notna(dth):
        add(60, subj, "DM", None, f"DTHDTC {r['DTHDTC']} recorded but DTHFL is not Y")
    if pd.notna(dth) and pd.notna(rf) and dth < rf:
        add(10, subj, "DM", None, f"DTHDTC {r['DTHDTC']} is before RFSTDTC {r['RFSTDTC']}")
    if pd.notna(rf) and pd.notna(rfe) and rfe < rf:
        add(60, subj, "DM", None, f"RFENDTC {r['RFENDTC']} is before RFSTDTC {r['RFSTDTC']}")
    for c in ["RFSTDTC", "RFENDTC", "DTHDTC"]:
        d = r[c + "_dt"]
        if pd.notna(d) and d > CUTOFF:
            add(50, subj, "DM", None, f"{c} {r[c]} is after the data cutoff 2013-10-05")

dth_map = dm.set_index("USUBJID")["DTHDTC_dt"].to_dict()
arm_map = dm.set_index("USUBJID")["ARM"].to_dict()
rfst_map = dm.set_index("USUBJID")["RFSTDTC_dt"].to_dict()
dm_subjects = set(dm["USUBJID"].dropna())

# ---------------- EX ----------------
ex["EXSTDTC_dt"] = to_dt(ex["EXSTDTC"])
ex["EXENDTC_dt"] = to_dt(ex["EXENDTC"])
ex["EXDOSE_n"] = to_num(ex["EXDOSE"])
ex["EXSEQ_n"] = to_num(ex["EXSEQ"])


def expected_dose(arm, visit):
    if arm is None or pd.isna(arm):
        return None
    arm = str(arm).strip()
    v = str(visit).upper()
    if arm == "Placebo":
        return 0
    if arm == "Xanomeline Low Dose":
        return 54
    if arm == "Xanomeline High Dose":
        if "BASELINE" in v:
            return 54
        m = re.search(r"WEEK\s+(\d+)", v)
        if m:
            wk = int(m.group(1))
            return 81 if 2 <= wk < 24 else 54
    return None


for _, r in ex.iterrows():
    subj = r["USUBJID"]
    seq = r["EXSEQ_n"]
    arm = arm_map.get(subj)
    trt = str(r["EXTRT"]).upper()
    dose = r["EXDOSE_n"]
    s, e = r["EXSTDTC_dt"], r["EXENDTC_dt"]

    if subj not in dm_subjects:
        add(75, subj, "EX", seq, "USUBJID not present in DM")
    if arm == "Placebo" and "PLACEBO" not in trt:
        add(30, subj, "EX", seq, f"Placebo-arm subject dosed with {r['EXTRT']}")
    if arm in ("Xanomeline Low Dose", "Xanomeline High Dose") and "XANOMELINE" not in trt:
        add(30, subj, "EX", seq, f"{arm} subject dosed with {r['EXTRT']}")
    exp = expected_dose(arm, r["VISIT"])
    if exp is not None and pd.notna(dose) and float(dose) != float(exp):
        add(30, subj, "EX", seq,
            f"{arm} at {r['VISIT']}: EXDOSE {r['EXDOSE']} mg does not match protocol-expected {exp} mg")
    if pd.notna(s) and pd.notna(e) and e < s:
        add(60, subj, "EX", seq, f"EXENDTC {r['EXENDTC']} is before EXSTDTC {r['EXSTDTC']}")
    for c in ["EXSTDTC", "EXENDTC"]:
        d = r[c + "_dt"]
        if pd.notna(d) and d > CUTOFF:
            add(50, subj, "EX", seq, f"{c} {r[c]} is after the data cutoff 2013-10-05")
    dth = dth_map.get(subj)
    if dth is not None and pd.notna(dth):
        if pd.notna(s) and s.normalize() > dth.normalize():
            add(10, subj, "EX", seq, f"Dosing starts {r['EXSTDTC']} after death date {dth.date()}")
        elif pd.notna(e) and e.normalize() > dth.normalize():
            add(10, subj, "EX", seq, f"Dosing continues to {r['EXENDTC']} after death date {dth.date()}")
    rfst = rfst_map.get(subj)
    if rfst is not None and pd.notna(rfst) and pd.notna(s) and s < rfst:
        add(30, subj, "EX", seq,
            f"EXSTDTC {r['EXSTDTC']} precedes RFSTDTC {rfst.date()} (dosing before first-dose date)")

# ---------------- AE ----------------
ae["AESTDTC_dt"] = to_dt(ae["AESTDTC"])
ae["AEENDTC_dt"] = to_dt(ae["AEENDTC"])
ae["AESEQ_n"] = to_num(ae["AESEQ"])

for _, r in ae.iterrows():
    subj = r["USUBJID"]
    seq = r["AESEQ_n"]
    s, e = r["AESTDTC_dt"], r["AEENDTC_dt"]

    if subj not in dm_subjects:
        add(75, subj, "AE", seq, "USUBJID not present in DM")
    if pd.notna(s) and pd.notna(e) and e < s:
        add(60, subj, "AE", seq, f"AEENDTC {r['AEENDTC']} is before AESTDTC {r['AESTDTC']}")
    for c in ["AESTDTC", "AEENDTC"]:
        d = r[c + "_dt"]
        if pd.notna(d) and d > CUTOFF:
            add(50, subj, "AE", seq, f"{c} {r[c]} is after the data cutoff 2013-10-05")
    dth = dth_map.get(subj)
    if dth is not None and pd.notna(dth) and pd.notna(s) and s.normalize() > dth.normalize():
        add(10, subj, "AE", seq, f"AE start {r['AESTDTC']} is after death date {dth.date()}")
    aeout = str(r["AEOUT"]).upper()
    aesdth = str(r["AESDTH"]).upper()
    if aeout == "FATAL" and aesdth != "Y":
        add(10, subj, "AE", seq, "AEOUT is FATAL but AESDTH is not Y")
    if aesdth == "Y" and (dth is None or pd.isna(dth)):
        add(10, subj, "AE", seq, "AESDTH is Y but subject has no death date in DM")
    if str(r["AESER"]).upper() == "Y":
        crits = ["AESDTH", "AESLIFE", "AESHOSP", "AESDISAB", "AESCONG", "AESCAN"]
        if not any(str(r[c]).upper() == "Y" for c in crits):
            add(65, subj, "AE", seq, "AESER is Y but no seriousness criterion flag is Y")
    sev = str(r["AESEV"]).upper()
    if sev not in ("MILD", "MODERATE", "SEVERE", "NAN", ""):
        add(70, subj, "AE", seq, f"AESEV '{r['AESEV']}' is not a valid severity")

# ---------------- LB ----------------
lb["LBDTC_dt"] = to_dt(lb["LBDTC"])
lb["LBSTRESN_n"] = to_num(lb["LBSTRESN"])
lb["LBSEQ_n"] = to_num(lb["LBSEQ"])

# Physiologically impossible ranges (SI units), not merely abnormal.
LB_LIMITS = {
    "K": (1.5, 10.0), "SODIUM": (100.0, 180.0), "CL": (60.0, 150.0),
    "GLUC": (1.0, 60.0), "BILI": (0.0, 500.0), "ALB": (10.0, 80.0),
    "CHOL": (0.5, 30.0), "TRIG": (0.1, 60.0), "HDL": (0.1, 10.0), "LDL": (0.1, 20.0),
    "HGB": (30.0, 250.0), "HCT": (0.15, 0.80), "WBC": (0.2, 200.0),
    "RBC": (1.0, 10.0), "PLAT": (10.0, 1500.0), "CREAT": (5.0, 1500.0),
    "ALT": (0.0, 5000.0), "AST": (0.0, 5000.0), "ALP": (0.0, 5000.0), "GGT": (0.0, 5000.0),
    "BUN": (0.5, 100.0), "UREA": (0.5, 100.0), "CA": (1.0, 4.0), "PHOS": (0.1, 5.0),
}

for _, r in lb.iterrows():
    subj = r["USUBJID"]
    seq = r["LBSEQ_n"]
    val = r["LBSTRESN_n"]
    test = str(r["LBTESTCD"]).upper()
    d = r["LBDTC_dt"]

    if subj not in dm_subjects:
        add(75, subj, "LB", seq, "USUBJID not present in DM")
    if pd.notna(d) and d.normalize() > CUTOFF:
        add(50, subj, "LB", seq, f"LBDTC {r['LBDTC']} is after the data cutoff 2013-10-05")
    dth = dth_map.get(subj)
    if dth is not None and pd.notna(dth) and pd.notna(d) and d.normalize() > dth.normalize():
        add(10, subj, "LB", seq, f"Lab collected {r['LBDTC']} after death date {dth.date()}")
    if pd.notna(val):
        if val < 0:
            add(20, subj, "LB", seq,
                f"{r['LBTEST']} result {r['LBSTRESN']} {r['LBSTRESU']} is negative (impossible)")
        elif test in LB_LIMITS:
            lo, hi = LB_LIMITS[test]
            if val < lo or val > hi:
                add(20, subj, "LB", seq,
                    f"{r['LBTEST']} result {r['LBSTRESN']} {r['LBSTRESU']} is physiologically impossible")

# ---------------- DS ----------------
ds["DSSTDTC_dt"] = to_dt(ds["DSSTDTC"])
ds["DSSEQ_n"] = to_num(ds["DSSEQ"])

for _, r in ds.iterrows():
    subj = r["USUBJID"]
    seq = r["DSSEQ_n"]
    d = r["DSSTDTC_dt"]
    if subj not in dm_subjects:
        add(75, subj, "DS", seq, "USUBJID not present in DM")
    if pd.notna(d) and d > CUTOFF:
        add(50, subj, "DS", seq, f"DSSTDTC {r['DSSTDTC']} is after the data cutoff 2013-10-05")

dead = dm[(dm["DTHDTC_dt"].notna()) | (dm["DTHFL"].fillna("").str.upper() == "Y")]
for _, r0 in dead.iterrows():
    subj = r0["USUBJID"]
    dth = r0["DTHDTC_dt"]
    dth_str = str(dth.date()) if pd.notna(dth) else "unknown date"
    sub = ds[ds["USUBJID"] == subj]
    for _, r in sub.iterrows():
        decod = str(r["DSDECOD"]).upper()
        d = r["DSSTDTC_dt"]
        if decod == "COMPLETED":
            add(10, subj, "DS", r["DSSEQ_n"],
                f"Subject died ({dth_str}) but disposition is COMPLETED on {r['DSSTDTC']}")
        elif pd.notna(dth) and pd.notna(d) and d.normalize() > dth.normalize() and decod != "DEATH":
            add(15, subj, "DS", r["DSSEQ_n"],
                f"{r['DSDECOD']} on {r['DSSTDTC']} occurs after death date {dth.date()}")

# ---------------- duplicate sequence numbers ----------------
for df, dom, sc in [(ae, "AE", "AESEQ"), (ex, "EX", "EXSEQ"),
                    (ds, "DS", "DSSEQ"), (lb, "LB", "LBSEQ")]:
    dups = df[df["USUBJID"].notna() & df.duplicated(subset=["USUBJID", sc], keep=False)]
    for _, r in dups.iterrows():
        add(80, r["USUBJID"], dom, pd.to_numeric(r[sc], errors="coerce"),
            f"Duplicate {sc} {r[sc]} within subject in {dom}")

# ---------------- output ----------------
cols = ["USUBJID", "DOMAIN", "SEQ", "ISSUE"]
if findings:
    out = pd.DataFrame(findings)
    out = out.sort_values(["priority", "USUBJID", "DOMAIN", "seq_sort"], kind="mergesort")
    out = out.drop_duplicates(subset=cols, keep="first")
    out = out.head(25)[cols]
else:
    out = pd.DataFrame(columns=cols)

out.to_csv(OUT_FILE, index=False)
print(f"Wrote {len(out)} findings to {OUT_FILE}")
