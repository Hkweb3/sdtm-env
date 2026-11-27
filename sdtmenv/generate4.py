"""Tier 4: open-ended clinical review. No check list: the spec gives a protocol synopsis
and asks for the problems a clinical reviewer would query, at most 25. Planted problems
need medical or protocol knowledge to notice (sex-specific AEs, physiologically
impossible labs, data after death, wrong body-system coding...).

Graded by recall of planted problems; each problem lists the records that count as
citing it. Natural oddities in the source are neither rewarded nor penalized, which is
why the 25-finding cap matters.
"""
import json
import random
from datetime import date, timedelta

import pandas as pd

from sdtmenv.generate import ANSWERS, write_task
from sdtmenv.generate3 import build_package

FEMALE_ONLY = [("PREGNANCY", "PREGNANCY, PUERPERIUM AND PERINATAL CONDITIONS"),
               ("MENORRHAGIA", "REPRODUCTIVE SYSTEM AND BREAST DISORDERS"),
               ("OVARIAN CYST", "REPRODUCTIVE SYSTEM AND BREAST DISORDERS"),
               ("VAGINAL HAEMORRHAGE", "REPRODUCTIVE SYSTEM AND BREAST DISORDERS")]
MALE_ONLY = [("BENIGN PROSTATIC HYPERPLASIA", "REPRODUCTIVE SYSTEM AND BREAST DISORDERS"),
             ("ERECTILE DYSFUNCTION", "REPRODUCTIVE SYSTEM AND BREAST DISORDERS"),
             ("TESTICULAR PAIN", "REPRODUCTIVE SYSTEM AND BREAST DISORDERS")]
# Incompatible with life, yet mostly within 8x of normal so a ratio-to-median rule misses them.
# Not used: glucose 48 mmol/L (seen in hyperosmolar crisis) and cholesterol 31 mmol/L (homozygous FH).
IMPOSSIBLE = {"SODIUM": ["240", "62"], "K": ["0.9", "14.5"], "ALB": ["98", "4"]}
# Body systems that are unambiguously wrong for the planted term (no pruritus -> skin style defensible picks)
WRONG_SOC = ["EYE DISORDERS", "RENAL AND URINARY DISORDERS", "PREGNANCY, PUERPERIUM AND PERINATAL CONDITIONS"]
SOC_WORDS = {"EYE DISORDERS": ("EYE", "VISION", "VISUAL", "CONJUNCT", "LACRIM"),
             "RENAL AND URINARY DISORDERS": ("RENAL", "URIN", "KIDNEY", "BLADDER", "MICTUR", "NOCTUR"),
             "PREGNANCY, PUERPERIUM AND PERINATAL CONDITIONS": ("PREGNAN",)}
TYPES = ["SEX_SPECIFIC_AE", "IMPOSSIBLE_LAB", "DATA_AFTER_DEATH", "UNDERAGE", "WRONG_SOC", "AFTER_CUTOFF",
         "ARM_MISMATCH", "IMPLAUSIBLE_DOSE", "DUPLICATE_SUBJECT"]


def add_birth_dates(rng, dm):
    out = []
    for r in dm.itertuples():
        ref = date.fromisoformat(r.RFSTDTC[:10]) if r.RFSTDTC else date(2013, 1, 1)
        b = ref.replace(year=ref.year - int(r.AGE) - 1) + timedelta(days=rng.randint(5, 355))
        out.append(b.isoformat())
    dm.insert(dm.columns.get_loc("AGE"), "BRTHDTC", out)


def next_seq(df, u, col):
    s = df[df.USUBJID == u][col]
    return str(int(s.astype(int).max()) + 1) if len(s) else "1"


