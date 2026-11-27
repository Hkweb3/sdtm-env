import pandas as pd
import numpy as np
from datetime import datetime

STUDYID = "PLX-295"

def parse_date(s):
    if pd.isna(s) or str(s).strip() == "":
        return pd.NaT
    return pd.to_datetime(str(s).strip(), format="%m/%d/%Y", errors="coerce")

def to_iso(dt):
    if pd.isna(dt):
        return ""
    return dt.strftime("%Y-%m-%d")

def completed_years(birth, ref):
    if pd.isna(birth) or pd.isna(ref):
        return ""
    years = ref.year - birth.year
    if (ref.month, ref.day) < (birth.month, birth.day):
        years -= 1
    return years

# Read inputs
demog = pd.read_csv("input/raw_demog.csv", dtype=str)
consent = pd.read_csv("input/raw_consent.csv", dtype=str)
rand = pd.read_csv("input/raw_rand.csv", dtype=str)
dosing = pd.read_csv("input/raw_dosing.csv", dtype=str)
sites = pd.read_csv("input/sites.csv", dtype=str)

# Parse subject
def split_subject(s):
    parts = str(s).split("-", 1)
    return parts[0], parts[1]

demog[["SITEID", "SUBJID"]] = demog["SUBJECT"].apply(lambda s: pd.Series(split_subject(s)))
demog["USUBJID"] = STUDYID + "-" + demog["SITEID"] + "-" + demog["SUBJID"]

# Dates
demog["BRTHDTC_dt"] = demog["BRTHDAT"].apply(parse_date)

consent["ICDAT_dt"] = consent["ICDAT"].apply(parse_date)
consent_map = dict(zip(consent["SUBJECT"], consent["ICDAT_dt"]))

# Dosing aggregation
dosing["DOSE_START_dt"] = dosing["DOSE_START"].apply(parse_date)
dosing["DOSE_END_dt"] = dosing["DOSE_END"].apply(parse_date)

dose_agg = {}
for subj, grp in dosing.groupby("SUBJECT"):
    starts = grp["DOSE_START_dt"].dropna()
    ends = grp["DOSE_END_dt"].dropna()
    rfstdtc = starts.min() if len(starts) > 0 else pd.NaT
    all_dates = pd.concat([starts, ends])
    rfendtc = all_dates.max() if len(all_dates) > 0 else pd.NaT
    dose_agg[subj] = (rfstdtc, rfendtc)

# Rand map
rand_map = dict(zip(rand["SUBJECT"], rand["TRT_GROUP"]))

# Site country map
site_country = dict(zip(sites["SITE"], sites["COUNTRY"]))

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}

rows = []
for _, r in demog.iterrows():
    subj = r["SUBJECT"]
    site = r["SITEID"]
    subjid = r["SUBJID"]
    usubjid = r["USUBJID"]
    brthdtc_dt = r["BRTHDTC_dt"]
    brthdtc = to_iso(brthdtc_dt)

    icdt = consent_map.get(subj, pd.NaT)
    rficdtc = to_iso(icdt)

    age = completed_years(brthdtc_dt, icdt)

    sex_raw = str(r["SEX"]).strip() if not pd.isna(r["SEX"]) else ""
    sex = {"Female": "F", "Male": "M"}.get(sex_raw, "")

    race = str(r["RACE"]).strip().upper() if not pd.isna(r["RACE"]) else ""

    hisp = str(r["HISPANIC"]).strip() if not pd.isna(r["HISPANIC"]) else ""
    if hisp == "Yes":
        ethnic = "HISPANIC OR LATINO"
    elif hisp == "No":
        ethnic = "NOT HISPANIC OR LATINO"
    else:
        ethnic = ""

    trt = rand_map.get(subj)
    if trt in ARM_MAP:
        armcd, arm = ARM_MAP[trt]
    else:
        armcd, arm = "SCRNFAIL", "Screen Failure"

    rfstdtc_dt, rfendtc_dt = dose_agg.get(subj, (pd.NaT, pd.NaT))
    rfstdtc = to_iso(rfstdtc_dt)
    rfendtc = to_iso(rfendtc_dt)

    country = site_country.get(site, "")

    rows.append({
        "STUDYID": STUDYID,
        "DOMAIN": "DM",
        "USUBJID": usubjid,
        "SUBJID": subjid,
        "SITEID": site,
        "BRTHDTC": brthdtc,
        "AGE": age,
        "AGEU": "YEARS",
        "SEX": sex,
        "RACE": race,
        "ETHNIC": ethnic,
        "ARMCD": armcd,
        "ARM": arm,
        "RFICDTC": rficdtc,
        "RFSTDTC": rfstdtc,
        "RFENDTC": rfendtc,
        "COUNTRY": country,
    })

out = pd.DataFrame(rows, columns=[
    "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "BRTHDTC", "AGE", "AGEU",
    "SEX", "RACE", "ETHNIC", "ARMCD", "ARM", "RFICDTC", "RFSTDTC", "RFENDTC", "COUNTRY"
])
out = out.sort_values("USUBJID").reset_index(drop=True)

import os
os.makedirs("output", exist_ok=True)
out.to_csv("output/dm.csv", index=False)
