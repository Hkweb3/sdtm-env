import pandas as pd
import numpy as np
import os
from datetime import datetime

# Site-specific date formats
site_format = {
    '100': 'MM/DD/YYYY',
    '112': 'MM/DD/YYYY',
    '310': 'DD/MM/YYYY',
    '314': 'DD/MM/YYYY',
    '430': 'MM/DD/YYYY',
    '554': 'DD/MM/YYYY',
    '691': 'MM/DD/YYYY',
    '775': 'MM/DD/YYYY',
    '884': 'MM/DD/YYYY'
}

rel_map = {
    'Not related': 'NONE',
    'Unlikely related': 'REMOTE',
    'Possibly related': 'POSSIBLE',
    'Probably related': 'PROBABLE'
}

def clean_str(val):
    if pd.isna(val):
        return ''
    return str(val).strip()

def iso_date_from_raw(date_str, site):
    if pd.isna(date_str):
        return ''
    s = str(date_str).strip()
    if not s or '/' not in s:
        return ''
    parts = s.split('/')
    if len(parts) != 3:
        return ''
    site_str = str(site)
    fmt = site_format.get(site_str, 'MM/DD/YYYY')
    if fmt == 'MM/DD/YYYY':
        month_part, day_part, year_part = parts[0], parts[1], parts[2]
    else:
        day_part, month_part, year_part = parts[0], parts[1], parts[2]

    def to_int_or_none(x):
        x = x.strip()
        if x == '' or not x.isdigit():
            return None
        return int(x)

    year = to_int_or_none(year_part)
    month = to_int_or_none(month_part)
    day = to_int_or_none(day_part)

    if year is None:
        return ''
    if month is not None and day is not None:
        try:
            datetime(year, month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return ''
    elif month is not None:
        return f"{year:04d}-{month:02d}"
    else:
        return f"{year:04d}"

def study_day(date_str, rfstdtc):
    if not date_str or pd.isna(rfstdtc):
        return ''
    if not isinstance(rfstdtc, str):
        rfstdtc = str(rfstdtc)
    if len(date_str) != 10 or len(rfstdtc) != 10:
        return ''
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        r = datetime.strptime(rfstdtc, '%Y-%m-%d').date()
    except ValueError:
        return ''
    delta = (d - r).days
    return delta + 1 if delta >= 0 else delta

def is_ongoing(val):
    return str(val).strip().upper() == 'Y' if pd.notna(val) else False

# Read input files
raw = pd.read_csv('input/raw_ae.csv')
dm = pd.read_csv('input/dm.csv')

# Build USUBJID from SUBJECT
def make_usubjid(subject):
    if pd.isna(subject):
        return ''
    s = str(subject).strip()
    if '-' not in s:
        return f"ALX-334-{s}"
    site, subj = s.split('-', 1)
    return f"ALX-334-{site}-{subj}"

raw['USUBJID'] = raw['SUBJECT'].apply(make_usubjid)

# Merge DM to get RFSTDTC
dm_sub = dm[['USUBJID', 'RFSTDTC']].copy()
df = raw.merge(dm_sub, on='USUBJID', how='left')

# Extract site for date format
df['SITE'] = df['SUBJECT'].apply(lambda s: str(s).split('-')[0] if pd.notna(s) and '-' in str(s) else '')

# Populate SDTM variables
df['STUDYID'] = 'ALX-334'
df['DOMAIN'] = 'AE'
df['AESPID'] = df['RECID'].apply(clean_str)
df['AETERM'] = df['AE_VERBATIM'].apply(lambda x: clean_str(x).upper())
df['AEDECOD'] = df['CODED_PT'].apply(clean_str)
df['AEBODSYS'] = df['CODED_SOC'].apply(clean_str)
df['AESEV'] = df['SEVERITY'].apply(lambda x: clean_str(x).upper())
df['AESER'] = df['SERIOUS'].apply(lambda x: {'Yes': 'Y', 'No': 'N'}.get(clean_str(x), ''))
df['AEREL'] = df['RELATIONSHIP'].apply(lambda x: rel_map.get(clean_str(x), ''))
df['AEOUT'] = df['OUTCOME'].apply(lambda x: clean_str(x).upper())

# Convert dates to ISO 8601
df['AESTDTC'] = df.apply(lambda row: iso_date_from_raw(row['AESTDAT'], row['SITE']), axis=1)
df['AEENDTC'] = df.apply(
    lambda row: '' if is_ongoing(row['AEONGO']) else iso_date_from_raw(row['AEENDAT'], row['SITE']),
    axis=1
)

# Compute study days
df['AESTDY'] = df.apply(lambda row: study_day(row['AESTDTC'], row['RFSTDTC']), axis=1)
df['AEENDY'] = df.apply(lambda row: study_day(row['AEENDTC'], row['RFSTDTC']), axis=1)

# Sort and assign AESEQ
df = df.sort_values(['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'], kind='stable')
df['AESEQ'] = df.groupby('USUBJID').cumcount() + 1

# Select output columns
out_cols = [
    'STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID', 'AETERM', 'AEDECOD',
    'AEBODSYS', 'AESEV', 'AESER', 'AEREL', 'AEOUT', 'AESTDTC', 'AEENDTC',
    'AESTDY', 'AEENDY'
]
ae = df[out_cols]

# Ensure output directory exists
os.makedirs('output', exist_ok=True)

# Write CSV
ae.to_csv('output/ae.csv', index=False)