def plant(rng, kind, dm, ae, ex, ds, lb, cutoff, studyid):
    """Plant one problem; return the list of (DOMAIN, USUBJID, SEQ) citations that count, or None."""
    if kind == "SEX_SPECIFIC_AE":
        r = dm.loc[rng.choice(list(dm.index))]
        term, soc = rng.choice(MALE_ONLY if r.SEX == "F" else FEMALE_ONLY)
        base = ae[(ae.USUBJID == r.USUBJID) & (ae.AESTDTC.str.len() == 10)]
        st = base.AESTDTC.iloc[0] if len(base) else r.RFSTDTC
        if not st:
            return None
        seq = next_seq(ae, r.USUBJID, "AESEQ")
        ae.loc[len(ae)] = {**{c: "" for c in ae.columns}, "STUDYID": studyid, "DOMAIN": "AE", "USUBJID": r.USUBJID,
                           "AESEQ": seq, "AETERM": term, "AEDECOD": term, "AEBODSYS": soc, "AESEV": "MILD",
                           "AESER": "N", **{c: "N" for c in ae.columns if c in ("AESCAN", "AESCONG", "AESDISAB",
                                                                                   "AESDTH", "AESHOSP", "AESLIFE",
                                                                                   "AESOD")},
                           "AEREL": "NONE", "AEOUT": "RECOVERED/RESOLVED", "AESTDTC": st, "AEENDTC": st}
        return [("AE", r.USUBJID, seq)]
    if kind == "IMPOSSIBLE_LAB":
        c = lb[lb.LBTESTCD.isin(IMPOSSIBLE) & (lb.LBSTRESN != "")]
        i = rng.choice(list(c.index))
        lb.at[i, "LBSTRESN"] = rng.choice(IMPOSSIBLE[lb.at[i, "LBTESTCD"]])
        return [("LB", lb.at[i, "USUBJID"], lb.at[i, "LBSEQ"])]
    if kind == "DATA_AFTER_DEATH":
        alive = dm[(dm.DTHDTC == "")]
        cands = [u for u in alive.USUBJID if lb[(lb.USUBJID == u)].LBDTC.str[:10].nunique() >= 5]
        if not cands:
            return None
        u = rng.choice(cands)
        dates = sorted(lb[lb.USUBJID == u].LBDTC.str[:10].unique())
        death = (date.fromisoformat(dates[len(dates) // 2]) - timedelta(days=2)).isoformat()
        j = dm.index[dm.USUBJID == u][0]
        dm.at[j, "DTHDTC"], dm.at[j, "DTHFL"] = death, "Y"
        seq = next_seq(ae, u, "AESEQ")
        ae.loc[len(ae)] = {**{c: "N" if c in ("AESCAN", "AESCONG", "AESDISAB", "AESHOSP", "AESLIFE", "AESOD") else ""
                              for c in ae.columns}, "STUDYID": studyid, "DOMAIN": "AE", "USUBJID": u, "AESEQ": seq,
                           "AETERM": "SUDDEN DEATH", "AEDECOD": "SUDDEN DEATH",
                           "AEBODSYS": "GENERAL DISORDERS AND ADMINISTRATION SITE CONDITIONS", "AESEV": "SEVERE",
                           "AESER": "Y", "AESDTH": "Y", "AEREL": "NONE", "AEOUT": "FATAL", "AESTDTC": death,
                           "AEENDTC": death}
        after = [("LB", u, s) for s, d in zip(lb[lb.USUBJID == u].LBSEQ, lb[lb.USUBJID == u].LBDTC) if d[:10] > death]
        after += [("EX", u, s) for s, d in zip(ex[ex.USUBJID == u].EXSEQ, ex[ex.USUBJID == u].EXSTDTC) if d[:10] > death]
        after += [("DS", u, s) for s in ds[(ds.USUBJID == u) & (ds.DSDECOD == "COMPLETED")].DSSEQ]
        return after
    if kind == "UNDERAGE":
        j = rng.choice(list(dm.index))
        age = rng.choice([17, 23, 34, 41])
        ref = date.fromisoformat(dm.at[j, "RFSTDTC"][:10]) if dm.at[j, "RFSTDTC"] else date(2013, 1, 1)
        dm.at[j, "AGE"] = str(age)
        dm.at[j, "BRTHDTC"] = (ref.replace(year=ref.year - age - 1) + timedelta(days=rng.randint(5, 355))).isoformat()
        return [("DM", dm.at[j, "USUBJID"], "")]
    if kind == "WRONG_SOC":
        common = ae.AEDECOD.value_counts()
        common = common[common >= 2].index
        c = ae[ae.AEDECOD.isin(common)]
        i = rng.choice(list(c.index))
        term = ae.at[i, "AEDECOD"]
        ok = [s for s in WRONG_SOC if s != ae.at[i, "AEBODSYS"] and not any(w in term for w in SOC_WORDS[s])]
        ae.at[i, "AEBODSYS"] = rng.choice(ok)
        return [("AE", ae.at[i, "USUBJID"], ae.at[i, "AESEQ"])]
    if kind == "AFTER_CUTOFF":
        i = rng.choice(list(ae[ae.AESTDTC.str.len() == 10].index))
        st = date.fromisoformat(cutoff) + timedelta(days=rng.randint(20, 300))
        ae.at[i, "AESTDTC"], ae.at[i, "AEENDTC"] = st.isoformat(), ""
        ae.at[i, "AEOUT"] = "NOT RECOVERED/NOT RESOLVED"
        return [("AE", ae.at[i, "USUBJID"], ae.at[i, "AESEQ"])]
    if kind == "ARM_MISMATCH":
        pbo = set(dm[dm.ARM == "Placebo"].USUBJID)
        c = ex[ex.USUBJID.isin(pbo)]
        if not len(c):
            return None
        i = rng.choice(list(c.index))
        ex.at[i, "EXTRT"], ex.at[i, "EXDOSE"] = "XANOMELINE", rng.choice(["54", "81"])
        return [("EX", ex.at[i, "USUBJID"], ex.at[i, "EXSEQ"])]
    if kind == "IMPLAUSIBLE_DOSE":
        c = ex[ex.EXTRT == "XANOMELINE"]
        if not len(c):
            return None
        i = rng.choice(list(c.index))
        ex.at[i, "EXDOSE"] = str(int(ex.at[i, "EXDOSE"]) * 10)
        return [("EX", ex.at[i, "USUBJID"], ex.at[i, "EXSEQ"])]
    if kind == "DUPLICATE_SUBJECT":
        r = dm.loc[rng.choice(list(dm.index))].copy()
        other_sites = sorted(set(dm.SITEID) - {r.SITEID}) or [str(int(r.SITEID) + 1)]
        site = rng.choice(other_sites)
        new_u = f"{studyid}-{site}-{rng.randint(1000, 9999)}"
        old_u = r.USUBJID
        r["USUBJID"], r["SITEID"] = new_u, site
        dm.loc[len(dm)] = r
        scr = lb[(lb.USUBJID == old_u) & (lb.VISIT.str.startswith("SCREENING"))]
        for k, (_, x) in enumerate(scr.iterrows(), 1):
            x = x.copy()
            x["USUBJID"], x["LBSEQ"] = new_u, str(k)
            lb.loc[len(lb)] = x
        return [("DM", old_u, ""), ("DM", new_u, "")]
    raise ValueError(kind)


SPEC = """# Task {tid}: clinical data review before database lock

Study `{studyid}`: a randomized, double-blind study of a xanomeline transdermal patch in mild-to-moderate Alzheimer's disease.

## Protocol synopsis
- Arms, one patch daily for 26 weeks:
  - `Placebo`: 0 mg
  - `Xanomeline Low Dose`: 54 mg throughout
  - `Xanomeline High Dose`: 54 mg until the Week 2 visit, 81 mg from Week 2 to Week 24, then 54 mg from Week 24 to the end of treatment
- Key inclusion criterion: age 50 or older at entry.
- Data cutoff for this delivery: **{cutoff}**. Nothing in the database should be dated after it.

## Data
`input/` holds the SDTM package: `dm.csv`, `ae.csv`, `ex.csv`, `ds.csv`, `lb.csv`. Lab results are in SI units (`LBSTRESU`).

## Your job
Review the package the way an experienced clinical data reviewer would, and find the problems you would raise as queries to the sites: values that are impossible or implausible, or inconsistent with each other, with the protocol, or with medicine. Ordinary abnormal lab results and ordinary adverse events are not problems.

Write `output/findings.csv` with columns `USUBJID`, `DOMAIN`, `SEQ`, `ISSUE`:
- one row per problem, most important first, **at most 25 rows** (rows after the 25th are ignored)
- `DOMAIN` and `SEQ` identify the specific record the problem is on (`AESEQ`, `EXSEQ`, `LBSEQ` or `DSSEQ` as an integer)
- for a problem with the subject itself, use `DOMAIN` = `DM` and leave `SEQ` blank
- `ISSUE` is a one-line explanation
"""


def make_or(tid, seed, n_subj, kinds):
    rng = random.Random(seed)
    studyid, dm, ae, ex, ds, lb = build_package(rng, n_subj)
    add_birth_dates(rng, dm)
    all_dates = [d[:10] for df, c in ((ae, "AESTDTC"), (ae, "AEENDTC"), (ex, "EXENDTC"), (lb, "LBDTC"),
                                       (ds, "DSSTDTC")) for d in df[c] if d]
    cutoff = (date.fromisoformat(max(all_dates)) + timedelta(days=rng.randint(10, 40))).isoformat()
    problems = []
    for k in kinds:
        targets = plant(rng, k, dm, ae, ex, ds, lb, cutoff, studyid)
        if targets:
            problems.append({"id": f"P{len(problems) + 1:02d}", "type": k,
                             "targets": [list(t) for t in targets]})
    rows = [{"PROBLEM": p["id"], "TYPE": p["type"], "DOMAIN": d, "USUBJID": u, "SEQ": s}
            for p in problems for d, u, s in p["targets"]]
    meta = {"task": tid, "domain": "OR", "kind": "open_review", "out": "findings.csv", "cap": 25,
            "n_subjects": int(len(dm)), "n_records": len(problems), "seed": seed,
            "types": [p["type"] for p in problems], "key": ["USUBJID", "DOMAIN", "SEQ"]}
    write_task(tid, SPEC.format(tid=tid, studyid=studyid, cutoff=cutoff),
               {"dm.csv": dm, "ae.csv": ae.sample(frac=1, random_state=seed), "ex.csv": ex, "ds.csv": ds,
                "lb.csv": lb.sample(frac=1, random_state=seed)}, pd.DataFrame(rows), meta)
    return meta


TIER4 = [
    ("OR-01", 20, ["SEX_SPECIFIC_AE", "IMPOSSIBLE_LAB", "UNDERAGE", "WRONG_SOC", "AFTER_CUTOFF", "ARM_MISMATCH"]),
    ("OR-02", 22, ["IMPOSSIBLE_LAB", "IMPOSSIBLE_LAB", "DATA_AFTER_DEATH", "SEX_SPECIFIC_AE", "IMPLAUSIBLE_DOSE",
                   "DUPLICATE_SUBJECT", "WRONG_SOC"]),
    ("OR-03", 24, ["SEX_SPECIFIC_AE", "SEX_SPECIFIC_AE", "WRONG_SOC", "WRONG_SOC", "AFTER_CUTOFF", "UNDERAGE",
                   "IMPOSSIBLE_LAB", "ARM_MISMATCH"]),
    ("OR-04", 26, ["DATA_AFTER_DEATH", "DUPLICATE_SUBJECT", "IMPLAUSIBLE_DOSE", "IMPOSSIBLE_LAB", "IMPOSSIBLE_LAB",
                   "AFTER_CUTOFF", "WRONG_SOC", "SEX_SPECIFIC_AE"]),
    ("OR-05", 28, TYPES),
    ("OR-06", 30, TYPES + ["IMPOSSIBLE_LAB"]),
]


# ---------- v2: cross-domain blind spots (needs CM and MH) ----------

# (verbatim as the site wrote it, coded name or UNCODED, indication); the synopsis names only the classes
PROHIBITED = [("ARICEPT", "DONEPEZIL HYDROCHLORIDE", "MEMORY LOSS"),
              ("EXELON PATCH", "RIVASTIGMINE", "DEMENTIA"),
              ("RAZADYNE ER", "GALANTAMINE HYDROBROMIDE", "MEMORY"),
              ("DITROPAN XL", "OXYBUTYNIN CHLORIDE", "OVERACTIVE BLADDER"),
              ("ELAVIL", "AMITRIPTYLINE HYDROCHLORIDE", "INSOMNIA"),
              ("BENADRYL", "DIPHENHYDRAMINE HYDROCHLORIDE", "SLEEP")]
CONTRACEPTIVES = [("YASMIN", "DROSPIRENONE;ETHINYLESTRADIOL"), ("LOESTRIN 1/20", "ETHINYLESTRADIOL;NORETHISTERONE"),
                  ("MICROGYNON", "ETHINYLESTRADIOL;LEVONORGESTREL")]
NO_UTERUS_AES = [("UTERINE LEIOMYOMA", "NEOPLASMS BENIGN, MALIGNANT AND UNSPECIFIED (INCL CYSTS AND POLYPS)"),
                 ("ENDOMETRIAL HYPERPLASIA", "REPRODUCTIVE SYSTEM AND BREAST DISORDERS"),
                 ("MENORRHAGIA", "REPRODUCTIVE SYSTEM AND BREAST DISORDERS")]
CHILD_AES = [("DELAYED PUBERTY", "ENDOCRINE DISORDERS"), ("PRECOCIOUS PUBERTY", "ENDOCRINE DISORDERS"),
             ("INFANTILE COLIC", "GASTROINTESTINAL DISORDERS")]
CRIT_N = ("AESCAN", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE", "AESOD")


def add_ae(ae, studyid, u, term, soc, st):
    seq = next_seq(ae, u, "AESEQ")
    ae.loc[len(ae)] = {**{c: "" for c in ae.columns}, **{c: "N" for c in CRIT_N if c in ae.columns},
                       "STUDYID": studyid, "DOMAIN": "AE", "USUBJID": u, "AESEQ": seq, "AETERM": term,
                       "AEDECOD": term, "AEBODSYS": soc, "AESEV": "MILD", "AESER": "N", "AEREL": "NONE",
                       "AEOUT": "RECOVERED/RESOLVED", "AESTDTC": st,
                       "AEENDTC": (date.fromisoformat(st) + timedelta(days=9)).isoformat()}
    return seq


def on_treatment_date(rng, dm, u, ex=None):
    """A date inside the subject's actual dosing period. Early discontinuers stop well before
    RFSTDTC + 90 days, so a prohibited drug planted by offset alone may not be prohibited at all."""
    if ex is not None and len(ex[ex.USUBJID == u]):
        s = ex[ex.USUBJID == u]
        a = date.fromisoformat(s.EXSTDTC.min()[:10])
        b = date.fromisoformat(max(s.EXENDTC.max(), s.EXSTDTC.max())[:10])
        return (a + timedelta(days=rng.randint(1, max(1, (b - a).days - 1)))).isoformat()
    rf = dm[dm.USUBJID == u].RFSTDTC.iloc[0]
    return (date.fromisoformat(rf[:10]) + timedelta(days=rng.randint(15, 90))).isoformat() if rf else ""


def plant2(rng, kind, dm, ae, ex, ds, lb, cm, mh, studyid):
    treated = [u for u in dm[dm.RFSTDTC != ""].USUBJID if len(ex[ex.USUBJID == u])]
    if kind == "PROHIBITED_CM":
        u = rng.choice(treated)
        verb, dec, ind = rng.choice(PROHIBITED)
        seq = next_seq(cm, u, "CMSEQ")
        cm.loc[len(cm)] = {**{c: "" for c in cm.columns}, "STUDYID": studyid, "DOMAIN": "CM", "USUBJID": u,
                           "CMSEQ": seq, "CMTRT": verb, "CMDECOD": dec if rng.random() < 0.5 else "UNCODED",
                           "CMINDC": ind, "CMDOSE": "1", "CMDOSU": "TABLET", "CMDOSFRQ": "QD", "CMROUTE": "ORAL",
                           "CMSTDTC": on_treatment_date(rng, dm, u, ex)}
        return [("CM", u, seq)]
    if kind == "SURGICAL_HISTORY_CONFLICT":
        u = rng.choice(treated)
        st = on_treatment_date(rng, dm, u, ex)
        mseq = next_seq(mh, u, "MHSEQ")
        year = str(rng.randint(1975, 2005))
        if dm[dm.USUBJID == u].SEX.iloc[0] == "F":
            surg, (term, soc) = ("TOTAL ABDOMINAL HYSTERECTOMY", "HYSTERECTOMY"), rng.choice(NO_UTERUS_AES)
        else:
            surg, (term, soc) = (("RADICAL PROSTATECTOMY", "PROSTATECTOMY"),
                                 ("BENIGN PROSTATIC HYPERPLASIA", "REPRODUCTIVE SYSTEM AND BREAST DISORDERS"))
        mh.loc[len(mh)] = {"STUDYID": studyid, "DOMAIN": "MH", "USUBJID": u, "MHSEQ": mseq, "MHTERM": surg[0],
                           "MHDECOD": surg[1], "MHCAT": "HISTORICAL DIAGNOSIS",
                           "MHBODSYS": "SURGICAL AND MEDICAL PROCEDURES", "MHSTDTC": year}
        aseq = add_ae(ae, studyid, u, term, soc, st)
        return [("AE", u, aseq), ("MH", u, mseq)]
    if kind == "AGE_INAPPROPRIATE_AE":
        u = rng.choice(treated)
        term, soc = rng.choice(CHILD_AES)
        return [("AE", u, add_ae(ae, studyid, u, term, soc, on_treatment_date(rng, dm, u, ex)))]
    if kind == "SEX_SPECIFIC_LAB":
        u = rng.choice(treated)
        female = dm[dm.USUBJID == u].SEX.iloc[0] == "F"
        sched = lb[(lb.USUBJID == u) & ~lb.VISIT.str.startswith("UNSCHEDULED")]
        row = sched.iloc[rng.randint(0, len(sched) - 1)].copy()
        row["LBSEQ"] = next_seq(lb, u, "LBSEQ")
        if female:
            row["LBTESTCD"], row["LBTEST"], row["LBSTRESN"], row["LBSTRESU"] = (
                "PSA", "Prostate Specific Antigen", str(round(rng.uniform(1.2, 6.5), 1)), "ug/L")
        else:
            row["LBTESTCD"], row["LBTEST"], row["LBSTRESN"], row["LBSTRESU"] = (
                "HCG", "Choriogonadotropin Beta", str(rng.randint(800, 25000)), "IU/L")
        lb.loc[len(lb)] = row
        return [("LB", u, row["LBSEQ"])]
    if kind == "SEX_SPECIFIC_CM":
        males = [u for u in treated if dm[dm.USUBJID == u].SEX.iloc[0] == "M"]
        if not males:
            return None
        u = rng.choice(males)
        verb, dec = rng.choice(CONTRACEPTIVES)
        seq = next_seq(cm, u, "CMSEQ")
        cm.loc[len(cm)] = {**{c: "" for c in cm.columns}, "STUDYID": studyid, "DOMAIN": "CM", "USUBJID": u,
                           "CMSEQ": seq, "CMTRT": verb, "CMDECOD": dec if rng.random() < 0.5 else "UNCODED",
                           "CMINDC": "", "CMDOSE": "1", "CMDOSU": "TABLET", "CMDOSFRQ": "QD", "CMROUTE": "ORAL",
                           "CMSTDTC": on_treatment_date(rng, dm, u, ex)}
        return [("CM", u, seq)]
    return plant(rng, kind, dm, ae, ex, ds, lb, None, studyid)


SPEC2 = SPEC.replace(
    "- Key inclusion criterion: age 50 or older at entry.",
    "- Key inclusion criterion: men and women aged 50 or older at entry.\n"
    "- Prohibited from first dose to end of treatment: cholinesterase inhibitors, and medications with strong "
    "anticholinergic activity.").replace(
    "`dm.csv`, `ae.csv`, `ex.csv`, `ds.csv`, `lb.csv`. Lab results are in SI units (`LBSTRESU`).",
    "`dm.csv`, `ae.csv`, `ex.csv`, `ds.csv`, `lb.csv`, `cm.csv` (concomitant medications as the site wrote them "
    "in `CMTRT`; `CMDECOD` is the coded drug name or `UNCODED`), `mh.csv` (medical and surgical history). "
    "Lab results are in SI units (`LBSTRESU`).").replace(
    "(`AESEQ`, `EXSEQ`, `LBSEQ` or `DSSEQ` as an integer)",
    "(`AESEQ`, `EXSEQ`, `LBSEQ`, `DSSEQ`, `CMSEQ` or `MHSEQ` as an integer)")


def make_or2(tid, seed, n_subj, kinds):
    rng = random.Random(seed)
    studyid, dm, ae, ex, ds, lb, cm, mh = build_package(rng, n_subj, extra=True)
    mh["MHTERM"] = [d if t.startswith("VERBATIM_") and d else t for t, d in zip(mh.MHTERM, mh.MHDECOD)]
    add_birth_dates(rng, dm)
    all_dates = [d[:10] for df, c in ((ae, "AESTDTC"), (ae, "AEENDTC"), (ex, "EXENDTC"), (lb, "LBDTC"),
                                       (ds, "DSSTDTC"), (cm, "CMSTDTC")) for d in df[c] if len(d) >= 10]
    cutoff = (date.fromisoformat(max(all_dates)) + timedelta(days=rng.randint(10, 40))).isoformat()
    problems = []
    for k in kinds:
        targets = plant2(rng, k, dm, ae, ex, ds, lb, cm, mh, studyid) if k != "AFTER_CUTOFF" else \
            plant(rng, k, dm, ae, ex, ds, lb, cutoff, studyid)
        if targets:
            problems.append({"id": f"P{len(problems) + 1:02d}", "type": k, "targets": [list(t) for t in targets]})
    rows = [{"PROBLEM": p["id"], "TYPE": p["type"], "DOMAIN": d, "USUBJID": u, "SEQ": s}
            for p in problems for d, u, s in p["targets"]]
    meta = {"task": tid, "domain": "OR", "kind": "open_review", "out": "findings.csv", "cap": 25,
            "n_subjects": int(len(dm)), "n_records": len(problems), "seed": seed,
            "types": [p["type"] for p in problems], "key": ["USUBJID", "DOMAIN", "SEQ"]}
    write_task(tid, SPEC2.format(tid=tid, studyid=studyid, cutoff=cutoff),
               {"dm.csv": dm, "ae.csv": ae.sample(frac=1, random_state=seed), "ex.csv": ex, "ds.csv": ds,
                "lb.csv": lb.sample(frac=1, random_state=seed), "cm.csv": cm.sample(frac=1, random_state=seed),
                "mh.csv": mh}, pd.DataFrame(rows), meta)
    return meta


NEW = ["PROHIBITED_CM", "SURGICAL_HISTORY_CONFLICT", "AGE_INAPPROPRIATE_AE", "SEX_SPECIFIC_LAB", "SEX_SPECIFIC_CM"]
TIER4B = [
    ("OR-07", 20, NEW + ["IMPOSSIBLE_LAB"]),
    ("OR-08", 22, NEW + ["SEX_SPECIFIC_AE", "WRONG_SOC"]),
    ("OR-09", 24, ["PROHIBITED_CM", "PROHIBITED_CM", "SEX_SPECIFIC_LAB", "SURGICAL_HISTORY_CONFLICT",
                   "DATA_AFTER_DEATH", "UNDERAGE", "WRONG_SOC"]),
    ("OR-10", 26, NEW + ["ARM_MISMATCH", "SEX_SPECIFIC_AE"]),
    ("OR-11", 28, NEW + ["PROHIBITED_CM", "SEX_SPECIFIC_CM", "IMPOSSIBLE_LAB", "AFTER_CUTOFF"]),
    ("OR-12", 30, NEW + NEW[:3] + ["WRONG_SOC", "DUPLICATE_SUBJECT"]),
]


# ---------- v3: hard mode, every planted problem needs two records plus clinical knowledge ----------

# (MH verbatim, MH coded, AEs impossible without the organ). Laterality matters: a unilateral
# amputee can still get an ingrown toenail, so a decoy with one leg gets one legitimately.
ABSENT_ORGAN = [(("BILATERAL BKA", "LEG AMPUTATION"),
                 [("INGROWN TOENAIL", "SKIN AND SUBCUTANEOUS TISSUE DISORDERS"),
                  ("ANKLE FRACTURE", "INJURY, POISONING AND PROCEDURAL COMPLICATIONS"),
                  ("PLANTAR FASCIITIS", "MUSCULOSKELETAL AND CONNECTIVE TISSUE DISORDERS")]),
                (("TOTAL LARYNGECTOMY FOR SCC LARYNX", "LARYNGECTOMY"),
                 [("VOCAL CORD POLYP", "RESPIRATORY, THORACIC AND MEDIASTINAL DISORDERS"),
                  ("VOCAL CORD PARALYSIS", "RESPIRATORY, THORACIC AND MEDIASTINAL DISORDERS")]),
                (("TOTAL GASTRECTOMY", "GASTRECTOMY"),
                 [("GASTRITIS", "GASTROINTESTINAL DISORDERS"), ("GASTRIC ULCER", "GASTROINTESTINAL DISORDERS")])]
# AE term -> (lab test, value range pointing the opposite way)
AE_VS_LAB = {"HYPOKALAEMIA": ("K", 5.8, 6.4), "HYPERKALAEMIA": ("K", 2.8, 3.1),
             "HYPONATRAEMIA": ("SODIUM", 147, 151), "HYPERNATRAEMIA": ("SODIUM", 126, 129),
             "HYPOGLYCAEMIA": ("GLUC", 16.0, 22.0), "HYPERGLYCAEMIA": ("GLUC", 2.4, 2.9)}
APP_SITE = ["APPLICATION SITE ERYTHEMA", "APPLICATION SITE PRURITUS", "APPLICATION SITE IRRITATION"]
# history a subject of the other sex cannot have, as sites abbreviate it
MALE_ONLY_MH = [("TURP", "TRANSURETHRAL PROSTATECTOMY"), ("VASECTOMY", "VASECTOMY")]
FEMALE_ONLY_MH = [("C-SECTION X2", "CAESAREAN SECTION"), ("BTL", "FEMALE STERILISATION")]


def add_mh(mh, studyid, u, term, decod, year):
    seq = next_seq(mh, u, "MHSEQ")
    mh.loc[len(mh)] = {"STUDYID": studyid, "DOMAIN": "MH", "USUBJID": u, "MHSEQ": seq, "MHTERM": term,
                       "MHDECOD": decod, "MHCAT": "HISTORICAL DIAGNOSIS",
                       "MHBODSYS": "SURGICAL AND MEDICAL PROCEDURES", "MHSTDTC": year}
    return seq


def adult_year(rng, dm, u):
    born = int(dm[dm.USUBJID == u].BRTHDTC.iloc[0][:4])
    return str(rng.randint(born + 25, min(born + 60, 2005)))


def plant3(rng, kind, dm, ae, ex, ds, lb, cm, mh, studyid):
    treated = [u for u in dm[dm.RFSTDTC != ""].USUBJID if len(ex[ex.USUBJID == u])]
    if kind == "ABSENT_ORGAN":
        (term, decod), aes = rng.choice(ABSENT_ORGAN)
        u = rng.choice(treated)
        mseq = add_mh(mh, studyid, u, term, decod, adult_year(rng, dm, u))
        aterm, soc = rng.choice(aes)
        aseq = add_ae(ae, studyid, u, aterm, soc, on_treatment_date(rng, dm, u, ex))
        if decod == "LEG AMPUTATION":  # decoy: one leg left, so the same AE is fine
            v = rng.choice([x for x in treated if x != u])
            add_mh(mh, studyid, v, "RIGHT BKA", "LEG AMPUTATION", adult_year(rng, dm, v))
            add_ae(ae, studyid, v, aterm, soc, on_treatment_date(rng, dm, v, ex))
        return [("AE", u, aseq), ("MH", u, mseq)]
    if kind == "AE_LAB_CONTRADICTION":
        term = rng.choice(sorted(AE_VS_LAB))
        test, lo, hi = AE_VS_LAB[term]
        c = lb[lb.USUBJID.isin(treated) & (lb.LBTESTCD == test) & (lb.LBSTRESN != "") &
               ~lb.VISIT.str.startswith("SCREENING")]
        # a lone sample: no other result for the same test within 10 days
        lone = [i for i in c.index if not any(
            abs((date.fromisoformat(d[:10]) - date.fromisoformat(c.at[i, "LBDTC"][:10])).days) <= 10
            for d in lb[(lb.USUBJID == c.at[i, "USUBJID"]) & (lb.LBTESTCD == test)].drop(i).LBDTC)]
        i = rng.choice(lone)
        v = rng.uniform(lo, hi)  # formatted like the source, so the planted value has no tell
        lb.at[i, "LBSTRESN"] = (str(round(v)) if test == "SODIUM" else
                                f"{round(v / 0.05551) * 0.05551:.5f}".rstrip("0") if test == "GLUC" else f"{v:.1f}")
        u, st = lb.at[i, "USUBJID"], lb.at[i, "LBDTC"][:10]
        aseq = add_ae(ae, studyid, u, term, "METABOLISM AND NUTRITION DISORDERS", st)
        ae.loc[ae.index[-1], "AESEV"] = "MODERATE"
        # only the AE counts: flagging the lab alone as "high" misses the contradiction
        return [("AE", u, aseq)]
    if kind == "APP_SITE_BEFORE_PATCH":
        u = rng.choice(treated)
        first = date.fromisoformat(ex[ex.USUBJID == u].EXSTDTC.min()[:10])
        st = (first - timedelta(days=rng.randint(4, 14))).isoformat()
        seq = add_ae(ae, studyid, u, rng.choice(APP_SITE), "GENERAL DISORDERS AND ADMINISTRATION SITE CONDITIONS", st)
        ae.loc[ae.index[-1], "AEENDTC"] = (date.fromisoformat(st) + timedelta(days=2)).isoformat()
        return [("AE", u, seq)]
    if kind == "SEX_SPECIFIC_MH":
        u = rng.choice(treated)
        term, decod = rng.choice(MALE_ONLY_MH if dm[dm.USUBJID == u].SEX.iloc[0] == "F" else FEMALE_ONLY_MH)
        return [("MH", u, add_mh(mh, studyid, u, term, decod, adult_year(rng, dm, u)))]
    if kind == "MH_BEFORE_BIRTH":
        born = dict(zip(dm.USUBJID, dm.BRTHDTC.str[:4].astype(int)))
        c = mh[(mh.MHSTDTC.str.len() >= 4) & (mh.MHCAT != "PRIMARY DIAGNOSIS")]
        i = rng.choice(list(c.index))
        y = born[mh.at[i, "USUBJID"]] - rng.randint(3, 12)
        mh.at[i, "MHSTDTC"] = str(y) + mh.at[i, "MHSTDTC"][4:]
        return [("MH", mh.at[i, "USUBJID"], mh.at[i, "MHSEQ"])]
    return plant2(rng, kind, dm, ae, ex, ds, lb, cm, mh, studyid)


def make_or3(tid, seed, n_subj, kinds):
    rng = random.Random(seed)
    studyid, dm, ae, ex, ds, lb, cm, mh = build_package(rng, n_subj, extra=True)
    mh["MHTERM"] = [d if t.startswith("VERBATIM_") and d else t for t, d in zip(mh.MHTERM, mh.MHDECOD)]
    add_birth_dates(rng, dm)
    problems = []
    for k in kinds:
        targets = plant3(rng, k, dm, ae, ex, ds, lb, cm, mh, studyid)
        if targets:
            problems.append({"id": f"P{len(problems) + 1:02d}", "type": k, "targets": [list(t) for t in targets]})
    all_dates = [d[:10] for df, c in ((ae, "AESTDTC"), (ae, "AEENDTC"), (ex, "EXENDTC"), (lb, "LBDTC"),
                                       (ds, "DSSTDTC"), (cm, "CMSTDTC")) for d in df[c] if len(d) >= 10]
    cutoff = (date.fromisoformat(max(all_dates)) + timedelta(days=rng.randint(10, 40))).isoformat()
    rows = [{"PROBLEM": p["id"], "TYPE": p["type"], "DOMAIN": d, "USUBJID": u, "SEQ": s}
            for p in problems for d, u, s in p["targets"]]
    meta = {"task": tid, "domain": "OR", "kind": "open_review", "out": "findings.csv", "cap": 25,
            "n_subjects": int(len(dm)), "n_records": len(problems), "seed": seed,
            "types": [p["type"] for p in problems], "key": ["USUBJID", "DOMAIN", "SEQ"]}
    mh = mh.sort_values(["USUBJID", "MHSEQ"], key=lambda s: s.astype(int) if s.name == "MHSEQ" else s)
    write_task(tid, SPEC2.format(tid=tid, studyid=studyid, cutoff=cutoff),
               {"dm.csv": dm, "ae.csv": ae.sample(frac=1, random_state=seed), "ex.csv": ex, "ds.csv": ds,
                "lb.csv": lb.sample(frac=1, random_state=seed), "cm.csv": cm.sample(frac=1, random_state=seed),
                "mh.csv": mh}, pd.DataFrame(rows), meta)
    return meta


HARD = ["ABSENT_ORGAN", "AE_LAB_CONTRADICTION", "APP_SITE_BEFORE_PATCH", "SEX_SPECIFIC_MH", "MH_BEFORE_BIRTH"]
TIER4C = [
    ("OR-13", 24, HARD + ["ABSENT_ORGAN", "SURGICAL_HISTORY_CONFLICT", "WRONG_SOC"]),
    ("OR-14", 28, HARD + ["AE_LAB_CONTRADICTION", "AGE_INAPPROPRIATE_AE", "SEX_SPECIFIC_AE", "SEX_SPECIFIC_CM"]),
    ("OR-15", 30, HARD + ["ABSENT_ORGAN", "AE_LAB_CONTRADICTION", "MH_BEFORE_BIRTH", "SURGICAL_HISTORY_CONFLICT"]),
]


def main():
    import sys
    if "--v3" in sys.argv:
        for i, (tid, n, kinds) in enumerate(TIER4C):
            m = make_or3(tid, 4200 + i, n, kinds)
            print(f"{tid}: {m['n_subjects']} subjects, {m['n_records']} planted problems: {m['types']}")
        return
    if "--v2" not in sys.argv:
        for i, (tid, n, kinds) in enumerate(TIER4):
            m = make_or(tid, 4000 + i, n, kinds)
            print(f"{tid}: {m['n_subjects']} subjects, {m['n_records']} planted problems: {m['types']}")
    for i, (tid, n, kinds) in enumerate(TIER4B):
        m = make_or2(tid, 4100 + i, n, kinds)
        print(f"{tid}: {m['n_subjects']} subjects, {m['n_records']} planted problems: {m['types']}")


if __name__ == "__main__":
    main()
