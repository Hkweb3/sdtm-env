import os
from datetime import datetime

import pandas as pd

STUDYID = 'KVT-131'
DOMAIN = 'MH'

OUT_COLS = ['STUDYID', 'DOMAIN', 'USUBJID', 'MHSEQ', 'MHSPID', 'MHTERM',
            'MHDECOD', 'MHCAT', 'MHBODSYS', 'MHDTC', 'MHSTDTC', 'MHDY']

MONTHS = {'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05',
          'JUN': '06', 'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10',
          'NOV': '11', 'DEC': '12'}

CATEGORY_MAP = {
    'PD': 'PRIMARY DIAGNOSIS',
    'SPC': 'SIGNIFICANT PRE-EXISTING CONDITION',
    'HD': 'HISTORICAL DIAGNOSIS',
}


def to_iso(raw):
    """Convert DDMONYYYY to ISO 8601. Day 'UN' -> YYYY-MM, month 'UNK' -> YYYY.
    Never impute missing parts."""
    s = '' if pd.isna(raw) else str(raw).strip().upper()
    if not s:
        return ''
    if len(s) == 9:
        day, mon, year = s[0:2], s[2:5], s[5:9]
        if year.isdigit():
            if day == 'UN' and mon == 'UNK':
                return year
            if day == 'UN' and mon in MONTHS:
                return '{}-{}'.format(year, MONTHS[mon])
            if day.isdigit() and mon in MONTHS:
                return '{}-{}-{}'.format(year, MONTHS[mon], day)
    return s  # already ISO or unrecognised: pass through unchanged


def study_day(dtc, rfstdtc):
    """SDTM study day relative to RFSTDTC (no day 0). Blank if either date
    is partial or missing."""
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ''
    try:
        d = datetime.strptime(dtc, '%Y-%m-%d').date()
        r = datetime.strptime(rfstdtc, '%Y-%m-%d').date()
    except ValueError:
        return ''
    diff = (d - r).days
    return str(diff + 1) if diff >= 0 else str(diff)


def main():
    dm = pd.read_csv(os.path.join('input', 'dm.csv'), dtype=str).fillna('')
    raw = pd.read_csv(os.path.join('input', 'raw_mh.csv'), dtype=str).fillna('')
    dm.columns = [c.strip() for c in dm.columns]
    raw.columns = [c.strip() for c in raw.columns]

    rfstdtc_by_subj = dict(zip(dm['USUBJID'].str.strip(), dm['RFSTDTC'].str.strip()))

    records = []
    for _, r in raw.iterrows():
        usubjid = '{}-{}'.format(STUDYID, r['SUBJECT'].strip())
        mhdtc = to_iso(r['VISIT_DATE'])
        records.append({
            'STUDYID': STUDYID,
            'DOMAIN': DOMAIN,
            'USUBJID': usubjid,
            'MHSEQ': 0,  # placeholder, assigned after sorting
            'MHSPID': r['RECID'].strip(),
            'MHTERM': r['MH_VERBATIM'].strip(),
            'MHDECOD': r['CODED_PT'].strip(),
            'MHCAT': CATEGORY_MAP.get(r['CATEGORY'].strip(), r['CATEGORY'].strip()),
            'MHBODSYS': r['CODED_SOC'].strip(),
            'MHDTC': mhdtc,
            'MHSTDTC': to_iso(r['MHSTDAT']),
            'MHDY': study_day(mhdtc, rfstdtc_by_subj.get(usubjid, '')),
        })

    mh = pd.DataFrame(records, columns=OUT_COLS)

    # MHSEQ: 1..n per subject after sorting by MHCAT, MHSTDTC (as text),
    # MHTERM, MHSPID
    mh = mh.sort_values(['USUBJID', 'MHCAT', 'MHSTDTC', 'MHTERM', 'MHSPID'],
                        kind='mergesort').reset_index(drop=True)
    mh['MHSEQ'] = mh.groupby('USUBJID').cumcount() + 1

    os.makedirs('output', exist_ok=True)
    mh.to_csv(os.path.join('output', 'mh.csv'), index=False)


if __name__ == '__main__':
    main()
