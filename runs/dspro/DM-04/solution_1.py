import os
import pandas as pd
from datetime import date

STUDYID = 'PLX-826'
DOMAIN = 'DM'

MONTHS = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

RACE_MAP = {
    '1': 'WHITE',
    '2': 'BLACK OR AFRICAN AMERICAN',
    '3': 'ASIAN',
    '4': 'AMERICAN INDIAN OR ALASKA NATIVE',
    '5': 'NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER'
}

ARM_MAP = {
    'A': ('PBO', 'Placebo'),
    'B': ('XANLO', 'Xanomeline Low Dose'),
    'C': ('XANHI', 'Xanomeline High Dose')
}


def parse_date(raw):
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None

    parts = raw.split()
    if len(parts) != 3:
        return None

    day_s, mon_s, year_s = parts

    if not year_s.isdigit():
        return None
    year = int(year_s)

    mon_s = mon_s.upper()
    if mon_s == 'UNK':
        month = None
    else:
        month = MONTHS.get(mon_s)
        if month is None:
            return None

    day_s = day_s.upper()
    if day_s == 'UN':
        day = None
    else:
        if not day_s.isdigit():
            return None
        day = int(day_s)

    if month is not None and day is not None:
        iso = f"{year:04d}-{month:02d}-{day:02d}"
    elif month is not None:
        iso = f"{year:04d}-{month:02d}"
    else:
        iso = f"{year:04d}"

    return {'iso': iso, 'year': year, 'month': month, 'day': day}


def min_dt_key(d):
    return (
        d['year'],
        d['month'] if d['month'] is not None else 1,
        d['day'] if d['day'] is not None else 1
    )


def max_dt_key(d):
    return (
        d['year'],
        d['month'] if d['month'] is not None else 12,
        d['day'] if d['day'] is not None else 31
    )


def compute_age(birth, consent):
    if not birth or not consent:
        return ''
    if birth['month'] is None or birth['day'] is None:
        return ''
    if consent['month'] is None or consent['day'] is None:
        return ''

    b = date(birth['year'], birth['month'], birth['day'])
    c = date(consent['year'], consent['month'], consent['day'])

    age = c.year - b.year - ((c.month, c.day) < (b.month, b.day))
    return age


def main():
    os.makedirs('output', exist_ok=True)

    demog = pd.read_csv('input/raw_demog.csv', dtype=str, keep_default_na=False)
    consent = pd.read_csv('input/raw_consent.csv', dtype=str, keep_default_na=False)
    rand = pd.read_csv('input/raw_rand.csv', dtype=str, keep_default_na=False)
    dosing = pd.read_csv('input/raw_dosing.csv', dtype=str, keep_default_na=False)
    sites = pd.read_csv('input/sites.csv', dtype=str, keep_default_na=False)

    for df in (demog, consent, rand, dosing, sites):
        for col in df.columns:
            df[col] = df[col].str.strip()

    site_country = dict(zip(sites['SITE'], sites['COUNTRY']))

    records = []

    for _, row in demog.iterrows():
        subj_raw = row['SUBJECT']

        if '-' in subj_raw:
            site, subj = subj_raw.split('-', 1)
        else:
            site, subj = subj_raw, ''

        rec = {
            'STUDYID': STUDYID,
            'DOMAIN': DOMAIN,
            'USUBJID': f"{STUDYID}-{site}-{subj}" if subj else f"{STUDYID}-{site}",
            'SUBJID': subj,
            'SITEID': site,
            'BRTHDTC': '',
            'AGE': '',
            'AGEU': 'YEARS',
            'SEX': '',
            'RACE': '',
            'ETHNIC': '',
            'ARMCD': '',
            'ARM': '',
            'RFICDTC': '',
            'RFSTDTC': '',
            'RFENDTC': '',
            'COUNTRY': site_country.get(site, '')
        }

        birth = parse_date(row['BRTHDAT'])
        if birth:
            rec['BRTHDTC'] = birth['iso']

        sex_raw = row['SEX'].strip().lower()
        if sex_raw == 'female':
            rec['SEX'] = 'F'
        elif sex_raw == 'male':
            rec['SEX'] = 'M'

        race_raw = row['RACE'].strip()
        rec['RACE'] = RACE_MAP.get(race_raw, '')

        hisp_raw = row['HISPANIC'].strip().lower()
        if hisp_raw == 'yes':
            rec['ETHNIC'] = 'HISPANIC OR LATINO'
        elif hisp_raw == 'no':
            rec['ETHNIC'] = 'NOT HISPANIC OR LATINO'

        cons_rows = consent.loc[consent['SUBJECT'] == subj_raw]
        if not cons_rows.empty:
            cons = parse_date(cons_rows.iloc[0]['ICDAT'])
            if cons:
                rec['RFICDTC'] = cons['iso']
                rec['AGE'] = compute_age(birth, cons)

        rand_rows = rand.loc[rand['SUBJECT'] == subj_raw]
        if not rand_rows.empty:
            trt = rand_rows.iloc[0]['TRT_GROUP'].strip().upper()
            armcd, arm = ARM_MAP.get(trt, ('SCRNFAIL', 'Screen Failure'))
        else:
            armcd, arm = 'SCRNFAIL', 'Screen Failure'

        rec['ARMCD'] = armcd
        rec['ARM'] = arm

        dose_rows = dosing.loc[dosing['SUBJECT'] == subj_raw]
        starts = []
        all_dates = []

        for _, drow in dose_rows.iterrows():
            ds = parse_date(drow['DOSE_START'])
            de = parse_date(drow['DOSE_END'])

            if ds:
                starts.append(ds)
                all_dates.append(ds)
            if de:
                all_dates.append(de)

        if starts:
            earliest = min(starts, key=min_dt_key)
            rec['RFSTDTC'] = earliest['iso']

        if all_dates:
            latest = max(all_dates, key=max_dt_key)
            rec['RFENDTC'] = latest['iso']

        records.append(rec)

    out_cols = [
        'STUDYID', 'DOMAIN', 'USUBJID', 'SUBJID', 'SITEID', 'BRTHDTC',
        'AGE', 'AGEU', 'SEX', 'RACE', 'ETHNIC', 'ARMCD', 'ARM',
        'RFICDTC', 'RFSTDTC', 'RFENDTC', 'COUNTRY'
    ]

    out_df = pd.DataFrame(records, columns=out_cols)
    out_df = out_df.sort_values('USUBJID').reset_index(drop=True)
    out_df.to_csv('output/dm.csv', index=False, na_rep='')


if __name__ == '__main__':
    main()
