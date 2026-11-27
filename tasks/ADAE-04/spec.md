# Task ADAE-04: derive ADaM ADAE from SDTM AE

Study `DRX-390`. Build `output/adae.csv` from `input/ae.csv` (SDTM AE) and `input/adsl.csv` (treatment start `TRTSDT` and end `TRTEDT` per subject). One output row per AE record.

## Output columns
`STUDYID`, `USUBJID`, `AESEQ`, `AETERM`, `AEDECOD`, `AEBODSYS`, `TRTSDT`, `TRTEDT`, `ASTDT`, `ASTDTF`, `AENDT`, `AENDTF`, `ASTDY`, `AENDY`, `ADURN`, `TRTEMFL`, `AOCCFL`, `AOCCPFL`

## Rules
- Carry `STUDYID`, `USUBJID`, `AESEQ`, `AETERM`, `AEDECOD`, `AEBODSYS` from AE, and `TRTSDT`, `TRTEDT` from ADSL.
- **End date `AENDT`** from `AEENDTC`, imputed:
  - complete date: use it, `AENDTF` blank
  - `YYYY-MM`: last day of that month, `AENDTF` = `D`
  - `YYYY`: December 31 of that year, `AENDTF` = `M`
  - missing (ongoing): `AENDT` and `AENDTF` blank
- **Start date `ASTDT`** from `AESTDTC`, imputed:
  - complete date: use it, `ASTDTF` blank
  - `YYYY-MM`: if it is the same year and month as `TRTSDT`, use `TRTSDT`; otherwise the first day of the month. `ASTDTF` = `D`
  - `YYYY`: if it is the same year as `TRTSDT`, use `TRTSDT`; otherwise January 1. `ASTDTF` = `M`
  - missing: use `TRTSDT`, `ASTDTF` = `Y`
  - If an *imputed* `ASTDT` falls after a *complete* (not imputed) `AENDT`, use `AENDT` instead (keep the flag).
- `ASTDY`, `AENDY`: study day relative to `TRTSDT` (date − TRTSDT + 1 on or after it, date − TRTSDT before it; no day 0). Blank if either date is blank.
- `ADURN` = `AENDT` − `ASTDT` + 1 in days, blank if either is blank.
- `TRTEMFL` = `Y` when `ASTDT` is on or after `TRTSDT` and on or before `TRTEDT` + 7 days; otherwise blank.
- Among records with `TRTEMFL` = `Y` only, sorted by `ASTDT` then `AESEQ`:
  - `AOCCFL` = `Y` on each subject's first record
  - `AOCCPFL` = `Y` on each subject's first record per `AEDECOD`
  - other records leave these blank
- All dates `YYYY-MM-DD`. Sort output by `USUBJID`, then `AESEQ`.
- Write the output as CSV with a header row and exactly the columns listed, in that order. Leave unknown values empty.
