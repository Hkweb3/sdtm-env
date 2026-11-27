"""Tier 3: data review. The agent gets a study package in SDTM (DM, AE, EX, DS, LB) and
must list every data issue in seven checks. Issues are planted on top of the
re-identified Pilot01 data; the expected list is the reference detector's output on
the final package, so natural issues in the source count too.

Graded by F1 over (CHECK, USUBJID, DOMAIN, SEQ); a pass is an exact match.
"""
import json
import random
from datetime import date, timedelta
from statistics import median

import pandas as pd

from sdtmenv.generate import ANSWERS, load, reidentify, shift, write_task

CRIT = ["AESCAN", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE", "AESOD"]
LB_KEEP = {"GLUC": 18.0, "CREAT": 1 / 88.4, "BILI": 1 / 17.1, "CHOL": 38.67, "ALB": 0.1, "ALT": None, "K": None,
           "SODIUM": None}  # factor = what a wrong-unit entry multiplies the SI value by
FINDING_COLS = ["CHECK", "USUBJID", "DOMAIN", "SEQ"]


def detect(dm, ae, ex, ds, lb):
    """Reference detector. Defines the expected findings for a package."""
    f = set()
    death = dict(zip(dm.USUBJID, dm.DTHDTC))
    for r in ae.itertuples():
        s, e = r.AESTDTC, r.AEENDTC
        if len(s) == 10 and len(e) == 10 and e < s:
            f.add(("AE_DATE_ORDER", r.USUBJID, "AE", r.AESEQ))
        crits = any(getattr(r, c) == "Y" for c in CRIT)
        if (r.AESER == "Y") != crits:
            f.add(("SAE_CRITERIA", r.USUBJID, "AE", r.AESEQ))
        d = death.get(r.USUBJID, "")
        if r.AEOUT == "FATAL" and not d:
            f.add(("DEATH_CONSISTENCY", r.USUBJID, "AE", r.AESEQ))
        if d and len(s) == 10 and s > d[:10]:
            f.add(("DEATH_CONSISTENCY", r.USUBJID, "AE", r.AESEQ))
    for (u, dec, st), g in ae.groupby(["USUBJID", "AEDECOD", "AESTDTC"]):
        if st and len(g) > 1:
            for seq in sorted(g.AESEQ, key=int)[1:]:
                f.add(("AE_DUPLICATE", u, "AE", seq))
    fatal = set(ae[ae.AEOUT == "FATAL"].USUBJID)
    for u, d in death.items():
        if d and u not in fatal:
            f.add(("DEATH_CONSISTENCY", u, "DM", ""))
    disp = ds[(ds.DSCAT == "DISPOSITION EVENT") & ~ds.DSDECOD.isin(["COMPLETED", "SCREEN FAILURE"])]
    disc = dict(zip(disp.USUBJID, disp.DSSTDTC))
    for r in ex.itertuples():
        d = disc.get(r.USUBJID, "")
        if d and len(r.EXSTDTC) >= 10 and r.EXSTDTC[:10] > d[:10]:
            f.add(("DOSE_AFTER_DISC", r.USUBJID, "EX", r.EXSEQ))
    num = lb[lb.LBSTRESN != ""]
    for (u, t), g in num.groupby(["USUBJID", "LBTESTCD"]):
        vals = dict(zip(g.LBSEQ, g.LBSTRESN.astype(float)))
        for seq, v in vals.items():
            others = [x for s, x in vals.items() if s != seq]
            if len(others) >= 2:
                m = median(others)
                if m > 0 and (v >= 8 * m or v <= m / 8):
                    f.add(("LAB_UNIT", u, "LB", seq))
    sched = lb[~lb.VISIT.str.startswith("UNSCHEDULED")]
    for (u, t), g in sched.groupby(["USUBJID", "LBTESTCD"]):
        g = g[g.LBDTC != ""].assign(VNUM=g.VISITNUM.astype(float)).sort_values("VNUM")
        for r in g.itertuples():
            earlier = g[g.VNUM < r.VNUM]
            if len(earlier) and r.LBDTC[:10] < earlier.LBDTC.str[:10].max():
                f.add(("LAB_VISIT_DATE", u, "LB", r.LBSEQ))
    return f


def build_package(rng, n_subj, extra=False):
    """Re-identified SDTM package. extra=True also returns CM and MH (open-review v2)."""
    dm, ae, ex, ds, lb = load("dm"), load("ae"), load("ex"), load("ds"), load("lb")
    lb = lb[lb.LBTESTCD.isin(LB_KEEP)]
    pool = sorted(set(ae.USUBJID))
    # make sure the package has early discontinuations and, sometimes, a death
    studyid, days, pick = reidentify(dm, rng, n_subj, pool=pool)
    ids = dict(zip(pick.USUBJID, pick.NEW_USUBJID))

    def remap(df, cols_dates, seq):
        df = df[df.USUBJID.isin(ids)].copy()
        df["STUDYID"] = studyid
        df["USUBJID"] = df.USUBJID.map(ids)
        for c in cols_dates:
            df[c] = [shift(x[:10], days) + x[10:16] if x else "" for x in df[c]]
        if seq:
            df[seq] = df[seq].map(lambda x: str(int(float(x))) if x != "" else "")
        return df.reset_index(drop=True)

    dm_ = remap(dm, ["RFSTDTC", "RFENDTC", "DTHDTC"], None)[
        ["STUDYID", "DOMAIN", "USUBJID", "SITEID", "AGE", "SEX", "ARM", "RFSTDTC", "RFENDTC", "DTHDTC", "DTHFL"]]
    dm_["AGE"] = dm_.AGE.map(lambda x: str(int(float(x))) if x != "" else "")
    # Pilot01 repeats some AEs (same PT and start date); drop those so AE_DUPLICATE measures planted cases
    ae = ae.drop_duplicates(["USUBJID", "AEDECOD", "AESTDTC"])
    ae_ = remap(ae, ["AESTDTC", "AEENDTC"], "AESEQ")[
        ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AETERM", "AEDECOD", "AEBODSYS", "AESEV", "AESER", *CRIT, "AEREL",
         "AEOUT", "AESTDTC", "AEENDTC"]]
    ex_ = remap(ex, ["EXSTDTC", "EXENDTC"], "EXSEQ")[
        ["STUDYID", "DOMAIN", "USUBJID", "EXSEQ", "EXTRT", "EXDOSE", "EXDOSU", "VISIT", "EXSTDTC", "EXENDTC"]]
    ex_["EXDOSE"] = ex_.EXDOSE.map(lambda x: str(int(round(float(x)))) if x != "" else "")
    ds_ = remap(ds, ["DSSTDTC"], "DSSEQ")[["STUDYID", "DOMAIN", "USUBJID", "DSSEQ", "DSTERM", "DSDECOD", "DSCAT",
                                           "DSSTDTC"]]
    lb_ = remap(lb, ["LBDTC"], "LBSEQ")[["STUDYID", "DOMAIN", "USUBJID", "LBSEQ", "LBTESTCD", "LBTEST", "LBSTRESN",
                                         "LBSTRESU", "VISITNUM", "VISIT", "LBDTC"]]
    lb_["LBSTRESN"] = lb_.LBSTRESN.map(lambda x: "" if x == "" else f"{float(x):g}")
    lb_["VISITNUM"] = lb_.VISITNUM.map(lambda x: f"{float(x):g}")
    if not extra:
        return studyid, dm_, ae_, ex_, ds_, lb_
    cm, mh = load("cm"), load("mh")
    # CM repeats each medication at every visit; keep one record per medication, and drop the
    # source's own cholinesterase inhibitors so prohibited-drug findings are all planted
    cm = cm.drop_duplicates(["USUBJID", "CMSPID", "CMTRT"])
    # ...and its anticholinergics (Benadryl alone appears 57 times), which would be real but unscored findings
    cm = cm[~cm.CMDECOD.str.contains("DONEPEZIL|GALANTAMINE|RIVASTIGMINE|DIPHENHYDRAMINE|PROMETHAZINE|PAROXETINE|"
                                     "CHLORPHENAMINE|MECLOZINE|IPRATROPIUM|ATROPINE") &
            ~cm.CMTRT.str.upper().str.contains("ARICEPT|DONEPEZIL|RAZADYNE|EXELON|REMINYL|BENADRYL|DIPHENHYD|"
                                               "MECLIZ|PROMETH|PHENERGAN|LOMOTIL|PAXIL|CHLORPHEN|ATROVENT")]
    cm_ = remap(cm, ["CMSTDTC", "CMENDTC"], "CMSEQ")[["STUDYID", "DOMAIN", "USUBJID", "CMSEQ", "CMTRT", "CMDECOD",
                                                       "CMINDC", "CMDOSE", "CMDOSU", "CMDOSFRQ", "CMROUTE",
                                                       "CMSTDTC", "CMENDTC"]]
    cm_["CMDOSE"] = cm_.CMDOSE.map(lambda x: f"{float(x):g}" if x != "" else "")
    cm_["CMSEQ"] = cm_.groupby("USUBJID").cumcount().add(1).astype(str)  # renumber after de-duplication
    mh_ = remap(mh[mh.MHTERM != ""], ["MHSTDTC"], "MHSEQ")[["STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHTERM",
                                                              "MHDECOD", "MHCAT", "MHBODSYS", "MHSTDTC"]]
    return studyid, dm_, ae_, ex_, ds_, lb_, cm_, mh_


