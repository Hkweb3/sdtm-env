import os
import traceback

import pandas as pd

CUTOFF = pd.Timestamp("2011-02-23")
FINDINGS = []


def add(usubjid, domain, seq, issue, prio):
    s = "" if seq is None else str(seq).strip()
    if s and s.lower() != "nan":
        try:
            s = str(int(float(s)))
        except ValueError:
            pass
    else:
        s = ""
    FINDINGS.append({"prio": prio, "USUBJID": str(usubjid), "DOMAIN": domain,
                     "SEQ": s, "ISSUE": issue})


def after_cutoff(v):
    return pd.notna(v) and v.normalize() > CUTOFF


def check_dm(dm, **ctx):
    for _, r in dm.iterrows():
        u = r["USUBJID"]
        age, brth = r["_AGE"], r["_BRTHDTC"]
        rfst, rfen = r["_RFSTDTC"], r["_RFENDTC"]
        if pd.notna(age) and age < 50:
            add(u, "DM", "", "Age at entry is {} but the protocol requires age 50 or older".format(int(age)), 5)
        if pd.notna(age) and pd.notna(brth) and pd.notna(rfst):
            calc = rfst.year - brth.year - ((rfst.month, rfst.day) < (brth.month, brth.day))
            if abs(calc - age) > 1:
                add(u, "DM", "", "AGE {} is inconsistent with BRTHDTC {} (calculated age {} at study start)".format(int(age), r["BRTHDTC"], calc), 25)
        if pd.notna(brth) and pd.notna(rfst) and brth >= rfst:
            add(u, "DM", "", "Birth date {} is not before study start {}".format(r["BRTHDTC"], r["RFSTDTC"]), 20)
        if pd.notna(rfst) and pd.notna(rfen) and rfen < rfst:
            add(u, "DM", "", "RFENDTC {} is before RFSTDTC {}".format(r["RFENDTC"], r["RFSTDTC"]), 18)
        for col in ("RFSTDTC", "RFENDTC", "DTHDTC"):
            if after_cutoff(r["_" + col]):
                add(u, "DM", "", "{} {} is after the data cutoff 2011-02-23".format(col, r[col]), 15)
        if r["DTHFL"] == "Y" and r["DTHDTC"] == "":
            add(u, "DM", "", "DTHFL is Y but DTHDTC is missing", 2)
        if r["DTHFL"] != "Y" and r["DTHDTC"] != "":
            add(u, "DM", "", "DTHDTC {} is populated but DTHFL is not Y".format(r["DTHDTC"]), 2)
        if r["SEX"] not in ("M", "F"):
            add(u, "DM", "", "Invalid SEX value '{}'".format(r["SEX"]), 30)
        if r["ARM"] not in ("Placebo", "Xanomeline Low Dose", "Xanomeline High Dose"):
            add(u, "DM", "", "Unexpected ARM '{}'".format(r["ARM"]), 30)


