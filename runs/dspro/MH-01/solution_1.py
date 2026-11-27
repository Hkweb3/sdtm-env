import os
import pandas as pd
from datetime import datetime

MONTH_MAP = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
}

def parse_dtc(value):
    """Convert raw date like DD MON YYYY to ISO 8601. Unknown day=UN, unknown month=UNK."""
    s = str(value).strip()
    if not s:
        return ''
    parts = s.split()
    if len(parts) != 3:
        return ''
    day, mon, year = parts
    year = year.strip()
    mon = mon.strip().upper()
    day = day.strip().upper()

    if mon == 'UNK':
        return year

    month_num = MONTH_MAP.get(mon)
    if month_num is None:
        return year

    if day in ('UN', 'UNK'):
        return f"{year}-{month_num}"

    try:
        return f"{year}-{month_num}-{int(day):02d}"
    except ValueError:
        return f"{year}-{month_num}"

def compute_mhdy(mhdtc, rfstdtc):
    """Calculate study day of MHDTC relative to RFSTDTC."""
    if not mhdtc or not rfstdtc:
        return ''
    try:
        d = datetime.strptime(mhdtc, '%Y-%m-%d').date()
        r = datetime.strptime(rfstdtc, '%Y-%m-%d').date()
    except ValueError:
        return ''
    diff = (d - r).days
    if diff >= 0:
        return str(diff + 1)
    return str(diff)

def main():
    raw = pd.read_csv('input/raw_mh.csv', dtype=str, keep_default_na=False)
    dm = pd.read_csv('input/dm.csv', dtype=str, keep_default_na=False)

    for col in raw.columns:
        raw[col] = raw[col].str.strip()
    for col in dm.columns:
        dm[col] = dm[col].str.strip()

    def make_usubjid(subject):
        s = str(subject).strip()
        if '-' in s:
            site, subj = s.split('-', 1)
            return f"DRX-647-{site.strip()}-{subj.strip()}"
        return f"DRX-647-{s}"

    raw['USUBJID'] = raw['SUBJECT'].apply(make_usubjid)

    df = raw.merge(dm[['USUBJID', 'RFSTDTC']], on='USUBJID', how='left')
    df['RFSTDTC'] = df['RFSTDTC'].fillna('')

    df['STUDYID'] = 'DRX-647'
    df['DOMAIN'] = 'MH'
    df['MHSPID'] = df['RECID'].str.strip()
    df['MHTERM'] = df['MH_VERBATIM'].str.strip()
    df['MHDECOD'] = df['CODED_PT'].str.strip()
    df['MHBODSYS'] = df['CODED_SOC'].str.strip()
    df['MHCAT'] = df['CATEGORY'].str.upper().str.strip()

    df['MHSTDTC'] = df['MHSTDAT'].apply(parse_dtc)
    df['MHDTC'] = df['VISIT_DATE'].apply(parse_dtc)
    df['MHDY'] = df.apply(lambda row: compute_mhdy(row['MHDTC'], row['RFSTDTC']), axis=1)

    df = df.sort_values(
        ['USUBJID', 'MHCAT', 'MHSTDTC', 'MHTERM', 'MHSPID'],
        kind='mergesort'
    )
    df['MHSEQ'] = df.groupby('USUBJID').cumcount() + 1

    df = df.sort_values(['USUBJID', 'MHSEQ'], kind='mergesort')

    out_cols = [
        'STUDYID', 'DOMAIN', 'USUBJID', 'MHSEQ', 'MHSPID', 'MHTERM',
        'MHDECOD', 'MHCAT', 'MHBODSYS', 'MHDTC', 'MHSTDTC', 'MHDY'
    ]
    out = df[out_cols]

    os.makedirs('output', exist_ok=True)
    out.to_csv('output/mh.csv', index=False)

if __name__ == '__main__':
    main()
