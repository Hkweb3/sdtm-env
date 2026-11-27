"""Reference solver: solves a task using only what an agent sees (spec.md + input/).

It never opens answers/. If it passes every task, every task is solvable from its
spec, and a failing agent failed on the work rather than on a broken task.
"""
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def codes(spec, field):
    """Parse '`FIELD` codes: `1` = X, `2` = Y.' into {'1': 'X', ...}."""
    m = re.search(rf"`{field}` codes: (.+)", spec)
    return dict(re.findall(r"`([^`]+)` = ([A-Z](?:[A-Z /,-]*[A-Z])?)", m.group(1))) if m else None


def parse_date(s, style, order=None):
    s = (s or "").strip()
    if not s:
        return ""
    if style in ("dmy_text", "compact"):
        m = re.fullmatch(r"(\d\d|UN) ?([A-Z]{3}) ?(\d{4})", s)
        d, mon, y = m.groups()
        if mon == "UNK":
            return y
        mm = f"{MON.index(mon) + 1:02d}"
        return f"{y}-{mm}" if d == "UN" else f"{y}-{mm}-{d}"
    if style == "iso":
        return s
    a, b, y = s.split("/")
    m_, d_ = (b, a) if order == "DMY" else (a, b)
    return f"{y}-{int(m_):02d}-{int(d_):02d}"


def from_split(d, m, y):
    if not y:
        return ""
    if not m:
        return y
    return f"{y}-{int(m):02d}" if not d else f"{y}-{int(m):02d}-{int(d):02d}"


def style_of(spec, prefix="dates"):
    line = next(l for l in spec.splitlines() if f"Raw {prefix} are" in l)
    line = line[line.index(f"Raw {prefix} are"):]
    if "`DD MON YYYY`" in line:
        return "dmy_text"
    if "`DDMONYYYY`" in line:
        return "compact"
    if "`MM/DD/YYYY`." in line:
        return "us"
    if "ISO 8601" in line:
        return "iso"
    if "split into three" in line:
        return "split"
    return "site"


def site_table(spec):
    return {s: ("DMY" if f.startswith("DD") else "MDY") for s, f in re.findall(r"\| (\d+) \| (\S+) \|", spec)}


def sdy(dtc, ref):
    if len(dtc) != 10 or len(ref) != 10:
        return ""
    n = (date.fromisoformat(dtc) - date.fromisoformat(ref)).days
    return str(n + 1 if n >= 0 else n)


def read(p):
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def solve_ae(spec, inp):
    studyid = re.search(r"Study `([^`]+)`", spec).group(1)
    raw, dm = read(inp / "raw_ae.csv"), read(inp / "dm.csv")
    if "RECORD_STATUS" in raw:
        raw = raw[raw.RECORD_STATUS != "DELETED"]
    if "AEYN" in raw:
        raw = raw[raw.AEYN != "No"]
    raw = raw.assign(_v=raw.VERSION.astype(int)).sort_values("_v").drop_duplicates(["SUBJECT", "RECID"], keep="last")
    style, sites = style_of(spec), site_table(spec)
    sev, ser = codes(spec, "SEVERITY"), codes(spec, "SERIOUS")
    rel = dict((v, k) for v, k in re.findall(r"`([A-Za-z ]+related)` = ([A-Z]+)", spec))
    ref = dict(zip(dm.USUBJID, dm.RFSTDTC))
    rows = []
    for r in raw.itertuples():
        site, subj = r.SUBJECT.split("-")
        u = f"{studyid}-{site}-{subj}"
        if style == "split":
            st = from_split(r.AESTDAT_DD, r.AESTDAT_MM, r.AESTDAT_YYYY)
            en = from_split(r.AEENDAT_DD, r.AEENDAT_MM, r.AEENDAT_YYYY)
        else:
            st = parse_date(r.AESTDAT, style, sites.get(site))
            en = parse_date(r.AEENDAT, style, sites.get(site))
        rows.append({"STUDYID": studyid, "DOMAIN": "AE", "USUBJID": u, "AESPID": r.RECID,
                     "AETERM": r.AE_VERBATIM.upper(), "AEDECOD": r.CODED_PT, "AEBODSYS": r.CODED_SOC,
                     "AESEV": sev[r.SEVERITY] if sev else r.SEVERITY.upper(),
                     "AESER": ser[r.SERIOUS] if ser else {"Yes": "Y", "No": "N"}[r.SERIOUS],
                     "AEREL": rel[r.RELATIONSHIP], "AEOUT": r.OUTCOME.upper(), "AESTDTC": st, "AEENDTC": en,
                     "AESTDY": sdy(st, ref[u]), "AEENDY": sdy(en, ref[u])})
    t = pd.DataFrame(rows).sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"])
    t["AESEQ"] = t.groupby("USUBJID").cumcount() + 1
    return t, "ae.csv"


