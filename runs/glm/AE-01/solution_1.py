import os
from datetime import datetime

import pandas as pd

STUDYID = 'PLX-785'
DOMAIN = 'AE'

MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05', 'JUN': '06',
    'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
}

SER_MAP = {'yes': 'Y', 'no': 'N'}
REL_MAP = {
    'not related': 'NONE',
    'unlikely related': 'REMOTE',
    'possibly related': 'POSSIBLE',
    'probably related': 'PROBABLE',
}

OUTPUT_COLUMNS = [
    'STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID', 'AETERM', 'AEDECOD',
    'AEBODSYS', 'AESEV', 'AESER', 'AEREL', 'AEOUT', 'AESTDTC', 'AEENDTC',
    'AESTDY', 'AEENDY',
]


def to_iso(raw):
    """'DD MON YYYY' (unknown day 'UN', unknown month 'UNK') -> ISO 8601 partial date."""
    s = '' if raw is None else str(raw).strip().upper()
    if not s:
        return ''
    parts = s.split()
    if len(parts) != 3:
        return ''
    day, mon, year = parts
    if len(year) != 4 or not year.isdigit():
        return ''
    mm = MONTHS.get(mon, '')
    if not mm:
        return year
    if day == 'UN' or not day.isdigit():
        return '{}-{}'.format(year, mm)
    return '{}-{}-{:02d}'.format(year, mm, int(day))


def study_day(dtc, rfstdtc):
    """SDTM study day relative to RFSTDTC; blank if either date is partial or missing."""
    if not dtc or not rfstdtc or len(dtc) != 10 or len(rfstdtc) != 10:
        return ''
    try:
        d = datetime.strptime(dtc, '%Y-%m-%d').date()
        r = datetime.strptime(rfstdtc, '%Y-%m-%d').date()
    except ValueError:
        return ''
    diff = (d - r).days
    return diff + 1 if diff >= 0 else diff


def main():
    dm = pd.read_csv(os.path.join('input', 'dm.csv'), dtype=str, keep_default_na=False)
    ae = pd.read_csv(os.path.join('input', 'raw_ae.csv'), dtype=str, keep_default_na=False)

    # USUBJID = STUDYID-SITE-SUBJECT (raw SUBJECT is '<site>-<subject>')
    ae['USUBJID'] = STUDYID + '-' + ae['SUBJECT'].astype(str).str.strip()

    # Attach RFSTDTC from the finished DM domain
    rfst = dm[['USUBJID', 'RFSTDTC']].drop_duplicates(subset='USUBJID')
    ae = ae.merge(rfst, on='USUBJID', how='left')
    rfstdtc = ae['RFSTDTC'].fillna('')

    out = pd.DataFrame(index=ae.index)
    out['STUDYID'] = STUDYID
    out['DOMAIN'] = DOMAIN
    out['USUBJID'] = ae['USUBJID']
    out['AESPID'] = ae['RECID'].astype(str).str.strip()
    out['AETERM'] = ae['AE_VERBATIM'].astype(str).str.strip().str.upper()
    out['AEDECOD'] = ae['CODED_PT'].astype(str).str.strip()
    out['AEBODSYS'] = ae['CODED_SOC'].astype(str).str.strip()
    out['AESEV'] = ae['SEVERITY'].astype(str).str.strip().str.upper()
    out['AESER'] = ae['SERIOUS'].astype(str).str.strip().str.lower().map(SER_MAP).fillna('')
    out['AEREL'] = ae['RELATIONSHIP'].astype(str).str.strip().str.lower().map(REL_MAP).fillna('')
    out['AEOUT'] = ae['OUTCOME'].astype(str).str.strip().str.upper()

    # Dates (never impute missing day or month)
    out['AESTDTC'] = ae['AESTDAT'].map(to_iso)
    ongoing = ae['AEONGO'].astype(str).str.strip().str.upper().eq('Y')
    end_source = ae['AEENDAT'].where(~ongoing, '')  # ongoing events have no end date
    out['AEENDTC'] = end_source.map(to_iso)

    # Study days (blank when either date is partial or missing)
    out['AESTDY'] = [study_day(d, r) for d, r in zip(out['AESTDTC'], rfstdtc)]
    out['AEENDY'] = [study_day(d, r) for d, r in zip(out['AEENDTC'], rfstdtc)]

    # AESEQ: 1..n per subject after sorting by AESTDTC (as text), AETERM, AESPID
    out = out.sort_values(by=['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'],
                          kind='mergesort').reset_index(drop=True)
    out['AESEQ'] = out.groupby('USUBJID').cumcount() + 1

    out = out[OUTPUT_COLUMNS]

    os.makedirs('output', exist_ok=True)
    out.to_csv(os.path.join('output', 'ae.csv'), index=False)


if __name__ == '__main__':
    main()
