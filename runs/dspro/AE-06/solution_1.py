import pandas as pd
import os
from datetime import datetime

MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
}

def parse_dtc(value):
    if pd.isna(value):
        return ''
    s = str(value).strip()
    if len(s) < 8:
        return ''

    year = s[-4:]
    mon = s[-7:-4].upper()
    day = s[:-7].upper()

    if mon in MONTHS:
        if day != 'UN':
            return f"{year}-{MONTHS[mon]}-{day.zfill(2)}"
        return f"{year}-{MONTHS[mon]}"

    return year

def calc_study_day(dtc, rf):
    if pd.isna(dtc) or pd.isna(rf) or dtc == '' or rf == '':
        return ''
    dtc_s = str(dtc)
    rf_s = str(rf)
    if len(dtc_s) < 10 or len(rf_s) < 10:
        return ''

    try:
        d = datetime.strptime(dtc_s[:10], '%Y-%m-%d').date()
        r = datetime.strptime(rf_s[:10], '%Y-%m-%d').date()
    except ValueError:
        return ''

    if d >= r:
        return (d - r).days + 1
    return (d - r).days

def main():
    os.makedirs('output', exist_ok=True)

    raw = pd.read_csv('input/raw_ae.csv', dtype=str, keep_default_na=False)
    dm = pd.read_csv('input/dm.csv', dtype=str, keep_default_na=False)

    raw['VERSION'] = pd.to_numeric(raw['VERSION'], errors='coerce').fillna(0).astype(int)
    raw = raw.loc[raw.groupby(['SUBJECT', 'RECID'], sort=False)['VERSION'].idxmax()].reset_index(drop=True)

    rel_map = {
        'NOT RELATED': 'NONE',
        'UNLIKELY RELATED': 'REMOTE',
        'POSSIBLY RELATED': 'POSSIBLE',
        'PROBABLY RELATED': 'PROBABLE'
    }

    out = pd.DataFrame({
        'STUDYID': 'PLX-650',
        'DOMAIN': 'AE',
        'USUBJID': raw['SUBJECT'].str.strip().map(lambda s: f"PLX-650-{s}"),
        'AESPID': raw['RECID'].str.strip(),
        'AETERM': raw['AE_VERBATIM'].str.strip().str.upper(),
        'AEDECOD': raw['CODED_PT'].str.strip().str.upper(),
        'AEBODSYS': raw['CODED_SOC'].str.strip().str.upper(),
        'AESEV': raw['SEVERITY'].str.strip().str.upper(),
        'AESER': raw['SERIOUS'].str.strip().str.upper().map({'YES': 'Y', 'NO': 'N'}).fillna(''),
        'AEREL': raw['RELATIONSHIP'].str.strip().str.upper().map(rel_map).fillna(''),
        'AEOUT': raw['OUTCOME'].str.strip().str.upper(),
        'AESTDTC': raw['AESTDAT'].map(parse_dtc),
        'AEENDTC': raw.apply(lambda r: '' if str(r['AEONGO']).strip().upper() == 'Y' else parse_dtc(r['AEENDAT']), axis=1)
    })

    out = out.merge(dm[['USUBJID', 'RFSTDTC']], on='USUBJID', how='left')

    out['AESTDY'] = out.apply(lambda r: calc_study_day(r['AESTDTC'], r['RFSTDTC']), axis=1)
    out['AEENDY'] = out.apply(lambda r: calc_study_day(r['AEENDTC'], r['RFSTDTC']), axis=1)

    out = out.sort_values(['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'], kind='stable')
    out['AESEQ'] = out.groupby('USUBJID').cumcount() + 1

    cols = [
        'STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID', 'AETERM',
        'AEDECOD', 'AEBODSYS', 'AESEV', 'AESER', 'AEREL', 'AEOUT',
        'AESTDTC', 'AEENDTC', 'AESTDY', 'AEENDY'
    ]
    out = out[cols]
    out.to_csv('output/ae.csv', index=False)

if __name__ == '__main__':
    main()
