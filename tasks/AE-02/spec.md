# Task AE-02: map raw adverse events to SDTM AE

Study `ALX-878`. Map `input/raw_ae.csv` to an SDTM AE dataset at `output/ae.csv`. `input/dm.csv` is the study's finished DM domain.

## Output columns
`STUDYID`, `DOMAIN`, `USUBJID`, `AESEQ`, `AESPID`, `AETERM`, `AEDECOD`, `AEBODSYS`, `AESEV`, `AESER`, `AEREL`, `AEOUT`, `AESTDTC`, `AEENDTC`, `AESTDY`, `AEENDY`

## Rules
- `STUDYID` = `ALX-878`, `DOMAIN` = `AE`.
- Raw `SUBJECT` is `<site>-<subject>`. `USUBJID` = `STUDYID-SITE-SUBJECT`, e.g. `ALX-878-123-4567`. It must match `dm.csv`.
- `AESPID` = raw `RECID`. `AETERM` = raw `AE_VERBATIM` in upper case. `AEDECOD` = `CODED_PT`, `AEBODSYS` = `CODED_SOC`.
- `SEVERITY` is the CDISC term in title case; output it in upper case.
- `SERIOUS`: `Yes` = Y, `No` = N.
- `RELATIONSHIP` maps to `AEREL`: `Not related` = NONE; `Unlikely related` = REMOTE; `Possibly related` = POSSIBLE; `Probably related` = PROBABLE.
- `AEOUT` = raw `OUTCOME` in upper case.
- `AESTDTC` from the start date, `AEENDTC` from the end date. `AEONGO` = `Y` means the event is ongoing and has no end date.
- Raw dates are `DDMONYYYY` (e.g. `07MAR2014`). Unknown parts are `UN` (day) and `UNK` (month), e.g. `UNMAR2014`, `UNUNK2014`.
- `AESEQ`: number each subject's records 1, 2, 3... after sorting by `AESTDTC` (as text), then `AETERM`, then `AESPID`.

- All `--DTC` variables are ISO 8601 dates `YYYY-MM-DD`. A partial date keeps only the known parts: `YYYY-MM` or `YYYY`. Never impute a missing day or month.
- Study day (`--DY`, `--STDY`, `--ENDY`) is relative to the subject's `RFSTDTC` from DM: `date - RFSTDTC + 1` when the date is on or after `RFSTDTC`, otherwise `date - RFSTDTC` (there is no day 0). Leave it blank when either date is partial or missing.
- Write the output as CSV with a header row and exactly the columns listed, in that order. Leave unknown values empty (not `NA`, `NULL` or `.`).
