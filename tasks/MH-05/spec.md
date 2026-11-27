# Task MH-05: map raw medical history to SDTM MH

Study `ALX-345`. Map `input/raw_mh.csv` to an SDTM MH dataset at `output/mh.csv`. `input/dm.csv` is the study's finished DM domain.

## Output columns
`STUDYID`, `DOMAIN`, `USUBJID`, `MHSEQ`, `MHSPID`, `MHTERM`, `MHDECOD`, `MHCAT`, `MHBODSYS`, `MHDTC`, `MHSTDTC`, `MHDY`

## Rules
- `STUDYID` = `ALX-345`, `DOMAIN` = `MH`.
- Raw `SUBJECT` is `<site>-<subject>`. `USUBJID` = `STUDYID-SITE-SUBJECT`. It must match `dm.csv`.
- `MHSPID` = raw `RECID`. `MHTERM` = raw `MH_VERBATIM`. `MHDECOD` = `CODED_PT`, `MHBODSYS` = `CODED_SOC`.
- `CATEGORY` codes: `PD` = PRIMARY DIAGNOSIS; `SPC` = SIGNIFICANT PRE-EXISTING CONDITION; `HD` = HISTORICAL DIAGNOSIS.
- `MHSTDTC` = the condition's start date. Many are partial.
- Raw start dates are split into three columns ending `_DD`, `_MM`, `_YYYY` (numbers, no zero padding). A blank day or month means that part is unknown.
- `MHDTC` = `VISIT_DATE`, the date the history was collected. Raw visit dates are `DD MON YYYY` (e.g. `07 MAR 2014`). Unknown parts are `UN` (day) and `UNK` (month), e.g. `UN MAR 2014`, `UN UNK 2014`.
- `MHDY` = study day of `MHDTC`.
- `MHSEQ`: number each subject's records 1, 2, 3... after sorting by `MHCAT`, then `MHSTDTC` (as text), then `MHTERM`, then `MHSPID`.
- Drop rows where `RECORD_STATUS` is `DELETED`.
- All `--DTC` variables are ISO 8601 dates `YYYY-MM-DD`. A partial date keeps only the known parts: `YYYY-MM` or `YYYY`. Never impute a missing day or month.
- Study day (`--DY`, `--STDY`, `--ENDY`) is relative to the subject's `RFSTDTC` from DM: `date - RFSTDTC + 1` when the date is on or after `RFSTDTC`, otherwise `date - RFSTDTC` (there is no day 0). Leave it blank when either date is partial or missing.
- Write the output as CSV with a header row and exactly the columns listed, in that order. Leave unknown values empty (not `NA`, `NULL` or `.`).