def check_ae(ae, dm_idx, **ctx):
    for _, r in ae.iterrows():
        u, seq = r["USUBJID"], r["AESEQ"]
        st, en = r["_AESTDTC"], r["_AEENDTC"]
        if pd.notna(st) and pd.notna(en) and en < st:
            add(u, "AE", seq, "AE end date {} is before start date {}".format(r["AEENDTC"], r["AESTDTC"]), 18)
        if after_cutoff(st):
            add(u, "AE", seq, "AE start date {} is after the data cutoff 2011-02-23".format(r["AESTDTC"]), 15)
        if after_cutoff(en):
            add(u, "AE", seq, "AE end date {} is after the data cutoff 2011-02-23".format(r["AEENDTC"]), 15)
        crit = [r[c] for c in ("AESDTH", "AESLIFE", "AESHOSP", "AESDISAB", "AESCAN", "AESCONG", "AESOD")]
        if r["AESER"] == "Y" and not any(c == "Y" for c in crit):
            add(u, "AE", seq, "AESER=Y but no seriousness criterion is marked", 20)
        if r["AESER"] == "N" and any(c == "Y" for c in crit):
            add(u, "AE", seq, "A seriousness criterion is marked but AESER=N", 20)
        if r["AESDTH"] == "Y" and r["AEOUT"] != "FATAL":
            add(u, "AE", seq, "AESDTH=Y but AEOUT is not FATAL", 8)
        if r["AEOUT"] == "FATAL" and r["AESDTH"] != "Y":
            add(u, "AE", seq, "AEOUT is FATAL but AESDTH is not Y", 8)
        if u in dm_idx.index:
            d = dm_idx.loc[u]
            dth = d["_DTHDTC"]
            if r["AESDTH"] == "Y" and d["DTHFL"] != "Y":
                add(u, "AE", seq, "AE with AESDTH=Y but subject has no death recorded in DM", 1)
            if r["AESDTH"] == "Y" and pd.notna(dth) and pd.notna(st) and st.normalize() != dth.normalize():
                add(u, "AE", seq, "Fatal AE date {} does not match DTHDTC {}".format(r["AESTDTC"], d["DTHDTC"]), 1)
            if pd.notna(dth) and pd.notna(st) and st.normalize() > dth.normalize():
                add(u, "AE", seq, "AE start {} is after subject death date {}".format(r["AESTDTC"], d["DTHDTC"]), 3)
        elif u not in dm_idx.index:
            add(u, "AE", seq, "Subject not found in DM", 40)
    dup = ae[ae.duplicated(subset=["USUBJID", "AEDECOD", "AESTDTC"], keep="first")]
    for _, r in dup.iterrows():
        add(r["USUBJID"], "AE", r["AESEQ"], "Duplicate AE record (same term and start date)", 50)


def check_ex(ex, dm_idx, **ctx):
    def expected_dose(arm, visit):
        v = visit.strip().upper()
        if arm == "Placebo":
            return 0
        if arm == "Xanomeline Low Dose":
            return 54
        if arm == "Xanomeline High Dose":
            if v == "BASELINE":
                return 54
            if v == "WEEK 2":
                return 81
            if v == "WEEK 24":
                return 54
        return None

    visit_start_day = {"BASELINE": 0, "WEEK 2": 15, "WEEK 24": 169}

    for _, r in ex.iterrows():
        u, seq = r["USUBJID"], r["EXSEQ"]
        st, en, dose = r["_EXSTDTC"], r["_EXENDTC"], r["_DOSE"]
        v = r["VISIT"].strip().upper()
        if u not in dm_idx.index:
            add(u, "EX", seq, "Subject not found in DM", 40)
            continue
        d = dm_idx.loc[u]
        arm = d["ARM"]
        exp = expected_dose(arm, r["VISIT"])
        if exp is not None and pd.notna(dose) and dose != exp:
            add(u, "EX", seq, "{} subject dosed {:g} mg at {}; protocol specifies {} mg".format(arm, dose, r["VISIT"], exp), 8)
        if arm == "Placebo" and r["EXTRT"].upper() != "PLACEBO":
            add(u, "EX", seq, "Placebo-arm subject received {}".format(r["EXTRT"]), 8)
        if arm.startswith("Xanomeline") and r["EXTRT"].upper() != "XANOMELINE":
            add(u, "EX", seq, "{} subject received {}".format(arm, r["EXTRT"]), 8)
        if pd.notna(dose) and dose not in (0, 54, 81):
            add(u, "EX", seq, "Implausible patch dose {:g} mg".format(dose), 12)
        if pd.notna(st) and pd.notna(en) and en < st:
            add(u, "EX", seq, "EX end date {} is before start date {}".format(r["EXENDTC"], r["EXSTDTC"]), 18)
        if after_cutoff(st):
            add(u, "EX", seq, "EX start {} is after the data cutoff 2011-02-23".format(r["EXSTDTC"]), 15)
        if after_cutoff(en):
            add(u, "EX", seq, "EX end {} is after the data cutoff 2011-02-23".format(r["EXENDTC"]), 15)
        rfst, rfen, dth = d["_RFSTDTC"], d["_RFENDTC"], d["_DTHDTC"]
        if pd.notna(st) and pd.notna(rfst) and st.normalize() < rfst.normalize():
            add(u, "EX", seq, "Dosing starts {} before reference start {}".format(r["EXSTDTC"], d["RFSTDTC"]), 30)
        if pd.notna(en) and pd.notna(rfen) and en.normalize() > rfen.normalize():
            add(u, "EX", seq, "Dosing ends {} after reference end {}".format(r["EXENDTC"], d["RFENDTC"]), 30)
        if pd.notna(dth) and pd.notna(st) and st.normalize() > dth.normalize():
            add(u, "EX", seq, "Dosing starts after subject death date {}".format(d["DTHDTC"]), 3)
        if v in visit_start_day and pd.notna(st) and pd.notna(rfst):
            exp_start = rfst + pd.Timedelta(days=visit_start_day[v])
            if abs((st - exp_start).days) > 10:
                add(u, "EX", seq, "{} dosing start {} is inconsistent with reference start {}".format(r["VISIT"], r["EXSTDTC"], d["RFSTDTC"]), 30)

    for u, g in ex.sort_values(["USUBJID", "_EXSTDTC"]).groupby("USUBJID"):
        prev_en, prev_seq = None, None
        for _, r in g.iterrows():
            if prev_en is not None and pd.notna(r["_EXSTDTC"]):
                delta = (r["_EXSTDTC"] - prev_en).days
                if delta <= 0:
                    add(u, "EX", r["EXSEQ"], "Exposure record overlaps with previous record EXSEQ {}".format(prev_seq), 30)
                elif delta > 1:
                    add(u, "EX", r["EXSEQ"], "Gap of {} day(s) between previous exposure end and this start".format(delta - 1), 45)
            if pd.notna(r["_EXENDTC"]):
                prev_en, prev_seq = r["_EXENDTC"], r["EXSEQ"]


