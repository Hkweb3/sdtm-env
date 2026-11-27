"""Generate raw-EDC -> SDTM mapping tasks from the public CDISC Pilot01 study.

Each task re-identifies a random subset of Pilot01 subjects (new study, site and
subject IDs, all dates shifted) to make the ground-truth SDTM, then renders the
raw EDC export *from* that truth with study-specific formats and traps. The
ground truth therefore has exactly one correct answer and never appears online.

Layout written:
  tasks/<id>/spec.md, tasks/<id>/input/*.csv   (what the agent sees)
  answers/<id>/expected.csv, answers/<id>/meta.json   (never copied to a sandbox)
"""
import json
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source"
TASKS = ROOT / "tasks"
ANSWERS = ROOT / "answers"

MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

AE_COLS = ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM", "AEDECOD", "AEBODSYS",
           "AESEV", "AESER", "AEREL", "AEOUT", "AESTDTC", "AEENDTC", "AESTDY", "AEENDY"]
MH_COLS = ["STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM", "MHDECOD", "MHCAT",
           "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY"]
DM_COLS = ["STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "BRTHDTC", "AGE", "AGEU", "SEX",
           "RACE", "ETHNIC", "ARMCD", "ARM", "RFICDTC", "RFSTDTC", "RFENDTC", "COUNTRY"]


def load(domain):
    df = pd.read_sas(SRC / f"{domain}.xpt", format="xport", encoding="latin-1")
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].fillna("").astype(str).str.strip()
    return df


# ---------- dates ----------

def iso_date(s):
    """Date part of an ISO 8601 string: YYYY-MM-DD, YYYY-MM, YYYY or ''."""
    s = (s or "").strip()[:10]
    return s if len(s) in (4, 7, 10) else ""


def shift(s, days):
    s = iso_date(s)
    if len(s) == 10:
        return (date.fromisoformat(s) + timedelta(days=days)).isoformat()
    if len(s) == 7:
        d = date(int(s[:4]), int(s[5:7]), 15) + timedelta(days=days)
        return f"{d.year:04d}-{d.month:02d}"
    if len(s) == 4:
        return str((date(int(s), 7, 1) + timedelta(days=days)).year)
    return ""


def study_day(dtc, ref):
    """SDTM study day: no day 0. Blank unless both dates are complete."""
    if len(dtc) != 10 or len(ref) != 10:
        return ""
    n = (date.fromisoformat(dtc) - date.fromisoformat(ref)).days
    return str(n + 1 if n >= 0 else n)


def raw_date(iso, style, site_order=None):
    """Render an ISO (possibly partial) date the way the EDC exports it."""
    if not iso:
        return ""
    y = iso[:4]
    m = int(iso[5:7]) if len(iso) >= 7 else None
    d = int(iso[8:10]) if len(iso) == 10 else None
    if style == "dmy_text":
        return (f"{d:02d}" if d else "UN") + " " + (MON[m - 1] if m else "UNK") + f" {y}"
    if style == "compact":
        return (f"{d:02d}" if d else "UN") + (MON[m - 1] if m else "UNK") + y
    if style == "us":
        return f"{m:02d}/{d:02d}/{y}"
    if style == "iso":
        return iso
    if style in ("site", "site_infer"):
        return f"{d:02d}/{m:02d}/{y}" if site_order == "DMY" else f"{m:02d}/{d:02d}/{y}"
    raise ValueError(style)


def split_date(iso):
    y = iso[:4] if iso else ""
    m = str(int(iso[5:7])) if len(iso) >= 7 else ""
    d = str(int(iso[8:10])) if len(iso) == 10 else ""
    return d, m, y


def truncate(iso, rng, p_month, p_year):
    if len(iso) != 10:
        return iso
    r = rng.random()
    if r < p_year:
        return iso[:4]
    if r < p_year + p_month:
        return iso[:7]
    return iso


# ---------- identity ----------

