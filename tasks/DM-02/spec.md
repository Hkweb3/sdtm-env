# Task DM-02: build SDTM DM from raw demographics, consent, randomization and dosing

Study `PLX-658`. Build the SDTM DM dataset at `output/dm.csv`, one row per subject in `input/raw_demog.csv`.

## Inputs
- `raw_demog.csv`: birth date, sex, race, ethnicity.
- `raw_consent.csv`: informed consent date.
- `raw_rand.csv`: randomized treatment group. Subjects missing here are screen failures.
- `raw_dosing.csv`: one row per dosing interval.
- `sites.csv`: country of each site.

## Output columns
`STUDYID`, `DOMAIN`, `USUBJID`, `SUBJID`, `SITEID`, `BRTHDTC`, `AGE`, `AGEU`, `SEX`, `RACE`, `ETHNIC`, `ARMCD`, `ARM`, `RFICDTC`, `RFSTDTC`, `RFENDTC`, `COUNTRY`

## Rules
- `STUDYID` = `PLX-658`, `DOMAIN` = `DM`. Raw `SUBJECT` is `<site>-<subject>`: `SITEID` = site, `SUBJID` = subject, `USUBJID` = `STUDYID-SITEID-SUBJID`.
- Raw dates are `DDMONYYYY` (e.g. `07MAR2014`). Unknown parts are `UN` (day) and `UNK` (month), e.g. `UNMAR2014`, `UNUNK2014`.
- `BRTHDTC` = birth date. `RFICDTC` = consent date.
- `AGE` = completed years from `BRTHDTC` to `RFICDTC` (the age on the consent date; a birthday on the consent date counts). `AGEU` = `YEARS`.
- `SEX` codes: `1` = M, `2` = F.
- `RACE` codes: `1` = WHITE; `2` = BLACK OR AFRICAN AMERICAN; `3` = ASIAN; `4` = AMERICAN INDIAN OR ALASKA NATIVE; `5` = NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER.
- `ETHNIC`: `HISPANIC` = `Yes` gives `HISPANIC OR LATINO`, `No` gives `NOT HISPANIC OR LATINO`.
- `TRT_GROUP` gives `ARMCD` / `ARM`: `A` = `PBO` / Placebo; `B` = `XANLO` / Xanomeline Low Dose; `C` = `XANHI` / Xanomeline High Dose. Screen failures get `ARMCD` = `SCRNFAIL`, `ARM` = `Screen Failure`.
- `RFSTDTC` = the earliest `DOSE_START`. `RFENDTC` = the latest of all `DOSE_START` and `DOSE_END` dates. Both are blank for subjects with no dosing.
- `COUNTRY` comes from `sites.csv`.
- Sort output rows by `USUBJID`.
- All `--DTC` variables are ISO 8601 dates `YYYY-MM-DD`. A partial date keeps only the known parts: `YYYY-MM` or `YYYY`. Never impute a missing day or month.
- Study day (`--DY`, `--STDY`, `--ENDY`) is relative to the subject's `RFSTDTC` from DM: `date - RFSTDTC + 1` when the date is on or after `RFSTDTC`, otherwise `date - RFSTDTC` (there is no day 0). Leave it blank when either date is partial or missing.
- Write the output as CSV with a header row and exactly the columns listed, in that order. Leave unknown values empty (not `NA`, `NULL` or `.`).
