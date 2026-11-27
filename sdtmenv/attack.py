"""Try to get reward without doing the mapping. Every attack must score far below a
real solution and never pass. Prints one line per attack, averaged over all tasks.
"""
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from sdtmenv.check import score
from sdtmenv.solve import ROOT, solve

ALL_TASKS = sorted(p for p in (ROOT / "tasks").iterdir() if p.is_dir())
TASKS = [p for p in ALL_TASKS if not p.name.startswith("DR")]
DR_TASKS = [p for p in ALL_TASKS if p.name.startswith("DR")]
CHECKS = ["AE_DATE_ORDER", "AE_DUPLICATE", "SAE_CRITERIA", "DEATH_CONSISTENCY", "DOSE_AFTER_DISC", "LAB_UNIT",
          "LAB_VISIT_DATE"]


def dr_empty(td, work):
    return pd.DataFrame(columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])


def dr_flag_everything(td, work):
    """Every AE under every AE check, every EX and LB record under its checks."""
    rows = []
    for dom, seq, checks in (("ae", "AESEQ", CHECKS[:4]), ("ex", "EXSEQ", ["DOSE_AFTER_DISC"]),
                             ("lb", "LBSEQ", ["LAB_UNIT", "LAB_VISIT_DATE"])):
        df = pd.read_csv(td / "input" / f"{dom}.csv", dtype=str, keep_default_na=False)
        for r in df.itertuples():
            rows += [(c, r.USUBJID, dom.upper(), getattr(r, seq)) for c in checks]
    return pd.DataFrame(rows, columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])


def dr_check_name_only(td, work):
    """Right checks, wrong records: shows citing the record matters."""
    ref_ = pd.read_csv(solve(td, work / "ref"), dtype=str, keep_default_na=False)
    ref_["SEQ"] = ref_["SEQ"].map(lambda s: str(int(s) + 1) if s else "1")
    return ref_


def dr_one_check_skipped(td, work):
    """A careful reviewer who never looks at labs: partial credit, no pass."""
    ref_ = pd.read_csv(solve(td, work / "ref"), dtype=str, keep_default_na=False)
    return ref_[~ref_.CHECK.str.startswith("LAB")]


DR_ATTACKS = [dr_empty, dr_flag_everything, dr_check_name_only, dr_one_check_skipped]
OR_TASKS = [p for p in ALL_TASKS if p.name.startswith("OR")]
TASKS = [p for p in TASKS if not p.name.startswith("OR")]


def _pkg(td):
    return [pd.read_csv(td / "input" / f"{d}.csv", dtype=str, keep_default_na=False)
            for d in ("dm", "ae", "ex", "ds", "lb")]


def or_all_subjects(td, work):
    """Cite every subject's DM row (up to the cap)."""
    dm = _pkg(td)[0]
    return pd.DataFrame({"USUBJID": dm.USUBJID, "DOMAIN": "DM", "SEQ": "", "ISSUE": "check subject"}).head(25)


def or_mechanical_checks(td, work):
    """Run tier 3's seven rule-based checks (which models ace) and submit their hits."""
    from sdtmenv.generate3 import detect
    hits = sorted(detect(*_pkg(td)))
    return pd.DataFrame([{"USUBJID": u, "DOMAIN": d, "SEQ": s, "ISSUE": c} for c, u, d, s in hits][:25],
                        columns=["USUBJID", "DOMAIN", "SEQ", "ISSUE"])


def or_extreme_labs(td, work):
    """The 25 lab values furthest from their test's median: a statistics-only reviewer."""
    lb = _pkg(td)[4]
    lb = lb[lb.LBSTRESN != ""].copy()
    lb["v"] = lb.LBSTRESN.astype(float)
    lb["z"] = lb.groupby("LBTESTCD").v.transform(lambda s: (s - s.median()).abs() / (s.std() or 1))
    top = lb.sort_values("z", ascending=False).head(25)
    return pd.DataFrame({"USUBJID": top.USUBJID, "DOMAIN": "LB", "SEQ": top.LBSEQ, "ISSUE": "outlier"})


OR_ATTACKS = [dr_empty, or_all_subjects, or_mechanical_checks, or_extreme_labs]


def cols_of(tid):
    return list(pd.read_csv(ROOT / "answers" / tid / "expected.csv", nrows=0).columns)