def plant(rng, dm, ae, ex, ds, lb, n_issues, kinds):
    planted = []
    for _ in range(n_issues):
        k = rng.choice(kinds)
        if k == "AE_DATE_ORDER":
            c = ae[(ae.AESTDTC.str.len() == 10) & (ae.AEENDTC.str.len() == 10) & (ae.AEENDTC > ae.AESTDTC)]
            if len(c):
                i = rng.choice(list(c.index))
                ae.at[i, "AEENDTC"] = (date.fromisoformat(ae.at[i, "AESTDTC"]) - timedelta(days=rng.randint(1, 20))).isoformat()
                planted.append(k)
        elif k == "AE_DUPLICATE":
            i = rng.choice(list(ae[ae.AESTDTC != ""].index))
            row = ae.loc[i].copy()
            row["AESEQ"] = str(int(ae[ae.USUBJID == row.USUBJID].AESEQ.astype(int).max()) + 1)
            ae.loc[len(ae)] = row
            planted.append(k)
        elif k == "SAE_CRITERIA":
            i = rng.choice(list(ae[(ae.AESER == "N")].index))
            if rng.random() < 0.5:
                ae.at[i, "AESER"] = "Y"
            else:
                ae.at[i, rng.choice(["AESHOSP", "AESLIFE", "AESDISAB"])] = "Y"
            planted.append(k)
        elif k == "DEATH_CONSISTENCY":
            alive = dm[dm.DTHDTC == ""]
            u = rng.choice(list(alive.USUBJID))
            if rng.random() < 0.5 and len(ae[ae.USUBJID == u]):
                ae.at[rng.choice(list(ae[ae.USUBJID == u].index)), "AEOUT"] = "FATAL"
            else:
                last = max([x for x in ae[ae.USUBJID == u].AESTDTC if len(x) == 10] or [dm[dm.USUBJID == u].RFSTDTC.iloc[0]])
                if not last:
                    continue
                j = dm.index[dm.USUBJID == u][0]
                dm.at[j, "DTHDTC"] = (date.fromisoformat(last[:10]) - timedelta(days=rng.randint(1, 10))).isoformat()
                dm.at[j, "DTHFL"] = "Y"
            planted.append(k)
        elif k == "DOSE_AFTER_DISC":
            disp = ds[(ds.DSCAT == "DISPOSITION EVENT") & ~ds.DSDECOD.isin(["COMPLETED", "SCREEN FAILURE"])]
            cands = [u for u in disp.USUBJID if len(ex[ex.USUBJID == u])]
            if cands:
                u = rng.choice(cands)
                d = disp[disp.USUBJID == u].DSSTDTC.iloc[0][:10]
                row = ex[ex.USUBJID == u].iloc[-1].copy()
                st = date.fromisoformat(d) + timedelta(days=rng.randint(1, 14))
                row["EXSEQ"] = str(int(ex[ex.USUBJID == u].EXSEQ.astype(int).max()) + 1)
                row["EXSTDTC"], row["EXENDTC"] = st.isoformat(), (st + timedelta(days=rng.randint(3, 14))).isoformat()
                row["VISIT"] = "UNSCHEDULED"
                ex.loc[len(ex)] = row
                planted.append(k)
        elif k == "LAB_UNIT":
            c = lb[lb.LBTESTCD.isin([t for t, fct in LB_KEEP.items() if fct]) & (lb.LBSTRESN != "")]
            i = rng.choice(list(c.index))
            lb.at[i, "LBSTRESN"] = f"{float(lb.at[i, 'LBSTRESN']) * LB_KEEP[lb.at[i, 'LBTESTCD']]:.4g}"
            planted.append(k)
        elif k == "LAB_VISIT_DATE":
            sch = ~lb.VISIT.str.startswith("UNSCHEDULED")
            c = lb[sch & (lb.VISITNUM.astype(float) > 4) & (lb.LBDTC != "")]
            i = rng.choice(list(c.index))
            r = lb.loc[i]
            prev = lb[sch & (lb.USUBJID == r.USUBJID) & (lb.LBTESTCD == r.LBTESTCD) &
                      (lb.VISITNUM.astype(float) < float(r.VISITNUM)) & (lb.LBDTC != "")]
            if len(prev):
                newd = date.fromisoformat(prev.LBDTC.str[:10].max()) - timedelta(days=rng.randint(1, 5))
                lb.at[i, "LBDTC"] = newd.isoformat() + r.LBDTC[10:]
                planted.append(k)
    return planted


