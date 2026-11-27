import os
from datetime import date

import pandas as pd

MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
}


def to_iso(value):
    """Convert 'DD MON YYYY' (UN day / UNK month for unknown parts) to
    ISO 8601, keeping only the known parts (YYYY-MM-DD, YYYY-MM or YYYY)."""
    if value is None or pd.isna(value):
        return ''
    parts = str(value).strip().split()
    if len(parts) != 3:
        return ''
    day, mon, year = parts[0].upper(), parts[1].upper(), parts[2].strip()
    if mon == 'UNK':
        return year
    mm = MONTHS.get(mon)
    if mm is None:
        return ''
    if day == 'UN':
        return f'{year}-{mm}'
    return f'{year}-{mm}-{day.zfill(2)}'


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC; blank if either date is partial/missing."""
    if not dtc or not rfstdtc or len(dtc) != 10 or len(rfstdtc) != 10:
        return ''
    d = date.fromisoformat(dtc)
    r = date.fromisoformat(rfstdtc)
    delta = (d - r).days
    return str(delta + 1) if delta >= 0 else str(delta)


dm = pd.read_csv('input/dm.csv', dtype=str)
raw = pd.read_csv('input/raw_mh.csv', dtype=str)

rfstdtc = dict(zip(dm['USUBJID'], dm['RFSTDTC']))

out = pd.DataFrame({
    'STUDYID': 'DRX-647',
    'DOMAIN': 'MH',
    'USUBJID': 'DRX-647-' + raw['SUBJECT'].str.strip(),
    'MHSPID': raw['RECID'],
    'MHTERM': raw['MH_VERBATIM'],
    'MHDECOD': raw['CODED_PT'],
    'MHCAT': raw['CATEGORY'].str.upper(),
    'MHBODSYS': raw['CODED_SOC'],
    'MHDTC': raw['VISIT_DATE'].map(to_iso),
    'MHSTDTC': raw['MHSTDAT'].map(to_iso),
})
out['MHDY'] = [
    study_day(dtc, rfstdtc.get(usubjid, ''))
    for dtc, usubjid in zip(out['MHDTC'], out['USUBJID'])
]
out = out.fillna('')

out = out.sort_values(
    ['USUBJID', 'MHCAT', 'MHSTDTC', 'MHTERM', 'MHSPID'],
    kind='mergesort',
).reset_index(drop=True)
out['MHSEQ'] = out.groupby('USUBJID').cumcount() + 1

columns = [
    'STUDYID', 'DOMAIN', 'USUBJID', 'MHSEQ', 'MHSPID', 'MHTERM',
    'MHDECOD', 'MHCAT', 'MHBODSYS', 'MHDTC', 'MHSTDTC', 'MHDY',
]
out = out[columns]

os.makedirs('output', exist_ok=True)
out.to_csv('output/mh.csv', index=False)
