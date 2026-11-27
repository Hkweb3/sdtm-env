import os
from collections import defaultdict

import pandas as pd

CUTOFF = pd.Timestamp("2010-09-21")

os.makedirs("output", exist_ok=True)

findings = []


def add(prio, subj, domain, seq, issue):
    s = "" if seq is None else str(seq)
    if s.lower() == "nan":
        s = ""
    findings.append({
        "PRIO": prio,
        "USUBJID": str(subj),
        "DOMAIN": domain,
        "SEQ": s,
        "ISSUE": str(issue),
    })


def to_dt(s):
    return pd.to_datetime(s, errors="coerce")


def dominant(series, thresh=0.9, min_n=3):
    s = series.dropna()
    if len(s) < min_n:
        return None
    vc = s.value_counts(normalize=True)
    if len(vc) and vc.iloc[0] >= thresh:
        return vc.index[0]
    return None


def seq_key(x):
    try:
        return int(x)
    except Exception:
        return 0


dm = pd.read_csv(os.path.join("input", "dm.csv"), dtype=str)
ae = pd.read_csv(os.path.join("input", "ae.csv"), dtype=str)
ex = pd.read_csv(os.path.join("input", "ex.csv"), dtype=str)
ds = pd.read_csv(os.path.join("input", "ds.csv"), dtype=str)
lb = pd.read_csv(os.path.join("input", "lb.csv"), dtype=str)

death, rfst_map, rfen_map, arm_map = {}, {}, {}, {}

