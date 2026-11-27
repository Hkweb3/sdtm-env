import os
from datetime import date

import pandas as pd

STUDYID = 'DRX-647'

MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05',
    'JUN': '06', 'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10',
    'NOV': '11', 'DEC': '12',
}


def to_iso(raw):
    """Convert 'DD MON YYYY' (day 'UN', month 'UNK' allowed) to an ISO 8601
    partial date: YYYY-MM-DD, YYYY-MM or YYYY. Never impute missing parts."""
    s = '' if raw is None else str(raw).strip().upper()
    if not s:
        return ''
    parts = s.split()
    if len(parts) != 3:
        return ''
    day, mon, year = parts
    if not year.isdigit():
        return ''
    mm = MONTHS.get(mon, '')
    dd = day.zfill(2) if day.isdigit() else ''
    if mm == '':
        return year
    if dd == '':
        return '{}-{}'.format(year, mm)
    return '{}-{}-{}'.format(year, mm, dd)


def study_day(dtc, rfstdtc):
    """SDTM --DY relative to RFSTDTC: date - RFSTDTC + 1 when on/after the
    reference date, otherwise date - RFSTDTC (no day 0). Blank if either
    date is partial or missing."""
    if not dtc or not rfstdtc or len(dtc) != 10 or len(rfstdtc) != 10:
        return ''
    try:
        d = date.fromisoformat(dtc)
        r = date.fromisoformat(rfstdtc)
    except ValueError:
        return ''
    diff = (d - r).days
    return str(diff + 1) if diff >= 0 else str(diff)


def main():
    dm = pd.read_csv(os.path.join('input', 'dm.csv'), dtype=str,
                     keep_default_na=False)
    raw = pd.read_csv(os.path.join('input', 'raw_mh.csv'), dtype=str,
                      keep_default_na=False)

    # RFSTDTC per subject from the finished DM domain
    rfst = dm.set_index('USUBJID')['RFSTDTC'].to_dict()

    df = pd.DataFrame()
    df['STUDYID'] = STUDYID
    df['DOMAIN'] = 'MH'
    # raw SUBJECT is <site>-<subject>; USUBJID = STUDYID-SITE-SUBJECT
    df['USUBJID'] = raw['SUBJECT'].str.strip().map(
        lambda s: '{}-{}'.format(STUDYID, s))
    df['MHSPID'] = raw['RECID'].str.strip()
    df['MHTERM'] = raw['MH_VERBATIM'].str.strip()
    df['MHDECOD'] = raw['CODED_PT'].str.strip()
    df['MHCAT'] = raw['CATEGORY'].str.strip().str.upper()
    df['MHBODSYS'] = raw['CODED_SOC'].str.strip()
    df['MHDTC'] = raw['VISIT_DATE'].map(to_iso)
    df['MHSTDTC'] = raw['MHSTDAT'].map(to_iso)

    # Study day of the collection date (MHDTC)
    df['MHDY'] = [study_day(d, rfst.get(u, ''))
                  for d, u in zip(df['MHDTC'], df['USUBJID'])]

    # Sort within subject by MHCAT, MHSTDTC (as text), MHTERM, MHSPID,
    # then number records 1, 2, 3, ... per subject
    df = df.sort_values(['USUBJID', 'MHCAT', 'MHSTDTC', 'MHTERM', 'MHSPID'],
                        kind='mergesort').reset_index(drop=True)
    df['MHSEQ'] = df.groupby('USUBJID').cumcount() + 1

    cols = ['STUDYID', 'DOMAIN', 'USUBJID', 'MHSEQ', 'MHSPID', 'MHTERM',
            'MHDECOD', 'MHCAT', 'MHBODSYS', 'MHDTC', 'MHSTDTC', 'MHDY']
    out = df[cols]

    os.makedirs('output', exist_ok=True)
    out.to_csv(os.path.join('output', 'mh.csv'), index=False)


if __name__ == '__main__':
    main()
