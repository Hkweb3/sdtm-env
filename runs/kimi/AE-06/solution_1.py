import os
from datetime import datetime

import pandas as pd

MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05',
    'JUN': '06', 'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10',
    'NOV': '11', 'DEC': '12',
}

REL_MAP = {
    'not related': 'NONE',
    'unlikely related': 'REMOTE',
    'possibly related': 'POSSIBLE',
    'probably related': 'PROBABLE',
}


def parse_raw_date(value):
    """Convert DDMONYYYY (UN day / UNK month) to ISO 8601, keeping only known parts."""
    if pd.isna(value) or str(value).strip() == '':
        return ''
    s = str(value).strip().upper()
    day, month, year = s[0:2], s[2:5], s[5:9]
    if month == 'UNK':
        return year
    mm = MONTHS.get(month)
    if mm is None:
        return ''
    if day == 'UN':
        return f'{year}-{mm}'
    return f'{year}-{mm}-{day}'


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC; blank if either date is partial/missing."""
    if dtc is None or pd.isna(dtc) or len(str(dtc)) != 10:
        return ''
    if rfstdtc is None or pd.isna(rfstdtc) or len(str(rfstdtc).strip()) != 10:
        return ''
    d = datetime.strptime(str(dtc), '%Y-%m-%d').date()
    r = datetime.strptime(str(rfstdtc).strip(), '%Y-%m-%d').date()
    diff = (d - r).days
    if diff >= 0:
        diff += 1
    return str(diff)


# ---- Read inputs ---------------------------------------------------------
ae = pd.read_csv('input/raw_ae.csv', dtype=str).fillna('')
dm = pd.read_csv('input/dm.csv', dtype=str).fillna('')

# ---- Keep only the highest VERSION per SUBJECT + RECID -------------------
ae['_ver'] = pd.to_numeric(ae['VERSION'], errors='coerce')
ae = (ae.sort_values('_ver', kind='mergesort')
        .drop_duplicates(subset=['SUBJECT', 'RECID'], keep='last'))

# ---- Identifiers ---------------------------------------------------------
ae['USUBJID'] = 'PLX-650-' + ae['SUBJECT'].str.strip()
ae['AESPID'] = ae['RECID'].str.strip()

# ---- Dates ---------------------------------------------------------------
ae['AESTDTC'] = ae['AESTDAT'].map(parse_raw_date)
ae['AEENDTC'] = ae['AEENDAT'].map(parse_raw_date)
ae.loc[ae['AEONGO'].str.strip().str.upper() == 'Y', 'AEENDTC'] = ''

# ---- Study days (need RFSTDTC from DM) -----------------------------------
ae = ae.merge(dm[['USUBJID', 'RFSTDTC']], on='USUBJID', how='left')
ae['AESTDY'] = [study_day(d, r) for d, r in zip(ae['AESTDTC'], ae['RFSTDTC'])]
ae['AEENDY'] = [study_day(d, r) for d, r in zip(ae['AEENDTC'], ae['RFSTDTC'])]

# ---- Straight mappings ---------------------------------------------------
ae['AETERM'] = ae['AE_VERBATIM'].str.strip().str.upper()
ae['AEDECOD'] = ae['CODED_PT'].str.strip()
ae['AEBODSYS'] = ae['CODED_SOC'].str.strip()
ae['AESEV'] = ae['SEVERITY'].str.strip().str.upper()
ae['AESER'] = (ae['SERIOUS'].str.strip().str.title()
               .map({'Yes': 'Y', 'No': 'N'}).fillna(''))
ae['AEREL'] = (ae['RELATIONSHIP'].str.strip().str.lower()
               .map(REL_MAP).fillna(''))
ae['AEOUT'] = ae['OUTCOME'].str.strip().str.upper()

# ---- AESEQ: per subject, sorted by AESTDTC (text), AETERM, AESPID --------
ae = ae.sort_values(['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'],
                    kind='mergesort')
ae['AESEQ'] = ae.groupby('USUBJID').cumcount() + 1

# ---- Assemble and write output -------------------------------------------
out = pd.DataFrame({
    'STUDYID': 'PLX-650',
    'DOMAIN': 'AE',
    'USUBJID': ae['USUBJID'],
    'AESEQ': ae['AESEQ'],
    'AESPID': ae['AESPID'],
    'AETERM': ae['AETERM'],
    'AEDECOD': ae['AEDECOD'],
    'AEBODSYS': ae['AEBODSYS'],
    'AESEV': ae['AESEV'],
    'AESER': ae['AESER'],
    'AEREL': ae['AEREL'],
    'AEOUT': ae['AEOUT'],
    'AESTDTC': ae['AESTDTC'],
    'AEENDTC': ae['AEENDTC'],
    'AESTDY': ae['AESTDY'],
    'AEENDY': ae['AEENDY'],
})

os.makedirs('output', exist_ok=True)
out.to_csv('output/ae.csv', index=False)
