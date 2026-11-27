# Task OR-08: clinical data review before database lock

Study `CTN-316`: a randomized, double-blind study of a xanomeline transdermal patch in mild-to-moderate Alzheimer's disease.

## Protocol synopsis
- Arms, one patch daily for 26 weeks:
  - `Placebo`: 0 mg
  - `Xanomeline Low Dose`: 54 mg throughout
  - `Xanomeline High Dose`: 54 mg until the Week 2 visit, 81 mg from Week 2 to Week 24, then 54 mg from Week 24 to the end of treatment
- Key inclusion criterion: men and women aged 50 or older at entry.
- Prohibited from first dose to end of treatment: cholinesterase inhibitors, and medications with strong anticholinergic activity.
- Data cutoff for this delivery: **2014-08-10**. Nothing in the database should be dated after it.

## Data
`input/` holds the SDTM package: `dm.csv`, `ae.csv`, `ex.csv`, `ds.csv`, `lb.csv`, `cm.csv` (concomitant medications as the site wrote them in `CMTRT`; `CMDECOD` is the coded drug name or `UNCODED`), `mh.csv` (medical and surgical history). Lab results are in SI units (`LBSTRESU`).

## Your job
Review the package the way an experienced clinical data reviewer would, and find the problems you would raise as queries to the sites: values that are impossible or implausible, or inconsistent with each other, with the protocol, or with medicine. Ordinary abnormal lab results and ordinary adverse events are not problems.

Write `output/findings.csv` with columns `USUBJID`, `DOMAIN`, `SEQ`, `ISSUE`:
- one row per problem, most important first, **at most 25 rows** (rows after the 25th are ignored)
- `DOMAIN` and `SEQ` identify the specific record the problem is on (`AESEQ`, `EXSEQ`, `LBSEQ`, `DSSEQ`, `CMSEQ` or `MHSEQ` as an integer)
- for a problem with the subject itself, use `DOMAIN` = `DM` and leave `SEQ` blank
- `ISSUE` is a one-line explanation
