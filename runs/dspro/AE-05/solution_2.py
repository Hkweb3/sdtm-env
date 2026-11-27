import pandas as pd
from pathlib import Path
from datetime import datetime

input_dir = Path('./input')
output_dir = Path('./output')
output_dir.mkdir(parents=True, exist_ok=True)

dm = pd.read_csv(input_dir / 'dm.csv', dtype=str, keep_default_na=False)
raw = pd.read_csv(input_dir / 'raw_ae.csv', dtype=str, keep_default_na=False)

# Strip whitespace from all string columns
for df in (dm, raw):
    for col in df.columns:
        df[col] = df[col].str.strip()

# Drop deleted and placeholder rows
raw = raw[raw['RECORD_STATUS'] != 'DELETED']
raw = raw[raw['AEYN'].str.upper() != 'NO']

# Construct USUBJID
site_subject = raw['SUBJECT'].str.split('-', n=1, expand=True)
raw['USUBJID'] = 'BRV-836-' + site_subject[0] + '-' + site_subject[1]

# Keep only subjects present in DM
dm_usubjids = set(dm['USUBJID'])
raw = raw[raw['USUBJID'].isin(dm_usubjids)].copy()

# RFSTDTC lookup
rf_map = dict(zip(dm['USUBJID'], dm['RFSTDTC']))
raw['RFSTDTC'] = raw['USUBJID'].map(rf_map)

month_map = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
}

def parse_dtc(value):
    if not value:
        return ''
    parts = value.split()
    if len(parts) != 3:
        return ''
    day_part, mon_part, year_part = parts
    mon_upper = mon_part.upper()

    if mon_upper == 'UNK':
        return year_part

    month = month_map.get(mon_upper)
    if not month:
        return ''

    if day_part.upper() == 'UN':
        return f"{year_part}-{month}"

    try:
        day = int(day_part)
    except ValueError:
        return ''

    return f"{year_part}-{month}-{day:02d}"

raw['AESTDTC'] = raw['AESTDAT'].apply(parse_dtc)
raw['AEENDTC'] = raw['AEENDAT'].apply(parse_dtc)

# Ongoing events have no end date
raw.loc[raw['AEONGO'].str.upper() == 'Y', 'AEENDTC'] = ''

# Map SDTM variables
raw['AETERM'] = raw['AE_VERBATIM'].str.upper()
raw['AEDECOD'] = raw['CODED_PT']
raw['AEBODSYS'] = raw['CODED_SOC']
raw['AESEV'] = raw['SEVERITY'].str.upper()
raw['AESER'] = raw['SERIOUS'].str.upper().map({'YES': 'Y', 'NO': 'N'}).fillna('')
raw['AEREL'] = raw['RELATIONSHIP'].map({
    'Not related': 'NONE',
    'Unlikely related': 'REMOTE',
    'Possibly related': 'POSSIBLE',
    'Probably related': 'PROBABLE'
}).fillna('')
raw['AEOUT'] = raw['OUTCOME'].str.upper()
raw['AESPID'] = raw['RECID']

def calc_dy(dtc, rfdtc):
    if not dtc or not rfdtc:
        return ''
    if len(dtc) != 10 or len(rfdtc) != 10:
        return ''
    try:
        dt = datetime.strptime(dtc, '%Y-%m-%d').date()
        rf = datetime.strptime(rfdtc, '%Y-%m-%d').date()
    except ValueError:
        return ''
    diff = (dt - rf).days
    if diff >= 0:
        return diff + 1
    return diff

raw['AESTDY'] = raw.apply(lambda row: calc_dy(row['AESTDTC'], row['RFSTDTC']), axis=1)
raw['AEENDY'] = raw.apply(lambda row: calc_dy(row['AEENDTC'], row['RFSTDTC']), axis=1)

# AESEQ based on sorting within subject
raw = raw.sort_values(['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'])
raw['AESEQ'] = raw.groupby('USUBJID').cumcount() + 1

# Output dataset
raw['STUDYID'] = 'BRV-836'
raw['DOMAIN'] = 'AE'

output_cols = [
    'STUDYID',
    'DOMAIN',
    'USUBJID',
    'AESEQ',
    'AESPID',
    'AETERM',
    'AEDECOD',
    'AEBODSYS',
    'AESEV',
    'AESER',
    'AEREL',
    'AEOUT',
    'AESTDTC',
    'AEENDTC',
    'AESTDY',
    'AEENDY'
]

raw[output_cols].to_csv(output_dir / 'ae.csv', index=False)
