# Clinical-data mapping environment

Agent tasks: turn raw clinical-trial data into CDISC SDTM and ADaM datasets, and review study packages for data issues. 51 tasks, each with a deterministic grader.

| Tier | Tasks | What makes it hard |
|---|---|---|
| 1 | AE-01..10, MH-01..05, DM-01..05 | Raw EDC formats, partial dates, coded values, deleted/versioned records, age at consent |
| 2 | ADAE-01..04 | ADaM partial-date imputation (TRTSDT rule, end-date cap), treatment-emergent window boundaries, first-occurrence flags |
| 2 | LB-01..03 | Unit conversion keyed on the raw unit (one site reports glucose in mmol/L already), half-up rounding with trailing zeros, `<` results, baseline = last pre-dose value including same-day retests |
| 2 | AEX-01..03 | Each site's DD/MM vs MM/DD date format is not given; the agent must infer it from the data |
| 3 | DR-01..06 | Data review: find every issue in a DM/AE/EX/DS/LB package across seven checks (AE date order, duplicates, seriousness vs criteria, death consistency, dosing after early discontinuation, wrong-unit lab values, lab visit-date order). Planted issues plus real ones from the source. Graded by F1 over cited records; pass = exact list |
| 4 | OR-01..06 | Open-ended clinical review: no check list, only a protocol synopsis. Planted problems need medical or protocol knowledge: sex-specific AEs, physiologically impossible labs (within 8x of normal), data after death, underage subjects, wrong body-system coding, post-cutoff dates, active drug in placebo subjects, 10x doses, duplicate enrollment. At most 25 findings; graded by recall of planted problems |
| 4c | OR-13..15 | Hard mode: every planted problem needs two records plus clinical knowledge (AE in a removed organ with a laterality decoy, AE contradicted by the same-day lab, patch reaction before the first patch, abbreviated sex-specific surgical history, history dated before birth). Kimi K3, GLM 5.3 and DeepSeek V4.1 Flash agents find 1-2 of 8-9 |

## How the tasks are built

- **Source:** the public CDISC Pilot01 study (`source/*.xpt`, from [cdisc-org/sdtm-adam-pilot-project](https://github.com/cdisc-org/sdtm-adam-pilot-project)). It is not redistributed here: download the SDTM `ae dm ds ex lb mh sv cm .xpt` files into `source/` to rebuild tasks. The generated `tasks/` and `answers/` are included, so grading and model runs work without it.
- **Results:** see [RESULTS.md](RESULTS.md).
- **Re-identification:** each task samples 8–24 subjects and gives them a new study ID, site IDs and subject IDs, and shifts every date by a random offset. The expected SDTM is therefore not on the internet.
- **Raw export:** rendered *from* the expected answer, using study-specific formats and traps:
  - date styles: `DD MON YYYY`, `DDMONYYYY`, `MM/DD/YYYY`, ISO, split day/month/year columns, and per-site locale (some sites DD/MM, others MM/DD)
  - partial dates (`UN JAN 2014`, `UNUNK2014`), which must stay partial
  - coded values (severity 1/2/3, serious 1/0, sex and race codes, MH category codes)
  - deleted records and "no adverse events" placeholder rows to drop
  - multiple saved versions of a record (keep the latest)
  - screen failures with no dosing, and ages within days of a birthday on the consent date
- **Derivations the agent must get right:** USUBJID, sequence numbering, study day with no day 0, RFSTDTC/RFENDTC from the dosing log, and age at consent.

## Files

| Path | Contents |
|---|---|
| `tasks/<id>/spec.md`, `tasks/<id>/input/` | What the agent sees |
| `answers/<id>/expected.csv`, `meta.json` | Hidden answer; never copy into a sandbox |
| `sdtmenv/generate.py` | Builds tasks and answers (seeded, reproducible) |
| `sdtmenv/check.py` | Grader: reward = cell accuracy over graded columns; pass = exact match |
| `sdtmenv/solve.py` | Independent reference solver that reads only spec + inputs |
| `sdtmenv/attack.py` | Reward-hacking attempts against the grader |
| `sdtmenv/run_models.py` | Model harness: the model writes a script, it runs in a scratch copy, then gets graded |
| `sdtmenv/summary.py` | Re-grades all saved runs |

## Commands

```
python -m sdtmenv.generate      # rebuild tier 1 tasks + answers
python -m sdtmenv.generate2     # rebuild tier 2
python -m sdtmenv.generate3     # rebuild tier 3 (data review)
python -m sdtmenv.generate4     # rebuild tier 4 (open review)
python -m sdtmenv.generate4 --v3   # rebuild tier 4c (hard mode, OR-13..15)
python -m sdtmenv.solve         # reference solver: must pass 51/51
python -m sdtmenv.attack        # every attack must stay far below 1.0 and never pass
python -m sdtmenv.run_models kimi glm --tasks AE-01
python -m sdtmenv.summary
```

## Grader hardening found by attacking it

1. An output with a header and no rows crashed the grader (empty frame). Fixed.
2. Copying only identifiers and constants earned 0.33 partial reward. Constants and keys are now required for a pass but earn no reward.
3. Tier 2 straight-copy columns (AE terms in ADAE; original result, unit and range in LB) are required for a pass but earn no reward (`meta.json` `free`).
4. Mostly-blank flag columns (LBBLFL, AOCCFL, ASTDTF...) paid out for leaving everything blank. A graded cell now counts only when the expected or submitted value is non-blank.
5. Rare rule branches were checked for coverage. The ADAE end-date cap fired 0 times and almost every AE was treatment-emergent, so the generator now injects window-boundary days (last day in, first day out), day-before-treatment starts and cap cases.

6. Data review: Pilot01 itself repeats AE records (same PT and start date) and numbers unscheduled visits out of date order, which swamped two checks with 10-33 natural hits. The source is de-duplicated before planting, and the visit-date check covers scheduled visits only.

7. Open review: the first protocol synopsis said the high-dose arm takes 81 mg, but the study titrates (54 mg to Week 2, 81 mg to Week 24, then 54 mg), so a reviewer following the synopsis flagged 18 correct records. The synopsis now states the titration. Glucose 48 mmol/L and cholesterol 31 mmol/L were dropped as "impossible" values because both occur in real patients.

After these fixes no attack passes any of the 42 tasks. Identifier-only and copy-only outputs earn at most 0.07. On data review, an empty report scores 0, flagging everything 0.009, and citing the wrong records 0.044. On open review, tier 3's rule-based checks find 2% of planted problems, citing every subject 16%, the 25 most extreme labs 23%.

## Known limits

- The answers sit on the same disk as the harness. In delivery, the grader must run outside the agent's container (as in verifiers/OpenEnv), or an agent can search the filesystem for `expected.csv`. `run_models.py` flags scripts that mention `answers` or `expected.csv`, but that's only a tripwire.
- MedDRA coding is given (`CODED_PT`, `CODED_SOC`); coding from verbatim is a possible harder tier.
- Pilot01 is a single Alzheimer's study, so term variety is limited; more public studies would widen it.
