# Task AEX-02: map raw adverse events to SDTM AE

Study `CTN-656`. Map `input/raw_ae.csv` to an SDTM AE dataset at `output/ae.csv`. `input/dm.csv` is the study's finished DM domain.

## Output columns
`STUDYID`, `DOMAIN`, `USUBJID`, `AESEQ`, `AESPID`, `AETERM`, `AEDECOD`, `AEBODSYS`, `AESEV`, `AESER`, `AEREL`, `AEOUT`, `AESTDTC`, `AEENDTC`, `AESTDY`, `AEENDY`

## Rules
- `STUDYID` = `CTN-656`, `DOMAIN` = `AE`.
- Raw `SUBJECT` is `<site>-<subject>`. `USUBJID` = `STUDYID-SITE-SUBJECT`, e.g. `CTN-656-123-4567`. It must match `dm.csv`.
- `AESPID` = raw `RECID`. `AETERM` = raw `AE_VERBATIM` in upper case. `AEDECOD` = `CODED_PT`, `AEBODSYS` = `CODED_SOC`.
- `SEVERITY` codes: `1` = MILD, `2` = MODERATE, `3` = SEVERE.
- `SERIOUS` codes: `1` = Y, `0` = N.
- `RELATIONSHIP` maps to `AEREL`: `Not related` = NONE; `Unlikely related` = REMOTE; `Possibly related` = POSSIBLE; `Probably related` = PROBABLE.
- `AEOUT` = raw `OUTCOME` in upper case.
- `AESTDTC` from the start date, `AEENDTC` from the end date. `AEONGO` = `Y` means the event is ongoing and has no end date.
- Raw dates are numeric, `DD/MM/YYYY` or `MM/DD/YYYY`. Each site uses one format for all its records, but the export does not say which. Work it out from the data: every site has at least one date that only one format can explain.
- `AESEQ`: number each subject's records 1, 2, 3... after sorting by `AESTDTC` (as text), then `AETERM`, then `AESPID`.
- Drop rows where `RECORD_STATUS` is `DELETED`.
- Drop placeholder rows with `AEYN` = `No` (the site ticked "no adverse events" on that page); they have no verbatim term.
- All `--DTC` variables are ISO 8601 dates `YYYY-MM-DD`. A partial date keeps only the known parts: `YYYY-MM` or `YYYY`. Never impute a missing day or month.
- Study day (`--DY`, `--STDY`, `--ENDY`) is relative to the subject's `RFSTDTC` from DM: `date - RFSTDTC + 1` when the date is on or after `RFSTDTC`, otherwise `date - RFSTDTC` (there is no day 0). Leave it blank when either date is partial or missing.
- Write the output as CSV with a header row and exactly the columns listed, in that order. Leave unknown values empty (not `NA`, `NULL` or `.`).
