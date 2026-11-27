import os
import pandas as pd

STUDYID = 'PLX-826'
INPUT_DIR = 'input'
OUTPUT_DIR = 'output'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'dm.csv')

MONTHS = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

RACE_MAP = {
    '1': 'WHITE',
    '2': 'BLACK OR AFRICAN AMERICAN',
    '3': 'ASIAN',
    '4': 'AMERICAN INDIAN OR ALASKA NATIVE',
    '5': 'NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER',
}

ARM_MAP = {
    'A': ('PBO', 'Placebo'),
    'B': ('XANLO', 'Xanomeline Low Dose'),
    'C': ('XANHI', 'Xanomeline High Dose'),
}

DM_COLUMNS = [
    'STUDYID', 'DOMAIN', 'USUBJID', 'SUBJID', 'SITEID', 'BRTHDTC', 'AGE',
    'AGEU', 'SEX', 'RACE', 'ETHNIC', 'ARMCD', 'ARM', 'RFICDTC', 'RFSTDTC',
    'RFENDTC', 'COUNTRY',
]


def parse_date(value):
    """Parse raw 'DD MON YYYY' dates ('UN' day, 'UNK' month allowed).
    Returns (year, month, day) with None for unknown parts; None if absent."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.upper() in {'NA', 'NAN', 'NULL', '.'}:
        return None
    parts = s.split()
    if len(parts) != 3:
        return None
    day_s, mon_s, year_s = parts[0].upper(), parts[1].upper(), parts[2]
    try:
        year = int(year_s)
    except ValueError:
        return None
    month = MONTHS.get(mon_s)  # 'UNK' or unrecognized -> None
    day = None
    if day_s != 'UN':
        try:
            day = int(day_s)
        except ValueError:
            day = None
    return (year, month, day)


def to_iso(d):
    """Format (year, month, day) as ISO 8601, keeping only the known parts."""
    if d is None:
        return ''
    year, month, day = d
    out = f'{year:04d}'
    if month is not None:
        out += f'-{month:02d}'
        if day is not None:
            out += f'-{day:02d}'
    return out


def date_key(d):
    """Sortable key for (possibly partial) dates; unknown parts sort lowest."""
    if d is None:
        return (-1, -1, -1)
    year, month, day = d
    return (year, month if month is not None else -1, day if day is not None else -1)


def is_complete(d):
    return d is not None and d[1] is not None and d[2] is not None


def completed_years(birth, ref):
    """Completed years from birth to ref; a birthday on ref counts as reached."""
    if not is_complete(birth) or not is_complete(ref):
        return ''
    by, bm, bd = birth
    ry, rm, rd = ref
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return str(age)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    demog = pd.read_csv(os.path.join(INPUT_DIR, 'raw_demog.csv'), dtype=str)
    consent = pd.read_csv(os.path.join(INPUT_DIR, 'raw_consent.csv'), dtype=str)
    rand = pd.read_csv(os.path.join(INPUT_DIR, 'raw_rand.csv'), dtype=str)
    dosing = pd.read_csv(os.path.join(INPUT_DIR, 'raw_dosing.csv'), dtype=str)
    sites = pd.read_csv(os.path.join(INPUT_DIR, 'sites.csv'), dtype=str)

    for df in (demog, consent, rand, dosing, sites):
        df.columns = [c.strip() for c in df.columns]
        for col in df.columns:
            df[col] = df[col].fillna('').str.strip()

    consent_map = dict(zip(consent['SUBJECT'], consent['ICDAT']))
    rand_map = dict(zip(rand['SUBJECT'], rand['TRT_GROUP']))
    country_map = dict(zip(sites['SITE'], sites['COUNTRY']))

    dose_info = {}
    for _, row in dosing.iterrows():
        subj = row['SUBJECT']
        start = parse_date(row['DOSE_START'])
        end = parse_date(row['DOSE_END'])
        info = dose_info.setdefault(subj, {'starts': [], 'all': []})
        if start is not None:
            info['starts'].append(start)
            info['all'].append(start)
        if end is not None:
            info['all'].append(end)

    records = []
    for _, row in demog.iterrows():
        subj = row['SUBJECT']
        site_id, _, subj_id = subj.partition('-')

        birth = parse_date(row['BRTHDAT'])
        ic_date = parse_date(consent_map.get(subj, ''))

        trt = rand_map.get(subj, '')
        if trt in ARM_MAP:
            armcd, arm = ARM_MAP[trt]
        else:
            armcd, arm = 'SCRNFAIL', 'Screen Failure'

        info = dose_info.get(subj)
        rfstdtc = to_iso(min(info['starts'], key=date_key)) if info and info['starts'] else ''
        rfendtc = to_iso(max(info['all'], key=date_key)) if info and info['all'] else ''

        sex = {'FEMALE': 'F', 'MALE': 'M'}.get(str(row.get('SEX', '')).upper(), '')
        race = RACE_MAP.get(str(row.get('RACE', '')), '')
        ethnic = {'YES': 'HISPANIC OR LATINO',
                  'NO': 'NOT HISPANIC OR LATINO'}.get(str(row.get('HISPANIC', '')).upper(), '')

        records.append({
            'STUDYID': STUDYID,
            'DOMAIN': 'DM',
            'USUBJID': f'{STUDYID}-{site_id}-{subj_id}',
            'SUBJID': subj_id,
            'SITEID': site_id,
            'BRTHDTC': to_iso(birth),
            'AGE': completed_years(birth, ic_date),
            'AGEU': 'YEARS',
            'SEX': sex,
            'RACE': race,
            'ETHNIC': ethnic,
            'ARMCD': armcd,
            'ARM': arm,
            'RFICDTC': to_iso(ic_date),
            'RFSTDTC': rfstdtc,
            'RFENDTC': rfendtc,
            'COUNTRY': country_map.get(site_id, ''),
        })

    dm = pd.DataFrame(records, columns=DM_COLUMNS)
    dm = dm.sort_values('USUBJID', kind='mergesort').reset_index(drop=True)
    dm.to_csv(OUTPUT_FILE, index=False)


if __name__ == '__main__':
    main()
