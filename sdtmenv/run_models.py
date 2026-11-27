"""Run models on the tasks: the model writes a Python script, we execute it in a
scratch copy of the task (spec + inputs only), then grade the output.

Two attempts per task. The second attempt only sees the crash/stderr of the first,
never the grader's verdict, so scores are not tuned against the hidden answers.

  python -m sdtmenv.run_models kimi glm qwen          # all tasks
  python -m sdtmenv.run_models kimi --tasks AE-01 DM-03
"""
import argparse
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from sdtmenv.check import score

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
RUNS = ROOT / "runs"
ENV = Path.home() / "projects" / "business" / "formerly" / ".env"
OUT_NAME = {"AE": "ae.csv", "AEX": "ae.csv", "MH": "mh.csv", "DM": "dm.csv", "ADAE": "adae.csv", "LB": "lb.csv",
            "DR": "findings.csv", "OR": "findings.csv"}

MODELS = {
    "kimi": ("river", "moonshotai/Kimi-K3"),
    "dsflash": ("river", "deepseek-ai/DeepSeek-V4.1-Flash"),
    "glm": ("river", "zai-org/GLM-5.3-Flash"),
    "qwen": ("river", "Qwen/Qwen3.8-27B-FP8"),
    "dspro": ("deepseek", "deepseek-v4-pro"),
    "gemini": ("gemini", "gemini-flash-latest"),
    "opus": ("openrouter", "anthropic/claude-opus-5.5"),
    "gpt": ("openrouter", "openai/gpt-6.1-sol"),
    "argon": ("openrouter", "google/gemini-4-argon"),
}
API = {"river": ("https://api.river.ai/v1/chat/completions", "RIVER_API_KEY"),
       "deepseek": ("https://api.deepseek.com/chat/completions", "DEEPSEEK_API_KEY"),
       "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY")}


def load_keys():
    keys = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip().strip('"')
    return keys


KEYS = load_keys()


def chat(model, messages):
    provider, name = MODELS[model]
    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent"
        body = {"contents": [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
                             for m in messages]}
        headers = {"x-goog-api-key": KEYS["GEMINI_API_KEY"]}
    else:
        url, key_name = API[provider]
        key = KEYS[key_name]
        body = {"model": name, "messages": messages, "temperature": 0.2, "max_tokens": 32000}
        headers = {"Authorization": f"Bearer {key}"}
    headers["Content-Type"] = "application/json"
    for attempt in range(10):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.loads(r.read())
            if provider == "gemini":
                return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
            return data["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 9:
                time.sleep(20 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:200]!r}")
        except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead, ConnectionError):
            if attempt < 9:
                time.sleep(10)
                continue
            raise


def preview(task_dir):
    parts = []
    for f in sorted((task_dir / "input").glob("*.csv")):
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
        parts.append(f"### input/{f.name} ({len(df)} rows; first 10 shown)\n```\n{df.head(10).to_csv(index=False)}```")
    return "\n\n".join(parts)


PROMPT = """You are a clinical data programmer. Complete this clinical data task.

{spec}

## Input files
{preview}

Write one Python 3 script that reads the files in `./input/` and writes the output file under `./output/` exactly as the spec requires. pandas is available. The script runs with the task folder as the working directory. Reply with only the script, in a single ```python code block."""


def code_blocks(text):
    """Fenced ```python blocks; failing that, Kimi's native tool-call format
    (`...<|sep|>CODE<|close|>...`), which River sometimes returns instead."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if not blocks and "<|sep|>" in text:
        segs = re.findall(r"<\|sep\|>((?:(?!<\|sep\|>).)*?)<\|close\|>", text, re.S)  # innermost segment
        blocks = [s for s in segs if "\n" in s.strip() or "import " in s]
    return blocks


def extract_code(text):
    blocks = code_blocks(text)
    return max(blocks, key=len) if blocks else text


def execute(task_dir, code):
    work = Path(tempfile.mkdtemp(prefix="sdtm_"))
    shutil.copy(task_dir / "spec.md", work / "spec.md")
    shutil.copytree(task_dir / "input", work / "input")
    (work / "output").mkdir()
    (work / "solution.py").write_text(code, encoding="utf-8")
    try:
        # -E, not -I: -I also hides user site-packages, where pandas lives on this machine
        p = subprocess.run([sys.executable, "-E", "solution.py"], cwd=work, capture_output=True, text=True, timeout=120)
        err = p.stderr[-2000:] if p.returncode else ""
    except subprocess.TimeoutExpired:
        err = "timed out after 120 s"
    outs = list((work / "output").glob("*.csv"))
    return work, outs, err


def run_one(model, tid):
    task_dir = TASKS / tid
    out_dir = RUNS / model / tid
    out_dir.mkdir(parents=True, exist_ok=True)
    expected_name = OUT_NAME[tid.split("-")[0]]
    messages = [{"role": "user", "content": PROMPT.format(spec=(task_dir / "spec.md").read_text(encoding="utf-8"),
                                                           preview=preview(task_dir))}]
    result = {"model": model, "task": tid, "attempts": 0}
    for attempt in (1, 2):
        result["attempts"] = attempt
        try:
            reply = chat(model, messages)
        except Exception as e:
            result.update(error=f"api: {e}", reward=0.0, passed=False)
            break
        code = extract_code(reply)
        (out_dir / f"solution_{attempt}.py").write_text(code, encoding="utf-8")
        work, outs, err = execute(task_dir, code)
        target = work / "output" / expected_name
        if target.exists() and not err:
            shutil.copy(target, out_dir / expected_name)
            result.update({k: v for k, v in score(tid, target).items() if k != "task"})
            result["suspicious"] = bool(re.search(r"answers|expected\.csv", code))
            shutil.rmtree(work, ignore_errors=True)
            break
        problem = err or f"the script ran but did not write output/{expected_name}"
        shutil.rmtree(work, ignore_errors=True)
        result.update(error=problem[-300:], reward=0.0, passed=False)
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": f"Running your script failed:\n```\n{problem}\n```\nReply with the corrected full script in a single ```python code block."}]
    (out_dir / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+", choices=list(MODELS))
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--workers", type=int, default=3)  # 7 GB RAM machine; 6 got the runs reaped
    a = ap.parse_args()
    tids = a.tasks or sorted(p.name for p in TASKS.iterdir() if p.is_dir())
    jobs = [(m, t) for m in a.models for t in tids]
    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(lambda j: run_one(*j), jobs):
            print(f"{r['model']:8s} {r['task']}  pass={r.get('passed')}  reward={r.get('reward')}  "
                  f"try={r['attempts']}  {(r.get('error') or '')[:80]}", flush=True)


if __name__ == "__main__":
    main()
