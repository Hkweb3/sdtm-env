import os
import sys
import numpy as np
import pandas as pd

INPUT_DIR = 'input'
OUTPUT_DIR = 'output'
OUTPUT_PATH = os.path.join(OUTPUT_DIR, 'findings.csv')

SERIOUSNESS_CRITERIA_COLS = [
    'AESCAN', 'AESCONG', 'AESDISAB', 'AESDTH', 'AESHOSP', 'AESLIFE', 'AESOD',
]

CHECK_ORDER = [
    'AE_DATE_ORDER',
    'AE_DUPLICATE',
    'SAE_CRITERIA',
    'DEATH_CONSISTENCY',
    'DOSE_AFTER_DISC',
    'LAB_UNIT',
    'LAB_VISIT_DATE',
]

findings = set()


def complete_date(value):
    """Return 'YYYY-MM-DD' if value starts with a complete valid date, else None."""
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    candidate = text[:10]
    try:
        ts = pd.Timestamp(candidate)
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return candidate


def seq_text(seq):
    """Normalise a SEQ value to a plain integer string (or '' for subject level)."""
    if seq is None:
        return ''
    text = str(seq).strip()
    if text == '' or text.lower() == 'nan':
        return ''
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def add_finding(check, usubjid, domain, seq=None):
    findings.add((check, str(usubjid).strip(), domain, seq_text(seq)))


def is_yes(value):
    return str(value).strip().upper() == 'Y'


def load(name):
    path = os.path.join(INPUT_DIR, name)
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')


def check_ae_date_order(ae):
    for _, row in ae.iterrows():
        start = complete_date(row.get('AESTDTC'))
        end = complete_date(row.get('AEENDTC'))
        if start and end and end < start:
            add_finding('AE_DATE_ORDER', row['USUBJID'], 'AE', row.get('AESEQ'))


def check_ae_duplicate(ae):
    pool = ae[ae['AESTDTC'].fillna('').str.strip() != '']
    for _, grp in pool.groupby(['USUBJID', 'AEDECOD', 'AESTDTC'], dropna=False):
        if len(grp) < 2:
            continue

        def sort_key(seq):
            try:
                return float(str(seq).strip())
            except (TypeError, ValueError):
                return float('inf')

        ordered = grp.assign(_s=grp['AESEQ'].map(sort_key)).sort_values('_s', kind='stable')
        for _, row in ordered.iloc[1:].iterrows():
            add_finding('AE_DUPLICATE', row['USUBJID'], 'AE', row.get('AESEQ'))


def check_sae_criteria(ae):
    for _, row in ae.iterrows():
        any_crit = any(is_yes(row.get(col)) for col in SERIOUSNESS_CRITERIA_COLS)
        serious = is_yes(row.get('AESER'))
        if serious != any_crit:
            add_finding('SAE_CRITERIA', row['USUBJID'], 'AE', row.get('AESEQ'))


def check_death_consistency(dm, ae):
    death_raw = {}
    death_date = {}
    for _, row in dm.iterrows():
        subj = row['USUBJID']
        raw = str(row.get('DTHDTC', '')).strip()
        death_raw[subj] = raw
        death_date[subj] = complete_date(raw)

    fatal_subjects = set()
    for _, row in ae.iterrows():
        subj = row['USUBJID']
        fatal = str(row.get('AEOUT', '')).strip().upper() == 'FATAL'
        start = complete_date(row.get('AESTDTC'))
        dth = death_date.get(subj)
        if fatal and not death_raw.get(subj):
            add_finding('DEATH_CONSISTENCY', subj, 'AE', row.get('AESEQ'))
        if dth and start and start > dth:
            add_finding('DEATH_CONSISTENCY', subj, 'AE', row.get('AESEQ'))
        if fatal:
            fatal_subjects.add(subj)

    for _, row in dm.iterrows():
        subj = row['USUBJID']
        if death_raw.get(subj) and subj not in fatal_subjects:
            add_finding('DEATH_CONSISTENCY', subj, 'DM', None)