def solve_mh(spec, inp):
    studyid = re.search(r"Study `([^`]+)`", spec).group(1)
    raw, dm = read(inp / "raw_mh.csv"), read(inp / "dm.csv")
    raw = raw[raw.RECORD_STATUS != "DELETED"]
    style = style_of(spec, "start dates")
    vstyle = style_of(spec, "visit dates") if "Raw visit dates are" in spec else style
    cat = codes(spec, "CATEGORY")
    ref = dict(zip(dm.USUBJID, dm.RFSTDTC))
    rows = []
    for r in raw.itertuples():
        site, subj = r.SUBJECT.split("-")
        u = f"{studyid}-{site}-{subj}"
        st = from_split(r.MHSTDAT_DD, r.MHSTDAT_MM, r.MHSTDAT_YYYY) if style == "split" else parse_date(r.MHSTDAT, style)
        dtc = parse_date(r.VISIT_DATE, vstyle)
        rows.append({"STUDYID": studyid, "DOMAIN": "MH", "USUBJID": u, "MHSPID": r.RECID, "MHTERM": r.MH_VERBATIM,
                     "MHDECOD": r.CODED_PT, "MHCAT": cat[r.CATEGORY] if cat else r.CATEGORY.upper(),
                     "MHBODSYS": r.CODED_SOC, "MHDTC": dtc, "MHSTDTC": st, "MHDY": sdy(dtc, ref[u])})
    t = pd.DataFrame(rows).sort_values(["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"])
    t["MHSEQ"] = t.groupby("USUBJID").cumcount() + 1
    return t, "mh.csv"


def solve_dm(spec, inp):
    studyid = re.search(r"Study `([^`]+)`", spec).group(1)
    demog, cons, rand = read(inp / "raw_demog.csv"), read(inp / "raw_consent.csv"), read(inp / "raw_rand.csv")
    dose, sites = read(inp / "raw_dosing.csv"), read(inp / "sites.csv")
    style = style_of(spec)
    style = "dmy_text" if style == "split" else style
    sex, race = codes(spec, "SEX"), codes(spec, "RACE")
    arms = {a: (c, n) for a, c, n in re.findall(r"`([A-Z])` = `([A-Z]+)` / ([A-Za-z ]+?)(?:;|\.)", spec)}
    ic = {r.SUBJECT: parse_date(r.ICDAT, style) for r in cons.itertuples()}
    grp = dict(zip(rand.SUBJECT, rand.TRT_GROUP))
    country = dict(zip(sites.SITE, sites.COUNTRY))
    rows = []
    for r in demog.itertuples():
        site, subj = r.SUBJECT.split("-")
        b = parse_date(r.BRTHDAT, style)
        bd, icd = date.fromisoformat(b), date.fromisoformat(ic[r.SUBJECT])
        age = icd.year - bd.year - ((icd.month, icd.day) < (bd.month, bd.day))
        d = dose[dose.SUBJECT == r.SUBJECT]
        starts = [parse_date(x, style) for x in d.DOSE_START if x]
        ends = [parse_date(x, style) for x in d.DOSE_END if x]
        armcd, arm = arms[grp[r.SUBJECT]] if r.SUBJECT in grp else ("SCRNFAIL", "Screen Failure")
        rows.append({"STUDYID": studyid, "DOMAIN": "DM", "USUBJID": f"{studyid}-{site}-{subj}", "SUBJID": subj,
                     "SITEID": site, "BRTHDTC": b, "AGE": str(age), "AGEU": "YEARS",
                     "SEX": sex[r.SEX] if sex else {"Female": "F", "Male": "M"}[r.SEX],
                     "RACE": race[r.RACE] if race else r.RACE.upper(),
                     "ETHNIC": "HISPANIC OR LATINO" if r.HISPANIC == "Yes" else "NOT HISPANIC OR LATINO",
                     "ARMCD": armcd, "ARM": arm, "RFICDTC": ic[r.SUBJECT],
                     "RFSTDTC": min(starts) if starts else "", "RFENDTC": max(starts + ends) if starts else "",
                     "COUNTRY": country[site]})
    return pd.DataFrame(rows).sort_values("USUBJID"), "dm.csv"


