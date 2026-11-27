import pandas as pd
import re
import calendar
import os


def parse_iso(tc):
    if not isinstance(tc, str):
        tc = str(tc)
    tc = tc.strip()
    if tc == '' or tc.lower() in ('nan', 'none', '<na>'):
        return None, None
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', tc):
        return 'complete', tc
    if re.fullmatch(r'\d{4}-\d{2}', tc):
        return 'month', tc
    if re.fullmatch(r'\d{4}', tc):
        return 'year', tc
    return None, None


def impute_end(tc):
    typ, val = parse_iso(tc)
    if typ is None:
        return pd.NaT, ''
    if typ == 'complete':
        return pd.to_datetime(val, errors='coerce'), ''
    if typ == 'month':
        y, m = map(int, val.split('-'))
        return pd.Timestamp(y, m, calendar.monthrange(y, m)[1]), 'D'
    if typ == 'year':
        y = int(val)
        return pd.Timestamp(y, 12, 31), 'M'


def impute_start(tc, trtsdt):
    typ, val = parse_iso(tc)
    if typ is None:
        if pd.isna(trtsdt):
            return pd.NaT, ''
        return trtsdt, 'Y'
    if typ == 'complete':
        return pd.to_datetime(val, errors='coerce'), ''
    if typ == 'month':
        y, m = map(int, val.split('-'))
        if pd.notna(trtsdt) and trtsdt.year == y and trtsdt.month == m:
            dt = trtsdt
        else:
            dt = pd.Timestamp(y, m, 1)
        return dt, 'D'
    if typ == 'year':
        y = int(val)
        if pd.notna(trtsdt) and trtsdt.year == y:
            dt = trtsdt
        else:
            dt = pd.Timestamp(y, 1, 1)
        return dt, 'M'


def adjust_start(row):
    ast_dt = row['ASTDT']
    flag = row['ASTDTF']
    aendt = row['AENDT']
    aendtf = row['AENDTF']
    if pd.notna(ast_dt) and pd.notna(aendt) and flag != '' and aendtf == '':
        if ast_dt > aendt:
            return aendt
    return ast_dt


def study_day(dt, trtsdt):
    if pd.isna(dt) or pd.isna(trtsdt):
        return ''
    diff = (dt - trtsdt).days
    if diff >= 0:
        return diff + 1
    return diff


def calc_adurn(row):
    if pd.isna(row['ASTDT']) or pd.isna(row['AENDT']):
        return ''
    return (row['AENDT'] - row['ASTDT']).days + 1


def calc_trtemfl(row):
    if pd.isna(row['ASTDT']) or pd.isna(row['TRTSDT']) or pd.isna(row['TRTEDT']):
        return ''
    if row['ASTDT'] >= row['TRTSDT'] and row['ASTDT'] <= row['TRTEDT'] + pd.Timedelta(days=30):
        return 'Y'
    return ''


def date_to_str(x):
    if pd.isna(x):
        return ''
    return x.strftime('%Y-%m-%d')


def main():
    os.makedirs('output', exist_ok=True)

    ae = pd.read_csv('input/ae.csv', dtype=str, keep_default_na=False)
    adsl = pd.read_csv('input/adsl.csv', dtype=str, keep_default_na=False)

    df = ae.merge(adsl[['USUBJID', 'TRTSDT', 'TRTEDT']], on='USUBJID', how='left')

    df['AESEQ'] = pd.to_numeric(df['AESEQ'], errors='coerce').astype('Int64')
    df['TRTSDT'] = pd.to_datetime(df['TRTSDT'], errors='coerce')
    df['TRTEDT'] = pd.to_datetime(df['TRTEDT'], errors='coerce')

    end_imputations = df['AEENDTC'].apply(impute_end)
    df['AENDT'] = [x[0] for x in end_imputations]
    df['AENDTF'] = [x[1] for x in end_imputations]

    start_imputations = df.apply(lambda row: impute_start(row['AESTDTC'], row['TRTSDT']), axis=1)
    df['ASTDT'] = [x[0] for x in start_imputations]
    df['ASTDTF'] = [x[1] for x in start_imputations]

    df['ASTDT'] = df.apply(adjust_start, axis=1)

    df['ASTDY'] = df.apply(lambda row: study_day(row['ASTDT'], row['TRTSDT']), axis=1)
    df['AENDY'] = df.apply(lambda row: study_day(row['AENDT'], row['TRTSDT']), axis=1)
    df['ADURN'] = df.apply(calc_adurn, axis=1)
    df['TRTEMFL'] = df.apply(calc_trtemfl, axis=1)

    df['AOCCFL'] = ''
    df['AOCCPFL'] = ''

    tea = df[df['TRTEMFL'] == 'Y']
    for subj, subj_df in tea.groupby('USUBJID'):
        subj_sorted = subj_df.sort_values(['ASTDT', 'AESEQ'])
        first_idx = subj_sorted.index[0]
        df.loc[first_idx, 'AOCCFL'] = 'Y'

        for decod, decod_df in subj_sorted.groupby('AEDECOD'):
            df.loc[decod_df.index[0], 'AOCCPFL'] = 'Y'

    df = df.sort_values(['USUBJID', 'AESEQ'])

    out_cols = [
        'STUDYID', 'USUBJID', 'AESEQ', 'AETERM', 'AEDECOD', 'AEBODSYS',
        'TRTSDT', 'TRTEDT', 'ASTDT', 'ASTDTF', 'AENDT', 'AENDTF',
        'ASTDY', 'AENDY', 'ADURN', 'TRTEMFL', 'AOCCFL', 'AOCCPFL'
    ]

    out = df[out_cols].copy()
    for col in ['TRTSDT', 'TRTEDT', 'ASTDT', 'AENDT']:
        out[col] = out[col].apply(date_to_str)

    out.to_csv('output/adae.csv', index=False, na_rep='')


if __name__ == '__main__':
    main()
