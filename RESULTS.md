# Model results (2026-10-26/27)

Harness: `run_models.py` single-shot (10-row preview, one script, one retry on crash) and `agent.py` multi-turn (explore by running code, 12–16 turns). Graders never consulted during a run. API failures excluded.

## Tier 1: explicit SDTM mapping (AE, MH, DM)

| Model | Passed |
|---|---|
| DeepSeek V4 Pro | 19/19 |
| DeepSeek V4.1 Flash | 18/20 |
| Kimi K3 | 18/20 |
| GLM 5.3 Flash | 15/17 |
| Qwen 3.8 27B | 7/18 |
| Gemini Flash (free tier) | 1/1; the other 19 runs hit the free-tier quota |

Too easy: every rule is in the spec.

## Tier 2: ADaM ADAE, LB conversion, inferred site locale

DeepSeek V4 Pro passed 3/3 ADAE tasks before its API balance ran out. Too easy for the same reason.

## Tier 3: data review with a stated check list (F1)

| Model | Passed |
|---|---|
| Kimi K3 | 6/6 (86/86 issues, 0 false positives) |
| GLM 5.3 Flash | 5/6 (the sixth was a script crash) |

Too easy: stated checks become code.

## Tier 4: open-ended clinical review (recall of planted problems, max 25 findings)

| | OR-01 | OR-02 | OR-03 | OR-04 | OR-05 | OR-06 | Passed |
|---|---|---|---|---|---|---|---|
| Kimi K3, agent (16 turns) | 0.67 | 0.71 | 0.50 | 0.75 | 0.78 | 0.80 | 0/6 |
| GLM 5.3 Flash, agent (12 turns) | 0.67 | 0.86 | 0.50 | 0.75 | 0.78 | 0.60 | 0/6 |
| Kimi K3, single-shot | 0.83 | 0.57 | 0.50 | 0.13 | 0.11 | 0.10 | 0/6 |
| GLM 5.3 Flash, single-shot | 0 | 0 | 0 | 0 | 0 | 0 | 0/6 (no usable findings file in any task) |

Baselines: reference clinical reviewer 1.00 on all six; tier 3's rule-based checks 0.02; citing every subject 0.16; the 25 most extreme labs 0.23.

**Misses by problem type (agents, all 12 runs):** every Kimi miss and every GLM miss except two in OR-06 was a sex-specific AE (e.g. ovarian cyst in a male) or an AE coded to an impossible body system (e.g. diarrhoea under pregnancy disorders). Both models reliably found impossible labs, data after death, underage subjects, post-cutoff dates, active drug in placebo subjects, 10x doses and duplicate enrollment.

Reading the transcripts: the models never cross-check AE terms against the subject's sex, and never validate the term-to-body-system coding. A human medical reviewer does both routinely.

## Harness issues found and fixed during the runs

- `python -I` hid pandas (user site-packages); now uses `-E`.
- River dropped long responses (`IncompleteRead`); now retried.
- Kimi on River sometimes replies in its native tool-call format (`<|sep|>code<|close|>`), which wasted 1–16 agent turns per task; now parsed.
- Agents ran out of turns before writing output; a warning now appears with 2 turns left.

## Tier 4b: cross-domain blind spots (OR-07..12, adds CM + MH; agents, 16 turns)

| | OR-07 | OR-08 | OR-09 | OR-10 | OR-11 | OR-12 | Passed |
|---|---|---|---|---|---|---|---|
| Kimi K3 | 0.67 | 0 (ran out of turns paging through CM, no output) | 0.71 | 0.57 | 0.56 | 0.40 | 0/6 |
| GLM 5.3 Flash | 0.83 | 0.43 | 0.71 | 0.57 | 0.56 | 0.20 | 0/6 |

Detection by problem type, both models (tasks with output):

| Type | Kimi | GLM | Read |
|---|---|---|---|
| Prohibited medication (class named in protocol, brand name, often uncoded) | 7/8 | 8/9 | Models know drug classes |
| Sex-specific lab (PSA in a woman, hCG in a man) | 4/5 | 4/6 | Mostly caught |
| Contraceptive recorded for a man | 2/5 | 2/6 | Blind spot |
| Age-inappropriate AE (delayed puberty at 74) | 1/5 | 2/6 | Blind spot |
| Surgical-history conflict (uterine fibroid after hysterectomy) | 1/6 | 0/7 | **Strongest blind spot** |
| Sex-specific AE, wrong body-system coding (from 4a) | 0/3 | 1/5 | Blind spot persists |
| Impossible labs, data after death, underage, cutoff, arm mismatch, duplicates | all found | all found | Solved |

Pattern: models catch problems they can find by scanning *one* table for something unusual (a drug class, an odd lab test). They miss problems that only appear when an AE is read *against the patient*: their sex, age, or surgical history. That cross-record clinical reasoning is what a medical reviewer does and what these tasks train.

Harness fix: the agent's DONE check matched "DONE" inside "DONEPEZIL" and ended a GLM run early; DONE must now be the reply's last line. That run was repeated.

## Tier 4c: hard mode (OR-13..15; agents, 16 turns; 2026-10-27)

Every planted problem needs two records plus clinical knowledge. New types: an AE in an organ the subject no longer has (bilateral BKA then ingrown toenail, total laryngectomy then vocal cord polyp, total gastrectomy then gastritis; a unilateral-BKA decoy has the same AE legitimately), an AE contradicted by the same-day lab (hypokalaemia with K 6.2), a patch-site reaction before the first patch, sex-specific surgical history written the way sites abbreviate it (TURP in a woman, BTL in a man), and history dated before birth. Plus the tier 4/4b blind-spot types.

| | OR-13 | OR-14 | OR-15 | Passed |
|---|---|---|---|---|
| Kimi K3 | 1/8 | 1/9 | 1/9 | 0/3 |
| GLM 5.3 Flash | 2/8 | 2/9 | 2/9 | 0/3 |
| DeepSeek V4.1 Flash | 1/8 | 2/9 | 1/9 | 0/3 |
| Reference reviewer | 8/8 | 9/9 | 9/9 | 3/3 |

Baselines: cite every subject 0.08, tier 3's mechanical checks 0.03, the 25 most extreme labs 0.11.

| Type (all 9 runs) | Found |
|---|---|
| Patch-site reaction before first patch | 9/9 |
| History dated before birth | 2/12 |
| AE contradicted by same-day lab | 1/15 |
| AE in a removed organ | 0/15 |
| Sex-specific surgical history (abbreviated) | 0/9 |
| Uterine/prostate AE after hysterectomy/prostatectomy | 0/6 |
| Sex-specific AE, wrong SOC, child AE, contraceptive in a man | 1/12 |

The agents do real review work and use all 16 turns: they find genuine natural issues (a fatal AE not flagged serious, olanzapine as a prohibited anticholinergic, pre-dose AEs, hospitalisation without AESER). GLM flagged "K 6.3, critical" without noticing the same-day AE said hypokalaemia.

Grader fix: the AE-vs-lab problem first counted a citation of the lab record, so flagging the lab merely as high scored the problem without the contradiction. Only the AE record counts now (inputs unchanged; runs re-graded, which lowered GLM from 0.38/0.33 to 0.25/0.22).

Not yet run on frontier models (Claude Opus 5.5, GPT-6.1, Gemini 4 Argon): `run_models.MODELS` has them via OpenRouter, but no `OPENROUTER_API_KEY` is set.
