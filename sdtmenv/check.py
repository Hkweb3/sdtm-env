"""Deterministic grader: compare an agent's SDTM output with the hidden expected dataset.

Reward is cell accuracy over the expected cells, with extra or duplicate rows
counted as fully wrong rows. Constant columns and the row key are required for a
pass but earn no reward: copying identifiers alone scored 0.33 before this rule. A task passes only on an exact match: same columns
in the same order, every expected row present once, no extra rows, every cell equal.
Numeric columns compare by value ("64" == "64.0"); everything else is exact text
after trimming surrounding whitespace.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ROOT / "answers"
NUMERIC = {"AESEQ", "MHSEQ", "AESTDY", "AEENDY", "MHDY", "AGE", "ASTDY", "AENDY", "ADURN", "LBSTRESN", "LBSTNRLO",
           "LBSTNRHI", "LBDY"}  # LBSTRESC is text on purpose: trailing zeros are part of the spec
FREE = {"STUDYID", "DOMAIN", "AGEU"}  # constants stated in the spec


def _read(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[]).apply(lambda s: s.str.strip())


def _same(col, a, b):
    if a == b:
        return True
    if col in NUMERIC and a != "" and b != "":
        try:
            return float(a) == float(b)
        except ValueError:
            return False
    return False


def score_findings(task_id, output_path, exp, meta):
    """Data-review tasks: F1 over cited issues. Duplicate rows count as false positives."""
    result = {"task": task_id, "reward": 0.0, "passed": False, "error": None}
    try:
        out = _read(output_path)
    except FileNotFoundError:
        result["error"] = "no output file"
        return result
    except Exception as e:
        result["error"] = f"unreadable output: {type(e).__name__}"
        return result
    missing = [c for c in meta["key"] if c not in out.columns]
    if missing:
        result["error"] = f"missing column(s) {missing}"
        return result

    def norm(df):
        seq = df["SEQ"].map(lambda s: str(int(float(s))) if s not in ("", None) else "")
        return list(zip(df["CHECK"].str.upper(), df["USUBJID"], df["DOMAIN"].str.upper(), seq))

    got, want = norm(out), set(norm(exp))
    tp = len(set(got) & want)
    fp, fn = len(got) - tp, len(want) - tp
    prec = tp / (tp + fp) if tp + fp else (1.0 if not want else 0.0)
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    by_check = {}
    for c, *_ in want - set(got):
        by_check[c] = by_check.get(c, 0) + 1
    result.update(reward=round(f1, 4), passed=fp == 0 and fn == 0, tp=tp, fp=fp, fn=fn,
                  col_errors={f"missed {k}": v for k, v in by_check.items()} |
                             ({"false positives": fp} if fp else {}),
                  examples=[{"false_positive": list(x)} for x in list(set(got) - want)[:5]])
    return result


def score_open(task_id, output_path, exp, meta):
    """Open review: recall of planted problems within the first `cap` rows. A problem counts as
    found when any of the first `cap` rows cites one of its target records."""
    result = {"task": task_id, "reward": 0.0, "passed": False, "error": None}
    try:
        out = _read(output_path)
    except FileNotFoundError:
        result["error"] = "no output file"
        return result
    except Exception as e:
        result["error"] = f"unreadable output: {type(e).__name__}"
        return result
    missing = [c for c in ("USUBJID", "DOMAIN", "SEQ") if c not in out.columns]
    if missing:
        result["error"] = f"missing column(s) {missing}"
        return result
    out = out.head(meta["cap"])
    seq = out["SEQ"].map(lambda s: str(int(float(s))) if s not in ("", None) else "")
    cited = set(zip(out["DOMAIN"].str.upper(), out["USUBJID"], seq))
    found, missed = 0, {}
    for pid, g in exp.groupby("PROBLEM"):
        if any((r.DOMAIN, r.USUBJID, r.SEQ) in cited for r in g.itertuples()):
            found += 1
        else:
            t = g.TYPE.iloc[0]
            missed[f"missed {t}"] = missed.get(f"missed {t}", 0) + 1
    n = exp.PROBLEM.nunique()
    result.update(reward=round(found / n, 4), passed=found == n, found=found, planted=n, rows=len(out),
                  col_errors=missed, examples=[])
    return result


def score(task_id, output_path):
    exp = _read(ANSWERS / task_id / "expected.csv")
    meta = json.loads((ANSWERS / task_id / "meta.json").read_text())
    if meta.get("kind") == "findings":
        return score_findings(task_id, output_path, exp, meta)
    if meta.get("kind") == "open_review":
        return score_open(task_id, output_path, exp, meta)
    key, cols = meta["key"], list(exp.columns)
    result = {"task": task_id, "reward": 0.0, "passed": False, "error": None}
    try:
        out = _read(output_path)
    except FileNotFoundError:
        result["error"] = "no output file"
        return result
    except Exception as e:  # unreadable CSV
        result["error"] = f"unreadable output: {type(e).__name__}"
        return result

    columns_exact = list(out.columns) == cols
    missing_cols = [c for c in cols if c not in out.columns]
    if any(k in missing_cols for k in key):
        result.update(error=f"missing key column(s) {missing_cols}", columns_exact=False)
        return result

    def keys(df):  # row-wise join; built per row so an empty frame still yields a column
        return pd.Series(["\x1f".join(r) for r in df[key].itertuples(index=False)], index=df.index, dtype=object)

    out = out.copy()
    out["_k"] = keys(out)
    exp = exp.copy()
    exp["_k"] = keys(exp)
    dup_keys = int(out["_k"].duplicated().sum())
    first = out.drop_duplicates("_k").set_index("_k")
    extra_rows = int((~out["_k"].isin(exp["_k"])).sum()) + dup_keys
    missing_rows = int((~exp["_k"].isin(first.index)).sum())

    free = FREE | set(meta.get("free", []))  # per-task straight copies from the input
    graded = [c for c in cols if c not in free and c not in key]
    # A graded cell counts only if the expected or the submitted value is non-blank, so mostly-blank
    # flag columns (LBBLFL, AOCCFL...) can't be farmed by leaving everything empty.
    correct, graded_correct, graded_total, col_errors, examples = 0, 0, 0, {}, []
    for _, row in exp.iterrows():
        got = first.loc[row["_k"]] if row["_k"] in first.index else None
        for c in cols:
            ok = got is not None and c in first.columns and _same(c, row[c], got[c])
            gv = got[c] if got is not None and c in first.columns else ""
            if c in graded and (row[c] != "" or gv != ""):
                graded_total += 1
                graded_correct += ok
            if ok:
                correct += 1
            else:
                col_errors[c] = col_errors.get(c, 0) + 1
                if len(examples) < 8 and got is not None:
                    examples.append({"key": row["_k"].replace("\x1f", " / "), "col": c, "expected": row[c],
                                     "got": got[c] if c in first.columns else "<missing column>"})
    denom = graded_total + extra_rows * len(graded)
    reward = graded_correct / denom if denom else 0.0
    result.update(reward=round(reward, 4), columns_exact=columns_exact, missing_cols=missing_cols,
                  missing_rows=missing_rows, extra_rows=extra_rows, col_errors=col_errors, examples=examples,
                  passed=bool(columns_exact and extra_rows == 0 and missing_rows == 0 and correct == len(exp) * len(cols)))
    return result


if __name__ == "__main__":
    print(json.dumps(score(sys.argv[1], sys.argv[2]), indent=1))