def reidentify(dm, rng, n_subj, pool=None):
    """Pick subjects and give them a new study, sites, subject IDs and a date shift."""
    pool = dm if pool is None else dm[dm.USUBJID.isin(pool)]
    pick = pool.sample(n=min(n_subj, len(pool)), random_state=rng.randint(0, 10**6)).copy()
    studyid = f"{rng.choice(['ALX', 'BRV', 'CTN', 'DRX', 'KVT', 'MRN', 'PLX', 'TQR'])}-{rng.randint(100, 999)}"
    sites = {s: str(rng.randint(100, 999)) for s in sorted(pick.SITEID.unique())}
    used, ids = set(), {}
    for u in pick.USUBJID:
        while True:
            n = str(rng.randint(1000, 9999))
            if n not in used:
                used.add(n)
                ids[u] = n
                break
    days = rng.randint(-1500, 900)
    pick["NEW_SITE"] = pick.SITEID.map(sites)
    pick["NEW_SUBJ"] = pick.USUBJID.map(ids)
    pick["NEW_USUBJID"] = studyid + "-" + pick.NEW_SITE + "-" + pick.NEW_SUBJ
    pick["NEW_RFSTDTC"] = pick.RFSTDTC.map(lambda s: shift(s, days))
    return studyid, days, pick


def site_orders(pick, rng):
    sites = sorted(pick.NEW_SITE.unique())
    orders = {s: rng.choice(["DMY", "MDY"]) for s in sites}
    if len(set(orders.values())) == 1 and len(sites) > 1:
        orders[sites[0]] = "DMY" if orders[sites[0]] == "MDY" else "MDY"
    return orders


def date_rule_text(style, orders=None, prefix="dates"):
    if style == "dmy_text":
        return f"Raw {prefix} are `DD MON YYYY` (e.g. `07 MAR 2014`). Unknown parts are `UN` (day) and `UNK` (month), e.g. `UN MAR 2014`, `UN UNK 2014`."
    if style == "compact":
        return f"Raw {prefix} are `DDMONYYYY` (e.g. `07MAR2014`). Unknown parts are `UN` (day) and `UNK` (month), e.g. `UNMAR2014`, `UNUNK2014`."
    if style == "us":
        return f"Raw {prefix} are `MM/DD/YYYY`."
    if style == "iso":
        return f"Raw {prefix} are already ISO 8601 `YYYY-MM-DD`; partial dates are `YYYY-MM` or `YYYY`."
    if style == "split":
        return (f"Raw {prefix} are split into three columns ending `_DD`, `_MM`, `_YYYY` (numbers, no zero padding). "
                "A blank day or month means that part is unknown.")
    if style == "site_infer":
        return (f"Raw {prefix} are numeric, `DD/MM/YYYY` or `MM/DD/YYYY`. Each site uses one format for all its records, "
                "but the export does not say which. Work it out from the data: every site has at least one date that "
                "only one format can explain.")
    if style == "site":
        rows = "\n".join(f"| {s} | {'DD/MM/YYYY' if o == 'DMY' else 'MM/DD/YYYY'} |" for s, o in sorted(orders.items()))
        return (f"Raw {prefix} are numeric, but the format depends on the site's locale:\n\n"
                f"| Site | Date format |\n|---|---|\n{rows}")
    raise ValueError(style)


COMMON_RULES = """- All `--DTC` variables are ISO 8601 dates `YYYY-MM-DD`. A partial date keeps only the known parts: `YYYY-MM` or `YYYY`. Never impute a missing day or month.
- Study day (`--DY`, `--STDY`, `--ENDY`) is relative to the subject's `RFSTDTC` from DM: `date - RFSTDTC + 1` when the date is on or after `RFSTDTC`, otherwise `date - RFSTDTC` (there is no day 0). Leave it blank when either date is partial or missing.
- Write the output as CSV with a header row and exactly the columns listed, in that order. Leave unknown values empty (not `NA`, `NULL` or `.`)."""


