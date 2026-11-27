import os
import numpy as np
import pandas as pd

CUTOFF = pd.Timestamp("2015-11-20")
IN_DIR = "input"
OUT_DIR = "output"
os.makedirs(OUT_DIR, exist_ok=True)


def load(name):
    df = pd.read_csv(os.path.join(IN_DIR, name), dtype=str)
    df.columns = df.columns.str.strip()
    return df


dm = load("dm.csv")
ae = load("ae.csv")
ex = load("ex.csv")
ds = load("ds.csv")
lb = load("lb.csv")


def add_dates(df, cols):
    for c in cols:
        df[c + "_DT"] = pd.to_datetime(df[c], errors="coerce").dt.normalize()


add_dates(dm, ["BRTHDTC", "RFSTDTC", "RFENDTC", "DTHDTC"])
add_dates(ae, ["AESTDTC", "AEENDTC"])
add_dates(ex, ["EXSTDTC", "EXENDTC"])
add_dates(ds, ["DSSTDTC"])
add_dates(lb, ["LBDTC"])

dm["AGE_N"] = pd.to_numeric(dm["AGE"], errors="coerce")
ex["EXDOSE_N"] = pd.to_numeric(ex["EXDOSE"], errors="coerce")
lb["LBSTRESN_N"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")


def txt(v):
    return "" if pd.isna(v) else str(v).strip()


findings = []


def add(prio, usubjid, domain, seq, issue):
    if seq is None or txt(seq) == "":
        seq_s, seq_n = "", -1
    else:
        seq_n = int(float(seq))
        seq_s = str(seq_n)
    findings.append({"PRIO": prio, "USUBJID": usubjid, "DOMAIN": domain,
                     "SEQ": seq_s, "SEQ_N": seq_n, "ISSUE": issue})


dmi = dm.set_index("USUBJID", drop=False)
arm_of = dmi["ARM"].to_dict()
rfst_of = dmi["RFSTDTC_DT"].to_dict()
rfen_of = dmi["RFENDTC_DT"].to_dict()
dthdtc_of = dmi["DTHDTC_DT"].to_dict()

# ---------------- DM checks ----------------
for _, r in dm.iterrows():
    sid = r["USUBJID"]
    age = r["AGE_N"]
    if pd.notna(age) and age < 50:
        add(1, sid, "DM", None,
            f"Age at entry {int(age)} violates the protocol inclusion criterion of age >= 50")
    if pd.notna(age) and pd.notna(r["BRTHDTC_DT"]) and pd.notna(r["RFSTDTC_DT"]):
        calc = (r["RFSTDTC_DT"] - r["BRTHDTC_DT"]).days / 365.25
        if abs(calc - age) > 1:
            add(3, sid, "DM", None,
                f"AGE {int(age)} is inconsistent with BRTHDTC {txt(r['BRTHDTC'])} at RFSTDTC {txt(r['RFSTDTC'])} (derived age {int(round(calc))})")
    for col, label in [("RFSTDTC", "Treatment start"), ("RFENDTC", "Treatment end"), ("DTHDTC", "Death")]:
        if pd.notna(r[col + "_DT"]) and r[col + "_DT"] > CUTOFF:
            add(2, sid, "DM", None,
                f"{label} date {txt(r[col])} is after the 2015-11-20 data cutoff")
    if pd.notna(r["RFSTDTC_DT"]) and pd.notna(r["RFENDTC_DT"]) and r["RFENDTC_DT"] < r["RFSTDTC_DT"]:
        add(3, sid, "DM", None,
            f"Treatment end {txt(r['RFENDTC'])} is before treatment start {txt(r['RFSTDTC'])}")
    dthfl = txt(r["DTHFL"]).upper()
    if dthfl == "Y" and pd.isna(r["DTHDTC_DT"]):
        add(1, sid, "DM", None, "DTHFL is Y but no death date (DTHDTC) is recorded")
    if dthfl != "Y" and pd.notna(r["DTHDTC_DT"]):
        add(1, sid, "DM", None,
            f"Death date {txt(r['DTHDTC'])} is recorded but DTHFL is not 'Y'")

fatal_ae = set(ae.loc[ae["AESDTH"].fillna("").str.upper().eq("Y")
                      | ae["AEOUT"].fillna("").str.upper().eq("FATAL"), "USUBJID"])
for _, r in dm.iterrows():
    sid = r["USUBJID"]
    if pd.notna(r["DTHDTC_DT"]) and sid not in fatal_ae:
        add(1, sid, "DM", None,
            "Subject has a death date but no AE with fatal outcome / AESDTH=Y is recorded")

# ---------------- EX checks ----------------
def expected(arm, visit):
    if arm == "Placebo":
        return ("PLACEBO", 0.0)
    if arm == "Xanomeline Low Dose":
        return ("XANOMELINE", 54.0)
    if arm == "Xanomeline High Dose":
        return {"BASELINE": ("XANOMELINE", 54.0),
                "WEEK 2": ("XANOMELINE", 81.0),
                "WEEK 24": ("XANOMELINE", 54.0)}.get(visit)
    return None


for _, r in ex.iterrows():
    sid = r["USUBJID"]
    arm = arm_of.get(sid, "")
    visit = txt(r["VISIT"]).upper()
    exp = expected(arm, visit)
    if exp is not None:
        etrt, edose = exp
        if txt(r["EXTRT"]).upper() != etrt or (pd.notna(r["EXDOSE_N"]) and r["EXDOSE_N"] != edose):
            add(1, sid, "EX", r["EXSEQ"],
                f"{arm} subject at {visit} dosed with {txt(r['EXTRT'])} {txt(r['EXDOSE'])} mg; protocol requires {etrt} {edose:g} mg")
    if pd.notna(r["EXSTDTC_DT"]) and r["EXSTDTC_DT"] > CUTOFF:
        add(2, sid, "EX", r["EXSEQ"],
            f"Exposure start {txt(r['EXSTDTC'])} is after the 2015-11-20 data cutoff")
    if pd.notna(r["EXENDTC_DT"]) and r["EXENDTC_DT"] > CUTOFF:
        add(2, sid, "EX", r["EXSEQ"],
            f"Exposure end {txt(r['EXENDTC'])} is after the 2015-11-20 data cutoff")
    if pd.notna(r["EXSTDTC_DT"]) and pd.notna(r["EXENDTC_DT"]) and r["EXENDTC_DT"] < r["EXSTDTC_DT"]:
        add(3, sid, "EX", r["EXSEQ"],
            f"Exposure end {txt(r['EXENDTC'])} is before exposure start {txt(r['EXSTDTC'])}")

# ---------------- AE checks ----------------
for _, r in ae.iterrows():
    sid = r["USUBJID"]
    seq = r["AESEQ"]
    if pd.notna(r["AESTDTC_DT"]) and r["AESTDTC_DT"] > CUTOFF:
        add(2, sid, "AE", seq, f"AE start {txt(r['AESTDTC'])} is after the 2015-11-20 data cutoff")
    if pd.notna(r["AEENDTC_DT"]) and r["AEENDTC_DT"] > CUTOFF:
        add(2, sid, "AE", seq, f"AE end {txt(r['AEENDTC'])} is after the 2015-11-20 data cutoff")
    if pd.notna(r["AESTDTC_DT"]) and pd.notna(r["AEENDTC_DT"]) and r["AEENDTC_DT"] < r["AESTDTC_DT"]:
        add(3, sid, "AE", seq, f"AE end {txt(r['AEENDTC'])} is before AE start {txt(r['AESTDTC'])}")
    if txt(r["AESDTH"]).upper() == "Y" or txt(r["AEOUT"]).upper() == "FATAL":
        if txt(r["AESER"]).upper() != "Y":
            add(1, sid, "AE", seq, "Fatal AE is not marked as serious (AESER is not Y)")
        if pd.isna(dthdtc_of.get(sid)):
            add(1, sid, "AE", seq, "AE with fatal outcome but subject has no death date in DM")
    out = txt(r["AEOUT"]).upper()
    if out.startswith("RECOVERED/RESOLVED") and pd.isna(r["AEENDTC_DT"]):
        add(3, sid, "AE", seq, f"AE outcome is {out} but no end date is recorded")
    if out == "NOT RECOVERED/NOT RESOLVED" and pd.notna(r["AEENDTC_DT"]):
        add(3, sid, "AE", seq, "AE outcome is NOT RECOVERED/NOT RESOLVED but an end date is recorded")
    rfst = rfst_of.get(sid)
    if pd.notna(r["AESTDTC_DT"]) and pd.notna(rfst) and r["AESTDTC_DT"] < rfst:
        add(4, sid, "AE", seq,
            f"AE start {txt(r['AESTDTC'])} precedes first dose ({rfst.date()}); confirm this is not medical history")

# ---------------- DS checks ----------------
for _, r in ds.iterrows():
    sid = r["USUBJID"]
    if pd.notna(r["DSSTDTC_DT"]) and r["DSSTDTC_DT"] > CUTOFF:
        add(2, sid, "DS", r["DSSEQ"],
            f"Disposition/event date {txt(r['DSSTDTC'])} is after the 2015-11-20 data cutoff")
    if txt(r["DSDECOD"]).upper() == "COMPLETED":
        rfst, rfen = rfst_of.get(sid), rfen_of.get(sid)
        if pd.notna(rfst) and pd.notna(rfen) and (rfen - rfst).days < 150:
            add(3, sid, "DS", r["DSSEQ"],
                f"Subject recorded as COMPLETED but treatment lasted only {(rfen - rfst).days} days on a 26-week protocol")

# ---------------- LB checks ----------------
HARD = {
    "K": (1.5, 10.0), "NA": (100.0, 190.0), "SODIUM": (100.0, 190.0),
    "GLUC": (1.0, 60.0), "CREAT": (5.0, 2000.0), "BILI": (0.5, 600.0),
    "ALT": (1.0, 20000.0), "AST": (1.0, 20000.0), "ALP": (5.0, 10000.0),
    "GGT": (1.0, 20000.0), "ALB": (5.0, 70.0), "CHOL": (0.5, 40.0),
    "TRIG": (0.05, 60.0), "HGB": (20.0, 250.0), "HCT": (0.05, 0.85),
    "WBC": (0.2, 500.0), "PLAT": (2.0, 3000.0), "RBC": (0.5, 10.0),
    "CA": (0.5, 5.0), "PHOS": (0.1, 6.0), "UREA": (0.5, 120.0),
    "BUN": (0.5, 120.0), "CK": (1.0, 200000.0), "LDH": (10.0, 50000.0),
    "CL": (60.0, 150.0), "BICARB": (3.0, 50.0), "TPROT": (10.0, 120.0),
}
for _, r in lb.iterrows():
    sid = r["USUBJID"]
    seq = r["LBSEQ"]
    val = r["LBSTRESN_N"]
    test = txt(r["LBTESTCD"]).upper()
    if pd.notna(val):
        if val < 0:
            add(1, sid, "LB", seq,
                f"Negative {txt(r['LBTEST'])} result ({val} {txt(r['LBSTRESU'])}) is impossible")
        elif test in HARD:
            lo, hi = HARD[test]
            if val < lo or val > hi:
                add(1, sid, "LB", seq,
                    f"{txt(r['LBTEST'])} result {val} {txt(r['LBSTRESU'])} is physiologically impossible")
    if pd.notna(r["LBDTC_DT"]) and r["LBDTC_DT"] > CUTOFF:
        add(2, sid, "LB", seq,
            f"Lab collection date {txt(r['LBDTC'])[:10]} is after the 2015-11-20 data cutoff")

# ---------------- duplicate records ----------------
dup_specs = [
    (ae, "AE", "AESEQ", ["USUBJID", "AETERM", "AESTDTC"]),
    (ex, "EX", "EXSEQ", ["USUBJID", "VISIT", "EXSTDTC"]),
    (lb, "LB", "LBSEQ", ["USUBJID", "LBTESTCD", "VISIT", "LBDTC"]),
]
for df, dom, seqcol, keys in dup_specs:
    d = df.copy()
    d["_SEQ_N"] = pd.to_numeric(d[seqcol], errors="coerce")
    d["_K"] = d[keys].fillna("").astype(str).agg("|".join, axis=1)
    for _, grp in d.groupby("_K"):
        if len(grp) > 1:
            grp = grp.sort_values("_SEQ_N")
            for _, grow in grp.iloc[1:].iterrows():
                if pd.notna(grow["_SEQ_N"]):
                    add(3, grow["USUBJID"], dom, grow["_SEQ_N"],
                        f"Duplicate {dom} record (same {', '.join(keys)}) already captured on another record")

# ---------------- output ----------------
out = pd.DataFrame(findings)
if out.empty:
    out = pd.DataFrame(columns=["USUBJID", "DOMAIN", "SEQ", "ISSUE"])
else:
    out = out.drop_duplicates(subset=["USUBJID", "DOMAIN", "SEQ", "ISSUE"])
    out = out.sort_values(["PRIO", "USUBJID", "DOMAIN", "SEQ_N"], kind="mergesort")
    out = out.head(25)[["USUBJID", "DOMAIN", "SEQ", "ISSUE"]]

out_path = os.path.join(OUT_DIR, "findings.csv")
out.to_csv(out_path, index=False)
print(f"Wrote {len(out)} findings to {out_path}")
