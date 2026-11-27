import pandas as pd
import numpy as np
import os

MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05', 'JUN': '06',
    'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
}

def parse_date(s):
    if pd.isna(s):
        return None
    s = str(s).strip()
    if not s:
        return None
    parts = s.split()
    if len(parts) != 3:
        return None
    day, mon, year = parts
    y = year if year.isdigit() else None
    m = MONTHS.get(mon.upper()) if mon.upper() in MONTHS else None
    d = day if day.isdigit() else None
    if y is None:
        return None
    if m is None:
        return y
    if d is None:
        return f"{y}-{m}"
    return f"{y}-{m}-{d}"

def to_iso(s):
    return parse_date(s)

def age_years(birth_iso, ref_iso):
    if birth_iso is None or ref_iso is None:
        return None
    if len(birth_iso) < 10 or len(ref_iso) < 10:
        return None
    by, bm, bd = int(birth_iso[0:4]), int(birth_iso[5:7]), int(birth_iso[8:10])
    ry, rm, rd = int(ref_iso[0:4]), int(ref_iso[5:7]), int(ref_iso[8:10])
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return age

demog = pd.read_csv('input/raw_demog.csv', dtype=str)
consent = pd.read_csv('input/raw_consent.csv', dtype=str)
rand = pd.read_csv('input/raw_rand.csv', dtype=str)
dosing = pd.read_csv('input/raw_dosing.csv', dtype=str)
sites = pd.read_csv('input/sites.csv', dtype=str)

sites_map = dict(zip(sites['SITE'], sites['COUNTRY']))

consent_map = dict(zip(consent['SUBJECT'], consent['ICDAT']))
rand_map = dict(zip(rand['SUBJECT'], rand['TRT_GROUP']))

dosing_map = {}
for _, row in dosing.iterrows():
    subj = row['SUBJECT']
    if subj not in dosing_map:
        dosing_map[subj] = []
    dosing_map[subj].append((row['DOSE_START'], row['DOSE_END']))

ARM_MAP = {
    'A': ('PBO', 'Placebo'),
    'B': ('XANLO', 'Xanomeline Low Dose'),
    'C': ('XANHI', 'Xanomeline High Dose'),
}

RACE_MAP = {
    '1': 'WHITE',
    '2': 'BLACK OR AFRICAN AMERICAN',
    '3': 'ASIAN',
    '4': 'AMERICAN INDIAN OR ALASKA NATIVE',
    '5': 'NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER',
}

rows = []
for _, r in demog.iterrows():
    subject = r['SUBJECT']
    parts = subject.split('-')
    siteid = parts[0]
    subjid = parts[1]
    usubjid = f"PLX-826-{siteid}-{subjid}"

    brthdtc = to_iso(r['BRTHDAT'])
    rficdtc = to_iso(consent_map.get(subject))

    age = age_years(brthdtc, rficdtc)

    sex_raw = r['SEX']
    sex = 'F' if sex_raw == 'Female' else ('M' if sex_raw == 'Male' else '')

    race = RACE_MAP.get(r['RACE'], '')

    hisp = r['HISPANIC']
    if hisp == 'Yes':
        ethnic = 'HISPANIC OR LATINO'
    elif hisp == 'No':
        ethnic = 'NOT HISPANIC OR LATINO'
    else:
        ethnic = ''

    trt = rand_map.get(subject)
    if trt is None:
        armcd = 'SCRNFAIL'
        arm = 'Screen Failure'
    else:
        armcd, arm = ARM_MAP.get(trt, ('', ''))

    # Dosing
    rfstdtc = ''
    rfendtc = ''
    if subject in dosing_map:
        starts = []
        ends = []
        for ds, de in dosing_map[subject]:
            if pd.notna(ds) and str(ds).strip():
                starts.append(str(ds).strip())
            if pd.notna(de) and str(de).strip():
                ends.append(str(de).strip())
        all_dates = starts + ends
        if starts:
            # earliest start
            parsed_starts = [(parse_date(d), d) for d in starts]
            parsed_starts = [p for p in parsed_starts if p[0] is not None]
            if parsed_starts:
                parsed_starts.sort(key=lambda x: x[0])
                rfstdtc = parsed_starts[0][0]
        if all_dates:
            parsed_all = [(parse_date(d), d) for d in all_dates]
            parsed_all = [p for p in parsed_all if p[0] is not None]
            if parsed_all:
                parsed_all.sort(key=lambda x: x[0])
                rfendtc = parsed_all[-1][0]

    country = sites_map.get(siteid, '')

    rows.append({
        'STUDYID': 'PLX-826',
        'DOMAIN': 'DM',
        'USUBJID': usubjid,
        'SUBJID': subjid,
        'SITEID': siteid,
        'BRTHDTC': brthdtc if brthdtc else '',
        'AGE': age if age is not None else '',
        'AGEU': 'YEARS',
        'SEX': sex,
        'RACE': race,
        'ETHNIC': ethnic,
        'ARMCD': armcd,
        'ARM': arm,
        'RFICDTC': rficdtc if rficdtc else '',
        'RFSTDTC': rfstdtc,
        'RFENDTC': rfendtc,
        'COUNTRY': country,
    })

out = pd.DataFrame(rows, columns=[
    'STUDYID', 'DOMAIN', 'USUBJID', 'SUBJID', 'SITEID', 'BRTHDTC', 'AGE', 'AGEU',
    'SEX', 'RACE', 'ETHNIC', 'ARMCD', 'ARM', 'RFICDTC', 'RFSTDTC', 'RFENDTC', 'COUNTRY'
])

out = out.sort_values('USUBJID').reset_index(drop=True)

os.makedirs('output', exist_ok=True)
out.to_csv('output/dm.csv', index=False)
