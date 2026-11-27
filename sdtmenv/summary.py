"""Re-grade every saved model output with the current grader and print the results."""
import json
import sys
from pathlib import Path

import pandas as pd

from sdtmenv.check import score
from sdtmenv.run_models import OUT_NAME

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"


def collect():
    rows = []
    for mdir in sorted(p for p in RUNS.iterdir() if p.is_dir() and p.name != "reference"):
        for tdir in sorted(p for p in mdir.iterdir() if p.is_dir()):
            res = json.loads((tdir / "result.json").read_text()) if (tdir / "result.json").exists() else {}
            out = tdir / OUT_NAME[tdir.name.split("-")[0]]
            s = score(tdir.name, out) if out.exists() else {"reward": 0.0, "passed": False, "col_errors": {}}
            rows.append({"model": mdir.name, "task": tdir.name, "passed": s["passed"], "reward": s["reward"],
                         "api_error": str(res.get("error", "")).startswith("api:"),
                         "no_output": not out.exists(), "col_errors": s.get("col_errors", {})})
    return pd.DataFrame(rows)


def main():
    global RUNS
    if len(sys.argv) > 1:  # e.g. `python -m sdtmenv.summary runs_agent`
        RUNS = ROOT / sys.argv[1]
    df = collect()
    ok = df[~df.api_error]
    print("Per model (tasks with an API failure excluded):")
    print(ok.groupby("model").agg(tasks=("task", "count"), passed=("passed", "sum"), mean_reward=("reward", "mean"),
                                  crashed=("no_output", "sum")).round(3).to_string())
    print("\nPer task: models passing / models run")
    t = ok.groupby("task").agg(passed=("passed", "sum"), run=("passed", "count"), mean_reward=("reward", "mean")).round(3)
    t["pass_rate"] = (t.passed / t.run).round(2)
    print(t.to_string())
    errs = {}
    for ce in ok.col_errors:
        for c, n in ce.items():
            errs[c] = errs.get(c, 0) + n
    print("\nWrong cells by column, all models:", dict(sorted(errs.items(), key=lambda kv: -kv[1])))
    print("\nAPI failures:", df[df.api_error][["model", "task"]].values.tolist())
    df.to_csv(RUNS / "summary.csv", index=False)


if __name__ == "__main__":
    main()