ALL = ["AE_DATE_ORDER", "AE_DUPLICATE", "SAE_CRITERIA", "DEATH_CONSISTENCY", "DOSE_AFTER_DISC", "LAB_UNIT",
       "LAB_VISIT_DATE"]

SPEC = """# Task {tid}: data review of an SDTM study package

Study `{studyid}`. Review the package in `input/` (`dm.csv`, `ae.csv`, `ex.csv`, `ds.csv`, `lb.csv`) the way a clinical data manager would before database lock. List every issue found by the checks below in `output/findings.csv`.

## Output
CSV with columns `CHECK`, `USUBJID`, `DOMAIN`, `SEQ`: one row per issue. `DOMAIN` and `SEQ` identify the record the issue is raised on (`AESEQ`, `EXSEQ` or `LBSEQ` as plain integers). A subject-level issue uses `DOMAIN` = `DM` and a blank `SEQ`. Do not list the same issue twice.

## Checks
- `AE_DATE_ORDER`: an adverse event that ends before it starts. Only compare complete dates. Raise it on the AE.
- `AE_DUPLICATE`: the same event entered more than once for a subject, meaning the same `AEDECOD` with the same `AESTDTC` (non-blank). Raise it on every copy except the one with the lowest `AESEQ`.
- `SAE_CRITERIA`: the serious flag and the seriousness criteria disagree. Either an AE marked serious with no seriousness criterion recorded as `Y`, or an AE not marked serious with any criterion recorded as `Y`. Raise it on the AE.
- `DEATH_CONSISTENCY`, any of:
  - an AE with a fatal outcome for a subject with no death date in DM (raise on the AE)
  - an AE with a complete start date after the subject's death date (raise on the AE)
  - a subject with a death date but no AE with a fatal outcome (raise on the subject)
- `DOSE_AFTER_DISC`: an exposure record that starts after the date the subject discontinued the study early. Early discontinuation is a disposition event other than completion or screen failure. Raise it on the EX record.
- `LAB_UNIT`: a numeric lab result that looks entered in the wrong unit, meaning it is at least 8 times higher, or at most 1/8, of the median of the same subject's *other* results for that test. Needs at least two other results. Raise it on the LB record.
- `LAB_VISIT_DATE`: at scheduled visits only (ignore visits named `UNSCHEDULED ...`), a lab result dated earlier than the latest date of the same subject's results for the same test at earlier scheduled visits (lower `VISITNUM`). Compare dates only, ignoring time. Raise it on the out-of-order record.

Some checks may find nothing in this package. Issues already present in the source data count the same as any others.
"""


