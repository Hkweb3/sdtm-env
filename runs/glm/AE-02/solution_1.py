import os
from datetime import datetime

import pandas as pd

STUDYID = 'ALX-878'

MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05', 'JUN': '06',
    'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
}

AEREL_MAP = {
    'not related': 'NONE',
    'unlikely related': 'REMOTE',
    'possibly related': 'POSSIBLE',
    'probably related': 'PROBABLE',
}

AESER_MAP = {'yes': 'Y', 'no': 'N'}

OUTPUT_COLS = ['STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID', 'AETERM',
               'AEDECOD', 'AEBODSYS', 'AESEV', 'AESER', 'AEREL', 'AEOUT',
               'AESTDTC', 'AEENDTC', 'AESTDY', 'AEENDY']


def to_iso(raw):
    """Convert DDMONYYYY (day 'UN', month 'UNK' allowed) to ISO 8601.

    Keeps only the known parts: YYYY-MM-DD, YYYY-MM or YYYY. Never imputes.
    """
    s = '' if raw is None else str(raw).strip().upper()
    if len(s) != 9:
        return ''
    day, mon, year = s[:2], s[2:5], s[5:]
    if not (len(year) == 4 and year.isdigit()):
        return ''
    month = MONTHS.get(mon, '')
    d = day if day.isdigit() else ''
    if month and d:
        return '{}-{}-{}'.format(year, month, d)
    if month:
        return '{}-{}'.format(year, month)
    return year


def study_day(dtc, rfstdtc):
    """SDTM --DY relative to RFSTDTC (no day 0). Blank if either date is partial/missing."""
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ''
    try:
        delta = (datetime.strptime(dtc, '%Y-%m-%d').date()
                 - datetime.strptime(rfstdtc, '%Y-%m-%d').date()).days
    except ValueError:
        return ''
    return delta + 1 if delta >= 0 else delta


def main():
    dm = pd.read_csv(os.path.join('input', 'dm.csv'), dtype=str, keep_default_na=False)
    ae = pd.read_csv(os.path.join('input', 'raw_ae.csv'), dtype=str, keep_default_na=False)

    rfstdtc_by_usubjid = dict(zip(dm['USUBJID'].str.strip(), dm['RFSTDTC'].str.strip()))

    records = []
    for _, row in ae.iterrows():
        site, _, subj = str(row['SUBJECT']).strip().partition('-')
        usubjid = '{}-{}-{}'.format(STUDYID, site, subj)

        # Ongoing events have no end date.
        ongoing = str(row.get('AEONGO', '')).strip().upper() == 'Y'
        end_raw = '' if ongoing else row.get('AEENDAT', '')

        serious = str(row.get('SERIOUS', '')).strip().lower()
        rel = str(row.get('RELATIONSHIP', '')).strip().lower()

        records.append({
            'STUDYID': STUDYID,
            'DOMAIN': 'AE',
            'USUBJID': usubjid,
            'AESPID': str(row['RECID']).strip(),
            'AETERM': str(row['AE_VERBATIM']).strip().upper(),
            'AEDECOD': str(row['CODED_PT']).strip(),
            'AEBODSYS': str(row['CODED_SOC']).strip(),
            'AESEV': str(row['SEVERITY']).strip().upper(),
            'AESER': AESER_MAP.get(serious, ''),
            'AEREL': AEREL_MAP.get(rel, ''),
            'AEOUT': str(row['OUTCOME']).strip().upper(),
            'AESTDTC': to_iso(row.get('AESTDAT', '')),
            'AEENDTC': to_iso(end_raw),
            '_RFSTDTC': rfstdtc_by_usubjid.get(usubjid, ''),
        })

    ae_out = pd.DataFrame(records)

    # AESEQ: within each subject, sort by AESTDTC (as text), then AETERM, then AESPID.
    ae_out = ae_out.sort_values(['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'],
                                kind='mergesort')
    ae_out['AESEQ'] = ae_out.groupby('USUBJID').cumcount() + 1

    ae_out['AESTDY'] = [study_day(s, r)
                        for s, r in zip(ae_out['AESTDTC'], ae_out['_RFSTDTC'])]
    ae_out['AEENDY'] = [study_day(e, r)
                        for e, r in zip(ae_out['AEENDTC'], ae_out['_RFSTDTC'])]

    ae_out = ae_out[OUTPUT_COLS]

    os.makedirs('output', exist_ok=True)
    ae_out.to_csv(os.path.join('output', 'ae.csv'), index=False)


if __name__ == '__main__':
    main()