def check_ds(ds, dm_idx, **ctx):
    for _, r in ds.iterrows():
        u, seq, st = r["USUBJID"], r["DSSEQ"], r["_DSSTDTC"]
        if u not in dm_idx.index:
            add(u, "DS", seq, "Subject not found in DM", 40)
            continue
        d = dm_idx.loc[u]
        if after_cutoff(st):
            add(u, "DS", seq, "Disposition date {} is after the data cutoff 2011-02-23".format(r["DSSTDTC"]), 15)
        dth = d["_DTHDTC"]
        if pd.notna(dth) and pd.notna(st) and st.normalize() > dth.normalize() and r["DSDECOD"].upper() != "DEATH":
            add(u, "DS", seq, "Disposition event {} is after subject death date {}".format(r["DSSTDTC"], d["DTHDTC"]), 3)
        if r["DSDECOD"].upper() == "DEATH":
            if d["DTHFL"] != "Y":
                add(u, "DS", seq, "Death disposition recorded but DTHFL in DM is not Y", 1)
            elif pd.notna(dth) and pd.notna(st) and st.normalize() != dth.normalize():
                add(u, "DS", seq, "Death disposition date {} does not match DTHDTC {}".format(r["DSSTDTC"], d["DTHDTC"]), 1)
        if r["DSDECOD"].upper() == "COMPLETED":
            rfst, rfen = d["_RFSTDTC"], d["_RFENDTC"]
            if pd.notna(rfst) and pd.notna(rfen) and (rfen - rfst).days < 160:
                add(u, "DS", seq, "Recorded as COMPLETED but treatment lasted only {} days (protocol is 26 weeks)".format((rfen - rfst).days), 35)
        if r["DSCAT"].upper() == "DISPOSITION EVENT" and pd.notna(st):
            if pd.notna(d["_RFSTDTC"]) and st.normalize() < d["_RFSTDTC"].normalize():
                add(u, "DS", seq, "Disposition event {} is before first dose {}".format(r["DSSTDTC"], d["RFSTDTC"]), 30)
            if pd.notna(d["_RFENDTC"]) and st.normalize() != d["_RFENDTC"].normalize():
                add(u, "DS", seq, "Disposition date {} does not match RFENDTC {}".format(r["DSSTDTC"], d["RFENDTC"]), 40)


