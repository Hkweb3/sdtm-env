"""Tier 2 tasks: ADaM ADAE derivations, LB unit conversion + baseline, and AE mapping
where each site's date locale has to be inferred from the data.

Same contract as generate.py: truth first (re-identified Pilot01), inputs rendered
from it, answers kept outside tasks/.
"""
import calendar
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from sdtmenv.generate import (COMMON_RULES, MON, load, make_ae, raw_date, reidentify, shift, study_day, write_task,
                              ANSWERS)

# ---------- ADAE ----------

ADAE_COLS = ["STUDYID", "USUBJID", "AESEQ", "AETERM", "AEDECOD", "AEBODSYS", "TRTSDT", "TRTEDT", "ASTDT", "ASTDTF",
             "AENDT", "AENDTF", "ASTDY", "AENDY", "ADURN", "TRTEMFL", "AOCCFL", "AOCCPFL"]


def imp_end(dtc):
    if len(dtc) == 10:
        return dtc, ""
    if len(dtc) == 7:
        y, m = int(dtc[:4]), int(dtc[5:7])
        return f"{dtc}-{calendar.monthrange(y, m)[1]:02d}", "D"
    if len(dtc) == 4:
        return f"{dtc}-12-31", "M"
    return "", ""


def imp_start(dtc, trtsdt, aendt_full):
    if len(dtc) == 10:
        d, f = dtc, ""
    elif len(dtc) == 7:
        d, f = (trtsdt if trtsdt[:7] == dtc else f"{dtc}-01"), "D"
    elif len(dtc) == 4:
        d, f = (trtsdt if trtsdt[:4] == dtc else f"{dtc}-01-01"), "M"
    else:
        d, f = (trtsdt, "Y") if trtsdt else ("", "")
    if f and d and aendt_full and d > aendt_full:
        d = aendt_full
    return d, f


