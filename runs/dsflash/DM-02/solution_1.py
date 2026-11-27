import pandas as pd
import os
from datetime import date

os.makedirs("output", exist_ok=True)

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
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return (None, None, None)
    s = str(s).strip()
    if s == "" or s.lower() == "nan":
        return (None, None, None)
    day_s = s[0:2]
    mon_s = s[2:5]
    year_s = s[5:9]
    day = None if day_s.upper() == "UN" else int(day_s)
    month = None if mon_s.upper() == "UNK" else MONTHS.get(mon_s.upper())
    year = None if year_s.upper() == "UNK" else int(year_s)
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


def is_complete(parts):
    return all(p is not None for p in parts)


def completed_years(birth, ref):
    """Completed years from birth to ref. Both must be complete dates."""
    by, bm, bd = birth
    ry, rm, rd = ref
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return age


SEX_MAP = {"1": "M", "2": "F"}
RACE_MAP = {
    "1": "WHITE",
    "2": "BLACK OR AFRICAN AMERICAN",
    "3": "ASIAN",
    "4": "AMERICAN INDIAN OR ALASKA NATIVE",
    "5": "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
}
ETHNIC_MAP = {"Yes": "HISPANIC OR LATINO", "No": "NOT HISPANIC OR LATINO"}
ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}

site_country = dict(zip(sites["SITE"], sites["COUNTRY"]))

consent_map = dict(zip(consent["SUBJECT"], consent["ICDAT"]))
rand_map = dict(zip(rand["SUBJECT"], rand["TRT_GROUP"]))

# Dosing aggregation per subject
dose_start_map = {}
dose_end_map = {}
for _, row in dosing.iterrows():
    subj = row["SUBJECT"]
    ds = parse_raw_date(row["DOSE_START"])
    de = parse_raw_date(row["DOSE_END"])
    if subj not in dose_start_map:
        dose_start_map[subj] = []
        dose_end_map[subj] = []
    if is_complete(ds):
        dose_start_map[subj].append(ds)
    if is_complete(de):
        dose_end_map[subj].append(de)

rows = []
for _, r in demog.iterrows():
    subject = r["SUBJECT"]
    site, subj_id = subject.split("-", 1)
    usubjid = f"PLX-658-{site}-{subj_id}"

    birth = parse_raw_date(r["BRTHDAT"])
    brthdtc = to_iso(birth)

    ic = parse_raw_date(consent_map.get(subject, ""))
    rficdtc = to_iso(ic)

    if is_complete(birth) and is_complete(ic):
        age = completed_years(birth, ic)
    else:
        age = ""

    sex = SEX_MAP.get(r["SEX"], "")
    race = RACE_MAP.get(r["RACE"], "")
    ethnic = ETHNIC_MAP.get(r["HISPANIC"], "")

    trt = rand_map.get(subject)
    if trt is None:
        armcd = "SCRNFAIL"
        arm = "Screen Failure"
    else:
        armcd, arm = ARM_MAP.get(trt, ("", ""))

    starts = dose_start_map.get(subject, [])
    ends = dose_end_map.get(subject, [])
    if starts:
        rfstdtc = to_iso(min(starts))
    else:
        rfstdtc = ""
    all_dates = starts + ends
    if all_dates:
        rfendtc = to_iso(max(all_dates))
    else:
        rfendtc = ""

    country = site_country.get(site, "")

    rows.append({
        "STUDYID": "PLX-658",
        "DOMAIN": "DM",
        "USUBJID": usubjid,
        "SUBJID": subj_id,
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
