import pandas as pd
import os
from datetime import datetime

MONTHS = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

def parse_raw_date(s):
    if pd.isna(s) or str(s).strip() == '':
        return None
    parts = str(s).strip().split()
    if len(parts) != 3:
        return None
    d, m, y = parts
    day = None if d.upper() == 'UN' else int(d)
    month = None if m.upper() == 'UNK' else MONTHS[m.upper()]
    year = int(y)
    return (year, month, day)

def to_iso(parsed):
    if parsed is None:
        return ''
    y, m, d = parsed
    if m is None:
        return f"{y:04d}"
    if d is None:
        return f"{y:04d}-{m:02d}"
    return f"{y:04d}-{m:02d}-{d:02d}"

def to_date(parsed):
    if parsed is None:
        return None
    y, m, d = parsed
    if m is None or d is None:
        return None
    return datetime(y, m, d)

def completed_years(birth, ref):
    if birth is None or ref is None:
        return ''
    y = ref.year - birth.year
    if (ref.month, ref.day) < (birth.month, birth.day):
        y -= 1
    return y

# Read inputs
demog = pd.read_csv('input/raw_demog.csv', dtype=str)
consent = pd.read_csv('input/raw_consent.csv', dtype=str)
rand = pd.read_csv('input/raw_rand.csv', dtype=str)
dosing = pd.read_csv('input/raw_dosing.csv', dtype=str)
sites = pd.read_csv('input/sites.csv', dtype=str)

site_country = dict(zip(sites['SITE'], sites['COUNTRY']))
consent_map = dict(zip(consent['SUBJECT'], consent['ICDAT']))
rand_map = dict(zip(rand['SUBJECT'], rand['TRT_GROUP']))

ARM_MAP = {
    'A': ('PBO', 'Placebo'),
    'B': ('XANLO', 'Xanomeline Low Dose'),
    'C': ('XANHI', 'Xanomeline High Dose'),
}

# Dosing aggregation
dose_start_map = {}
dose_end_map = {}
for _, row in dosing.iterrows():
    subj = row['SUBJECT']
    ds = parse_raw_date(row['DOSE_START'])
    de = parse_raw_date(row['DOSE_END'])
    if ds is not None:
        if subj not in dose_start_map or ds < dose_start_map[subj]:
            dose_start_map[subj] = ds
    for d in (ds, de):
        if d is not None:
            if subj not in dose_end_map or d > dose_end_map[subj]:
                dose_end_map[subj] = d

rows = []
for _, r in demog.iterrows():
    subject = r['SUBJECT']
    site, subj = subject.split('-', 1)
    usubjid = f"KVT-998-{site}-{subj}"

    brth = parse_raw_date(r['BRTHDAT'])
    ic = parse_raw_date(consent_map.get(subject))

    age = completed_years(to_date(brth), to_date(ic))

    sex_raw = r['SEX']
    sex = 'F' if sex_raw == 'Female' else ('M' if sex_raw == 'Male' else '')

    race = str(r['RACE']).upper() if pd.notna(r['RACE']) else ''

    hisp = r['HISPANIC']
    if hisp == 'Yes':
        ethnic = 'HISPANIC OR LATINO'
    elif hisp == 'No':
        ethnic = 'NOT HISPANIC OR LATINO'
    else:
        ethnic = ''

    trt = rand_map.get(subject)
    if trt in ARM_MAP:
        armcd, arm = ARM_MAP[trt]
    else:
        armcd, arm = 'SCRNFAIL', 'Screen Failure'

    rfstdtc = to_iso(dose_start_map.get(subject))
    rfendtc = to_iso(dose_end_map.get(subject))

    rows.append({
        'STUDYID': 'KVT-998',
        'DOMAIN': 'DM',
        'USUBJID': usubjid,
        'SUBJID': subj,
        'SITEID': site,
        'BRTHDTC': to_iso(brth),
        'AGE': age,
        'AGEU': 'YEARS',
        'SEX': sex,
        'RACE': race,
        'ETHNIC': ethnic,
        'ARMCD': armcd,
        'ARM': arm,
        'RFICDTC': to_iso(ic),
        'RFSTDTC': rfstdtc,
        'RFENDTC': rfendtc,
        'COUNTRY': site_country.get(site, ''),
    })

out = pd.DataFrame(rows, columns=[
    'STUDYID', 'DOMAIN', 'USUBJID', 'SUBJID', 'SITEID', 'BRTHDTC', 'AGE', 'AGEU',
    'SEX', 'RACE', 'ETHNIC', 'ARMCD', 'ARM', 'RFICDTC', 'RFSTDTC', 'RFENDTC', 'COUNTRY'
])
out = out.sort_values('USUBJID').reset_index(drop=True)

os.makedirs('output', exist_ok=True)
out.to_csv('output/dm.csv', index=False)
