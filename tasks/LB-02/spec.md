# Task LB-02: map central-lab results to SDTM LB with standard units

Study `ALX-178`. Map `input/raw_lab.csv` to `output/lb.csv`. `input/dm.csv` gives each subject's `RFSTDTC` (first dose date).

## Output columns
`STUDYID`, `DOMAIN`, `USUBJID`, `LBSPID`, `LBTESTCD`, `LBTEST`, `LBORRES`, `LBORRESU`, `LBORNRLO`, `LBORNRHI`, `LBSTRESC`, `LBSTRESN`, `LBSTRESU`, `LBSTNRLO`, `LBSTNRHI`, `LBNRIND`, `LBBLFL`, `VISIT`, `LBDTC`, `LBDY`

## Tests and conversion to standard units

| Raw `TEST` | `LBTESTCD` | `LBTEST` | Standard unit `LBSTRESU` | Factor from the conventional unit | Decimals |
|---|---|---|---|---|---|
| Glucose | `GLUC` | Glucose | mmol/L | 0.0555 | 2 |
| Creatinine | `CREAT` | Creatinine | umol/L | 88.42 | 1 |
| Bilirubin, total | `BILI` | Bilirubin | umol/L | 17.1 | 1 |
| Hemoglobin | `HGB` | Hemoglobin | mmol/L | 0.6206 | 2 |
| Albumin | `ALB` | Albumin | g/L | 10 | 0 |
| ALT (SGPT) | `ALT` | Alanine Aminotransferase | U/L | 1 | 0 |
| Cholesterol, total | `CHOL` | Cholesterol | mmol/L | 0.02586 | 2 |
| Potassium | `K` | Potassium | mmol/L | 1 | 1 |
| Sodium | `SODIUM` | Sodium | mmol/L | 1 | 0 |
| Calcium | `CA` | Calcium | mmol/L | 0.2495 | 2 |

## Rules
- `STUDYID` = `ALX-178`, `DOMAIN` = `LB`. Raw `SUBJECT` is `<site>-<subject>`; `USUBJID` = `STUDYID-SITE-SUBJECT`. `LBSPID` = raw `RECID`.
- `LBORRES`, `LBORRESU`, `LBORNRLO`, `LBORNRHI` = raw `RESULT`, `UNIT`, `RANGE_LOW`, `RANGE_HIGH` unchanged.
- **Conversion:** if the raw `UNIT` already equals the standard unit, the factor is 1. Otherwise, multiply by the factor in the table. Apply the same conversion to the result and to both range limits.
- **Rounding:** round the converted values to the table's decimals, half away from zero (2.345 → 2.35).
- `LBSTRESN` is the rounded number. `LBSTRESC` is the same number as text with exactly that many decimals, keeping trailing zeros (`5.50`, not `5.5`).
- `LBSTNRLO`, `LBSTNRHI` are the rounded converted limits. `LBSTRESU` is the standard unit.
- **Results like `<0.2`:** `LBSTRESC` = the raw text unchanged, and `LBSTRESN` and `LBNRIND` are blank. The limits are still converted.
- `LBNRIND`: `LOW` if `LBSTRESN` < `LBSTNRLO`, `HIGH` if `LBSTRESN` > `LBSTNRHI`, otherwise `NORMAL`. Compare the rounded values. Blank when the result or either limit is missing.
- `LBDTC` = `COLLECTED` as `YYYY-MM-DDTHH:MM`. Raw format is `DDMONYYYY HH:MM`. `VISIT` = raw `VISIT`.
- `LBDY` = study day of the `LBDTC` date relative to `RFSTDTC` (no day 0).
- **Baseline `LBBLFL` = `Y`:** for each subject and test, the latest record (by `LBDTC`, time included) with a non-blank `LBSTRESN` whose date is on or before `RFSTDTC`. Leave it blank on all other records.
- Sort by `USUBJID`, `LBTESTCD`, `LBDTC`, `LBSPID`.
- Write the output as CSV with a header row and exactly the columns listed, in that order. Leave unknown values empty.