def make_adae(tid, seed, n_subj, p_partial, window):
    rng = random.Random(seed)
    dm, ae = load("dm"), load("ae")
    ae = ae[ae.AETERM != ""]
    treated = dm[dm.RFXSTDTC.str.len() >= 10].USUBJID
    studyid, days, pick = reidentify(dm, rng, n_subj, pool=sorted(set(ae.USUBJID) & set(treated)))
    idmap = pick.set_index("USUBJID")
    sdtm, truth = [], []
    for u, g in ae[ae.USUBJID.isin(pick.USUBJID)].groupby("USUBJID"):
        p = idmap.loc[u]
        trtsdt, trtedt = shift(p.RFXSTDTC, days), shift(p.RFXENDTC, days)
        for i, r in enumerate(g.sort_values("AESEQ").itertuples(), 1):
            st, en = shift(r.AESTDTC, days), shift(r.AEENDTC, days)
            x = rng.random()
            if len(st) == 10 and x < p_partial:
                st = st[:7]
            elif len(st) == 10 and x < p_partial * 1.4:
                st = st[:4]
            elif len(st) == 10 and x < p_partial * 1.55:
                st = ""
            y = rng.random()
            if len(en) == 10 and y < p_partial * 0.8:
                en = en[:7]
            elif len(en) == 10 and y < p_partial:
                en = en[:4]
            # edge cases the natural data rarely produces
            if i <= 2 and trtsdt and trtedt and rng.random() < 0.5:
                kind = rng.choice(["cap", "window_last_day", "window_plus_1", "day_before"])
                tsd, ted = date.fromisoformat(trtsdt), date.fromisoformat(trtedt)
                if kind == "cap":  # partial start in TRTSDT's month, complete end before TRTSDT
                    st, en = trtsdt[:7], (tsd - timedelta(days=rng.randint(1, 3))).isoformat()
                elif kind == "window_last_day":
                    st = (ted + timedelta(days=window)).isoformat()
                    en = (ted + timedelta(days=window + 5)).isoformat()
                elif kind == "window_plus_1":
                    st = (ted + timedelta(days=window + 1)).isoformat()
                    en = ""
                else:
                    st = (tsd - timedelta(days=1)).isoformat()
                    en = (tsd + timedelta(days=rng.randint(0, 20))).isoformat()
            sdtm.append({"STUDYID": studyid, "DOMAIN": "AE", "USUBJID": p.NEW_USUBJID, "AESEQ": i, "AETERM": r.AETERM,
                         "AEDECOD": r.AEDECOD, "AEBODSYS": r.AEBODSYS, "AESEV": r.AESEV, "AESER": r.AESER,
                         "AESTDTC": st, "AEENDTC": en})
            aendt, aendtf = imp_end(en)
            astdt, astdtf = imp_start(st, trtsdt, aendt if aendtf == "" else "")
            upper = (date.fromisoformat(trtedt) + timedelta(days=window)).isoformat() if trtedt else "9999-12-31"
            teae = "Y" if astdt and trtsdt and trtsdt <= astdt <= upper else ""
            dur = str((date.fromisoformat(aendt) - date.fromisoformat(astdt)).days + 1) if astdt and aendt else ""
            truth.append({"STUDYID": studyid, "USUBJID": p.NEW_USUBJID, "AESEQ": i, "AETERM": r.AETERM,
                          "AEDECOD": r.AEDECOD, "AEBODSYS": r.AEBODSYS, "TRTSDT": trtsdt, "TRTEDT": trtedt,
                          "ASTDT": astdt, "ASTDTF": astdtf, "AENDT": aendt, "AENDTF": aendtf,
                          "ASTDY": study_day(astdt, trtsdt), "AENDY": study_day(aendt, trtsdt), "ADURN": dur,
                          "TRTEMFL": teae})
    t = pd.DataFrame(truth)
    t["AOCCFL"], t["AOCCPFL"] = "", ""
    te = t[t.TRTEMFL == "Y"].sort_values(["USUBJID", "ASTDT", "AESEQ"])
    t.loc[te.drop_duplicates("USUBJID").index, "AOCCFL"] = "Y"
    t.loc[te.drop_duplicates(["USUBJID", "AEDECOD"]).index, "AOCCPFL"] = "Y"
    expected = t[ADAE_COLS].sort_values(["USUBJID", "AESEQ"]).reset_index(drop=True)
    adsl = pd.DataFrame({"STUDYID": studyid, "USUBJID": pick.NEW_USUBJID,
                         "TRTSDT": [shift(s, days) for s in pick.RFXSTDTC],
                         "TRTEDT": [shift(s, days) for s in pick.RFXENDTC]}).sort_values("USUBJID")
    spec = f"""# Task {tid}: derive ADaM ADAE from SDTM AE

Study `{studyid}`. Build `output/adae.csv` from `input/ae.csv` (SDTM AE) and `input/adsl.csv` (treatment start `TRTSDT` and end `TRTEDT` per subject). One output row per AE record.

## Output columns
{", ".join(f"`{c}`" for c in ADAE_COLS)}

## Rules
- Carry `STUDYID`, `USUBJID`, `AESEQ`, `AETERM`, `AEDECOD`, `AEBODSYS` from AE, and `TRTSDT`, `TRTEDT` from ADSL.
- **End date `AENDT`** from `AEENDTC`, imputed:
  - complete date: use it, `AENDTF` blank
  - `YYYY-MM`: last day of that month, `AENDTF` = `D`
  - `YYYY`: December 31 of that year, `AENDTF` = `M`
  - missing (ongoing): `AENDT` and `AENDTF` blank
- **Start date `ASTDT`** from `AESTDTC`, imputed:
  - complete date: use it, `ASTDTF` blank
  - `YYYY-MM`: if it is the same year and month as `TRTSDT`, use `TRTSDT`; otherwise the first day of the month. `ASTDTF` = `D`
  - `YYYY`: if it is the same year as `TRTSDT`, use `TRTSDT`; otherwise January 1. `ASTDTF` = `M`
  - missing: use `TRTSDT`, `ASTDTF` = `Y`
  - If an *imputed* `ASTDT` falls after a *complete* (not imputed) `AENDT`, use `AENDT` instead (keep the flag).
- `ASTDY`, `AENDY`: study day relative to `TRTSDT` (date − TRTSDT + 1 on or after it, date − TRTSDT before it; no day 0). Blank if either date is blank.
- `ADURN` = `AENDT` − `ASTDT` + 1 in days, blank if either is blank.
- `TRTEMFL` = `Y` when `ASTDT` is on or after `TRTSDT` and on or before `TRTEDT` + {window} days; otherwise blank.
- Among records with `TRTEMFL` = `Y` only, sorted by `ASTDT` then `AESEQ`:
  - `AOCCFL` = `Y` on each subject's first record
  - `AOCCPFL` = `Y` on each subject's first record per `AEDECOD`
  - other records leave these blank
- All dates `YYYY-MM-DD`. Sort output by `USUBJID`, then `AESEQ`.
- Write the output as CSV with a header row and exactly the columns listed, in that order. Leave unknown values empty.
"""
    meta = {"task": tid, "domain": "ADAE", "key": ["USUBJID", "AESEQ"], "traps": [f"partial={p_partial}",
            f"window={window}"], "n_subjects": int(len(pick)), "n_records": int(len(expected)), "seed": seed,
            "out": "adae.csv", "free": ["AETERM", "AEDECOD", "AEBODSYS"]}
    write_task(tid, spec, {"ae.csv": pd.DataFrame(sdtm), "adsl.csv": adsl}, expected, meta)


