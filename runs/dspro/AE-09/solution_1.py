import os
import pandas as pd
from datetime import datetime


def clean(s):
    if pd.isna(s):
        return ''
    return str(s).strip()


def iso_date(y, m, d):
    y = clean(y)
    m = clean(m)
    d = clean(d)

    if y == '':
        return ''
    if m == '':
        return y

    m = m.zfill(2)

    if d == '':
        return f"{y}-{m}"

    d = d.zfill(2)
    return f"{y}-{m}-{d}"


def study_day(date_str, rfstdtc):
    if not date_str or not rfstdtc:
        return ''
    if len(date_str) != 10 or len(rfstdtc) != 10:
        return ''

    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        r = datetime.strptime(rfstdtc, '%Y-%m-%d')
    except ValueError:
        return ''

    delta = (d - r).days
    if delta >= 0:
        return str(delta + 1)
    return str(delta)


def make_usubjid(subject):
    subject = clean(subject)
    parts = subject.split('-', 1)
    if len(parts) == 2:
        site, subj = parts
        return f"TQR-448-{site}-{subj}"
    return f"TQR-448-{subject}"


def main():
    raw = pd.read_csv('input/raw_ae.csv', dtype=str, keep_default_na=False)
    dm = pd.read_csv('input/dm.csv', dtype=str, keep_default_na=False)

    for col in raw.columns:
        raw[col] = raw[col].apply(clean)
    for col in dm.columns:
        dm[col] = dm[col].apply(clean)

    # Keep only the highest version for each SUBJECT + RECID.
    raw['VERSION'] = pd.to_numeric(raw['VERSION'], errors='coerce').fillna(0).astype(int)
    raw = raw.sort_values('VERSION').drop_duplicates(['SUBJECT', 'RECID'], keep='last')

    raw['USUBJID'] = raw['SUBJECT'].apply(make_usubjid)

    dm_map = dm[['USUBJID', 'RFSTDTC']].drop_duplicates()
    raw = raw.merge(dm_map, on='USUBJID', how='left')
    raw['RFSTDTC'] = raw['RFSTDTC'].apply(clean)

    severity_map = {'1': 'MILD', '2': 'MODERATE', '3': 'SEVERE'}
    serious_map = {'1': 'Y', '0': 'N'}
    relationship_map = {
        'not related': 'NONE',
        'unlikely related': 'REMOTE',
        'possibly related': 'POSSIBLE',
        'probably related': 'PROBABLE'
    }

    raw['STUDYID'] = 'TQR-448'
    raw['DOMAIN'] = 'AE'
    raw['AESPID'] = raw['RECID']
    raw['AETERM'] = raw['AE_VERBATIM'].str.upper()
    raw['AEDECOD'] = raw['CODED_PT']
    raw['AEBODSYS'] = raw['CODED_SOC']
    raw['AESEV'] = raw['SEVERITY'].map(severity_map).fillna('')
    raw['AESER'] = raw['SERIOUS'].map(serious_map).fillna('')
    raw['AEREL'] = raw['RELATIONSHIP'].str.lower().map(relationship_map).fillna('')
    raw['AEOUT'] = raw['OUTCOME'].str.upper()

    raw['AESTDTC'] = raw.apply(
        lambda r: iso_date(r['AESTDAT_YYYY'], r['AESTDAT_MM'], r['AESTDAT_DD']),
        axis=1
    )
    raw['AEENDTC'] = raw.apply(
        lambda r: '' if clean(r['AEONGO']).upper() == 'Y'
        else iso_date(r['AEENDAT_YYYY'], r['AEENDAT_MM'], r['AEENDAT_DD']),
        axis=1
    )

    raw['AESTDY'] = raw.apply(lambda r: study_day(r['AESTDTC'], r['RFSTDTC']), axis=1)
    raw['AEENDY'] = raw.apply(lambda r: study_day(r['AEENDTC'], r['RFSTDTC']), axis=1)

    raw = raw.sort_values(
        ['USUBJID', 'AESTDTC', 'AETERM', 'AESPID'],
        ascending=True,
        na_position='last'
    )
    raw['AESEQ'] = raw.groupby('USUBJID').cumcount() + 1

    out_cols = [
        'STUDYID', 'DOMAIN', 'USUBJID', 'AESEQ', 'AESPID',
        'AETERM', 'AEDECOD', 'AEBODSYS', 'AESEV', 'AESER',
        'AEREL', 'AEOUT', 'AESTDTC', 'AEENDTC', 'AESTDY', 'AEENDY'
    ]

    os.makedirs('output', exist_ok=True)
    raw[out_cols].to_csv('output/ae.csv', index=False)


if __name__ == '__main__':
    main()
