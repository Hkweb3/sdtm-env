"""Multi-turn agent harness: the model explores the task folder by running Python, sees the
output, and iterates until it writes the output file and replies DONE.

Provider-neutral text protocol (no native tool calling), so every model in
run_models.MODELS works. The sandbox folder persists across turns; Python state does not.
The grader is never consulted during the episode.

  python -m sdtmenv.agent kimi --tasks OR-01 OR-02 --turns 12
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sdtmenv.check import score
from sdtmenv.run_models import MODELS, OUT_NAME, TASKS, chat, code_blocks

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs_agent"
MAX_OUT = 3500

SYSTEM = """You are a clinical data programmer working in a sandbox folder. It contains `spec.md` (your task) and `input/` (the data). Write your result under `output/`.

How to work:
- To run code, reply with exactly one ```python code block. It runs as a fresh Python 3 process in the sandbox folder (pandas is available), and you will see its stdout and stderr. Variables do not survive between runs; save anything you need to files.
- Explore the data before deciding what to do. Print what you need to see, but keep printed output short (it is truncated to about 3,500 characters).
- When `output/{out}` is written and you are finished, reply with the single word DONE and no code block.
- You have at most {turns} turns."""


def run_code(work, code):
    (work / "_turn.py").write_text(code, encoding="utf-8")
    try:
        p = subprocess.run([sys.executable, "-E", "_turn.py"], cwd=work, capture_output=True, text=True,
                           timeout=180)
        out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
    except subprocess.TimeoutExpired:
        out = "[timed out after 180 s]"
    if len(out) > MAX_OUT:
        out = out[:MAX_OUT // 2] + f"\n... [{len(out) - MAX_OUT} characters truncated] ...\n" + out[-MAX_OUT // 2:]
    return out or "[no output]"


def run_agent(model, tid, turns):
    task_dir = ROOT / "tasks" / tid
    out_name = OUT_NAME[tid.split("-")[0]]
    rdir = RUNS / model / tid
    if rdir.exists():
        shutil.rmtree(rdir)
    rdir.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="agent_"))
    shutil.copy(task_dir / "spec.md", work / "spec.md")
    shutil.copytree(task_dir / "input", work / "input")
    (work / "output").mkdir()
    spec = (task_dir / "spec.md").read_text(encoding="utf-8")
    messages = [{"role": "system", "content": SYSTEM.format(out=out_name, turns=turns)},
                {"role": "user", "content": f"Here is spec.md:\n\n{spec}\n\nStart by exploring `input/`."}]
    if MODELS[model][0] == "gemini":  # no system role in this client: fold it into the first message
        messages = [{"role": "user", "content": messages[0]["content"] + "\n\n" + messages[1]["content"]}]
    transcript, result, codes = [], {"model": model, "task": tid}, []
    for turn in range(1, turns + 1):
        try:
            reply = chat(model, messages)
        except Exception as e:
            result["error"] = f"api: {e}"
            break
        blocks = code_blocks(reply)
        transcript.append({"turn": turn, "assistant": reply})
        messages.append({"role": "assistant", "content": reply})
        if not blocks:
            # DONE must be the whole reply or its last line: "DONEPEZIL" in a progress note once ended a run
            lines = [l.strip(" *`.") for l in reply.strip().splitlines() if l.strip()]
            if lines and lines[-1].upper() == "DONE":
                break
            nudge = "Reply with one ```python code block to run, or DONE if output/" + out_name + " is written."
            messages.append({"role": "user", "content": nudge})
            continue
        codes.append(blocks[0])
        obs = run_code(work, blocks[0])
        transcript[-1]["observation"] = obs
        left = turns - turn
        warn = ""
        if left <= 2 and not (work / "output" / out_name).exists():
            warn = f" output/{out_name} does not exist yet: write it in your next code block, or the task scores 0."
        messages.append({"role": "user", "content": f"Output:\n```\n{obs}\n```\n({left} turns left){warn}"})
    result["turns"] = len(transcript)
    target = work / "output" / out_name
    if target.exists():
        shutil.copy(target, rdir / out_name)
        result.update({k: v for k, v in score(tid, target).items() if k != "task"})
    else:
        result.update(reward=0.0, passed=False, error=result.get("error") or "no output file")
    result["suspicious"] = any(re.search(r"answers|expected\.csv", c) for c in codes)
    (rdir / "transcript.json").write_text(json.dumps(transcript, indent=1), encoding="utf-8")
    (rdir / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+", choices=list(MODELS))
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--turns", type=int, default=12)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    tids = a.tasks or sorted(p.name for p in TASKS.iterdir() if p.is_dir())
    jobs = [(m, t) for m in a.models for t in tids]
    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(lambda j: run_agent(j[0], j[1], a.turns), jobs):
            print(f"{r['model']:8s} {r['task']}  pass={r.get('passed')}  reward={r.get('reward')}  "
                  f"turns={r.get('turns')}  {r.get('col_errors') or ''} {(r.get('error') or '')[:80]}", flush=True)


if __name__ == "__main__":
    main()