# ---------- LB ----------

# test: (raw vendor name, LBTEST, standard unit, factor from the conventional unit, decimals)
LB_TESTS = {
    "GLUC": ("Glucose", "Glucose", "mmol/L", "0.0555", 2),
    "CREAT": ("Creatinine", "Creatinine", "umol/L", "88.42", 1),
    "BILI": ("Bilirubin, total", "Bilirubin", "umol/L", "17.1", 1),
    "HGB": ("Hemoglobin", "Hemoglobin", "mmol/L", "0.6206", 2),
    "ALB": ("Albumin", "Albumin", "g/L", "10", 0),
    "ALT": ("ALT (SGPT)", "Alanine Aminotransferase", "U/L", "1", 0),
    "CHOL": ("Cholesterol, total", "Cholesterol", "mmol/L", "0.02586", 2),
    "K": ("Potassium", "Potassium", "mmol/L", "1", 1),
    "SODIUM": ("Sodium", "Sodium", "mmol/L", "1", 0),
    "CA": ("Calcium", "Calcium", "mmol/L", "0.2495", 2),
}
LB_COLS = ["STUDYID", "DOMAIN", "USUBJID", "LBSPID", "LBTESTCD", "LBTEST", "LBORRES", "LBORRESU", "LBORNRLO",
           "LBORNRHI", "LBSTRESC", "LBSTRESN", "LBSTRESU", "LBSTNRLO", "LBSTNRHI", "LBNRIND", "LBBLFL", "VISIT",
           "LBDTC", "LBDY"]


def rnd(x, dp):
    q = Decimal(1).scaleb(-dp)
    return str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))


def raw_dt(iso_dt):
    d = date.fromisoformat(iso_dt[:10])
    return f"{d.day:02d}{MON[d.month - 1]}{d.year} {iso_dt[11:16]}" if len(iso_dt) >= 16 else f"{d.day:02d}{MON[d.month - 1]}{d.year}"


