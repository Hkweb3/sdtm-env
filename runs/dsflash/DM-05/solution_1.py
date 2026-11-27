import pandas as pd
import numpy as np
import os
from datetime import date

os.makedirs("output", exist_ok=True)

STUDYID = "MRN-319"

demog = pd.read_csv("input/raw_demog.csv", dtype=str)
consent = pd.read_csv("input/raw_consent.csv", dtype=str)
rand = pd.read_csv("input/raw_rand.csv", dtype=str)
dosing = pd.read_csv("input/raw_dosing.csv", dtype=str)
sites = pd.read_csv("input/sites.csv", dtype=str)

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

def parse_raw_date(s):
    """Parse DDMONYYYY with UN/UNK parts. Returns (year, month, day) with None for unknown."""
    if s is None or (isinstance(s, float) and np.isnan(s)) or s == "":
        return (None, None, None)
    s = str(s).strip()
    if s == "":
        return (None, None, None)
    # day = first 2 chars, month = next 3, year = rest
    day_s = s[0:2]
    mon_s = s[2:5]
    year_s = s[5:]
    day = None if day_s == "UN" else int(day_s)
    month = None if mon_s == "UNK" else MONTHS[mon_s]
    year = None if year_s == "UNK" else int(year_s)
    return (year, month, day)

def to_iso(parts):
    year, month, day = parts
    if year is None:
        return ""
    if month is None:
        return f"{year:04d}"
    if day is None:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}-{month:02d}-{day:02d}"

def to_date(parts):
    year, month, day = parts
    if year is None or month is None or day is None:
        return None
    return date(year, month, day)

# Build subject-level data
rows = []
for _, d in demog.iterrows():
    subj = d["SUBJECT"]
    site, subjid = subj.split("-", 1)
    usubjid = f"{STUDYID}-{site}-{subjid}"

    brth_parts = parse_raw_date(d["BRTHDAT"])
    brthdtc = to_iso(brth_parts)

    # consent
    c_row = consent[consent["SUBJECT"] == subj]
    if len(c_row) > 0:
        ic_parts = parse_raw_date(c_row.iloc[0]["ICDAT"])
    else:
        ic_parts = (None, None, None)
    rficdtc = to_iso(ic_parts)

    # age
    brth_d = to_date(brth_parts)
    ic_d = to_date(ic_parts)
    if brth_d is not None and ic_d is not None:
        age = ic_d.year - brth_d.year
        if (ic_d.month, ic_d.day) < (brth_d.month, brth_d.day):
            age -= 1
        age = str(age)
    else:
        age = ""

    # sex
    sex = {"1": "M", "2": "F"}.get(d["SEX"], "")

    # race
    race = {
        "1": "WHITE",
        "2": "BLACK OR AFRICAN AMERICAN",
        "3": "ASIAN",
        "4": "AMERICAN INDIAN OR ALASKA NATIVE",
        "5": "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
    }.get(d["RACE"], "")

    # ethnic
    hisp = d["HISPANIC"]
    if hisp == "Yes":
        ethnic = "HISPANIC OR LATINO"
    elif hisp == "No":
        ethnic = "NOT HISPANIC OR LATINO"
    else:
        ethnic = ""

    # randomization
    r_row = rand[rand["SUBJECT"] == subj]
    if len(r_row) > 0:
        tg = r_row.iloc[0]["TRT_GROUP"]
        arm_map = {
            "A": ("PBO", "Placebo"),
            "B": ("XANLO", "Xanomeline Low Dose"),
            "C": ("XANHI", "Xanomeline High Dose"),
        }
        armcd, arm = arm_map.get(tg, ("", ""))
    else:
        armcd, arm = "SCRNFAIL", "Screen Failure"

    # dosing
    d_rows = dosing[dosing["SUBJECT"] == subj]
    starts = []
    ends = []
    for _, dr in d_rows.iterrows():
        sp = parse_raw_date(dr["DOSE_START"])
        ep = parse_raw_date(dr["DOSE_END"])
        sd = to_date(sp)
        ed = to_date(ep)
        if sd is not None:
            starts.append(sd)
        if ed is not None:
            ends.append(ed)

    if starts:
        rfstdtc = min(starts).isoformat()
    else:
        rfstdtc = ""

    all_dates = starts + ends
    if all_dates:
        rfendtc = max(all_dates).isoformat()
    else:
        rfendtc = ""

    # country
    s_row = sites[sites["SITE"] == site]
    country = s_row.iloc[0]["COUNTRY"] if len(s_row) > 0 else ""

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
    "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "BRTHDTC", "AGE",
    "AGEU", "SEX", "RACE", "ETHNIC", "ARMCD", "ARM", "RFICDTC", "RFSTDTC",
    "RFENDTC", "COUNTRY",
])
out = out.sort_values("USUBJID").reset_index(drop=True)
out.to_csv("output/dm.csv", index=False)
