import os
from datetime import datetime

import pandas as pd

STUDYID = 'ALX-919'

MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05', 'JUN': '06',
    'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
}

SEV_MAP = {'1': 'MILD', '2': 'MODERATE', '3': 'SEVERE'}
SER_MAP = {'YES': 'Y', 'NO': 'N'}
REL_MAP = {
    'NOT RELATED': 'NONE',
    'UNLIKELY RELATED': 'REMOTE',
    'POSSIBLY RELATED': 'POSSIBLE',
    'PROBABLY RELATED': 'PROBABLE',
}

OUTPUT_COLS = ['STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID', 'AETERM',
               'AEDECOD', 'AEBODSYS', 'AESEV', 'AESER', 'AEREL', 'AEOUT',
               'AESTDTC', 'AEENDTC', 'AESTDY', 'AEENDY']


def to_iso(raw):
    """DDMONYYYY -> ISO 8601. UN day / UNK month yield partial dates (YYYY-MM / YYYY)."""
    s = str(raw).strip().upper()
    if len(s) != 9:
        return ''
    dd, mon, yyyy = s[:2], s[2:5], s[5:9]
    if not yyyy.isdigit():
        return ''
    if mon == 'UNK':
        return yyyy
    mm = MONTHS.get(mon)
    if mm is None:
        return ''
    if dd == 'UN':
        return '{}-{}'.format(yyyy, mm)
    if dd.isdigit():
        return '{}-{}-{}'.format(yyyy, mm, dd)
    return '{}-{}'.format(yyyy, mm)


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC (no day 0); blank if either date is partial/missing."""
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ''
    try:
        d = datetime.strptime(dtc, '%Y-%m-%d')
        r = datetime.strptime(rfstdtc, '%Y-%m-%d')
    except ValueError:
        return ''
    diff = (d - r).days
    return str(diff + 1) if diff >= 0 else str(diff)


def main():
    dm = pd.read_csv('input/dm.csv', dtype=str, keep_default_na=False)
    raw = pd.read_csv('input/raw_ae.csv', dtype=str, keep_default_na=False)
    for df in (dm, raw):
        for c in df.columns:
            df[c] = df[c].str.strip()

    # Keep only the latest saved version of each record (SUBJECT + RECID).
    raw['_ver'] = pd.to_numeric(raw['VERSION'], errors='coerce').fillna(-1)
    raw = raw.sort_values('_ver', kind='mergesort')
    raw = raw.drop_duplicates(subset=['SUBJECT', 'RECID'], keep='last')

    # Drop deleted records and "no adverse events" placeholder pages.
    raw = raw[raw['RECORD_STATUS'].str.upper() != 'DELETED']
    raw = raw[raw['AEYN'].str.upper() != 'NO']

    # Standard mappings.
    raw['STUDYID'] = STUDYID
    raw['DOMAIN'] = 'AE'
    raw['USUBJID'] = STUDYID + '-' + raw['SUBJECT']
    raw['AESPID'] = raw['RECID']
    raw['AETERM'] = raw['AE_VERBATIM'].str.upper()
    raw['AEDECOD'] = raw['CODED_PT']
    raw['AEBODSYS'] = raw['CODED_SOC']
    raw['AESEV'] = raw['SEVERITY'].map(SEV_MAP).fillna('')
    raw['AESER'] = raw['SERIOUS'].str.upper().map(SER_MAP).fillna('')
    raw['AEREL'] = raw['RELATIONSHIP'].str.upper().map(REL_MAP).fillna('')
    raw['AEOUT'] = raw['OUTCOME'].str.upper()

    # Dates in ISO 8601; partial dates keep only known parts, never imputed.
    raw['AESTDTC'] = raw['AESTDAT'].apply(to_iso)
    raw['AEENDTC'] = raw['AEENDAT'].apply(to_iso)
    raw.loc[raw['AEONGO'].str.upper() == 'Y', 'AEENDTC'] = ''

    # Study days relative to each subject's RFSTDTC from DM.
    rfst = dm.drop_duplicates('USUBJID').set_index('USUBJID')['RFSTDTC']
    raw['_rfst'] = raw['USUBJID'].map(rfst).fillna('')
    raw['AESTDY'] = [study_day(d, r) for d, r in zip(raw['AESTDTC'], raw['_rfst'])]
    raw['AEENDY'] = [study_day(d, r) for d, r in zip(raw['AEENDTC'], raw['_rfst'])]

    # AESEQ: within each subject, sort by AESTDTC (as text), then AETERM, then AESPID.
    raw = raw.sort_values(['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'], kind='mergesort')
    raw['AESEQ'] = raw.groupby('USUBJID', sort=False).cumcount() + 1

    out = raw[OUTPUT_COLS]
    os.makedirs('output', exist_ok=True)
    out.to_csv('output/ae.csv', index=False)


if __name__ == '__main__':
    main()
