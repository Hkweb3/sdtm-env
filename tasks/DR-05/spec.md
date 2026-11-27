# Task DR-05: data review of an SDTM study package

Study `TQR-311`. Review the package in `input/` (`dm.csv`, `ae.csv`, `ex.csv`, `ds.csv`, `lb.csv`) the way a clinical data manager would before database lock. List every issue found by the checks below in `output/findings.csv`.

## Output
CSV with columns `CHECK`, `USUBJID`, `DOMAIN`, `SEQ`: one row per issue. `DOMAIN` and `SEQ` identify the record the issue is raised on (`AESEQ`, `EXSEQ` or `LBSEQ` as plain integers). A subject-level issue uses `DOMAIN` = `DM` and a blank `SEQ`. Do not list the same issue twice.

## Checks
- `AE_DATE_ORDER`: an adverse event that ends before it starts. Only compare complete dates. Raise it on the AE.
- `AE_DUPLICATE`: the same event entered more than once for a subject, meaning the same `AEDECOD` with the same `AESTDTC` (non-blank). Raise it on every copy except the one with the lowest `AESEQ`.
- `SAE_CRITERIA`: the serious flag and the seriousness criteria disagree. Either an AE marked serious with no seriousness criterion recorded as `Y`, or an AE not marked serious with any criterion recorded as `Y`. Raise it on the AE.
- `DEATH_CONSISTENCY`, any of:
  - an AE with a fatal outcome for a subject with no death date in DM (raise on the AE)
  - an AE with a complete start date after the subject's death date (raise on the AE)
  - a subject with a death date but no AE with a fatal outcome (raise on the subject)
- `DOSE_AFTER_DISC`: an exposure record that starts after the date the subject discontinued the study early. Early discontinuation is a disposition event other than completion or screen failure. Raise it on the EX record.
- `LAB_UNIT`: a numeric lab result that looks entered in the wrong unit, meaning it is at least 8 times higher, or at most 1/8, of the median of the same subject's *other* results for that test. Needs at least two other results. Raise it on the LB record.
- `LAB_VISIT_DATE`: at scheduled visits only (ignore visits named `UNSCHEDULED ...`), a lab result dated earlier than the latest date of the same subject's results for the same test at earlier scheduled visits (lower `VISITNUM`). Compare dates only, ignoring time. Raise it on the out-of-order record.

Some checks may find nothing in this package. Issues already present in the source data count the same as any others.
