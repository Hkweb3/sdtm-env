import os
from datetime import date

import pandas as pd

STUDYID = 'KVT-998'
DOMAIN = 'DM'

MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05',
    'JUN': '06', 'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10',
    'NOV': '11', 'DEC': '12',
}

ARM_MAP = {
    'A': ('PBO', 'Placebo'),
    'B': ('XANLO', 'Xanomeline Low Dose'),
    'C': ('XANHI', 'Xanomeline High Dose'),
}

SEX_MAP = {'FEMALE': 'F', 'MALE': 'M'}

OUTPUT_COLUMNS = [
    'STUDYID', 'DOMAIN', 'USUBJID', 'SUBJID', 'SITEID', 'BRTHDTC', 'AGE',
    'AGEU', 'SEX', 'RACE', 'ETHNIC', 'ARMCD', 'ARM', 'RFICDTC', 'RFSTDTC',
    'RFENDTC', 'COUNTRY',
]


def clean(value):
    """Normalize a raw value to a stripped string; missing values become ''."""
    if value is None:
        return ''
    s = str(value).strip()
    if s.lower() in ('', 'nan', 'na', 'null', '.', 'none'):
        return ''
    return s


def to_iso(raw):
    """Convert 'DD MON YYYY' to ISO 8601.

    Unknown day (UN) or month (UNK) parts are dropped, never imputed:
    '07 MAR 2014' -> '2014-03-07', 'UN MAR 2014' -> '2014-03',
    'UN UNK 2014' -> '2014'.
    """
    s = clean(raw)
    if not s:
        return ''
    parts = s.split()
    if len(parts) != 3:
        return ''
    day, mon, year = (p.upper() for p in parts)
    if not year or year in ('UN', 'UNK'):
        return ''
    iso = year
    if mon in MONTHS:
        iso += '-' + MONTHS[mon]
    elif mon not in ('UN', 'UNK'):
        return ''
    if day in ('UN', 'UNK'):
        return iso
    return iso + '-' + day.zfill(2)


def is_full(iso):
    """True when iso is a complete calendar date YYYY-MM-DD."""
    return len(iso) == 10 and iso[4] == '-' and iso[7] == '-'


def to_date(iso):
    y, m, d = iso.split('-')
    return date(int(y), int(m), int(d))


def completed_years(birth_iso, ref_iso):
    """Completed years from birth to reference date; a birthday on the
    reference date counts as reached."""
    b = to_date(birth_iso)
    r = to_date(ref_iso)
    age = r.year - b.year
    if (r.month, r.day) < (b.month, b.day):
        age -= 1
    return age


def main():
    os.makedirs('output', exist_ok=True)

    demog = pd.read_csv('input/raw_demog.csv', dtype=str, keep_default_na=False)
    consent = pd.read_csv('input/raw_consent.csv', dtype=str, keep_default_na=False)
    rand = pd.read_csv('input/raw_rand.csv', dtype=str, keep_default_na=False)
    dosing = pd.read_csv('input/raw_dosing.csv', dtype=str, keep_default_na=False)
    sites = pd.read_csv('input/sites.csv', dtype=str, keep_default_na=False)

    ic_map = {clean(r['SUBJECT']): to_iso(r['ICDAT']) for _, r in consent.iterrows()}
    trt_map = {clean(r['SUBJECT']): clean(r['TRT_GROUP']) for _, r in rand.iterrows()}
    country_map = {clean(r['SITE']): clean(r['COUNTRY']) for _, r in sites.iterrows()}

    # Collect dosing dates per subject.
    starts_by_subj = {}
    all_dates_by_subj = {}
    for _, r in dosing.iterrows():
        subj = clean(r['SUBJECT'])
        start = to_iso(r['DOSE_START'])
        end = to_iso(r['DOSE_END'])
        if start:
            starts_by_subj.setdefault(subj, []).append(start)
            all_dates_by_subj.setdefault(subj, []).append(start)
        if end:
            all_dates_by_subj.setdefault(subj, []).append(end)

    records = []
    for _, r in demog.iterrows():
        subject = clean(r['SUBJECT'])
        siteid, subjid = subject.split('-', 1)
        usubjid = '-'.join([STUDYID, siteid, subjid])

        brthdtc = to_iso(r['BRTHDAT'])
        rficdtc = ic_map.get(subject, '')

        # Age in completed years at consent; blank if either date is partial.
        age = ''
        if is_full(brthdtc) and is_full(rficdtc):
            age = str(completed_years(brthdtc, rficdtc))

        sex = SEX_MAP.get(clean(r['SEX']).upper(), '')
        race = clean(r['RACE']).upper()

        hisp = clean(r['HISPANIC']).upper()
        if hisp == 'YES':
            ethnic = 'HISPANIC OR LATINO'
        elif hisp == 'NO':
            ethnic = 'NOT HISPANIC OR LATINO'
        else:
            ethnic = ''

        # Randomized treatment; subjects absent from raw_rand are screen failures.
        trt = trt_map.get(subject, '')
        armcd, arm = ARM_MAP.get(trt, ('SCRNFAIL', 'Screen Failure'))

        # Treatment start/end from dosing; blank when the subject has no dosing.
        starts = starts_by_subj.get(subject, [])
        all_dates = all_dates_by_subj.get(subject, [])
        rfstdtc = min(starts) if starts else ''
        rfendtc = max(all_dates) if all_dates else ''

        records.append({
            'STUDYID': STUDYID,
            'DOMAIN': DOMAIN,
            'USUBJID': usubjid,
            'SUBJID': subjid,
            'SITEID': siteid,
            'BRTHDTC': brthdtc,
            'AGE': age,
            'AGEU': 'YEARS',
            'SEX': sex,
            'RACE': race,
            'ETHNIC': ethnic,
            'ARMCD': armcd,
            'ARM': arm,
            'RFICDTC': rficdtc,
            'RFSTDTC': rfstdtc,
            'RFENDTC': rfendtc,
            'COUNTRY': country_map.get(siteid, ''),
        })

    dm = pd.DataFrame(records, columns=OUTPUT_COLUMNS)
    dm = dm.sort_values('USUBJID', kind='mergesort').reset_index(drop=True)
    dm.to_csv('output/dm.csv', index=False)


if __name__ == '__main__':
    main()
