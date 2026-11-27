```python
#!/usr/bin/env python3
"""
Task OR-05: clinical data review before database lock (study MRN-611).

Reads the SDTM package from ./input/ (dm.csv, ae.csv, ex.csv, ds.csv, lb.csv),
runs plausibility/consistency/protocol checks and writes the queries to
./output/findings.csv (columns: USUBJID, DOMAIN, SEQ, ISSUE),
most important first, maximum 25 rows.  The output file is always written.
"""

import os
import re
import traceback

import numpy as np
import pandas as pd

INPUT_DIR = "input"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "findings.csv")

CUTOFF = pd.Timestamp("2014-12-17")
VALID_ARMS = {"Placebo", "Xanomeline Low Dose", "Xanomeline High Dose"}

# Expected SI units for common chemistry test codes (task states labs are SI).
EXPECTED_UNITS = {
    "ALB": "g/L", "BILI": "umol/L", "BUN": "mmol/L", "UREA": "mmol/L",
    "CA": "mmol/L", "CALCIUM": "mmol/L", "CHOL": "mmol/L", "CREAT": "umol/L",
    "GLUC": "mmol/L", "POTASSIUM": "mmol/L", "SODIUM": "mmol/L",
    "CHLORIDE": "mmol/L", "CO2": "mmol/L", "BICARB": "mmol/L",
    "PHOS": "mmol/L", "URATE": "umol/L", "TRIG": "mmol/L", "HDL": "mmol/L",
    "LDL": "mmol/L", "ALT": "U/L", "AST": "U/L", "ALP": "U/L", "GGT": "U/L",
    "AMY": "U/L", "LIPASE": "U/L", "CK": "U/L", "LDH": "U/L",
}

# Generous plausible SI ranges: only gross errors (unit mix-ups, decimal
# shifts) fall outside; ordinary abnormal results stay inside.
PLAUSIBLE = {
    "SODIUM": (95, 190), "POTASSIUM": (1.0, 10.0), "CHLORIDE": (70, 145),
    "GLUC": (0.8, 45.0), "CHOL": (0.5, 20.0), "TRIG": (0.2, 30.0),
    "HDL": (0.1, 6.0), "LDL": (0.1, 15.0), "ALB": (10, 80),
    "BILI": (0.0, 800.0), "BUN": (0.5, 60.0), "UREA": (0.5, 60.0),
    "CREAT": (10, 2000), "URATE": (50, 1500), "CA": (1.0, 5.0),
    "CALCIUM": (1.0, 5.0), "PHOS": (0.1, 6.0), "ALT": (0, 5000),
    "AST": (0, 5000), "ALP": (0, 5000), "GGT": (0, 5000),
    "CK": (0, 100000), "AMY": (0, 5000), "LIPASE": (0, 5000),
    "LDH": (0, 10000), "PROTEIN": (20, 160), "TSH": (0.005, 100.0),
    "INR": (0.2, 10.0), "HGB": (20, 300),
}

FINDING_COLUMNS = ["USUBJID", "DOMAIN", "SEQ", "ISSUE"]


# ----------------------------------------------------------------- utilities
def load_csv(name):
    path = os.path.join(INPUT_DIR, name)
    if not os.path.exists(path):
        print("WARNING: missing input file: %s" % path)
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str, keep_default_na=False,
                     na_values=[""], encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    return df


def s(value):
    """Safe string: '' for NaN/None."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def dts(value):
    if value is None:
        return pd.NaT
    try:
        return pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError):
        return pd.NaT


def num(value):
    try:
        return pd.to_numeric(value, errors="coerce")
    except (TypeError, ValueError):
        return np.nan


def seq_or_blank(value):
    v = s(value)
    if v == "":
        return ""
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return v


def after_cutoff(ts):
    return pd.notna(ts) and ts.normalize() > CUTOFF


class Reviewer(object):
    def __init__(self):
        self.findings = []

    def add(self, usubjid, domain, seq, priority, issue):
        self.findings.append({
            "USUBJID": s(usubjid),
            "DOMAIN": domain,
            "SEQ": seq_or_blank(seq),
            "ISSUE": " ".join(str(issue).split()),
            "PRIORITY": int(priority),
        })


def dup_seq_keys(df, seqcol):
    """Set of (USUBJID, seq) keys whose SEQ value is duplicated within subject."""
    if df.empty or "USUBJID" not in df.columns or seqcol not in df.columns:
        return set()
    tmp = pd.DataFrame({"U": df["USUBJID"].map(s),
                        "S": df[seqcol].map(seq_or_blank)})
    dup = tmp.duplicated(keep=False)
    if not dup.any():
        return set()
    return set(map(tuple, tmp[dup].values.tolist()))


def build_subject_info(dm):
    info = {}
    if dm.empty or "USUBJID" not in dm.columns:
        return info
    for _, r in dm.iterrows():
        usubj = s(r.get("USUBJID"))
        if not usubj:
            continue
        info[usubj] = {
            "arm": s(r.get("ARM")),
            "rfst": dts(r.get("RFSTDTC")),
            "rfend": dts(r.get("RFENDTC")),
            "brth": dts(r.get("BRTHDTC")),
            "age": num(r.get("AGE")),
            "dth": dts(r.get("DTHDTC")),
            "dthfl": s(r.get("DTHFL")).upper(),
        }
    return info


# --------------------------------------------------------------------- DM
def check_dm(rv, dm):
    if dm.empty or "USUBJID" not in dm.columns:
        return
    dupsub = set(dm.loc[dm["USUBJID"].duplicated(keep=False), "USUBJID"].map(s))
    for _, r in dm.iterrows():
        usubj = s(r.get("USUBJID"))
        if not usubj:
            continue
        age = num(r.get("AGE"))
        brth = dts(r.get("BRTHDTC"))
        rfst = dts(r.get("RFSTDTC"))
        rfend = dts(r.get("RFENDTC"))
        dth = dts(r.get("DTHDTC"))
        dthfl = s(r.get("DTHFL")).upper()
        arm = s(r.get("ARM"))

        if usubj in dupsub:
            rv.add(usubj, "DM", "", 4, "Duplicate DM record for this subject")

        if pd.notna(age) and age < 50:
            rv.add(usubj, "DM", "", 1,
                   "AGE %g is below the protocol inclusion criterion (age >= 50 years at entry)" % age)

        if pd.notna(brth) and pd.notna(rfst):
            calc = (rfst - brth).days / 365.25
            if calc < 0:
                rv.add(usubj, "DM", "", 1,
                       "BRTHDTC %s is after RFSTDTC %s" % (brth.date(), rfst.date()))
            elif calc < 50 and (pd.isna(age) or age >= 50):
                rv.add(usubj, "DM", "", 1,
                       "BRTHDTC implies age %.1f at first dose: inclusion criterion (age >= 50) not met" % calc)
            elif pd.notna(age) and abs(calc - age) >= 2:
                rv.add(usubj, "DM", "", 3,
                       "AGE %g inconsistent with BRTHDTC (%.1f years calculated at RFSTDTC)" % (age, calc))

        if pd.notna(brth) and after_cutoff(brth):
            rv.add(usubj, "DM", "", 1, "BRTHDTC %s is after the data cutoff (2014-12-17)" % brth.date())
        if pd.notna(rfst) and after_cutoff(rfst):
            rv.add(usubj, "DM", "", 2, "RFSTDTC %s is after the data cutoff (2014-12-17)" % rfst.date())
        if pd.notna(rfend) and after_cutoff(rfend):
            rv.add(usubj, "DM", "", 2, "RFENDTC %s is after the data cutoff (2014-12-17)" % rfend.date())
        if pd.notna(rfst) and pd.notna(rfend) and rfend < rfst:
            rv.add(usubj, "DM", "", 2, "RFENDTC %s is before RFSTDTC %s" % (rfend.date(), rfst.date()))

        if pd.notna(dth):
            if after_cutoff(dth):
                rv.add(usubj, "DM", "", 2, "DTHDTC %s is after the data cutoff (2014-12-17)" % dth.date())
            if pd.notna(brth) and dth < brth:
                rv.add(usubj, "DM", "", 1, "Death date is before birth date")
            elif pd.notna(rfst) and dth < rfst:
                rv.add(usubj, "DM", "", 1,
                       "Death date %s is before first dose (RFSTDTC %s)" % (dth.date(), rfst.date()))
            if dthfl != "Y":
                rv.add(usubj, "DM", "", 3, "DTHDTC present but DTHFL is not 'Y'")
        elif dthfl == "Y":
            rv.add(usubj, "DM", "", 3, "DTHFL='Y' but DTHDTC is missing")

        if arm and arm not in VALID_ARMS:
            rv.add(usubj, "DM", "", 4, "Unexpected ARM value '%s'" % arm)


# --------------------------------------------------------------------- AE
def check_ae(rv, ae, info):
    if ae.empty or "USUBJID" not in ae.columns:
        return
    dupkeys = dup_seq_keys(ae, "AESEQ")
    for _, r in ae.iterrows():
        usubj = s(r.get("USUBJID"))
        if not usubj:
            continue
        si = info.get(usubj, {})
        seq = r.get("AESEQ")
        term = s(r.get("AETERM")) or s(r.get("AEDECOD")) or "AE"
        st = dts(r.get("AESTDTC"))
        en = dts(r.get("AEENDTC"))
        rfst = si.get("rfst", pd.NaT)
        brth = si.get("brth", pd.NaT)
        dth = si.get("dth", pd.NaT)

        if (usubj, seq_or_blank(seq)) in dupkeys:
            rv.add(usubj, "AE", seq, 3, "Duplicate AESEQ within subject")

        if after_cutoff(st):
            rv.add(usubj, "AE", seq, 2, "AE start date %s is after the data cutoff (2014-12-17)" % st.date())
        if after_cutoff(en):
            rv.add(usubj, "AE", seq, 2, "AE end date %s is after the data cutoff (2014-12-17)" % en.date())
        if pd.notna(st) and pd.notna(en) and en < st:
            rv.add(usubj, "AE", seq, 1,
                   "AE end date %s is before AE start date %s (%s)" % (en.date(), st.date(), term))
        if pd.notna(brth) and pd.notna(st) and st < brth:
            rv.add(usubj, "AE", seq, 1, "AE start date is before the subject's birth date (%s)" % term)
        if pd.notna(dth):
            if pd.notna(st) and st > dth:
                rv.add(usubj, "AE", seq, 1,
                       "AE %s starts %s, after the subject's death date %s" % (term, st.date(), dth.date()))
            if pd.notna(en) and en > dth:
                rv.add(usubj, "AE", seq, 1,
                       "AE %s ends %s, after the subject's death date %s" % (term, en.date(), dth.date()))
        if pd.notna(rfst) and pd.notna(st) and st < rfst:
            rv.add(usubj, "AE", seq, 5,
                   "AE start date %s is before first dose (RFSTDTC %s)" % (st.date(), rfst.date()))

        aesdth = s(r.get("AESDTH")).upper()
        aeout = s(r.get("AEOUT")).upper()
        if aesdth == "Y":
            if pd.isna(dth) and si.get("dthfl", "") != "Y":
                rv.add(usubj, "AE", seq, 1,
                       "AE '%s' reported as fatal (AESDTH=Y) but DM has no death record" % term)
            if aeout and aeout != "FATAL":
                rv.add(usubj, "AE", seq, 2,
                       "AESDTH='Y' but AEOUT='%s' for AE '%s' (expected FATAL)" % (aeout, term))
        if aeout == "FATAL" and aesdth != "Y":
            rv.add(usubj, "AE", seq, 2, "AEOUT='FATAL' but AESDTH is not 'Y' for AE '%s'" % term)


# --------------------------------------------------------------------- EX
def expected_high_dose(visit):
    """Protocol titration for Xanomeline High Dose: 54 mg until Week 2,
    81 mg Week 2 -> Week 24, 54 mg from Week 24 on."""
    v = s(visit).upper()
    if not v:
        return None
    if "BASELINE" in v:
        return 54
    m = re.search(r"WEEK\s+(\d+)", v)
    if not m:
        return None
    wk = int(m.group(1))
    if wk < 2:
        return 54
    if wk < 24:
        return 81
    return 54


def check_ex(rv, ex, info):
    if ex.empty or "USUBJID" not in ex.columns:
        return
    dupkeys = dup_seq_keys(ex, "EXSEQ")
    for _, r in ex.iterrows():
        usubj = s(r.get("USUBJID"))
        if not usubj:
            continue
        si = info.get(usubj, {})
        seq = r.get("EXSEQ")
        arm = si.get("arm", "")
        dose = num(r.get("EXDOSE"))
        visit = s(r.get("VISIT"))
        st = dts(r.get("EXSTDTC"))
        en = dts(r.get("EXENDTC"))
        rfst = si.get("rfst", pd.NaT)
        rfend = si.get("rfend", pd.NaT)
        dth = si.get("dth", pd.NaT)

        if (usubj, seq_or_blank(seq)) in dupkeys:
            rv.add(usubj, "EX", seq, 3, "Duplicate EXSEQ within subject")

        if pd.notna(dose):
            if dose not in (0, 54, 81):
                rv.add(usubj, "EX", seq, 1,
                       "EXDOSE %g mg is not a protocol dose (allowed: 0, 54, 81 mg)" % dose)
            if arm == "Placebo" and dose > 0:
                rv.add(usubj, "EX", seq, 1,
                       "Active xanomeline %g mg dispensed to a Placebo subject" % dose)
            elif arm == "Xanomeline Low Dose" and dose != 54:
                rv.add(usubj, "EX", seq, 1,
                       "EXDOSE %g mg not allowed in Xanomeline Low Dose arm (54 mg throughout)" % dose)
            elif arm == "Xanomeline High Dose":
                exp = expected_high_dose(visit)
                if exp is not None and dose != exp:
                    rv.add(usubj, "EX", seq, 1,
                           "EXDOSE %g mg at %s inconsistent with High Dose titration (expected %d mg)"
                           % (dose, visit or "this visit", exp))

        if pd.notna(st) and pd.notna(en) and en < st:
            rv.add(usubj, "EX", seq, 1, "EX end date %s is before EX start date %s" % (en.date(), st.date()))
        if after_cutoff(st):
            rv.add(usubj, "EX", seq, 2, "EX start date %s is after the data cutoff (2014-12-17)" % st.date())
        if after_cutoff(en):
            rv.add(usubj, "EX", seq, 2, "EX end date %s is after the data cutoff (2014-12-17)" % en.date())
        if pd.notna(dth):
            if pd.notna(st) and st > dth:
                rv.add(usubj, "EX", seq, 1,
                       "Exposure starts %s, after the subject's death date %s" % (st.date(), dth.date()))
            if pd.notna(en) and en > dth:
                rv.add(usubj, "EX", seq, 1,
                       "Exposure ends %s, after the subject's death date %s" % (en.date(), dth.date()))
        if pd.notna(rfst) and pd.notna(st) and st < rfst:
            rv.add(usubj, "EX", seq, 3, "EX start date %s is before RFSTDTC %s" % (st.date(), rfst.date()))
        if pd.notna(rfend) and pd.notna(en) and en > rfend:
            rv.add(usubj, "EX", seq, 3, "EX end date %s is after RFENDTC %s" % (en.date(), rfend.date()))

    # overlapping exposure periods (one patch daily -> periods must not overlap)
    try:
        for usubj, grp in ex.groupby(ex["USUBJID"].map(s)):
            periods = []
            for _, rr in grp.iterrows():
                st = dts(rr.get("EXSTDTC"))
                en = dts(rr.get("EXENDTC"))
                if pd.notna(st):
                    periods.append((st, en if pd.notna(en) else st, rr))
            periods.sort(key=lambda t: t[0])
            for (st0, en0, _), (st1, _e1, r1) in zip(periods, periods[1:]):
                if st1 <= en0:
                    rv.add(usubj, "EX", r1.get("EXSEQ"), 2,
                           "EX period starting %s overlaps the previous period ending %s (one patch daily)"
                           % (st1.date(), en0.date()))
    except Exception:
        traceback.print_exc()


# --------------------------------------------------------------------- LB
def check_lb(rv, lb, info):
    if lb.empty or "USUBJID" not in lb.columns:
        return
    dupkeys = dup_seq_keys(lb, "LBSEQ")
    for _, r in lb.iterrows():
        usubj = s(r.get("USUBJID"))
        if not usubj:
            continue
        si = info.get(usubj, {})
        seq = r.get("LBSEQ")
        tc = s(r.get("LBTESTCD")).upper()
        unit = s(r.get("LBSTRESU"))
        res = num(r.get("LBSTRESN"))
        dt = dts(r.get("LBDTC"))
        brth = si.get("brth", pd.NaT)
        dth = si.get("dth", pd.NaT)

        if (usubj, seq_or_blank(seq)) in dupkeys:
            rv.add(usubj, "LB", seq, 3, "Duplicate LBSEQ within subject")

        if pd.notna(dt):
            if after_cutoff(dt):
                rv.add(usubj, "LB", seq, 2,
                       "Lab collection date %s is after the data cutoff (2014-12-17)" % dt.date())
            if pd.notna(brth) and dt < brth:
                rv.add(usubj, "LB", seq, 1, "Lab collected before the subject's birth date")
            if pd.notna(dth) and dt.normalize() > dth.normalize():
                rv.add(usubj, "LB", seq, 1,
                       "Lab collected %s, after the subject's death date %s" % (dt.date(), dth.date()))

        exp_unit = EXPECTED_UNITS.get(tc)
        if exp_unit and unit and unit.upper() != exp_unit.upper():
            rv.add(usubj, "LB", seq, 2,
                   "%s result reported in '%s'; expected SI unit '%s'" % (tc, unit, exp_unit))

        if pd.notna(res):
            if res < 0:
                rv.add(usubj, "LB", seq, 1,
                       "Negative %s result (%g %s) is impossible" % (tc, res, unit))
            else:
                rng = PLAUSIBLE.get(tc)
                if rng and (res < rng[0] or res > rng[1]):
                    rv.add(usubj, "LB", seq, 2,
                           "%s result %g %s is outside any plausible range (%g-%g); possible unit or decimal error"
                           % (tc, res, unit, rng[0], rng[1]))


# --------------------------------------------------------------------- DS
def check_ds(rv, ds, info):
    if ds.empty or "USUBJID" not in ds.columns:
        return
    dupkeys = dup_seq_keys(ds, "DSSEQ")
    for _, r in ds.iterrows():
        usubj = s(r.get("USUBJID"))
        if not usubj:
            continue
        si = info.get(usubj, {})
        seq = r.get("DSSEQ")
        term = s(r.get("DSDECOD")) or s(r.get("DSTERM"))
        dt = dts(r.get("DSSTDTC"))
        rfst = si.get("rfst", pd.NaT)
        rfend = si.get("rfend", pd.NaT)
        dth = si.get("dth", pd.NaT)

        if (usubj, seq_or_blank(seq)) in dupkeys:
            rv.add(usubj, "DS", seq, 3, "Duplicate DSSEQ within subject")

        if after_cutoff(dt):
            rv.add(usubj,