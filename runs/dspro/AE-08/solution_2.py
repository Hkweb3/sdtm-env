import pandas as pd
import os
from datetime import datetime

# Ensure output directory exists
os.makedirs('output', exist_ok=True)

# Read DM domain
dm = pd.read_csv('input/dm.csv', skipinitialspace=True)
dm['RFSTDTC'] = dm['RFSTDTC'].astype(str).str.strip()

# Read raw AE
ae = pd.read_csv('input/raw_ae.csv', skipinitialspace=True)

# Drop deleted records
ae = ae[ae['RECORD_STATUS'] != 'DELETED']

# Drop placeholder rows with AEYN = No
ae = ae[ae['AEYN'].astype(str).str.strip().str.upper() != 'NO']

# Keep highest VERSION per SUBJECT + RECID
ae['VERSION'] = pd.to_numeric(ae['VERSION'], errors='coerce').fillna(0).astype(int)
ae = ae.sort_values(['SUBJECT', 'RECID', 'VERSION'], ascending=[True, True, False])
ae = ae.drop_duplicates(subset=['SUBJECT', 'RECID'], keep='first')

# Derive USUBJID from SUBJECT
def derive_usubjid(subject):
    parts = str(subject).split('-', 1)
    if len(parts) == 2:
        site, subj = parts
        return f"ALX-919-{site}-{subj}"
    return ''

ae['USUBJID'] = ae['SUBJECT'].apply(derive_usubjid)

# Mapping dictionaries
sev_map = {
    '1': 'MILD', '2': 'MODERATE', '3': 'SEVERE',
    1: 'MILD', 2: 'MODERATE', 3: 'SEVERE'
}
ser_map = {'Yes': 'Y', 'No': 'N'}
rel_map = {
    'Not related': 'NONE',
    'Unlikely related': 'REMOTE',
    'Possibly related': 'POSSIBLE',
    'Probably related': 'PROBABLE'
}

# Apply mappings
ae['AESEV'] = ae['SEVERITY'].apply(lambda x: sev_map.get(x, '') if pd.notna(x) else '')
ae['AESER'] = ae['SERIOUS'].apply(lambda x: ser_map.get(x, '') if pd.notna(x) else '')
ae['AEREL'] = ae['RELATIONSHIP'].apply(lambda x: rel_map.get(x, '') if pd.notna(x) else '')

# Text fields
def safe_upper(s):
    if pd.isna(s):
        return ''
    return str(s).strip().upper()

ae['AETERM'] = ae['AE_VERBATIM'].apply(safe_upper)
ae['AEOUT'] = ae['OUTCOME'].apply(safe_upper)
ae['AEDECOD'] = ae['CODED_PT']
ae['AEBODSYS'] = ae['CODED_SOC']
ae['AESPID'] = ae['RECID']

# Date parsing
def parse_raw_date(s):
    if pd.isna(s) or s == '':
        return ''
    s = str(s).strip()
    if len(s) < 9:
        return ''
    day = s[0:2].upper()
    month = s[2:5].upper()
    year = s[5:9]
    month_map = {
        'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
        'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
        'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
    }
    if month == 'UNK':
        return year
    elif day == 'UN':
        if month in month_map:
            return f"{year}-{month_map[month]}"
        else:
            return year
    else:
        if month in month_map:
            return f"{year}-{month_map[month]}-{day}"
        else:
            return year

ae['AESTDTC'] = ae['AESTDAT'].apply(parse_raw_date)

# AEENDTC: empty if AEONGO == Y, otherwise parse AEENDAT
ae['AEONGO_STR'] = ae['AEONGO'].astype(str).str.strip().str.upper()
ae['AEENDTC'] = ae.apply(
    lambda row: '' if row['AEONGO_STR'] == 'Y' else parse_raw_date(row['AEENDAT']),
    axis=1
)

# Merge with DM to get RFSTDTC
ae = ae.merge(dm[['USUBJID', 'RFSTDTC']], on='USUBJID', how='left')

# Study day calculation
def compute_study_day(date_str, rfstdtc_str):
    if pd.isna(date_str) or pd.isna(rfstdtc_str) or date_str == '' or rfstdtc_str == '':
        return ''
    if len(str(date_str)) != 10 or len(str(rfstdtc_str)) != 10:
        return ''
    try:
        d = datetime.strptime(str(date_str), '%Y-%m-%d')
        r = datetime.strptime(str(rfstdtc_str), '%Y-%m-%d')
        if d >= r:
            return (d - r).days + 1
        else:
            return (d - r).days
    except:
        return ''

ae['AESTDY'] = ae.apply(lambda row: compute_study_day(row['AESTDTC'], row['RFSTDTC']), axis=1)
ae['AEENDY'] = ae.apply(lambda row: compute_study_day(row['AEENDTC'], row['RFSTDTC']), axis=1)

# Sort for AESEQ
ae = ae.sort_values(['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'])
ae['AESEQ'] = ae.groupby('USUBJID').cumcount() + 1

# Output columns
ae['STUDYID'] = 'ALX-919'
ae['DOMAIN'] = 'AE'
out_cols = [
    'STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID', 'AETERM', 'AEDECOD',
    'AEBODSYS', 'AESEV', 'AESER', 'AEREL', 'AEOUT', 'AESTDTC', 'AEENDTC',
    'AESTDY', 'AEENDY'
]
out = ae[out_cols].copy()

# Replace any remaining NaN with empty string
for col in out_cols:
    out[col] = out[col].fillna('')

# Write output CSV
out.to_csv('output/ae.csv', index=False)
