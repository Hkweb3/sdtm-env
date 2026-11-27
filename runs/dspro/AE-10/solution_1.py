import os
import pandas as pd
from datetime import date, datetime

STUDYID = 'ALX-599'
DOMAIN = 'AE'

# Read input files as text to preserve leading zeros and date formats.
dm = pd.read_csv('input/dm.csv', dtype=str, keep_default_na=False)
raw = pd.read_csv('input/raw_ae.csv', dtype=str, keep_default_na=False)

# Strip key fields.
for col in ['SUBJECT', 'RECID', 'RECORD_STATUS', 'AEYN']:
    raw[col] = raw[col].str.strip()

# Drop deleted records and "no adverse events" placeholders.
raw = raw[~raw['RECORD_STATUS'].str.upper().eq('DELETED')].copy()
raw = raw[~raw['AEYN'].str.upper().eq('NO')].copy()

# Keep only the highest VERSION for each SUBJECT + RECID.
raw['VERSION'] = pd.to_numeric(raw['VERSION'], errors='coerce').fillna(0).astype(int)
raw = raw.sort_values(['SUBJECT', 'RECID', 'VERSION'], ascending=[True, True, False])
raw = raw.drop_duplicates(['SUBJECT', 'RECID'], keep='first').copy()

# USUBJID mapping.
dm['USUBJID'] = dm['USUBJID'].str.strip()
valid_usubjids = set(dm['USUBJID'])
dm_rf = dict(zip(dm['USUBJID'], dm['RFSTDTC'].str.strip()))


def make_usubjid(subject):
    s = str(subject).strip()
    if '-' in s:
        site, subj = s.split('-', 1)
    else:
        site, subj = '', s
    return f'{STUDYID}-{site}-{subj}'


raw['USUBJID'] = raw['SUBJECT'].apply(make_usubjid)
raw = raw[raw['USUBJID'].isin(valid_usubjids)].copy()


def get_site(subject):
    s = str(subject).strip()
    if '-' in s:
        return s.split('-', 1)[0]
    return ''


raw['SITE'] = raw['SUBJECT'].apply(get_site)

site_formats = {
    '179': 'MM/DD/YYYY',
    '271': 'DD/MM/YYYY',
    '589': 'DD/MM/YYYY',
    '615': 'MM/DD/YYYY',
    '635': 'DD/MM/YYYY',
    '856': 'MM/DD/YYYY',
    '983': 'DD/MM/YYYY',
    '997': 'DD/MM/YYYY',
}


def parse_date(val, site):
    if pd.isna(val):
        return ''
    s = str(val).strip()
    if not s:
        return ''

    # Already ISO-like.
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        try:
            datetime.strptime(s, '%Y-%m-%d')
            return s
        except ValueError:
            return ''
    if len(s) == 7 and s[4] == '-':
        try:
            datetime.strptime(s, '%Y-%m')
            return s
        except ValueError:
            return ''
    if len(s) == 4 and s.isdigit():
        return s

    fmt = site_formats.get(str(site), '')
    parts = [p.strip() for p in s.split('/')]

    if len(parts) == 3:
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return ''

        if fmt == 'DD/MM/YYYY':
            day, month, year = nums
        else:
            month, day, year = nums

        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ''

    elif len(parts) == 2:
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return ''

        if len(parts[1]) == 4 and 1 <= nums[0] <= 12:
            return f'{nums[1]:04d}-{nums[0]:02d}'
        elif len(parts[0]) == 4 and 1 <= nums[1] <= 12:
            return f'{nums[0]:04d}-{nums[1]:02d}'
        return ''

    elif len(parts) == 1:
        try:
            year = int(parts[0])
        except ValueError:
            return ''
        if 1900 <= year <= 2100:
            return str(year)
        return ''

    return ''


raw['AESTDTC'] = raw.apply(lambda row: parse_date(row['AESTDAT'], row['SITE']), axis=1)
raw['AEENDTC'] = raw.apply(
    lambda row: '' if row['AEONGO'].strip().upper() == 'Y' else parse_date(row['AEENDAT'], row['SITE']),
    axis=1
)

# AE identifiers and dictionary terms.
raw['AESPID'] = raw['RECID'].str.strip()
raw['AETERM'] = raw['AE_VERBATIM'].str.strip().str.upper()
raw['AEDECOD'] = raw['CODED_PT'].str.strip()
raw['AEBODSYS'] = raw['CODED_SOC'].str.strip()


def map_severity(x):
    if pd.isna(x):
        return ''
    try:
        v = int(float(x))
    except (ValueError, TypeError):
        return ''
    return {1: 'MILD', 2: 'MODERATE', 3: 'SEVERE'}.get(v, '')


def map_serious(x):
    if pd.isna(x):
        return ''
    try:
        v = int(float(x))
    except (ValueError, TypeError):
        return ''
    return {1: 'Y', 0: 'N'}.get(v, '')


rel_map = {
    'not related': 'NONE',
    'unlikely related': 'REMOTE',
    'possibly related': 'POSSIBLE',
    'probably related': 'PROBABLE',
}


def map_rel(x):
    if pd.isna(x):
        return ''
    return rel_map.get(str(x).strip().lower(), '')


raw['AESEV'] = raw['SEVERITY'].apply(map_severity)
raw['AESER'] = raw['SERIOUS'].apply(map_serious)
raw['AEREL'] = raw['RELATIONSHIP'].apply(map_rel)
raw['AEOUT'] = raw['OUTCOME'].str.strip().str.upper()

# Study day calculation.
raw['RFSTDTC'] = raw['USUBJID'].map(dm_rf).fillna('')


def calc_dy(dtc, rfstdtc):
    if not dtc or not rfstdtc:
        return ''
    try:
        d = datetime.strptime(str(dtc), '%Y-%m-%d').date()
        r = datetime.strptime(str(rfstdtc), '%Y-%m-%d').date()
    except ValueError:
        return ''
    if d >= r:
        return (d - r).days + 1
    else:
        return (d - r).days


raw['AESTDY'] = raw.apply(lambda row: calc_dy(row['AESTDTC'], row['RFSTDTC']), axis=1)
raw['AEENDY'] = raw.apply(lambda row: calc_dy(row['AEENDTC'], row['RFSTDTC']), axis=1)

# Sequence within subject.
raw = raw.sort_values(
    ['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'],
    ascending=[True, True, True, True]
)
raw['AESEQ'] = raw.groupby('USUBJID').cumcount() + 1

raw['STUDYID'] = STUDYID
raw['DOMAIN'] = DOMAIN

out_cols = [
    'STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID', 'AETERM',
    'AEDECOD', 'AEBODSYS', 'AESEV', 'AESER', 'AEREL', 'AEOUT',
    'AESTDTC', 'AEENDTC', 'AESTDY', 'AEENDY'
]

out = raw[out_cols].copy()
out = out.fillna('')
out = out.sort_values(['USUBJID', 'AESEQ'], ascending=[True, True])

os.makedirs('output', exist_ok=True)
out.to_csv('output/ae.csv', index=False)