def infer_site_orders(raw, date_cols):
    """A site is DD/MM if any of its dates has a first part > 12, MM/DD if any second part > 12."""
    orders = {}
    for r in raw.itertuples():
        site = r.SUBJECT.split("-")[0]
        for c in date_cols:
            v = getattr(r, c)
            if v:
                a, b, _ = v.split("/")
                if int(a) > 12:
                    orders[site] = "DMY"
                elif int(b) > 12:
                    orders[site] = "MDY"
    return orders


def solve_aex(spec, inp):
    raw = read(inp / "raw_ae.csv")
    active = raw[(raw.get("RECORD_STATUS", "ACTIVE") != "DELETED") & (raw.AESTDAT != "")]
    orders = infer_site_orders(active, ["AESTDAT", "AEENDAT"])
    spec = spec + "\n" + "\n".join(f"| {s} | {'DD/MM/YYYY' if o == 'DMY' else 'MM/DD/YYYY'} |" for s, o in orders.items())
    spec = spec.replace("Raw dates are numeric, `DD/MM/YYYY` or", "Raw dates are numeric, but the format depends")
    return solve_ae(spec, inp)


def days_between(a, b):
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def solve_adae(spec, inp):
    import calendar
    from datetime import timedelta
    ae, adsl = read(inp / "ae.csv"), read(inp / "adsl.csv")
    window = int(re.search(r"`TRTEDT` \+ (\d+) days", spec).group(1))
    trt = adsl.set_index("USUBJID")
    rows = []
    for r in ae.itertuples():
        ts, te = trt.loc[r.USUBJID, "TRTSDT"], trt.loc[r.USUBJID, "TRTEDT"]
        e = r.AEENDTC
        if len(e) == 10:
            aendt, ef = e, ""
        elif len(e) == 7:
            aendt, ef = f"{e}-{calendar.monthrange(int(e[:4]), int(e[5:]))[1]:02d}", "D"
        elif len(e) == 4:
            aendt, ef = f"{e}-12-31", "M"
        else:
            aendt, ef = "", ""
        s = r.AESTDTC
        if len(s) == 10:
            astdt, sf = s, ""
        elif len(s) == 7:
            astdt, sf = (ts if ts.startswith(s) else s + "-01"), "D"
        elif len(s) == 4:
            astdt, sf = (ts if ts.startswith(s) else s + "-01-01"), "M"
        else:
            astdt, sf = ts, "Y"
        if sf and ef == "" and aendt and astdt > aendt:
            astdt = aendt
        hi = (date.fromisoformat(te) + timedelta(days=window)).isoformat() if te else "9999"
        rows.append({"STUDYID": r.STUDYID, "USUBJID": r.USUBJID, "AESEQ": int(r.AESEQ), "AETERM": r.AETERM,
                     "AEDECOD": r.AEDECOD, "AEBODSYS": r.AEBODSYS, "TRTSDT": ts, "TRTEDT": te, "ASTDT": astdt,
                     "ASTDTF": sf, "AENDT": aendt, "AENDTF": ef, "ASTDY": sdy(astdt, ts), "AENDY": sdy(aendt, ts),
                     "ADURN": str(days_between(aendt, astdt) + 1) if astdt and aendt else "",
                     "TRTEMFL": "Y" if astdt and ts and ts <= astdt <= hi else "", "AOCCFL": "", "AOCCPFL": ""})
    t = pd.DataFrame(rows)
    te_ = t[t.TRTEMFL == "Y"].sort_values(["USUBJID", "ASTDT", "AESEQ"])
    t.loc[te_.drop_duplicates("USUBJID").index, "AOCCFL"] = "Y"
    t.loc[te_.drop_duplicates(["USUBJID", "AEDECOD"]).index, "AOCCPFL"] = "Y"
    return t.sort_values(["USUBJID", "AESEQ"]), "adae.csv"