def make_lb(tid, seed, n_subj, traps):
    rng = random.Random(seed)
    dm, lb = load("dm"), load("lb")
    lb = lb[lb.LBTESTCD.isin(LB_TESTS) & (lb.LBORRES != "")]
    treated = dm[dm.RFXSTDTC.str.len() >= 10].USUBJID
    studyid, days, pick = reidentify(dm, rng, n_subj, pool=sorted(set(lb.USUBJID) & set(treated)))
    idmap = pick.set_index("USUBJID")
    si_site = rng.choice(sorted(pick.NEW_SITE.unique())) if "si_site" in traps else None
    rows = []
    for u, g in lb[lb.USUBJID.isin(pick.USUBJID)].groupby("USUBJID"):
        p = idmap.loc[u]
        recs = []
        for r in g.itertuples():
            recs.append(dict(test=r.LBTESTCD, orres=r.LBORRES, orresu=r.LBORRESU, lo=r.LBORNRLO, hi=r.LBORNRHI,
                             visit=r.VISIT, dtc=shift(r.LBDTC[:10], days) + r.LBDTC[10:16]))
        rfst = shift(p.RFXSTDTC, days)
        if "retest" in traps:  # same-day retests before first dose: the later one is baseline
            for test in rng.sample(sorted({x["test"] for x in recs}), k=3):
                base = [x for x in recs if x["test"] == test and x["dtc"][:10] <= rfst]
                if base:
                    b = max(base, key=lambda x: x["dtc"])
                    t2 = (pd.Timestamp(b["dtc"] if len(b["dtc"]) > 10 else b["dtc"] + "T08:00") + pd.Timedelta(minutes=rng.randint(40, 300)))
                    v = float(b["orres"]) * rng.uniform(0.85, 1.15)
                    recs.append(dict(b, orres=rnd(v, max(0, len(b["orres"].split(".")[1]) if "." in b["orres"] else 0)),
                                     visit="UNSCHEDULED", dtc=t2.strftime("%Y-%m-%dT%H:%M")))
        if "lessthan" in traps:
            for x in rng.sample([x for x in recs if x["test"] in ("BILI", "ALT")], k=2):
                x["orres"] = "<" + ("0.2" if x["test"] == "BILI" else "3")
        for i, x in enumerate(sorted(recs, key=lambda x: (x["test"], x["dtc"])), 1):
            name, lbtest, stdu, factor, dp = LB_TESTS[x["test"]]
            si = si_site == p.NEW_SITE and x["test"] == "GLUC"
            numeric = not x["orres"].startswith("<")
            if si and numeric:  # this site's lab reports glucose already in mmol/L
                x["orres"] = rnd(Decimal(x["orres"]) * Decimal(factor), 1)
                x["lo"], x["hi"] = (rnd(Decimal(v) * Decimal(factor), 1) if v else "" for v in (x["lo"], x["hi"]))
                x["orresu"] = "mmol/L"
            f = Decimal("1") if x["orresu"] == stdu else Decimal(factor)
            strn = rnd(Decimal(x["orres"]) * f, dp) if numeric else ""
            nlo = rnd(Decimal(x["lo"]) * f, dp) if x["lo"] else ""
            nhi = rnd(Decimal(x["hi"]) * f, dp) if x["hi"] else ""
            ind = ""
            if strn and nlo and nhi:
                ind = "LOW" if Decimal(strn) < Decimal(nlo) else "HIGH" if Decimal(strn) > Decimal(nhi) else "NORMAL"
            rows.append({"STUDYID": studyid, "DOMAIN": "LB", "USUBJID": p.NEW_USUBJID, "LBSPID": f"L{i:04d}",
                         "LBTESTCD": x["test"], "LBTEST": lbtest, "LBORRES": x["orres"], "LBORRESU": x["orresu"],
                         "LBORNRLO": x["lo"], "LBORNRHI": x["hi"], "LBSTRESC": strn if numeric else x["orres"],
                         "LBSTRESN": strn, "LBSTRESU": stdu, "LBSTNRLO": nlo, "LBSTNRHI": nhi, "LBNRIND": ind,
                         "VISIT": x["visit"], "LBDTC": x["dtc"], "LBDY": study_day(x["dtc"][:10], rfst),
                         "_rfst": rfst, "SUBJECT": f"{p.NEW_SITE}-{p.NEW_SUBJ}", "NAME": name})
    t = pd.DataFrame(rows)
    t["LBBLFL"] = ""
    pre = t[(t.LBSTRESN != "") & (t.LBDTC.str[:10] <= t._rfst)].sort_values(["USUBJID", "LBTESTCD", "LBDTC"])
    t.loc[pre.drop_duplicates(["USUBJID", "LBTESTCD"], keep="last").index, "LBBLFL"] = "Y"
    expected = t[LB_COLS].sort_values(["USUBJID", "LBTESTCD", "LBDTC", "LBSPID"]).reset_index(drop=True)
    raw = pd.DataFrame({"SUBJECT": t.SUBJECT, "RECID": t.LBSPID, "VISIT": t.VISIT, "COLLECTED": t.LBDTC.map(raw_dt),
                        "TEST": t.NAME, "RESULT": t.LBORRES, "UNIT": t.LBORRESU, "RANGE_LOW": t.LBORNRLO,
                        "RANGE_HIGH": t.LBORNRHI}).sample(frac=1, random_state=rng.randint(0, 10**6))
    dmi = pd.DataFrame({"STUDYID": studyid, "USUBJID": pick.NEW_USUBJID, "RFSTDTC": [shift(s, days) for s in pick.RFXSTDTC]})
    conv = "\n".join(f"| {name} | `{cd}` | {lbt} | {stdu} | {factor} | {dp} |"
                     for cd, (name, lbt, stdu, factor, dp) in LB_TESTS.items())
    spec = f"""# Task {tid}: map central-lab results to SDTM LB with standard units

Study `{studyid}`. Map `input/raw_lab.csv` to `output/lb.csv`. `input/dm.csv` gives each subject's `RFSTDTC` (first dose date).

## Output columns
{", ".join(f"`{c}`" for c in LB_COLS)}

## Tests and conversion to standard units

| Raw `TEST` | `LBTESTCD` | `LBTEST` | Standard unit `LBSTRESU` | Factor from the conventional unit | Decimals |
|---|---|---|---|---|---|
{conv}

## Rules
- `STUDYID` = `{studyid}`, `DOMAIN` = `LB`. Raw `SUBJECT` is `<site>-<subject>`; `USUBJID` = `STUDYID-SITE-SUBJECT`. `LBSPID` = raw `RECID`.
- `LBORRES`, `LBORRESU`, `LBORNRLO`, `LBORNRHI` = raw `RESULT`, `UNIT`, `RANGE_LOW`, `RANGE_HIGH` unchanged.
- **Conversion:** if the raw `UNIT` already equals the standard unit, the factor is 1. Otherwise, multiply by the factor in the table. Apply the same conversion to the result and to both range limits.
- **Rounding:** round the converted values to the table's decimals, half away from zero (2.345 → 2.35).
- `LBSTRESN` is the rounded number. `LBSTRESC` is the same number as text with exactly that many decimals, keeping trailing zeros (`5.50`, not `5.5`).
- `LBSTNRLO`, `LBSTNRHI` are the rounded converted limits. `LBSTRESU` is the standard unit.
- **Results like `<0.2`:** `LBSTRESC` = the raw text unchanged, and `LBSTRESN` and `LBNRIND` are blank. The limits are still converted.
- `LBNRIND`: `LOW` if `LBSTRESN` < `LBSTNRLO`, `HIGH` if `LBSTRESN` > `LBSTNRHI`, otherwise `NORMAL`. Compare the rounded values. Blank when the result or either limit is missing.
- `LBDTC` = `COLLECTED` as `YYYY-MM-DDTHH:MM`. Raw format is `DDMONYYYY HH:MM`. `VISIT` = raw `VISIT`.
- `LBDY` = study day of the `LBDTC` date relative to `RFSTDTC` (no day 0).
- **Baseline `LBBLFL` = `Y`:** for each subject and test, the latest record (by `LBDTC`, time included) with a non-blank `LBSTRESN` whose date is on or before `RFSTDTC`. Leave it blank on all other records.
- Sort by `USUBJID`, `LBTESTCD`, `LBDTC`, `LBSPID`.
- Write the output as CSV with a header row and exactly the columns listed, in that order. Leave unknown values empty.
"""
    meta = {"task": tid, "domain": "LB", "key": ["USUBJID", "LBSPID"], "traps": traps, "n_subjects": int(len(pick)),
            "n_records": int(len(expected)), "seed": seed, "out": "lb.csv",
            "free": ["LBORRES", "LBORRESU", "LBORNRLO", "LBORNRHI", "VISIT"]}
    write_task(tid, spec, {"raw_lab.csv": raw, "dm.csv": dmi}, expected, meta)


