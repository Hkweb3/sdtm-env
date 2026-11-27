"""Run local CLI coding agents (Claude Code, Codex) on tasks in isolated C:\\tmp workspaces.

  python -m sdtmenv.run_cli_agents opus-5.5 gpt-6-astra gpt-6.2-sol --tasks OR-13 OR-14 OR-15
"""
import argparse
import json
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sdtmenv.check import score
from sdtmenv.run_models import OUT_NAME, TASKS

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs_cli"
SANDBOX_BASE = Path(r"C:\tmp") if Path(r"C:\tmp").exists() else Path.home() / ".sdtm_eval_tmp"

CLI_MODELS = {
    "opus-5.5": ("claude", "claude-opus-5-5", "high"),
    "gpt-6-astra": ("codex", "gpt-6-astra", "high"),
    "gpt-6.2-sol": ("codex", "gpt-6.2-sol", "high"),
}

PROMPT = (
    "You are an experienced clinical data reviewer working in this isolated directory. "
    "Read `spec.md` and thoroughly inspect all CSV files in `input/`. "
    "You may write and run Python scripts (pandas is available) inside this directory "
    "to cross-check every table against the protocol and clinical/medical logic. "
    "Stay strictly inside the current working directory. "
    "Write your final findings to `output/{out}` matching the exact schema in `spec.md`. "
    "Verify `output/{out}` exists and is valid CSV, then reply DONE."
)

SUSPICIOUS_RE = re.compile(r"answers[\\/]|expected\.csv|sdtm-env|projects[\\/]business", re.I)


def run_one(tag, tid, timeout=600):
    cli, model, effort = CLI_MODELS[tag]
    exe = shutil.which(cli)
    if not exe:
        raise RuntimeError(f"{cli} CLI not found on PATH")

    task_dir = TASKS / tid
    out_name = OUT_NAME[tid.split("-")[0]]
    rdir = RUNS / tag / tid
    if rdir.exists():
        shutil.rmtree(rdir)
    rdir.mkdir(parents=True)

    work = SANDBOX_BASE / f"sdtm_eval_{tag}_{tid}_{int(time.time())}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    shutil.copy(task_dir / "spec.md", work / "spec.md")
    shutil.copytree(task_dir / "input", work / "input")
    (work / "output").mkdir()

    prompt = PROMPT.format(out=out_name)
    if cli == "claude":
        cmd = [
            exe, "--safe-mode", "--model", model, "--effort", effort,
            "--no-session-persistence", "--permission-mode", "dontAsk",
            "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
            "--output-format", "stream-json", "--verbose",
            "-p", prompt,
        ]
    else:
        cmd = [
            exe, "exec", "-m", model,
            "-c", f'model_reasoning_effort="{effort}"',
            "-c", 'windows.sandbox="unelevated"',
            "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
            "-s", "workspace-write", "-C", str(work), "--json",
            prompt,
        ]

    t0 = time.time()
    result = {"model": tag, "cli": cli, "model_id": model, "effort": effort, "task": tid}
    try:
        p = subprocess.run(
            cmd, cwd=work, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        result["returncode"] = p.returncode
        stdout, stderr = p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired as e:
        result["returncode"] = -1
        result["error"] = f"timed out after {timeout}s"
        stdout = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")

    result["elapsed_s"] = round(time.time() - t0, 1)
    (rdir / "transcript.jsonl").write_text(stdout, encoding="utf-8")
    if stderr:
        (rdir / "stderr.txt").write_text(stderr, encoding="utf-8")
    result["suspicious"] = bool(SUSPICIOUS_RE.search(stdout))

    target = work / "output" / out_name
    if target.exists():
        shutil.copy(target, rdir / out_name)
        result.update({k: v for k, v in score(tid, target).items() if k != "task"})
    else:
        result.update(reward=0.0, passed=False, error=result.get("error") or f"no output/{out_name}")

    (rdir / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return result


def run_model_series(tag, tids, timeout):
    out = []
    for tid in tids:
        r = run_one(tag, tid, timeout=timeout)
        print(
            f"{tag:12s} {tid}  found={r.get('found','-')}/{r.get('planted','-')}  "
            f"reward={r.get('reward')}  pass={r.get('passed')}  rows={r.get('rows','-')}  "
            f"susp={r.get('suspicious')}  {r.get('elapsed_s')}s  {r.get('error') or ''}",
            flush=True,
        )
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+", choices=list(CLI_MODELS))
    ap.add_argument("--tasks", nargs="+", default=["OR-13", "OR-14", "OR-15"])
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    with ThreadPoolExecutor(max_workers=len(a.models)) as ex:
        futs = [ex.submit(run_model_series, m, a.tasks, a.timeout) for m in a.models]
        for f in futs:
            f.result()


if __name__ == "__main__":
    main()
