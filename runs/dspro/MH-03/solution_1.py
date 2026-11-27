import pandas as pd
from pathlib import Path
from datetime import datetime

STUDYID = 'CTN-248'
DOMAIN = 'MH'

MONTH_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

def clean_component(x):
    if pd.isna(x):
        return ''
    s = str(x).strip()
    if s == '':
        return ''
    if s.endswith('.0'):
        s = s[:-2]
    return s

def make_start_date(dd, mm, yyyy):
    y = clean_component(yyyy)
    if y == '':
        return ''
    m = clean_component(mm)
    d = clean_component(dd)

    try:
        y_int = int(y)
        y_norm = f"{y_int:04d}"
    except ValueError:
        return ''

    if m == '':
        return y_norm

    try:
        m_int = int(m)
    except ValueError:
        return y_norm

    if d == '':
        return f"{y_norm}-{m_int:02d}"

    try:
        d_int = int(d)
    except ValueError:
        return f"{y_norm}-{m_int:02d}"

    return f"{y_norm}-{m_int:02d}-{d_int:02d}"

def make_visit_date(v):
    if pd.isna(v):
        return ''
    s = str(v).strip()
    if s == '':
        return ''

    parts = s.split()
    if len(parts) < 3:
        return ''

    day, mon, year = parts[0], parts[1], parts[2]
    year = year.strip()
    if year == '':
        return ''

    try:
        year_int = int(year)
        year_norm = f"{year_int:04d}"
    except ValueError:
        return ''

    mon_upper = mon.upper()
    if mon_upper == 'UNK':
        return year_norm

    month_num = MONTH_MAP.get(mon_upper)
    if month_num is None:
        return year_norm

    if day.upper() == 'UN':
        return f"{year_norm}-{month_num:02d}"

    try:
        day_int = int(day)
    except ValueError:
        return f"{year_norm}-{month_num:02d}"

    return f"{year_norm}-{month_num:02d}-{day_int:02d}"

def compute_dy(mhdtc, rfstdtc):
    if pd.isna(mhdtc) or pd.isna(rfstdtc):
        return ''
    mh = str(mhdtc).strip()
    rf = str(rfstdtc).strip()
    if len(mh) != 10 or len(rf) != 10:
        return ''

    try:
        mh_date = datetime.strptime(mh, '%Y-%m-%d').date()
        rf_date = datetime.strptime(rf, '%Y-%m-%d').date()
    except ValueError:
        return ''

    diff = (mh_date - rf_date).days
    if diff >= 0:
        return diff + 1
    return diff

# Read input files
dm = pd.read_csv('input/dm.csv', dtype=str, keep_default_na=False)
raw = pd.read_csv('input/raw_mh.csv', dtype=str, keep_default_na=False)

# Trim relevant columns
for col in ['SUBJECT', 'RECID', 'MH_VERBATIM', 'CODED_PT', 'CODED_SOC', 'CATEGORY',
            'MHSTDAT_DD', 'MHSTDAT_MM', 'MHSTDAT_YYYY', 'VISIT_DATE']:
    raw[col] = raw[col].str.strip()
dm['RFSTDTC'] = dm['RFSTDTC'].str.strip()

# Build USUBJID and merge to DM for RFSTDTC
raw['USUBJID'] = STUDYID + '-' + raw['SUBJECT']
df = raw.merge(dm[['USUBJID', 'RFSTDTC']], on='USUBJID', how='left')

# Map columns
df['STUDYID'] = STUDYID
df['DOMAIN'] = DOMAIN
df['MHSPID'] = df['RECID']
df['MHTERM'] = df['MH_VERBATIM']
df['MHDECOD'] = df['CODED_PT']
df['MHBODSYS'] = df['CODED_SOC']
df['MHCAT'] = df['CATEGORY'].str.upper()
df['MHSTDTC'] = df.apply(
    lambda row: make_start_date(row['MHSTDAT_DD'], row['MHSTDAT_MM'], row['MHSTDAT_YYYY']),
    axis=1
)
df['MHDTC'] = df['VISIT_DATE'].apply(make_visit_date)
df['MHDY'] = df.apply(lambda row: compute_dy(row['MHDTC'], row['RFSTDTC']), axis=1)

# Assign MHSEQ after sorting within subject
df = df.sort_values(
    ['USUBJID', 'MHCAT', 'MHSTDTC', 'MHTERM', 'MHSPID'],
    kind='mergesort'
)
df['MHSEQ'] = df.groupby('USUBJID').cumcount() + 1

# Final output order
df = df.sort_values(['USUBJID', 'MHSEQ'], kind='mergesort')

output_columns = [
    'STUDYID', 'DOMAIN', 'USUBJID', 'MHSEQ', 'MHSPID', 'MHTERM',
    'MHDECOD', 'MHCAT', 'MHBODSYS', 'MHDTC', 'MHSTDTC', 'MHDY'
]
df_output = df[output_columns]

Path('output').mkdir(exist_ok=True)
df_output.to_csv('output/mh.csv', index=False, na_rep='')
