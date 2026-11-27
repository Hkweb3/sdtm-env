import os
import pandas as pd
from datetime import datetime

STUDYID = "TQR-883"
DOMAIN = "MH"

dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)
raw = pd.read_csv("input/raw_mh.csv", dtype=str, keep_default_na=False)

# Drop deleted records
raw = raw[raw["RECORD_STATUS"].str.strip().str.upper() != "DELETED"].copy()

# Create USUBJID and filter to DM subjects
raw["SUBJECT"] = raw["SUBJECT"].str.strip()
raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

dm["USUBJID"] = dm["USUBJID"].str.strip()
raw = raw[raw["USUBJID"].isin(dm["USUBJID"])].copy()

# Merge RFSTDTC for study day calculation
dm_ref = dm[["USUBJID", "RFSTDTC"]].drop_duplicates(subset="USUBJID").copy()
dm_ref["RFSTDTC"] = dm_ref["RFSTDTC"].str.strip()
raw = raw.merge(dm_ref, on="USUBJID", how="left")

# Map SDTM variables
raw["STUDYID"] = STUDYID
raw["DOMAIN"] = DOMAIN
raw["MHSPID"] = raw["RECID"]
raw["MHTERM"] = raw["MH_VERBATIM"]
raw["MHDECOD"] = raw["CODED_PT"]
raw["MHCAT"] = raw["CATEGORY"].str.strip().str.upper()
raw["MHBODSYS"] = raw["CODED_SOC"]
raw["MHDTC"] = raw["VISIT_DATE"].str.strip()
raw["MHSTDTC"] = raw["MHSTDAT"].str.strip()

# Ensure missing strings are empty
for col in ["MHSPID", "MHTERM", "MHDECOD", "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "RFSTDTC"]:
    raw[col] = raw[col].fillna("")

# Sort within subjects and assign MHSEQ
raw = raw.sort_values(
    ["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
    ascending=True,
    kind="mergesort"
).reset_index(drop=True)

raw["MHSEQ"] = raw.groupby("USUBJID", sort=False).cumcount() + 1

# Calculate MHDY
def calc_study_day(mhdtc, rfstdtc):
    if not mhdtc or not rfstdtc:
        return ""
    try:
        d = datetime.strptime(mhdtc, "%Y-%m-%d").date()
        r = datetime.strptime(rfstdtc, "%Y-%m-%d").date()
    except ValueError:
        return ""
    delta = (d - r).days
    if delta >= 0:
        return str(delta + 1)
    return str(delta)

raw["MHDY"] = raw.apply(lambda row: calc_study_day(row["MHDTC"], row["RFSTDTC"]), axis=1)

# Write output
os.makedirs("output", exist_ok=True)
output_cols = [
    "STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM",
    "MHDECOD", "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY"
]
raw[output_cols].to_csv("output/mh.csv", index=False, na_rep="")
