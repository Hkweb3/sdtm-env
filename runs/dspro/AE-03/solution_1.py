import os
import pandas as pd
from datetime import datetime

STUDYID = 'PLX-326'


def to_int(v):
    if pd.isna(v):
        return None
    if isinstance(v, str):
        v = v.strip()
        if v == '':
            return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def make_dtc(y, m, d):
    y = to_int(y)
    if y is None:
        return ''
    m = to_int(m)
    if m is None:
        return f'{y:04d}'
    d = to_int(d)
    if d is None:
        return f'{y:04d}-{m:02d}'
    return f'{y:04d}-{m:02d}-{d:02d}'


def study_day(dtc, rfs):
    if pd.isna(dtc) or pd.isna(rfs) or dtc == '' or rfs == '':
        return ''
    try:
        d = datetime.strptime(str(dtc), '%Y-%m-%d').date()
        r = datetime.strptime(str(rfs), '%Y-%m-%d').date()
    except ValueError:
        return ''
    delta = (d - r).days
    return delta + 1 if delta >= 0 else delta


def main():
    os.makedirs('output', exist_ok=True)

    dm = pd.read_csv('input/dm.csv')
    ae = pd.read_csv('input/raw_ae.csv')

    out = ae.copy()

    out['STUDYID'] = STUDYID
    out['DOMAIN'] = 'AE'
    out['USUBJID'] = STUDYID + '-' + out['SUBJECT'].fillna('').astype(str).str.strip()
    out['AESPID'] = out['RECID'].fillna('').astype(str).str.strip()
    out['AETERM'] = out['AE_VERBATIM'].fillna('').astype(str).str.strip().str.upper()
    out['AEDECOD'] = out['CODED_PT'].fillna('').astype(str).str.strip()
    out['AEBODSYS'] = out['CODED_SOC'].fillna('').astype(str).str.strip()
    out['AESEV'] = out['SEVERITY'].fillna('').astype(str).str.strip().str.upper()
    out['AESER'] = out['SERIOUS'].str.strip().map({'Yes': 'Y', 'No': 'N'}).fillna('')
    out['AEREL'] = out['RELATIONSHIP'].str.strip().map({
        'Not related': 'NONE',
        'Unlikely related': 'REMOTE',
        'Possibly related': 'POSSIBLE',
        'Probably related': 'PROBABLE'
    }).fillna('')
    out['AEOUT'] = out['OUTCOME'].fillna('').astype(str).str.strip().str.upper()

    out['AESTDTC'] = out.apply(
        lambda r: make_dtc(r['AESTDAT_YYYY'], r['AESTDAT_MM'], r['AESTDAT_DD']),
        axis=1
    )
    out['AEENDTC'] = out.apply(
        lambda r: make_dtc(r['AEENDAT_YYYY'], r['AEENDAT_MM'], r['AEENDAT_DD']),
        axis=1
    )

    out.loc[out['AEONGO'] == 'Y', 'AEENDTC'] = ''

    out = out.merge(dm[['USUBJID', 'RFSTDTC']], on='USUBJID', how='left')
    out['AESTDY'] = out.apply(lambda r: study_day(r['AESTDTC'], r['RFSTDTC']), axis=1)
    out['AEENDY'] = out.apply(lambda r: study_day(r['AEENDTC'], r['RFSTDTC']), axis=1)

    out = out.sort_values(['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'], kind='mergesort')
    out['AESEQ'] = out.groupby('USUBJID').cumcount() + 1

    out = out.sort_values(['USUBJID', 'AESEQ'], kind='mergesort')

    cols = [
        'STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID',
        'AETERM', 'AEDECOD', 'AEBODSYS', 'AESEV', 'AESER',
        'AEREL', 'AEOUT', 'AESTDTC', 'AEENDTC', 'AESTDY', 'AEENDY'
    ]
    out = out[cols].fillna('')
    out.to_csv('output/ae.csv', index=False)


if __name__ == '__main__':
    main()