# ---------------- DM ----------------
try:
    dm["_rfst"] = to_dt(dm["RFSTDTC"])
    dm["_rfen"] = to_dt(dm["RFENDTC"])
    dm["_dth"] = to_dt(dm["DTHDTC"])
    dm["_brth"] = to_dt(dm["BRTHDTC"])
    dm["_age"] = pd.to_numeric(dm["AGE"], errors="coerce")

    for _, r in dm.iterrows():
        s = r["USUBJID"]
        if pd.notna(r["_dth"]):
            death[s] = r["_dth"]
        rfst_map[s] = r["_rfst"]
        rfen_map[s] = r["_rfen"]
        arm_map[s] = r["ARM"]

    for s in dm.loc[dm["USUBJID"].duplicated(), "USUBJID"].unique():
        add(45, s, "DM", "", "Duplicate subject record in DM")

    for _, r in dm.iterrows():
        s = r["USUBJID"]
        brth, rfst, rfen, dth = r["_brth"], r["_rfst"], r["_rfen"], r["_dth"]
        dthfl = "" if pd.isna(r["DTHFL"]) else str(r["DTHFL"]).strip().upper()
        if pd.notna(brth) and pd.notna(rfst):
            age_calc = int((rfst - brth).days // 365.25)
            if pd.notna(r["_age"]) and abs(age_calc - int(r["_age"])) > 1:
                add(40, s, "DM", "", "AGE {} inconsistent with BRTHDTC {} and RFSTDTC {} (computed {})".format(
                    r["AGE"], r["BRTHDTC"], r["RFSTDTC"], age_calc))
            if age_calc < 50:
                add(38, s, "DM", "", "Subject was {} years old at entry (BRTHDTC {}, RFSTDTC {}); inclusion criterion requires age >= 50".format(
                    age_calc, r["BRTHDTC"], r["RFSTDTC"]))
        elif pd.notna(r["_age"]) and r["_age"] < 50:
            add(38, s, "DM", "", "AGE {} violates inclusion criterion age >= 50".format(r["AGE"]))
        if pd.notna(rfen) and pd.notna(rfst) and rfen < rfst:
            add(35, s, "DM", "", "RFENDTC {} is before RFSTDTC {}".format(r["RFENDTC"], r["RFSTDTC"]))
        if pd.notna(dth) and dthfl != "Y":
            add(36, s, "DM", "", "DTHDTC {} present but DTHFL is not 'Y'".format(r["DTHDTC"]))
        if pd.isna(dth) and dthfl == "Y":
            add(36, s, "DM", "", "DTHFL is 'Y' but DTHDTC is missing")
        if pd.notna(dth):
            if dth > CUTOFF:
                add(25, s, "DM", "", "DTHDTC {} is after data cutoff 2010-09-21".format(r["DTHDTC"]))
            if pd.notna(rfst) and dth < rfst:
                add(34, s, "DM", "", "DTHDTC {} is before RFSTDTC {}".format(r["DTHDTC"], r["RFSTDTC"]))
            if pd.notna(rfen) and rfen > dth:
                add(12, s, "DM", "", "Subject died {} but RFENDTC {} is after the death date".format(
                    r["DTHDTC"], r["RFENDTC"]))
        if pd.notna(rfst) and rfst > CUTOFF:
            add(25, s, "DM", "", "RFSTDTC {} is after data cutoff 2010-09-21".format(r["RFSTDTC"]))
        if pd.notna(rfen) and rfen > CUTOFF:
            add(25, s, "DM", "", "RFENDTC {} is after data cutoff 2010-09-21".format(r["RFENDTC"]))
except Exception:
    pass

# ---------------- AE ----------------
try:
    ae["_st"] = to_dt(ae["AESTDTC"])
    ae["_en"] = to_dt(ae["AEENDTC"])
    SEV_OK = {"MILD", "MODERATE", "SEVERE"}
    for _, r in ae.iterrows():
        s = r["USUBJID"]
        q = r["AESEQ"]
        st, en = r["_st"], r["_en"]
        dth = death.get(s)
        if s not in arm_map:
            add(45, s, "AE", q, "AE record for subject not found in DM")
        if pd.notna(st) and pd.notna(en) and en < st:
            add(30, s, "AE", q, "AE end date {} is before start date {}".format(r["AEENDTC"], r["AESTDTC"]))
        if pd.notna(st) and st > CUTOFF:
            add(24, s, "AE", q, "AE start {} is after data cutoff 2010-09-21".format(r["AESTDTC"]))
        if pd.notna(en) and en > CUTOFF:
            add(24, s, "AE", q, "AE end {} is after data cutoff 2010-09-21".format(r["AEENDTC"]))
        if dth is not None:
            if pd.notna(st) and st > dth:
                add(10, s, "AE", q, "AE start {} is after death date {}".format(r["AESTDTC"], dth.date()))
            elif pd.notna(en) and en > dth:
                add(10, s, "AE", q, "AE end {} is after death date {}".format(r["AEENDTC"], dth.date()))
        out = "" if pd.isna(r["AEOUT"]) else str(r["AEOUT"]).strip().upper()
        if out.startswith("RECOVERED") and pd.isna(en):
            add(50, s, "AE", q, "AE outcome is '{}' but AEENDTC is missing".format(r["AEOUT"]))
        aesdth = "" if pd.isna(r.get("AESDTH", "")) else str(r.get("AESDTH", "")).strip().upper()
        if (out == "FATAL" or aesdth == "Y") and s not in death:
            add(20, s, "AE", q, "AE is recorded as fatal but no death date exists in DM")
        sev = "" if pd.isna(r["AESEV"]) else str(r["AESEV"]).strip().upper()
        if sev and sev not in SEV_OK:
            add(55, s, "AE", q, "AESEV '{}' is not a valid severity".format(r["AESEV"]))
except Exception:
    pass

# ---------------- EX ----------------
try:
    ex["_st"] = to_dt(ex["EXSTDTC"])
    ex["_en"] = to_dt(ex["EXENDTC"])
    ex["_dose"] = pd.to_numeric(ex["EXDOSE"], errors="coerce")

    HIGH = {"BASELINE": 54, "WEEK 2": 81, "WEEK 24": 54}

    def expected(arm, visit):
        v = str(visit).strip().upper()
        if arm == "Placebo":
            return 0, "PLACEBO"
        if arm == "Xanomeline Low Dose":
            return 54, "XANOMELINE"
        if arm == "Xanomeline High Dose":
            return HIGH.get(v), "XANOMELINE"
        return None, None

    for _, r in ex.iterrows():
        s = r["USUBJID"]
        q = r["EXSEQ"]
        arm = arm_map.get(s)
        st, en = r["_st"], r["_en"]
        dth = death.get(s)
        if s not in arm_map:
            add(45, s, "EX", q, "EX record for subject not found in DM")
        exp_d, exp_t = expected(arm, r["VISIT"]) if arm else (None, None)
        flagged = False
        if exp_d is not None and pd.notna(r["_dose"]) and float(r["_dose"]) != float(exp_d):
            add(15, s, "EX", q, "{} dose {} mg at {} is inconsistent with the {} arm (expected {} mg)".format(
                r["EXTRT"], r["EXDOSE"], r["VISIT"], arm, exp_d))
            flagged = True
        trt = "" if pd.isna(r["EXTRT"]) else str(r["EXTRT"]).strip().upper()
        if exp_t and trt and trt != exp_t and not flagged:
            add(15, s, "EX", q, "EXTRT '{}' is inconsistent with randomized arm '{}'".format(r["EXTRT"], arm))
        if pd.notna(st) and pd.notna(en) and en < st:
            add(30, s, "EX", q, "EXENDTC {} is before EXSTDTC {}".format(r["EXENDTC"], r["EXSTDTC"]))
        if pd.notna(st) and st > CUTOFF:
            add(24, s, "EX", q, "EXSTDTC {} is after data cutoff 2010-09-21".format(r["EXSTDTC"]))
        if pd.notna(en) and en > CUTOFF:
            add(24, s, "EX", q, "EXENDTC {} is after data cutoff 2010-09-21".format(r["EXENDTC"]))
        if dth is not None:
            if pd.notna(st) and st > dth:
                add(10, s, "EX", q, "Dosing starts {} after death date {}".format(r["EXSTDTC"], dth.date()))
            elif pd.notna(en) and en > dth:
                add(10, s, "EX", q, "Dosing continues to {} after death date {}".format(r["EXENDTC"], dth.date()))
        rfst, rfen = rfst_map.get(s), rfen_map.get(s)
        if pd.notna(st) and rfst is not None and pd.notna(rfst) and st < rfst:
            add(32, s, "EX", q, "EXSTDTC {} precedes first dose date RFSTDTC {}".format(r["EXSTDTC"], rfst.date()))
        if pd.notna(en) and rfen is not None and pd.notna(rfen) and en > rfen:
            add(32, s, "EX", q, "EXENDTC {} is after end of participation RFENDTC {}".format(r["EXENDTC"], rfen.date()))
except Exception:
    pass

# ---------------- DS ----------------
try:
    ds["_st"] = to_dt(ds["DSSTDTC"])
    for _, r in ds.iterrows():
        s = r["USUBJID"]
        q = r["DSSEQ"]
        st = r["_st"]
        dth = death.get(s)
        decod = "" if pd.isna(r["DSDECOD"]) else str(r["DSDECOD"]).strip().upper()
        cat = "" if pd.isna(r["DSCAT"]) else str(r["DSCAT"]).strip().upper()
        if s not in arm_map:
            add(45, s, "DS", q, "DS record for subject not found in DM")
        if pd.notna(st) and st > CUTOFF:
            add(24, s, "DS", q, "DSSTDTC {} is after data cutoff 2010-09-21".format(r["DSSTDTC"]))
        if dth is not None and pd.notna(st) and st > dth:
            if decod == "COMPLETED":
                add(11, s, "DS", q, "Subject died {} but disposition is '{}' dated {}".format(
                    dth.date(), r["DSTERM"], r["DSSTDTC"]))
            else:
                add(11, s, "DS", q, "Disposition event '{}' dated {} is after death date {}".format(
                    r["DSTERM"], r["DSSTDTC"], dth.date()))
        elif decod == "COMPLETED" and s in death:
            add(11, s, "DS", q, "Subject has a death date in DM but disposition is COMPLETED")
        if "DEATH" in decod and s not in death:
            add(20, s, "DS", q, "Disposition records death but DM has no DTHDTC")
        if decod == "COMPLETED":
            rfst, rfen = rfst_map.get(s), rfen_map.get(s)
            if rfst is not None and rfen is not None and pd.notna(rfst) and pd.notna(rfen):
                dur = (rfen - rfst).days
                if dur < 150:
                    add(46, s, "DS", q, "Disposition COMPLETED but participation was only {} days ({} to {}), far short of 26 weeks".format(
                        dur, rfst.date(), rfen.date()))
        if cat == "DISPOSITION EVENT":
            rfen = rfen_map.get(s)
            if pd.notna(st) and rfen is not None and pd.notna(rfen) and st != rfen:
                add(48, s, "DS", q, "Disposition date {} does not match RFENDTC {}".format(r["DSSTDTC"], rfen.date()))
            rfst = rfst_map.get(s)
            if pd.notna(st) and rfst is not None and pd.notna(rfst) and st < rfst:
                add(48, s, "DS", q, "Disposition date {} precedes first dose date {}".format(r["DSSTDTC"], rfst.date()))
except Exception:
    pass

# ---------------- LB ----------------
try:
    lb["_dt"] = to_dt(lb["LBDTC"])
    lb["_val"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")

    # physiologically impossible ranges (SI units); ordinary abnormalities excluded
    BOUNDS = {
        "K": (1.5, 10.0), "NA": (90.0, 190.0), "CL": (60.0, 150.0),
        "GLUC": (0.5, 40.0), "CHOL": (0.5, 30.0), "TRIG": (0.05, 50.0),
        "ALT": (1.0, 5000.0), "AST": (1.0, 5000.0), "ALP": (5.0, 5000.0),
        "GGT": (1.0, 5000.0), "BILI": (0.5, 600.0), "TBILI": (0.5, 600.0),
        "CREAT": (5.0, 1500.0), "UREA": (0.5, 80.0), "BUN": (0.5, 80.0),
        "HGB": (25.0, 240.0), "HCT": (0.08, 0.75), "WBC": (0.1, 600.0),
        "RBC": (0.5, 9.0), "PLAT": (2.0, 3000.0), "CA": (0.5, 5.0),
        "PHOS": (0.1, 6.0), "ALB": (5.0, 80.0), "TP": (20.0, 120.0),
        "PROT": (20.0, 120.0), "LDH": (10.0, 20000.0), "CK": (1.0, 100000.0),
        "HBA1C": (2.0, 20.0), "TSH": (0.001, 500.0),
    }

    unit_mode = {}
    for tc, grp in lb.groupby("LBTESTCD"):
        m = dominant(grp["LBSTRESU"])
        if m is not None:
            unit_mode[tc] = m
    visit_mode = {}
    for v, grp in lb.groupby("VISIT"):
        m = dominant(grp["VISITNUM"])
        if m is not None:
            visit_mode[str(v)] = str(m)

    lb_rows = []
    for _, r in lb.iterrows():
        s = r["USUBJID"]
        q = r["LBSEQ"]
        tc = r["LBTESTCD"]
        d = r["_dt"]
        val = r["_val"]
        dth = death.get(s)
        if pd.notna(d):
            dn = d.normalize()
            if dn > CUTOFF:
                lb_rows.append((24, s, q, "CUTOFF",
                                "Lab collection date {} is after data cutoff 2010-09-21".format(r["LBDTC"])))
            if dth is not None and dn > dth:
                lb_rows.append((10, s, q, "DEATH",
                                "Lab collected {} after death date {}".format(r["LBDTC"], dth.date())))
        if pd.notna(val):
            if val < 0:
                lb_rows.append((28, s, q, "RANGE_" + str(tc),
                                "Negative result {} {} for {} is not physiologically possible".format(
                                    r["LBSTRESN"], r["LBSTRESU"], r["LBTEST"])))
            elif tc in BOUNDS:
                lo, hi = BOUNDS[tc]
                if val < lo or val > hi:
                    lb_rows.append((28, s, q, "RANGE_" + str(tc),
                                    "Result {} {} for {} is physiologically impossible".format(
                                        r["LBSTRESN"], r["LBSTRESU"], r["LBTEST"])))
        um = unit_mode.get(tc)
        if um is not None and pd.notna(r["LBSTRESU"]) and str(r["LBSTRESU"]) != str(um):
            lb_rows.append((55, s, q, "UNIT_" + str(tc),
                            "Unit '{}' for {} differs from unit '{}' used throughout the study".format(
                                r["LBSTRESU"], r["LBTEST"], um)))
        vm = visit_mode.get(str(r["VISIT"]))
        if vm is not None and pd.notna(r["VISITNUM"]) and str(r["VISITNUM"]) != vm:
            lb_rows.append((60, s, q, "VISITMAP",
                            "VISITNUM {} does not correspond to visit '{}' (expected VISITNUM {})".format(
                                r["VISITNUM"], r["VISIT"], vm)))

    groups = defaultdict(list)
    for prio, s, q, kind, msg in lb_rows:
        groups[(s, kind)].append((prio, q, msg))
    for (s, kind), items in groups.items():
        items.sort(key=lambda t: seq_key(t[1]))
        prio, q, msg = items[0]
        if len(items) > 1:
            msg += " [{} records affected for this subject; earliest shown]".format(len(items))
        add(prio, s, "LB", q, msg)
except Exception:
    pass

# ---------------- output ----------------
out = pd.DataFrame(findings, columns=["PRIO", "USUBJID", "DOMAIN", "SEQ", "ISSUE"])
if len(out):
    out["_seqn"] = pd.to_numeric(out["SEQ"], errors="coerce")
    out = out.sort_values(["PRIO", "USUBJID", "DOMAIN", "_seqn"], na_position="last")
    out = out.head(25)[["USUBJID", "DOMAIN", "SEQ", "ISSUE"]]
else:
    out = pd.DataFrame(columns=["USUBJID", "DOMAIN", "SEQ", "ISSUE"])

out.to_csv(os.path.join("output", "findings.csv"), index=False)