def solve_lb(spec, inp):
    from decimal import ROUND_HALF_UP, Decimal
    studyid = re.search(r"Study `([^`]+)`", spec).group(1)
    raw, dm = read(inp / "raw_lab.csv"), read(inp / "dm.csv")
    table = {}
    for name, cd, lbt, u, f, dp in re.findall(r"^\| (.+?) \| `([A-Z]+)` \| (.+?) \| (\S+) \| ([\d.]+) \| (\d+) \|$", spec, re.M):
        table[name] = (cd, lbt, u, Decimal(f), int(dp))
    rf = dict(zip(dm.USUBJID, dm.RFSTDTC))

    def rd(x, dp):
        return str(x.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP))

    rows = []
    for r in raw.itertuples():
        cd, lbt, u, f, dp = table[r.TEST]
        f = Decimal(1) if r.UNIT == u else f
        site, subj = r.SUBJECT.split("-")
        usub = f"{studyid}-{site}-{subj}"
        num = not r.RESULT.startswith(("<", ">"))
        strn = rd(Decimal(r.RESULT) * f, dp) if num else ""
        lo = rd(Decimal(r.RANGE_LOW) * f, dp) if r.RANGE_LOW else ""
        hi = rd(Decimal(r.RANGE_HIGH) * f, dp) if r.RANGE_HIGH else ""
        ind = ("LOW" if Decimal(strn) < Decimal(lo) else "HIGH" if Decimal(strn) > Decimal(hi) else "NORMAL") \
            if strn and lo and hi else ""
        d, tm = r.COLLECTED.split(" ") if " " in r.COLLECTED else (r.COLLECTED, "")
        iso = f"{d[5:9]}-{MON.index(d[2:5]) + 1:02d}-{d[:2]}"
        rows.append({"STUDYID": studyid, "DOMAIN": "LB", "USUBJID": usub, "LBSPID": r.RECID, "LBTESTCD": cd,
                     "LBTEST": lbt, "LBORRES": r.RESULT, "LBORRESU": r.UNIT, "LBORNRLO": r.RANGE_LOW,
                     "LBORNRHI": r.RANGE_HIGH, "LBSTRESC": strn if num else r.RESULT, "LBSTRESN": strn,
                     "LBSTRESU": u, "LBSTNRLO": lo, "LBSTNRHI": hi, "LBNRIND": ind, "VISIT": r.VISIT,
                     "LBDTC": iso + ("T" + tm if tm else ""), "LBDY": sdy(iso, rf[usub]), "LBBLFL": ""})
    t = pd.DataFrame(rows)
    pre = t[(t.LBSTRESN != "") & (t.LBDTC.str[:10] <= t.USUBJID.map(rf))].sort_values(["USUBJID", "LBTESTCD", "LBDTC"])
    t.loc[pre.drop_duplicates(["USUBJID", "LBTESTCD"], keep="last").index, "LBBLFL"] = "Y"
    return t.sort_values(["USUBJID", "LBTESTCD", "LBDTC", "LBSPID"]), "lb.csv"