def write_task(tid, spec, inputs, expected, meta):
    tdir, adir = TASKS / tid, ANSWERS / tid
    for d in (tdir, adir):
        if d.exists():
            shutil.rmtree(d)
    (tdir / "input").mkdir(parents=True)
    adir.mkdir(parents=True)
    (tdir / "spec.md").write_text(spec, encoding="utf-8")
    for name, df in inputs.items():
        df.to_csv(tdir / "input" / name, index=False)
    expected.to_csv(adir / "expected.csv", index=False)
    (adir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


def dm_input(studyid, pick):
    return pd.DataFrame({"STUDYID": studyid, "DOMAIN": "DM", "USUBJID": pick.NEW_USUBJID,
                         "SUBJID": pick.NEW_SUBJ, "SITEID": pick.NEW_SITE,
                         "RFSTDTC": pick.NEW_RFSTDTC}).reset_index(drop=True)


# ---------- AE ----------

AE_SEV = ["MILD", "MODERATE", "SEVERE"]
AE_REL_RAW = {"NONE": "Not related", "REMOTE": "Unlikely related", "POSSIBLE": "Possibly related",
              "PROBABLE": "Probably related"}
AE_OUT = ["RECOVERED/RESOLVED", "NOT RECOVERED/NOT RESOLVED", "RECOVERING/RESOLVING",
          "RECOVERED/RESOLVED WITH SEQUELAE", "FATAL"]


def make_ae(tid, seed, n_subj, style, traps):
    rng = random.Random(seed)
    dm, ae = load("dm"), load("ae")
    ae = ae[ae.AETERM != ""]
    studyid, days, pick = reidentify(dm, rng, n_subj, pool=ae.USUBJID.unique())
    orders = site_orders(pick, rng) if style in ("site", "site_infer") else None
    partial = "partial" in traps and style not in ("us", "site", "site_infer")
    idmap = pick.set_index("USUBJID")

    rows = []
    for u, g in ae[ae.USUBJID.isin(pick.USUBJID)].groupby("USUBJID"):
        p = idmap.loc[u]
        for i, r in enumerate(g.itertuples(), 1):
            st = shift(r.AESTDTC, days)
            en = shift(r.AEENDTC, days)
            if partial:
                st = truncate(st, rng, 0.15, 0.05)
                en = truncate(en, rng, 0.10, 0.0) if en else en
            rows.append({"USUBJID": p.NEW_USUBJID, "SITE": p.NEW_SITE, "SUBJ": p.NEW_SUBJ,
                         "AESPID": f"AE{i:02d}", "AETERM": r.AETERM, "AEDECOD": r.AEDECOD,
                         "AEBODSYS": r.AEBODSYS, "AESEV": r.AESEV, "AESER": r.AESER or "N",
                         "AEREL": r.AEREL, "AEOUT": r.AEOUT, "AESTDTC": st, "AEENDTC": en,
                         "RFSTDTC": p.NEW_RFSTDTC})
    t = pd.DataFrame(rows)
    t = t[t.AEREL.isin(AE_REL_RAW) & t.AESEV.isin(AE_SEV) & t.AEOUT.isin(AE_OUT)].copy()
    if style in ("us", "site", "site_infer"):  # numeric formats can't express partial dates
        t = t[t.AESTDTC.str.len().isin([10]) & t.AEENDTC.str.len().isin([0, 10])].copy()
    if style == "site_infer":  # every site needs a date with day > 12, or its format is unknowable
        for s in t.SITE.unique():
            days_ = [int(x[8:10]) for x in pd.concat([t[t.SITE == s].AESTDTC, t[t.SITE == s].AEENDTC]) if len(x) == 10]
            if not any(d > 12 for d in days_):
                t = t[t.SITE != s]
        if t.SITE.nunique() < 2:
            raise ValueError("site_infer task needs at least two sites with evidence; change the seed")
    t["AESTDY"] = [study_day(a, b) for a, b in zip(t.AESTDTC, t.RFSTDTC)]
    t["AEENDY"] = [study_day(a, b) for a, b in zip(t.AEENDTC, t.RFSTDTC)]
    t = t.sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"])
    t["AESEQ"] = t.groupby("USUBJID").cumcount() + 1
    t["STUDYID"], t["DOMAIN"] = studyid, "AE"
    expected = t[AE_COLS].reset_index(drop=True)
    if style == "site_infer":  # sites dropped above must leave DM too
        pick = pick[pick.NEW_USUBJID.isin(t.USUBJID)]

    # ---- render raw EDC export from the truth ----
    sev_codes = "sevcodes" in traps
    ser_style = rng.choice(["yesno", "10"]) if "sevcodes" in traps else "yesno"
    raw = []
    for r in t.sample(frac=1, random_state=rng.randint(0, 10**6)).itertuples():
        row = {"SUBJECT": f"{r.SITE}-{r.SUBJ}", "RECID": r.AESPID, "AE_VERBATIM": r.AETERM.title() if rng.random() < 0.5 else r.AETERM,
               "CODED_PT": r.AEDECOD, "CODED_SOC": r.AEBODSYS}
        if style == "split":
            for k, v in (("AESTDAT", r.AESTDTC), ("AEENDAT", r.AEENDTC)):
                d, m, y = split_date(v)
                row[k + "_DD"], row[k + "_MM"], row[k + "_YYYY"] = d, m, y
        else:
            o = orders.get(r.SITE) if orders else None
            row["AESTDAT"] = raw_date(r.AESTDTC, style, o)
            row["AEENDAT"] = raw_date(r.AEENDTC, style, o)
        row["AEONGO"] = "Y" if not r.AEENDTC else ""
        row["SEVERITY"] = str(AE_SEV.index(r.AESEV) + 1) if sev_codes else r.AESEV.title()
        ser = r.AESER == "Y"
        row["SERIOUS"] = ("1" if ser else "0") if ser_style == "10" else ("Yes" if ser else "No")
        row["RELATIONSHIP"] = AE_REL_RAW[r.AEREL]
        row["OUTCOME"] = r.AEOUT.capitalize()
        row["RECORD_STATUS"] = "ACTIVE"
        row["VERSION"] = "1"
        raw.append(row)

    notes = []
    if "deleted" in traps:
        for r in rng.sample(raw, k=min(3, len(raw))):
            ghost = dict(r, RECID=r["RECID"] + "X", RECORD_STATUS="DELETED", AE_VERBATIM="Entered in error: " + r["AE_VERBATIM"])
            raw.append(ghost)
        subj_no_ae = rng.sample(sorted({r["SUBJECT"] for r in raw}), k=2)
        for s in subj_no_ae:
            raw.append({"SUBJECT": s, "RECID": "AE00", "AE_VERBATIM": "", "RECORD_STATUS": "ACTIVE", "VERSION": "1",
                        "AEYN": "No"})
        notes.append("- Drop rows where `RECORD_STATUS` is `DELETED`.\n- Drop placeholder rows with `AEYN` = `No` (the site ticked \"no adverse events\" on that page); they have no verbatim term.")
    if "dup" in traps:
        for r in rng.sample([x for x in raw if x.get("AE_VERBATIM")], k=min(4, len(raw))):
            if r["RECORD_STATUS"] != "ACTIVE":
                continue
            old = dict(r, VERSION="1")
            r["VERSION"] = "2"
            old["SEVERITY"] = ("1" if sev_codes else "Mild") if r["SEVERITY"] not in ("1", "Mild") else ("2" if sev_codes else "Moderate")
            raw.append(old)
        notes.append("- The export contains every saved version of a record. For each `SUBJECT` + `RECID`, keep only the row with the highest `VERSION`.")
    rdf = pd.DataFrame(raw).fillna("")
    if "AEYN" not in rdf.columns:
        rdf = rdf.drop(columns=[])
    rdf = rdf.sample(frac=1, random_state=rng.randint(0, 10**6)).reset_index(drop=True)

    sev_rule = ("`SEVERITY` codes: `1` = MILD, `2` = MODERATE, `3` = SEVERE." if sev_codes
                else "`SEVERITY` is the CDISC term in title case; output it in upper case.")
    ser_rule = ("`SERIOUS` codes: `1` = Y, `0` = N." if ser_style == "10" else "`SERIOUS`: `Yes` = Y, `No` = N.")
    rel_rule = "; ".join(f"`{v}` = {k}" for k, v in AE_REL_RAW.items())
    spec = f"""# Task {tid}: map raw adverse events to SDTM AE

Study `{studyid}`. Map `input/raw_ae.csv` to an SDTM AE dataset at `output/ae.csv`. `input/dm.csv` is the study's finished DM domain.

## Output columns
{", ".join(f"`{c}`" for c in AE_COLS)}

## Rules
- `STUDYID` = `{studyid}`, `DOMAIN` = `AE`.
- Raw `SUBJECT` is `<site>-<subject>`. `USUBJID` = `STUDYID-SITE-SUBJECT`, e.g. `{studyid}-123-4567`. It must match `dm.csv`.
- `AESPID` = raw `RECID`. `AETERM` = raw `AE_VERBATIM` in upper case. `AEDECOD` = `CODED_PT`, `AEBODSYS` = `CODED_SOC`.
- {sev_rule}
- {ser_rule}
- `RELATIONSHIP` maps to `AEREL`: {rel_rule}.
- `AEOUT` = raw `OUTCOME` in upper case.
- `AESTDTC` from the start date, `AEENDTC` from the end date. `AEONGO` = `Y` means the event is ongoing and has no end date.
- {date_rule_text(style, orders)}
- `AESEQ`: number each subject's records 1, 2, 3... after sorting by `AESTDTC` (as text), then `AETERM`, then `AESPID`.
{chr(10).join(notes)}
{COMMON_RULES}
"""
    meta = {"task": tid, "domain": "AE", "key": ["USUBJID", "AESPID"], "style": style, "traps": traps,
            "n_subjects": int(len(pick)), "n_records": int(len(expected)), "seed": seed}
    write_task(tid, spec, {"raw_ae.csv": rdf, "dm.csv": dm_input(studyid, pick)}, expected, meta)


# ---------- MH ----------

MH_CAT_CODES = {"PRIMARY DIAGNOSIS": "PD", "SIGNIFICANT PRE-EXISTING CONDITION": "SPC", "HISTORICAL DIAGNOSIS": "HD"}


def make_mh(tid, seed, n_subj, style, traps):
    rng = random.Random(seed)
    dm, mh = load("dm"), load("mh")
    mh = mh[(mh.MHTERM != "") & mh.MHCAT.isin(MH_CAT_CODES)]
    studyid, days, pick = reidentify(dm, rng, n_subj, pool=mh.USUBJID.unique())
    idmap = pick.set_index("USUBJID")
    rows = []
    for u, g in mh[mh.USUBJID.isin(pick.USUBJID)].groupby("USUBJID"):
        p = idmap.loc[u]
        for i, r in enumerate(g.itertuples(), 1):
            term = r.MHDECOD if r.MHTERM.startswith("VERBATIM_") and r.MHDECOD else r.MHTERM
            rows.append({"USUBJID": p.NEW_USUBJID, "SITE": p.NEW_SITE, "SUBJ": p.NEW_SUBJ, "MHSPID": f"MH{i:02d}",
                         "MHTERM": term, "MHDECOD": r.MHDECOD, "MHCAT": r.MHCAT, "MHBODSYS": r.MHBODSYS,
                         "MHDTC": shift(r.MHDTC, days), "MHSTDTC": shift(r.MHSTDTC, days), "RFSTDTC": p.NEW_RFSTDTC})
    t = pd.DataFrame(rows)
    t["MHDY"] = [study_day(a, b) for a, b in zip(t.MHDTC, t.RFSTDTC)]
    t = t.sort_values(["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"])
    t["MHSEQ"] = t.groupby("USUBJID").cumcount() + 1
    t["STUDYID"], t["DOMAIN"] = studyid, "MH"
    expected = t[MH_COLS].reset_index(drop=True)

    cat_codes = "catcodes" in traps
    raw = []
    for r in t.itertuples():
        row = {"SUBJECT": f"{r.SITE}-{r.SUBJ}", "RECID": r.MHSPID, "MH_VERBATIM": r.MHTERM,
               "CODED_PT": r.MHDECOD, "CODED_SOC": r.MHBODSYS,
               "CATEGORY": MH_CAT_CODES[r.MHCAT] if cat_codes else r.MHCAT.title()}
        if style == "split":
            d, m, y = split_date(r.MHSTDTC)
            row["MHSTDAT_DD"], row["MHSTDAT_MM"], row["MHSTDAT_YYYY"] = d, m, y
        else:
            row["MHSTDAT"] = raw_date(r.MHSTDTC, style)
        row["VISIT_DATE"] = raw_date(r.MHDTC, "dmy_text" if style == "split" else style)
        row["RECORD_STATUS"] = "ACTIVE"
        raw.append(row)
    notes = []
    if "deleted" in traps:
        for r in rng.sample(raw, k=min(3, len(raw))):
            raw.append(dict(r, RECID=r["RECID"] + "X", RECORD_STATUS="DELETED"))
        notes.append("- Drop rows where `RECORD_STATUS` is `DELETED`.")
    rdf = pd.DataFrame(raw).fillna("").sample(frac=1, random_state=rng.randint(0, 10**6)).reset_index(drop=True)
    cat_rule = ("`CATEGORY` codes: " + "; ".join(f"`{v}` = {k}" for k, v in MH_CAT_CODES.items()) + "."
                if cat_codes else "`MHCAT` = raw `CATEGORY` in upper case.")
    visit_style = "dmy_text" if style == "split" else style
    spec = f"""# Task {tid}: map raw medical history to SDTM MH

Study `{studyid}`. Map `input/raw_mh.csv` to an SDTM MH dataset at `output/mh.csv`. `input/dm.csv` is the study's finished DM domain.

## Output columns
{", ".join(f"`{c}`" for c in MH_COLS)}

## Rules
- `STUDYID` = `{studyid}`, `DOMAIN` = `MH`.
- Raw `SUBJECT` is `<site>-<subject>`. `USUBJID` = `STUDYID-SITE-SUBJECT`. It must match `dm.csv`.
- `MHSPID` = raw `RECID`. `MHTERM` = raw `MH_VERBATIM`. `MHDECOD` = `CODED_PT`, `MHBODSYS` = `CODED_SOC`.
- {cat_rule}
- `MHSTDTC` = the condition's start date. Many are partial.
- {date_rule_text(style, prefix="start dates")}
- `MHDTC` = `VISIT_DATE`, the date the history was collected. {date_rule_text(visit_style, prefix="visit dates") if visit_style != style else "It uses the same format."}
- `MHDY` = study day of `MHDTC`.
- `MHSEQ`: number each subject's records 1, 2, 3... after sorting by `MHCAT`, then `MHSTDTC` (as text), then `MHTERM`, then `MHSPID`.
{chr(10).join(notes)}
{COMMON_RULES}
"""
    meta = {"task": tid, "domain": "MH", "key": ["USUBJID", "MHSPID"], "style": style, "traps": traps,
            "n_subjects": int(len(pick)), "n_records": int(len(expected)), "seed": seed}
    write_task(tid, spec, {"raw_mh.csv": rdf, "dm.csv": dm_input(studyid, pick)}, expected, meta)


# ---------- DM ----------

RACE_CODES = {"WHITE": "1", "BLACK OR AFRICAN AMERICAN": "2", "ASIAN": "3",
              "AMERICAN INDIAN OR ALASKA NATIVE": "4", "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER": "5"}
ARM_CODES = {"Pbo": ("A", "PBO", "Placebo"), "Xan_Lo": ("B", "XANLO", "Xanomeline Low Dose"),
             "Xan_Hi": ("C", "XANHI", "Xanomeline High Dose")}


def make_dm(tid, seed, n_subj, style, traps):
    rng = random.Random(seed)
    dm, ex, ds = load("dm"), load("ex"), load("ds")
    studyid, days, pick = reidentify(dm, rng, n_subj)
    countries = {s: rng.choice(["USA", "CAN", "GBR", "DEU"]) for s in pick.NEW_SITE.unique()}
    rows, demog, rand, dose, consent = [], [], [], [], []
    for p in pick.itertuples():
        scrnfail = p.ARMCD not in ARM_CODES
        ic = shift(p.DMDTC, days - rng.randint(0, 6))
        icd = date.fromisoformat(ic)
        age = int(float(p.AGE))
        # birth date: `age` completed years at consent; a third land within 3 days of a birthday
        if rng.random() < 0.35 and "ageedge" in traps:
            bday_this_year = icd.replace(year=icd.year - age) + timedelta(days=rng.choice([-2, -1, 0, 1, 2]))
            b = bday_this_year
        else:
            b = icd.replace(year=icd.year - age - 1) + timedelta(days=rng.randint(2, 360))
        bd = b.isoformat()
        true_age = icd.year - b.year - ((icd.month, icd.day) < (b.month, b.day))
        exs = ex[ex.USUBJID == p.USUBJID]
        intervals = [] if scrnfail else [
            (shift(s, days), shift(e, days)) for s, e in zip(exs.EXSTDTC, exs.EXENDTC) if len(iso_date(s)) == 10]
        intervals = [(s, e if len(e) == 10 else "") for s, e in intervals]
        rfst = min(s for s, _ in intervals) if intervals else ""
        rfen = max([s for s, _ in intervals] + [e for _, e in intervals if e]) if intervals else ""
        armcd, arm = ("SCRNFAIL", "Screen Failure") if scrnfail else ARM_CODES[p.ARMCD][1:]
        race = p.RACE if p.RACE in RACE_CODES else "WHITE"
        rows.append({"STUDYID": studyid, "DOMAIN": "DM", "USUBJID": p.NEW_USUBJID, "SUBJID": p.NEW_SUBJ,
                     "SITEID": p.NEW_SITE, "BRTHDTC": bd, "AGE": str(true_age), "AGEU": "YEARS", "SEX": p.SEX,
                     "RACE": race, "ETHNIC": p.ETHNIC, "ARMCD": armcd, "ARM": arm, "RFICDTC": ic,
                     "RFSTDTC": rfst, "RFENDTC": rfen, "COUNTRY": countries[p.NEW_SITE]})
        subj = f"{p.NEW_SITE}-{p.NEW_SUBJ}"
        sexraw = {"F": "2", "M": "1"}[p.SEX] if "sexcodes" in traps else {"F": "Female", "M": "Male"}[p.SEX]
        demog.append({"SUBJECT": subj, "BRTHDAT": raw_date(bd, style if style != "split" else "dmy_text"),
                      "SEX": sexraw, "RACE": RACE_CODES[race] if "racecodes" in traps else race.title(),
                      "HISPANIC": "Yes" if p.ETHNIC == "HISPANIC OR LATINO" else "No"})
        consent.append({"SUBJECT": subj, "ICDAT": raw_date(ic, style if style != "split" else "dmy_text")})
        if not scrnfail:
            rand.append({"SUBJECT": subj, "TRT_GROUP": ARM_CODES[p.ARMCD][0]})
            for st, en in intervals:
                dose.append({"SUBJECT": subj, "DOSE_START": raw_date(st, "dmy_text" if style == "split" else style),
                             "DOSE_END": raw_date(en, "dmy_text" if style == "split" else style) if en else ""})
    expected = pd.DataFrame(rows)[DM_COLS].sort_values("USUBJID").reset_index(drop=True)
    sh = lambda df: pd.DataFrame(df).sample(frac=1, random_state=rng.randint(0, 10**6)).reset_index(drop=True)
    sites = pd.DataFrame([{"SITE": s, "COUNTRY": c} for s, c in sorted(countries.items())])
    dstyle = style if style != "split" else "dmy_text"
    sex_rule = "`SEX` codes: `1` = M, `2` = F." if "sexcodes" in traps else "`SEX`: `Female` = F, `Male` = M."
    race_rule = ("`RACE` codes: " + "; ".join(f"`{v}` = {k}" for k, v in RACE_CODES.items()) + "."
                 if "racecodes" in traps else "`RACE` = raw `RACE` in upper case.")
    arm_rule = "; ".join(f"`{a}` = `{c}` / {n}" for a, c, n in ARM_CODES.values())
    spec = f"""# Task {tid}: build SDTM DM from raw demographics, consent, randomization and dosing

Study `{studyid}`. Build the SDTM DM dataset at `output/dm.csv`, one row per subject in `input/raw_demog.csv`.

## Inputs
- `raw_demog.csv`: birth date, sex, race, ethnicity.
- `raw_consent.csv`: informed consent date.
- `raw_rand.csv`: randomized treatment group. Subjects missing here are screen failures.
- `raw_dosing.csv`: one row per dosing interval.
- `sites.csv`: country of each site.

## Output columns
{", ".join(f"`{c}`" for c in DM_COLS)}

## Rules
- `STUDYID` = `{studyid}`, `DOMAIN` = `DM`. Raw `SUBJECT` is `<site>-<subject>`: `SITEID` = site, `SUBJID` = subject, `USUBJID` = `STUDYID-SITEID-SUBJID`.
- {date_rule_text(dstyle)}
- `BRTHDTC` = birth date. `RFICDTC` = consent date.
- `AGE` = completed years from `BRTHDTC` to `RFICDTC` (the age on the consent date; a birthday on the consent date counts). `AGEU` = `YEARS`.
- {sex_rule}
- {race_rule}
- `ETHNIC`: `HISPANIC` = `Yes` gives `HISPANIC OR LATINO`, `No` gives `NOT HISPANIC OR LATINO`.
- `TRT_GROUP` gives `ARMCD` / `ARM`: {arm_rule}. Screen failures get `ARMCD` = `SCRNFAIL`, `ARM` = `Screen Failure`.
- `RFSTDTC` = the earliest `DOSE_START`. `RFENDTC` = the latest of all `DOSE_START` and `DOSE_END` dates. Both are blank for subjects with no dosing.
- `COUNTRY` comes from `sites.csv`.
- Sort output rows by `USUBJID`.
{COMMON_RULES}
"""
    meta = {"task": tid, "domain": "DM", "key": ["USUBJID"], "style": style, "traps": traps,
            "n_subjects": int(len(pick)), "n_records": int(len(expected)), "seed": seed}
    write_task(tid, spec, {"raw_demog.csv": sh(demog), "raw_consent.csv": sh(consent), "raw_rand.csv": sh(rand),
                           "raw_dosing.csv": sh(dose), "sites.csv": sites}, expected, meta)


TASK_LIST = [
    ("AE-01", make_ae, 8, "dmy_text", []),
    ("AE-02", make_ae, 12, "compact", ["partial"]),
    ("AE-03", make_ae, 12, "split", ["partial"]),
    ("AE-04", make_ae, 12, "us", ["sevcodes"]),
    ("AE-05", make_ae, 12, "dmy_text", ["deleted"]),
    ("AE-06", make_ae, 12, "compact", ["dup"]),
    ("AE-07", make_ae, 12, "site", []),
    ("AE-08", make_ae, 16, "compact", ["partial", "deleted", "dup", "sevcodes"]),
    ("AE-09", make_ae, 16, "split", ["partial", "dup", "sevcodes"]),
    ("AE-10", make_ae, 16, "site", ["deleted", "dup", "sevcodes"]),
    ("MH-01", make_mh, 8, "dmy_text", []),
    ("MH-02", make_mh, 12, "compact", ["catcodes"]),
    ("MH-03", make_mh, 12, "split", []),
    ("MH-04", make_mh, 12, "iso", ["deleted"]),
    ("MH-05", make_mh, 16, "split", ["catcodes", "deleted"]),
    ("DM-01", make_dm, 12, "dmy_text", []),
    ("DM-02", make_dm, 16, "compact", ["sexcodes", "racecodes"]),
    ("DM-03", make_dm, 16, "us", ["ageedge"]),
    ("DM-04", make_dm, 20, "split", ["ageedge", "racecodes"]),
    ("DM-05", make_dm, 24, "compact", ["ageedge", "sexcodes", "racecodes"]),
]


def main():
    for i, (tid, fn, n, style, traps) in enumerate(TASK_LIST):
        fn(tid, 1000 + i, n, style, traps)
        meta = json.loads((ANSWERS / tid / "meta.json").read_text())
        print(f"{tid}: {meta['n_subjects']} subjects, {meta['n_records']} records, {style}, {traps}")


if __name__ == "__main__":
    main()