RANGES = {
    "ALB": (5, 80), "ALP": (1, 3000), "ALT": (1, 10000), "AST": (1, 10000),
    "BILI": (0.1, 800), "BUN": (0.3, 120), "CA": (0.5, 5.5), "CHOL": (0.5, 40),
    "CK": (1, 300000), "CL": (60, 150), "CREAT": (5, 2500), "GGT": (1, 10000),
    "GLUC": (0.5, 90), "K": (1.5, 12), "SODIUM": (90, 220), "PHOS": (0.1, 7),
    "PLAT": (2, 4000), "PROT": (10, 130), "RBC": (0.5, 10), "TRIG": (0.05, 90),
    "UREA": (0.3, 120), "WBC": (0.05, 1500), "BASO": (0, 100), "EOS": (0, 100),
    "LYM": (0, 100), "MONO": (0, 100), "NEUT": (0, 100),
}


def check_lb(lb, dm_idx, **ctx):
    for _, r in lb.iterrows():
        u, seq = r["USUBJID"], r["LBSEQ"]
        tc = r["LBTESTCD"].upper()
        dtc, val = r["_LBDTC"], r["_VAL"]
        if u not in dm_idx.index:
            add(u, "LB", seq, "Subject not found in DM", 40)
            continue
        d = dm_idx.loc[u]
        if after_cutoff(dtc):
            add(u, "LB", seq, "Lab collection date {} is after the data cutoff 2011-02-23".format(r["LBDTC"][:10]), 15)
        dth = d["_DTHDTC"]
        if pd.notna(dth) and pd.notna(dtc) and dtc.normalize() > dth.normalize():
            add(u, "LB", seq, "Lab collected {} after subject death date {}".format(r["LBDTC"][:10], d["DTHDTC"]), 3)
        brth = d["_BRTHDTC"]
        if pd.notna(brth) and pd.notna(dtc) and dtc.normalize() < brth.normalize():
            add(u, "LB", seq, "Lab collection date {} is before subject birth date".format(r["LBDTC"][:10]), 12)
        rfst = d["_RFSTDTC"]
        if pd.notna(rfst) and pd.notna(dtc) and (rfst - dtc).days > 90:
            add(u, "LB", seq, "Lab collected {} long before first dose {}".format(r["LBDTC"][:10], d["RFSTDTC"]), 45)
        if pd.notna(val):
            lo_hi = RANGES.get(tc)
            if tc == "HGB":
                lo_hi = (2, 30) if r["LBSTRESU"].lower() == "g/dl" else (20, 300)
            if tc == "HCT":
                lo_hi = (5, 95) if r["LBSTRESU"] == "%" else (0.05, 0.95)
            if val < 0:
                add(u, "LB", seq, "Negative result {:g} {} for {} is impossible".format(val, r["LBSTRESU"], r["LBTEST"]), 12)
            elif lo_hi is not None and (val < lo_hi[0] or val > lo_hi[1]):
                add(u, "LB", seq, "{} result {:g} {} is physiologically impossible".format(r["LBTEST"], val, r["LBSTRESU"]), 12)
        if r["LBSTRESU"] in ("mg/dL", "g/dL", "mEq/L", "ug/dL"):
            add(u, "LB", seq, "Result unit '{}' is not the SI unit expected for this delivery".format(r["LBSTRESU"]), 30)

    dup = lb[lb.duplicated(subset=["USUBJID", "LBTESTCD", "VISITNUM", "LBDTC"], keep="first")]
    for _, r in dup.iterrows():
        add(r["USUBJID"], "LB", r["LBSEQ"], "Duplicate {} result for {} on {}".format(r["LBTEST"], r["VISIT"], r["LBDTC"][:10]), 50)

    for u, g in lb.dropna(subset=["_LBDTC", "_VN"]).groupby("USUBJID"):
        visit_min = g.groupby("_VN")["_LBDTC"].min().sort_index()
        prev_max = None
        for vn, dmin in visit_min.items():
            if prev_max is not None and dmin < prev_max:
                rec = g[(g["_VN"] == vn) & (g["_LBDTC"] == dmin)].iloc[0]
                add(u, "LB", rec["LBSEQ"], "{} lab date {} is earlier than a previous visit's date".format(rec["VISIT"], rec["LBDTC"][:10]), 45)
            prev_max = dmin if prev_max is None else max(prev_max, dmin)


