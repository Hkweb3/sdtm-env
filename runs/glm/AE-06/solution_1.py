import os
import re
from datetime import date

import pandas as pd

STUDYID = 'PLX-650'
AE_IN = os.path.join('input', 'raw_ae.csv')
DM_IN = os.path.join('input', 'dm.csv')
AE_OUT = os.path.join('output', 'ae.csv')

MONTHS = {'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05',
          'JUN': '06', 'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10',
          'NOV': '11', 'DEC': '12'}

SER_MAP = {'yes': 'Y', 'no': 'N'}
REL_MAP = {'not related': 'NONE', 'unlikely related': 'REMOTE',
           'possibly related': 'POSSIBLE', 'probably related': 'PROBABLE'}

OUT_COLS = ['STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID', 'AETERM',
            'AEDECOD', 'AEBODSYS', 'AESEV', 'AESER', 'AEREL', 'AEOUT',
            'AESTDTC', 'AEENDTC', 'AESTDY', 'AEENDY']


def rawdate_to_iso(raw):
    """DDMONYYYY -> ISO 8601. 'UN' day / 'UNK' month stay partial; no imputation."""
    s = str(raw).strip().upper()
    if not s:
        return ''
    if re.fullmatch(r'\d{4}(-\d{2}(-\d{2})?)?', s):  # already ISO (defensive)
        return s
    m = re.fullmatch(r'(\d{2}|UN)([A-Z]{3}|UNK)(\d{4})', s)
    if not m:
        return ''
    d_part, m_part, y_part = m.groups()
    month = MONTHS.get(m_part, '')
    if not month:
        return y_part
    if d_part == 'UN':
        return y_part + '-' + month
    return '{}-{}-{:02d}'.format(y_part, month, int(d_part))


def iso_to_date(s):
    """datetime.date for a complete ISO date, else None."""
    s = str(s).strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
        try:
            return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
        except ValueError:
            return None
    return None


def study_day(dtc, rfstdtc):
    """--DY relative to RFSTDTC; no day 0; blank if either date is partial/missing."""
    d = iso_to_date(dtc)
    r = iso_to_date(rfstdtc)
    if d is None or r is None:
        return ''
    delta = (d - r).days
    return delta + 1 if delta >= 0 else delta


def main():
    os.makedirs('output', exist_ok=True)

    ae = pd.read_csv(AE_IN, dtype=str, keep_default_na=False)
    dm = pd.read_csv(DM_IN, dtype=str, keep_default_na=False)

    # Export holds every saved version: keep highest VERSION per SUBJECT + RECID.
    ae['_VER'] = pd.to_numeric(ae['VERSION'], errors='coerce').fillna(-1)
    ae = (ae.sort_values('_VER', kind='mergesort')
            .drop_duplicates(subset=['SUBJECT', 'RECID'], keep='last')
            .drop(columns='_VER'))

    # USUBJID = STUDYID-SITE-SUBJECT (raw SUBJECT is <site>-<subject>).
    parts = ae['SUBJECT'].str.strip().str.split('-', n=1, expand=True)
    site = parts[0].fillna('').str.strip() if 0 in parts.columns else pd.Series('', index=ae.index)
    subj = parts[1].fillna('').str.strip() if 1 in parts.columns else pd.Series('', index=ae.index)
    ae['USUBJID'] = STUDYID + '-' + site + '-' + subj

    # RFSTDTC from the finished DM domain.
    rfst = {str(k).strip(): str(v).strip() for k, v in zip(dm['USUBJID'], dm['RFSTDTC'])}
    ae['RFSTDTC'] = ae['USUBJID'].map(rfst).fillna('')

    # --DTC (ISO 8601; partial dates keep only known parts).
    ae['AESTDTC'] = ae['AESTDAT'].map(rawdate_to_iso)
    ongoing = ae['AEONGO'].str.strip().str.upper().eq('Y')
    ae['AEENDTC'] = ''
    ae.loc[~ongoing, 'AEENDTC'] = ae.loc[~ongoing, 'AEENDAT'].map(rawdate_to_iso)

    # Study days.
    ae['AESTDY'] = [study_day(s, r) for s, r in zip(ae['AESTDTC'], ae['RFSTDTC'])]
    ae['AEENDY'] = ['' if o else study_day(e, r)
                    for o, e, r in zip(ongoing, ae['AEENDTC'], ae['RFSTDTC'])]

    # Direct mappings.
    ae['STUDYID'] = STUDYID
    ae['DOMAIN'] = 'AE'
    ae['AESPID'] = ae['RECID'].str.strip()
    ae['AETERM'] = ae['AE_VERBATIM'].str.strip().str.upper()
    ae['AEDECOD'] = ae['CODED_PT'].str.strip()
    ae['AEBODSYS'] = ae['CODED_SOC'].str.strip()
    ae['AESEV'] = ae['SEVERITY'].str.strip().str.upper()
    ae['AESER'] = ae['SERIOUS'].str.strip().str.lower().map(SER_MAP).fillna('')
    ae['AEREL'] = ae['RELATIONSHIP'].str.strip().str.lower().map(REL_MAP).fillna('')
    ae['AEOUT'] = ae['OUTCOME'].str.strip().str.upper()

    # AESEQ: per subject, after sorting by AESTDTC (as text), AETERM, AESPID.
    ae = ae.sort_values(['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'],
                        kind='mergesort').reset_index(drop=True)
    ae['AESEQ'] = ae.groupby('USUBJID').cumcount() + 1

    ae[OUT_COLS].to_csv(AE_OUT, index=False)


if __name__ == '__main__':
    main()