def solve_dr(spec, inp):
    """Data review, written from the spec text (not from the generator's detector)."""
    dm, ae, ex, ds, lb = (read(inp / f"{d}.csv") for d in ("dm", "ae", "ex", "ds", "lb"))
    crit_cols = [c for c in ae.columns if c.startswith("AES") and c not in ("AESEQ", "AESEV", "AESER", "AESTDTC")]
    out = []
    death = {r.USUBJID: r.DTHDTC[:10] for r in dm.itertuples()}
    for r in ae.itertuples():
        if len(r.AESTDTC) == 10 and len(r.AEENDTC) == 10 and r.AEENDTC < r.AESTDTC:
            out.append(("AE_DATE_ORDER", r.USUBJID, "AE", r.AESEQ))
        any_crit = any(getattr(r, c) == "Y" for c in crit_cols)
        if (r.AESER == "Y" and not any_crit) or (r.AESER != "Y" and any_crit):
            out.append(("SAE_CRITERIA", r.USUBJID, "AE", r.AESEQ))
        d = death[r.USUBJID]
        if (r.AEOUT == "FATAL" and not d) or (d and len(r.AESTDTC) == 10 and r.AESTDTC > d):
            out.append(("DEATH_CONSISTENCY", r.USUBJID, "AE", r.AESEQ))
    seen = {}
    for r in sorted(ae.itertuples(), key=lambda r: int(r.AESEQ)):
        if r.AESTDTC:
            k = (r.USUBJID, r.AEDECOD, r.AESTDTC)
            if k in seen:
                out.append(("AE_DUPLICATE", r.USUBJID, "AE", r.AESEQ))
            seen[k] = True
    for u, d in death.items():
        if d and not ((ae.USUBJID == u) & (ae.AEOUT == "FATAL")).any():
            out.append(("DEATH_CONSISTENCY", u, "DM", ""))
    early = ds[(ds.DSCAT == "DISPOSITION EVENT") & ~ds.DSDECOD.isin(["COMPLETED", "SCREEN FAILURE"])]
    stop = {r.USUBJID: r.DSSTDTC[:10] for r in early.itertuples()}
    for r in ex.itertuples():
        if r.USUBJID in stop and r.EXSTDTC[:10] > stop[r.USUBJID]:
            out.append(("DOSE_AFTER_DISC", r.USUBJID, "EX", r.EXSEQ))
    lbn = lb[lb.LBSTRESN != ""]
    for _, g in lbn.groupby(["USUBJID", "LBTESTCD"]):
        v = g.LBSTRESN.astype(float).tolist()
        for i, r in enumerate(g.itertuples()):
            rest = v[:i] + v[i + 1:]
            if len(rest) >= 2:
                med = pd.Series(rest).median()
                if med > 0 and (v[i] >= 8 * med or v[i] <= med / 8):
                    out.append(("LAB_UNIT", r.USUBJID, "LB", r.LBSEQ))
    sch = lb[~lb.VISIT.str.startswith("UNSCHEDULED") & (lb.LBDTC != "")]
    for _, g in sch.groupby(["USUBJID", "LBTESTCD"]):
        g = g.assign(vn=g.VISITNUM.astype(float), d=g.LBDTC.str[:10])
        for r in g.itertuples():
            prior = g[g.vn < r.vn]
            if len(prior) and r.d < prior.d.max():
                out.append(("LAB_VISIT_DATE", r.USUBJID, "LB", r.LBSEQ))
    return pd.DataFrame(sorted(set(out)), columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"]), "findings.csv"


FEMALE_TERMS = ("PREGNAN", "MENORRH", "OVARI", "VAGIN", "UTER", "CERVI", "MENOPAUS")
MALE_TERMS = ("PROSTAT", "ERECTILE", "TESTI", "SCROT", "PENI")
# limits beyond which a value is incompatible with life (SI units)
VIABLE = {"SODIUM": (100, 190), "K": (1.5, 10), "ALB": (10, 70), "GLUC": (0.5, 80), "CREAT": (10, 3000)}


# drug knowledge a reviewer brings: brand and generic names by class
CHOLINESTERASE = ("ARICEPT", "DONEPEZIL", "EXELON", "RIVASTIGMINE", "RAZADYNE", "REMINYL", "GALANTAMINE")
ANTICHOLINERGIC = ("DITROPAN", "OXYBUTYNIN", "ELAVIL", "AMITRIPTYLINE", "BENADRYL", "DIPHENHYDRAMINE", "DETROL",
                   "TOLTERODINE", "COGENTIN", "BENZTROPINE", "PHENERGAN", "PROMETHAZINE", "PAXIL", "PAROXETINE")
CONTRACEPTIVE = ("YASMIN", "LOESTRIN", "MICROGYNON", "ETHINYLESTRADIOL", "LEVONORGESTREL", "NORETHISTERONE",
                 "DROSPIRENONE", "CONTRACEPT")
CHILDHOOD = ("PUBERTY", "INFANTILE", "NEONATAL", "TEETHING")
MALE_HISTORY = ("PROSTAT", "TURP", "VASECTOMY", "ORCHI")
FEMALE_HISTORY = ("CAESAREAN", "C-SECTION", "BTL", "TUBAL", "FEMALE STERILISATION", "HYSTERECT", "OOPHOR")
# AE term -> (lab test, value that says the opposite)
AE_VS_LAB = {"HYPOKALAEMIA": ("K", lambda v: v > 5.5), "HYPERKALAEMIA": ("K", lambda v: v < 3.3),
             "HYPONATRAEMIA": ("SODIUM", lambda v: v > 146), "HYPERNATRAEMIA": ("SODIUM", lambda v: v < 130),
             "HYPOGLYCAEMIA": ("GLUC", lambda v: v > 11), "HYPERGLYCAEMIA": ("GLUC", lambda v: v < 3.0)}


def review_cross_domain(dm, ae, lb, cm, mh, ex):
    out = []
    sex, age = dict(zip(dm.USUBJID, dm.SEX)), dict(zip(dm.USUBJID, dm.AGE))
    first = ex.groupby("USUBJID").EXSTDTC.min().to_dict()
    last = ex.groupby("USUBJID").EXENDTC.max().to_dict()
    for r in cm.itertuples():
        name = f"{r.CMTRT} {r.CMDECOD}".upper()
        f, l = first.get(r.USUBJID, ""), last.get(r.USUBJID, "")
        overlaps = f and r.CMSTDTC[:10] <= (l or "9999") and (not r.CMENDTC or r.CMENDTC[:10] >= f)
        if overlaps and any(k in name for k in CHOLINESTERASE + ANTICHOLINERGIC):
            out.append((r.USUBJID, "CM", r.CMSEQ, f"prohibited medication {r.CMTRT} during treatment"))
        if sex.get(r.USUBJID) == "M" and any(k in name for k in CONTRACEPTIVE):
            out.append((r.USUBJID, "CM", r.CMSEQ, f"oral contraceptive {r.CMTRT} recorded for a male subject"))
    no_uterus = set(mh[mh.MHDECOD.str.contains("HYSTERECT") | mh.MHTERM.str.upper().str.contains("HYSTERECT")].USUBJID)
    no_prostate = set(mh[mh.MHTERM.str.upper().str.contains("RADICAL PROSTATECT")].USUBJID)
    for r in ae.itertuples():
        t = r.AEDECOD
        if r.USUBJID in no_uterus and any(w in t for w in ("UTER", "ENDOMETR", "MENORRH")):
            out.append((r.USUBJID, "AE", r.AESEQ, f"{t} after a recorded hysterectomy"))
        if r.USUBJID in no_prostate and "PROSTAT" in t:
            out.append((r.USUBJID, "AE", r.AESEQ, f"{t} after a radical prostatectomy"))
        if age.get(r.USUBJID) and int(age[r.USUBJID]) >= 18 and any(w in t for w in CHILDHOOD):
            out.append((r.USUBJID, "AE", r.AESEQ, f"{t} in a {age[r.USUBJID]}-year-old"))
    for r in lb.itertuples():
        if (r.LBTESTCD == "PSA" and sex.get(r.USUBJID) == "F") or (r.LBTESTCD == "HCG" and sex.get(r.USUBJID) == "M"):
            out.append((r.USUBJID, "LB", r.LBSEQ, f"{r.LBTEST} in a {sex[r.USUBJID]} subject"))
    # organ removed before the study, AE in that organ during it
    for u, g in mh.groupby("USUBJID"):
        gone = []
        for t in g.MHTERM.str.upper():
            if "BILATERAL BKA" in t or "BILATERAL" in t and "AMPUTAT" in t:
                gone += [(w, t) for w in ("TOE", "ANKLE", "PLANTAR", "FOOT")]
            if "LARYNGECTOMY" in t:
                gone += [(w, t) for w in ("VOCAL CORD", "LARYN")]
            if "TOTAL GASTRECTOMY" in t:
                gone += [("GASTRI", t)]
        for r in ae[ae.USUBJID == u].itertuples():
            hit = [t for w, t in gone if w in r.AEDECOD]
            if hit:
                out.append((u, "AE", r.AESEQ, f"{r.AEDECOD} after {hit[0]}"))
    # AE diagnosis contradicted by the same-day lab
    for r in ae.itertuples():
        if r.AEDECOD in AE_VS_LAB and len(r.AESTDTC) >= 10:
            test, wrong = AE_VS_LAB[r.AEDECOD]
            d0 = date.fromisoformat(r.AESTDTC[:10])
            for x in lb[(lb.USUBJID == r.USUBJID) & (lb.LBTESTCD == test) & (lb.LBSTRESN != "")].itertuples():
                if abs((date.fromisoformat(x.LBDTC[:10]) - d0).days) <= 3 and wrong(float(x.LBSTRESN)):
                    out.append((r.USUBJID, "AE", r.AESEQ, f"{r.AEDECOD} but {test} {x.LBSTRESN} the same day"))
    # a patch reaction needs a patch
    for r in ae[ae.AEDECOD.str.startswith("APPLICATION SITE")].itertuples():
        f = first.get(r.USUBJID, "")
        if not f or r.AESTDTC[:10] < f[:10]:
            out.append((r.USUBJID, "AE", r.AESEQ, f"{r.AEDECOD} before the first patch"))
    born = dict(zip(dm.USUBJID, dm.BRTHDTC.str[:4]))
    for r in mh.itertuples():
        t = f"{r.MHTERM} {r.MHDECOD}".upper()
        if (sex.get(r.USUBJID) == "F" and any(w in t for w in MALE_HISTORY)) or \
           (sex.get(r.USUBJID) == "M" and any(w in t for w in FEMALE_HISTORY)):
            out.append((r.USUBJID, "MH", r.MHSEQ, f"{r.MHTERM} in a {sex[r.USUBJID]} subject"))
        if len(r.MHSTDTC) >= 4 and r.MHSTDTC[:4] < born.get(r.USUBJID, "0000"):
            out.append((r.USUBJID, "MH", r.MHSEQ, f"history dated {r.MHSTDTC}, before birth"))
    return out


def solve_or(spec, inp):
    """Open review from clinical knowledge: what a careful reviewer checks without a list."""
    dm, ae, ex, ds, lb = (read(inp / f"{d}.csv") for d in ("dm", "ae", "ex", "ds", "lb"))
    cutoff = re.search(r"Data cutoff for this delivery: \*\*(\d{4}-\d\d-\d\d)\*\*", spec).group(1)
    min_age = int(re.search(r"aged? (\d+) or older", spec).group(1))
    hd = {"BASELINE": "54", "WEEK 2": "81", "WEEK 24": "54"}  # high-dose titration per the synopsis
    doses = {"Placebo": lambda v: "0", "Xanomeline Low Dose": lambda v: "54",
             "Xanomeline High Dose": lambda v: hd.get(v)}
    sex = dict(zip(dm.USUBJID, dm.SEX))
    arm = dict(zip(dm.USUBJID, dm.ARM))
    out = []
    for r in dm.itertuples():
        if r.AGE and int(r.AGE) < min_age:
            out.append((r.USUBJID, "DM", "", f"age {r.AGE} below the protocol minimum {min_age}"))
    for _, g in dm.groupby(["BRTHDTC", "SEX"]):
        if len(g) > 1:
            out += [(u, "DM", "", "same birth date and sex as another subject; possible duplicate enrollment")
                    for u in g.USUBJID]
    for r in ae.itertuples():
        t = r.AEDECOD
        if (sex[r.USUBJID] == "M" and any(w in t for w in FEMALE_TERMS)) or \
           (sex[r.USUBJID] == "F" and any(w in t for w in MALE_TERMS)):
            out.append((r.USUBJID, "AE", r.AESEQ, f"{t} in a {sex[r.USUBJID]} subject"))
        if r.AESTDTC[:10] > cutoff:
            out.append((r.USUBJID, "AE", r.AESEQ, "AE start after data cutoff"))
    for pt, g in ae.groupby("AEDECOD"):
        if g.AEBODSYS.nunique() > 1:
            top = g.AEBODSYS.value_counts()
            for r in g.itertuples():
                if r.AEBODSYS != top.index[0] or (top.iloc[0] == top.iloc[-1] and any(
                        k in r.AEBODSYS for k in ("EYE", "RENAL", "PREGNANCY"))):
                    out.append((r.USUBJID, "AE", r.AESEQ, f"{pt} coded to {r.AEBODSYS}"))
    for r in ex.itertuples():
        rule = doses.get(arm.get(r.USUBJID, ""))
        want = rule(r.VISIT) if rule else None
        if want is not None and r.EXDOSE != want:
            out.append((r.USUBJID, "EX", r.EXSEQ, f"dose {r.EXDOSE} does not match arm {arm[r.USUBJID]}"))
        elif arm.get(r.USUBJID) == "Placebo" and r.EXTRT != "PLACEBO":
            out.append((r.USUBJID, "EX", r.EXSEQ, "active drug recorded for a placebo subject"))
    for r in lb[lb.LBSTRESN != ""].itertuples():
        lo, hi = VIABLE.get(r.LBTESTCD, (None, None))
        if lo is not None and not lo <= float(r.LBSTRESN) <= hi:
            out.append((r.USUBJID, "LB", r.LBSEQ, f"{r.LBTESTCD} {r.LBSTRESN} is not compatible with life"))
    for r in dm[dm.DTHDTC != ""].itertuples():
        after = lb[(lb.USUBJID == r.USUBJID) & (lb.LBDTC.str[:10] > r.DTHDTC)]
        if len(after):
            out.append((r.USUBJID, "LB", after.LBSEQ.iloc[0], "lab collected after the recorded death date"))
    if (inp / "cm.csv").exists():
        out += review_cross_domain(dm, ae, lb, read(inp / "cm.csv"), read(inp / "mh.csv"), ex)
    seen, rows = set(), []
    for u, d, s, why in out:
        if (u, d, s) not in seen:
            seen.add((u, d, s))
            rows.append({"USUBJID": u, "DOMAIN": d, "SEQ": s, "ISSUE": why})
    return pd.DataFrame(rows[:25], columns=["USUBJID", "DOMAIN", "SEQ", "ISSUE"]), "findings.csv"


SOLVERS = {"AE": solve_ae, "MH": solve_mh, "DM": solve_dm, "AEX": solve_aex, "ADAE": solve_adae, "LB": solve_lb,
           "DR": solve_dr, "OR": solve_or}


def solve(task_dir, out_dir):
    spec = (task_dir / "spec.md").read_text(encoding="utf-8")
    if "## Output columns" in spec:
        cols = re.findall(r"`([A-Z0-9]+)`", spec.split("## Output columns")[1].split("##")[0])
    elif "## Checks" in spec:  # data review: findings table
        cols = ["CHECK", "USUBJID", "DOMAIN", "SEQ"]
    else:  # open review
        cols = ["USUBJID", "DOMAIN", "SEQ", "ISSUE"]
    t, name = SOLVERS[task_dir.name.split("-")[0]](spec, task_dir / "input")
    out_dir.mkdir(parents=True, exist_ok=True)
    t[cols].to_csv(out_dir / name, index=False)
    return out_dir / name


if __name__ == "__main__":
    from sdtmenv.check import score
    tasks = sorted(p for p in (ROOT / "tasks").iterdir() if p.is_dir())
    for td in tasks if len(sys.argv) < 2 else [ROOT / "tasks" / sys.argv[1]]:
        out = solve(td, ROOT / "runs" / "reference" / td.name)
        s = score(td.name, out)
        print(td.name, s["passed"], s["reward"], s.get("col_errors") or "", s.get("examples", [])[:2] if not s["passed"] else "")