def check_dose_after_disc(ds, ex):
    disc_date = {}
    for _, row in ds.iterrows():
        if str(row.get('DSCAT', '')).strip().upper() != 'DISPOSITION EVENT':
            continue
        decod = str(row.get('DSDECOD', '')).strip().upper()
        if decod in ('COMPLETED', 'SCREEN FAILURE'):
            continue
        date = complete_date(row.get('DSSTDTC'))
        if not date:
            continue
        subj = row['USUBJID']
        if subj not in disc_date or date < disc_date[subj]:
            disc_date[subj] = date
    for _, row in ex.iterrows():
        disc = disc_date.get(row['USUBJID'])
        start = complete_date(row.get('EXSTDTC'))
        if disc and start and start > disc:
            add_finding('DOSE_AFTER_DISC', row['USUBJID'], 'EX', row.get('EXSEQ'))


def check_lab_unit(lb):
    work = lb.copy()
    work['_val'] = pd.to_numeric(work['LBSTRESN'], errors='coerce')
    for (subj, test), grp in work.groupby(['USUBJID', 'LBTESTCD'], dropna=False):
        grp = grp[grp['_val'].notna()]
        if len(grp) < 3:
            continue
        values = grp['_val'].to_numpy(dtype=float)
        seqs = grp['LBSEQ'].tolist()
        for i in range(len(values)):
            others = np.delete(values, i)
            if len(others) < 2:
                continue
            median = float(np.median(others))
            if median == 0:
                continue
            value = float(values[i])
            if value >= 8.0 * median or value <= median / 8.0:
                add_finding('LAB_UNIT', subj, 'LB', seqs[i])


def check_lab_visit_date(lb):
    work = lb.copy()
    work['_vnum'] = pd.to_numeric(work['VISITNUM'], errors='coerce')
    work['_date'] = work['LBDTC'].apply(complete_date)
    visit_upper = work['VISIT'].fillna('').str.strip().str.upper()
    scheduled = work[(~visit_upper.str.startswith('UNSCHEDULED'))
                     & work['_vnum'].notna()
                     & work['_date'].notna()]
    for (subj, test), grp in scheduled.groupby(['USUBJID', 'LBTESTCD'], dropna=False):
        for _, row in grp.iterrows():
            earlier = grp[grp['_vnum'] < row['_vnum']]
            if earlier.empty:
                continue
            latest = earlier['_date'].max()
            if row['_date'] < latest:
                add_finding('LAB_VISIT_DATE', subj, 'LB', row.get('LBSEQ'))


def main():
    dm = load('dm.csv')
    ae = load('ae.csv')
    ex = load('ex.csv')
    ds = load('ds.csv')
    lb = load('lb.csv')

    checks = [
        ('AE_DATE_ORDER', lambda: check_ae_date_order(ae)),
        ('AE_DUPLICATE', lambda: check_ae_duplicate(ae)),
        ('SAE_CRITERIA', lambda: check_sae_criteria(ae)),
        ('DEATH_CONSISTENCY', lambda: check_death_consistency(dm, ae)),
        ('DOSE_AFTER_DISC', lambda: check_dose_after_disc(ds, ex)),
        ('LAB_UNIT', lambda: check_lab_unit(lb)),
        ('LAB_VISIT_DATE', lambda: check_lab_visit_date(lb)),
    ]
    for name, fn in checks:
        try:
            fn()
        except Exception as exc:
            print(f'WARNING: check {name} failed: {exc}', file=sys.stderr)

    def sort_key(f):
        check, usubjid, domain, seq = f
        try:
            seq_val = float(seq) if seq != '' else -1.0
        except ValueError:
            seq_val = float('inf')
        order = CHECK_ORDER.index(check) if check in CHECK_ORDER else len(CHECK_ORDER)
        return (order, usubjid, domain, seq_val)

    rows = sorted(findings, key=sort_key)
    out = pd.DataFrame(rows, columns=['CHECK', 'USUBJID', 'DOMAIN', 'SEQ'])

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out.to_csv(OUTPUT_PATH, index=False)
    print(f'Wrote {len(out)} finding(s) to {OUTPUT_PATH}')


main()