def check_cross(ds, lb, dm_idx, **ctx):
    flv = ds[ds["DSDECOD"].str.upper() == "FINAL LAB VISIT"]
    last_lb = lb.dropna(subset=["_LBDTC"]).groupby("USUBJID")["_LBDTC"].max()
    for _, r in flv.iterrows():
        u = r["USUBJID"]
        if u in last_lb.index and pd.notna(r["_DSSTDTC"]):
            if last_lb[u].normalize() != r["_DSSTDTC"].normalize():
                add(u, "DS", r["DSSEQ"], "FINAL LAB VISIT date {} does not match last lab collection {}".format(r["DSSTDTC"], last_lb[u].strftime("%Y-%m-%d")), 45)


def main():
    os.makedirs("output", exist_ok=True)

    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)
    ae = pd.read_csv("input/ae.csv", dtype=str, keep_default_na=False)
    ex = pd.read_csv("input/ex.csv", dtype=str, keep_default_na=False)
    ds = pd.read_csv("input/ds.csv", dtype=str, keep_default_na=False)
    lb = pd.read_csv("input/lb.csv", dtype=str, keep_default_na=False)

    for df, cols in ((dm, ["BRTHDTC", "RFSTDTC", "RFENDTC", "DTHDTC"]),
                     (ae, ["AESTDTC", "AEENDTC"]),
                     (ex, ["EXSTDTC", "EXENDTC"]),
                     (ds, ["DSSTDTC"]),
                     (lb, ["LBDTC"])):
        for c in cols:
            df["_" + c] = pd.to_datetime(df[c], errors="coerce")

    dm["_AGE"] = pd.to_numeric(dm["AGE"], errors="coerce")
    ex["_DOSE"] = pd.to_numeric(ex["EXDOSE"], errors="coerce")
    lb["_VAL"] = pd.to_numeric(lb["LBSTRESN"], errors="coerce")
    lb["_VN"] = pd.to_numeric(lb["VISITNUM"], errors="coerce")

    for u in dm[dm.duplicated("USUBJID", keep=False)]["USUBJID"].unique():
        add(u, "DM", "", "USUBJID appears more than once in DM", 20)

    dm_idx = dm.drop_duplicates("USUBJID").set_index("USUBJID", drop=False)

    ctx = dict(dm=dm, ae=ae, ex=ex, ds=ds, lb=lb, dm_idx=dm_idx)
    for func in (check_dm, check_ae, check_ex, check_ds, check_lb, check_cross):
        try:
            func(**ctx)
        except Exception:
            traceback.print_exc()

    seen, rows = set(), []
    for f in sorted(FINDINGS, key=lambda x: x["prio"]):
        key = (f["USUBJID"], f["DOMAIN"], f["SEQ"], f["ISSUE"])
        if key in seen:
            continue
        seen.add(key)
        rows.append({"USUBJID": f["USUBJID"], "DOMAIN": f["DOMAIN"],
                     "SEQ": f["SEQ"], "ISSUE": f["ISSUE"]})
        if len(rows) >= 25:
            break

    out = pd.DataFrame(rows, columns=["USUBJID", "DOMAIN", "SEQ", "ISSUE"])
    path = os.path.join("output", "findings.csv")
    out.to_csv(path, index=False)
    print("Wrote {} findings to {}".format(len(out), os.path.abspath(path)))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        os.makedirs("output", exist_ok=True)
        if not os.path.exists("output/findings.csv"):
            pd.DataFrame(columns=["USUBJID", "DOMAIN", "SEQ", "ISSUE"]).to_csv(
                "output/findings.csv", index=False)
