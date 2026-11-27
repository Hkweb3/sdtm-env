import os
import pandas as pd

STUDYID = 'PLX-658'

MONTHS = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
          'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}

SEX_MAP = {'1': 'M', '2': 'F'}

RACE_MAP = {'1': 'WHITE',
            '2': 'BLACK OR AFRICAN AMERICAN',
            '3': 'ASIAN',
            '4': 'AMERICAN INDIAN OR ALASKA NATIVE',
            '5': 'NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER'}

ARM_MAP = {'A': ('PBO', 'Placebo'),
           'B': ('XANLO', 'Xanomeline Low Dose'),
           'C': ('XANHI', 'Xanomeline High Dose')}

COLUMNS = ['STUDYID', 'DOMAIN', 'USUBJID', 'SUBJID', 'SITEID', 'BRTHDTC', 'AGE',
           'AGEU', 'SEX', 'RACE', 'ETHNIC', 'ARMCD', 'ARM', 'RFICDTC',
           'RFSTDTC', 'RFENDTC', 'COUNTRY']


def parse_dtc_parts(value):
    """Parse raw DDMONYYYY date (day may be 'UN', month may be 'UNK').
    Returns (year, month, day) with None for unknown parts."""
    if not isinstance(value, str):
        return (None, None, None)
    s = value.strip().upper()
    if len(s) != 9:
        return (None, None, None)
    day_s, mon_s, year_s = s[:2], s[2:5], s[5:]
    if not year_s.isdigit():
        return (None, None, None)
    year = int(year_s)
    month = MONTHS.get(mon_s)
    day = int(day_s) if day_s.isdigit() else None
    return (year, month, day)


def to_iso(parts):
    """Convert (year, month, day) with possible None parts to ISO 8601 string.
    Never imputes missing parts."""
    year, month, day = parts
    if year is None:
        return ''
    if month is None:
        return '%04d' % year
    if day is None:
        return '%04d-%02d' % (year, month)
    return '%04d-%02d-%02d' % (year, month, day)


def completed_years(birth, ref):
    """Completed years from birth to reference date; birthday on ref date counts.
    Blank if either date is partial or missing."""
    if any(p is None for p in birth) or any(p is None for p in ref):
        return ''
    by, bm, bd = birth
    ry, rm, rd = ref
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return age


def main():
    os.makedirs('output', exist_ok=True)

    demog = pd.read_csv('input/raw_demog.csv', dtype=str, keep_default_na=False)
    consent = pd.read_csv('input/raw_consent.csv', dtype=str, keep_default_na=False)
    rand = pd.read_csv('input/raw_rand.csv', dtype=str, keep_default_na=False)
    dosing = pd.read_csv('input/raw_dosing.csv', dtype=str, keep_default_na=False)
    sites = pd.read_csv('input/sites.csv', dtype=str, keep_default_na=False)

    consent_map = {r['SUBJECT'].strip(): r['ICDAT'].strip() for _, r in consent.iterrows()}
    rand_map = {r['SUBJECT'].strip(): r['TRT_GROUP'].strip() for _, r in rand.iterrows()}
    site_map = {r['SITE'].strip(): r['COUNTRY'].strip() for _, r in sites.iterrows()}

    # Collect dosing dates per subject
    start_dates = {}
    all_dates = {}
    for _, r in dosing.iterrows():
        subj = r['SUBJECT'].strip()
        s_iso = to_iso(parse_dtc_parts(r['DOSE_START']))
        e_iso = to_iso(parse_dtc_parts(r['DOSE_END']))
        if s_iso:
            start_dates.setdefault(subj, []).append(s_iso)
            all_dates.setdefault(subj, []).append(s_iso)
        if e_iso:
            all_dates.setdefault(subj, []).append(e_iso)

    records = []
    for _, r in demog.iterrows():
        subject = r['SUBJECT'].strip()
        site, subj = subject.split('-', 1)
        usubjid = '-'.join([STUDYID, site, subj])

        brth = parse_dtc_parts(r['BRTHDAT'])
        ic = parse_dtc_parts(consent_map.get(subject, ''))
        age = completed_years(brth, ic)

        # Treatment group; subjects absent from randomization are screen failures
        tg = rand_map.get(subject)
        armcd, arm = ARM_MAP.get(tg, ('SCRNFAIL', 'Screen Failure'))

        subj_starts = start_dates.get(subject, [])
        subj_all = all_dates.get(subject, [])
        rfstdtc = min(subj_starts) if subj_starts else ''
        rfendtc = max(subj_all) if subj_all else ''

        hisp = r['HISPANIC'].strip()
        if hisp == 'Yes':
            ethnic = 'HISPANIC OR LATINO'
        elif hisp == 'No':
            ethnic = 'NOT HISPANIC OR LATINO'
        else:
            ethnic = ''

        records.append({
            'STUDYID': STUDYID,
            'DOMAIN': 'DM',
            'USUBJID': usubjid,
            'SUBJID': subj,
            'SITEID': site,
            'BRTHDTC': to_iso(brth),
            'AGE': age,
            'AGEU': 'YEARS',
            'SEX': SEX_MAP.get(r['SEX'].strip(), ''),
            'RACE': RACE_MAP.get(r['RACE'].strip(), ''),
            'ETHNIC': ethnic,
            'ARMCD': armcd,
            'ARM': arm,
            'RFICDTC': to_iso(ic),
            'RFSTDTC': rfstdtc,
            'RFENDTC': rfendtc,
            'COUNTRY': site_map.get(site, ''),
        })

    dm = pd.DataFrame(records, columns=COLUMNS)
    dm = dm.sort_values('USUBJID', kind='mergesort').reset_index(drop=True)
    dm.to_csv('output/dm.csv', index=False)


if __name__ == '__main__':
    main()