def make_dr(tid, seed, n_subj, n_issues, kinds):
    rng = random.Random(seed)
    studyid, dm, ae, ex, ds, lb = build_package(rng, n_subj)
    natural = detect(dm, ae, ex, ds, lb)
    planted = plant(rng, dm, ae, ex, ds, lb, n_issues, kinds)
    found = detect(dm, ae, ex, ds, lb)
    expected = pd.DataFrame(sorted(found), columns=FINDING_COLS)
    meta = {"task": tid, "domain": "DR", "kind": "findings", "key": FINDING_COLS, "out": "findings.csv",
            "n_subjects": int(len(dm)), "n_records": int(len(expected)), "n_natural": len(natural),
            "planted": planted, "seed": seed,
            "by_check": {k: int((expected.CHECK == k).sum()) for k in ALL}}
    write_task(tid, SPEC.format(tid=tid, studyid=studyid),
               {"dm.csv": dm, "ae.csv": ae.sample(frac=1, random_state=seed), "ex.csv": ex, "ds.csv": ds,
                "lb.csv": lb.sample(frac=1, random_state=seed)}, expected, meta)
    return meta


TIER3 = [
    ("DR-01", 12, 6, ALL),
    ("DR-02", 16, 8, ALL),
    ("DR-03", 20, 10, ["AE_DATE_ORDER", "AE_DUPLICATE", "LAB_UNIT", "LAB_VISIT_DATE"]),
    ("DR-04", 24, 12, ["SAE_CRITERIA", "DEATH_CONSISTENCY", "DOSE_AFTER_DISC", "LAB_UNIT"]),
    ("DR-05", 28, 14, ALL),
    ("DR-06", 32, 16, ALL),
]


def main():
    for i, (tid, n, k, kinds) in enumerate(TIER3):
        m = make_dr(tid, 3000 + i, n, k, kinds)
        print(f"{tid}: {m['n_subjects']} subjects, {m['n_records']} findings ({m['n_natural']} natural), {m['by_check']}")


if __name__ == "__main__":
    main()