def ref(td, work):
    return pd.read_csv(solve(td, work / "ref"), dtype=str, keep_default_na=False)


def a_header_only(td, work):
    return pd.DataFrame(columns=cols_of(td.name))


def a_raw_renamed(td, work):
    files = sorted((td / "input").glob("raw_*.csv")) or sorted((td / "input").glob("*.csv"))
    raw = pd.read_csv(files[0], dtype=str, keep_default_na=False)
    cols = cols_of(td.name)
    return pd.DataFrame({c: raw.iloc[:, i % raw.shape[1]] for i, c in enumerate(cols)})


def a_keys_only(td, work):
    """Copy only the identifiers and constants a lazy agent could fill in for free."""
    r = ref(td, work)
    keep = {"STUDYID", "DOMAIN", "USUBJID", "AESPID", "MHSPID", "LBSPID", "AESEQ", "SUBJID", "SITEID"}
    for c in r.columns:
        if c not in keep and not (td.name.startswith("ADAE") and c == "AESEQ"):
            r[c] = ""
    return r


def a_copy_through(td, work):
    """Keep only columns that are straight copies of an input column; skip every derivation."""
    r = ref(td, work)
    inputs = set()
    for f in (td / "input").glob("*.csv"):
        inputs |= set(pd.read_csv(f, nrows=0).columns)
    for c in r.columns:
        if c not in inputs and c not in {"STUDYID", "DOMAIN", "USUBJID"}:
            r[c] = ""
    if td.name.startswith("LB"):
        for c in ("LBORRES", "LBORRESU", "LBORNRLO", "LBORNRHI", "VISIT"):
            r[c] = ref(td, work)[c]
    return r


def a_duplicate_rows(td, work):
    r = ref(td, work)
    return pd.concat([r, r])


def a_extra_junk_rows(td, work):
    r = ref(td, work)
    junk = r.copy()
    key = "AESPID" if "AESPID" in r else "MHSPID" if "MHSPID" in r else "USUBJID"
    junk[key] = junk[key] + "Z"
    return pd.concat([r, junk])


def a_lowercase(td, work):
    r = ref(td, work)
    return r.apply(lambda s: s.str.lower() if s.name not in ("USUBJID", "AESPID", "MHSPID") else s)


def a_drop_sequence(td, work):
    """Skip ordering work: sequence numbers all 1, first-occurrence and baseline flags on every row."""
    r = ref(td, work)
    for c in ("AESEQ", "MHSEQ"):
        if c in r and not td.name.startswith("ADAE"):
            r[c] = "1"
    for c in ("AOCCFL", "AOCCPFL", "LBBLFL"):
        if c in r:
            r[c] = "Y"
    if td.name.startswith("DM"):
        r["AGE"] = (r["AGE"].astype(int) + 1).astype(str)  # age by year subtraction, ignoring the birthday
    return r


def a_no_study_days(td, work):
    r = ref(td, work)
    for c in ("AESTDY", "AEENDY", "MHDY", "AGE", "ASTDY", "ADURN", "LBDY"):
        if c in r:
            r[c] = ""
    return r


ATTACKS = [a_header_only, a_raw_renamed, a_keys_only, a_copy_through, a_duplicate_rows, a_extra_junk_rows,
           a_lowercase, a_drop_sequence, a_no_study_days]


def main():
    print(f"{'attack':22s} {'mean reward':>11s} {'passed':>7s}")
    for atk, tasks in ([(a, TASKS) for a in ATTACKS] + [(a, DR_TASKS) for a in DR_ATTACKS] +
                       [(a, OR_TASKS) for a in OR_ATTACKS]):
        rewards, passes = [], 0
        for td in tasks:
            work = Path(tempfile.mkdtemp(prefix="atk_"))
            out = work / "out.csv"
            atk(td, work).to_csv(out, index=False)
            s = score(td.name, out)
            rewards.append(s["reward"])
            passes += s["passed"]
            shutil.rmtree(work, ignore_errors=True)
        name = atk.__name__[2:] if atk.__name__.startswith("a_") else atk.__name__
        print(f"{name:22s} {sum(rewards) / len(rewards):11.3f} {passes:4d}/{len(tasks)}")


if __name__ == "__main__":
    main()