TIER2 = [
    ("ADAE-01", lambda t, s: make_adae(t, s, 10, 0.20, 30)),
    ("ADAE-02", lambda t, s: make_adae(t, s, 14, 0.30, 30)),
    ("ADAE-03", lambda t, s: make_adae(t, s, 18, 0.35, 14)),
    ("ADAE-04", lambda t, s: make_adae(t, s, 24, 0.40, 7)),
    ("LB-01", lambda t, s: make_lb(t, s, 4, ["retest"])),
    ("LB-02", lambda t, s: make_lb(t, s, 5, ["retest", "lessthan"])),
    ("LB-03", lambda t, s: make_lb(t, s, 6, ["retest", "lessthan", "si_site"])),
    ("AEX-01", lambda t, s: make_ae(t, s, 14, "site_infer", [])),
    ("AEX-02", lambda t, s: make_ae(t, s, 18, "site_infer", ["deleted", "sevcodes"])),
    ("AEX-03", lambda t, s: make_ae(t, s, 22, "site_infer", ["deleted", "dup", "sevcodes"])),
]


def main():
    import json
    for i, (tid, fn) in enumerate(TIER2):
        seed = 2000 + i
        while True:
            try:
                fn(tid, seed)
                break
            except ValueError:
                seed += 100
        meta = json.loads((ANSWERS / tid / "meta.json").read_text())
        print(f"{tid}: {meta['n_subjects']} subjects, {meta['n_records']} records, {meta['traps']}, seed {seed}")


if __name__ == "__main__":
    main()
