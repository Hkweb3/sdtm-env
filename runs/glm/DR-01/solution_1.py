import os
import re
from datetime import date

import pandas as pd

INPUT_DIR = 'input'
OUTPUT_DIR = 'output'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'findings.csv')

CRIT_COLS = ['AESCAN', 'AESCONG', 'AESDISAB', 'AESDTH', 'AESHOSP', 'AESLIFE', 'AESOD']

CHECK_ORDER = [
    'AE_DATE_ORDER',
    'AE_DUPLICATE',
    'SAE_CRITERIA',
    'DEATH_CONSISTENCY',
    'DOSE_AFTER_DISC',
    'LAB_UNIT',
    'LAB_VISIT_DATE',
]


def read_csv(name):
    df = pd.read_csv(
        os.path.join(INPUT_DIR, name),
        dtype=str,
        keep_default_na=False,
        encoding='utf-8-sig',
    )
    df.columns = [c.strip() for c in df.columns]
    return df


def full_date(value):
    """Return a datetime.date when the value starts with a complete YYYY-MM-DD date, else None."""
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:$|[\sT])', s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def as_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def is_y(value):
    return str(value).strip().upper() == 'Y'


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    dm = read_csv('dm.csv')
    ae = read_csv('ae.csv')
    ex = read_csv('ex.csv')
    ds = read_csv('ds.csv')
    lb = read_csv('lb.csv')

    findings = []

    def add(check, usubjid, domain, seq=None):
        seq_val = '' if seq is None or seq == '' else int(seq)
        findings.append((check, str(usubjid), domain, seq_val))

    # ---------------------------------------------------------------
    # AE_DATE_ORDER: AE ends before it starts (complete dates only).
    # ---------------------------------------------------------------
    for _, r in ae.iterrows():
        start = full_date(r['AESTDTC'])
        end = full_date(r['AEENDTC'])
        if start is not None and end is not None and end < start:
            add('AE_DATE_ORDER', r['USUBJID'], 'AE', as_int(r['AESEQ']))

    # ---------------------------------------------------------------
    # AE_DUPLICATE: same AEDECOD + same non-blank AESTDTC more than
    # once per subject; raise on every copy except the lowest AESEQ.
    # ---------------------------------------------------------------
    ae_nb = ae.copy()
    ae_nb['_decod'] = ae_nb['AEDECOD'].str.strip()
    ae_nb['_stdtc'] = ae_nb['AESTDTC'].str.strip()
    ae_nb = ae_nb[ae_nb['_stdtc'] != '']
    for (subj, _decod, _stdtc), grp in ae_nb.groupby(['USUBJID', '_decod', '_stdtc']):
        if len(grp) > 1:
            g = grp.copy()
            g['_seq'] = g['AESEQ'].map(as_int)
            g = g.sort_values('_seq')
            for _, r in g.iloc[1:].iterrows():
                add('AE_DUPLICATE', subj, 'AE', r['_seq'])

    # ---------------------------------------------------------------
    # SAE_CRITERIA: AESER disagrees with the seriousness criteria.
    # ---------------------------------------------------------------
    for _, r in ae.iterrows():
        any_crit = any(is_y(r[c]) for c in CRIT_COLS)
        serious = is_y(r['AESER'])
        if serious != any_crit:
            add('SAE_CRITERIA', r['USUBJID'], 'AE', as_int(r['AESEQ']))

    # ---------------------------------------------------------------
    # DEATH_CONSISTENCY
    # ---------------------------------------------------------------
    dth_raw = {r['USUBJID']: str(r['DTHDTC']).strip() for _, r in dm.iterrows()}
    dth_date = {s: full_date(v) for s, v in dth_raw.items()}
    fatal_subjects = set(ae.loc[ae['AEOUT'].str.strip().str.upper() == 'FATAL', 'USUBJID'])

    for _, r in ae.iterrows():
        subj = r['USUBJID']
        seq = as_int(r['AESEQ'])
        has_death = dth_raw.get(subj, '') != ''
        death_d = dth_date.get(subj)
        # fatal AE for a subject with no death date in DM
        if str(r['AEOUT']).strip().upper() == 'FATAL' and not has_death:
            add('DEATH_CONSISTENCY', subj, 'AE', seq)
        # AE with a complete start date after the subject's death date
        start = full_date(r['AESTDTC'])
        if start is not None and death_d is not None and start > death_d:
            add('DEATH_CONSISTENCY', subj, 'AE', seq)

    for _, r in dm.iterrows():
        subj = r['USUBJID']
        # subject with a death date but no AE with a fatal outcome
        if str(r['DTHDTC']).strip() != '' and subj not in fatal_subjects:
            add('DEATH_CONSISTENCY', subj, 'DM')

    # ---------------------------------------------------------------
    # DOSE_AFTER_DISC: exposure starting after early discontinuation.
    # ---------------------------------------------------------------
    early_disc = {}
    for _, r in ds.iterrows():
        if str(r['DSCAT']).strip().upper() != 'DISPOSITION EVENT':
            continue
        if str(r['DSDECOD']).strip().upper() in ('COMPLETED', 'SCREEN FAILURE'):
            continue
        d = full_date(r['DSSTDTC'])
        if d is None:
            continue
        subj = r['USUBJID']
        if subj not in early_disc or d < early_disc[subj]:
            early_disc[subj] = d

    for _, r in ex.iterrows():
        start = full_date(r['EXSTDTC'])
        subj = r['USUBJID']
        if start is not None and subj in early_disc and start > early_disc[subj]:
            add('DOSE_AFTER_DISC', subj, 'EX', as_int(r['EXSEQ']))

    # ---------------------------------------------------------------
    # LAB_UNIT: value >= 8x or <= 1/8 of the median of the subject's
    # other results for the same test (needs at least 2 other results).
    # ---------------------------------------------------------------
    lb_num = lb.copy()
    lb_num['_val'] = pd.to_numeric(lb_num['LBSTRESN'].str.strip(), errors='coerce')
    lb_num['_testcd'] = lb_num['LBTESTCD'].str.strip()
    lb_num = lb_num[lb_num['_val'].notna()]

    for (subj, testcd), grp in lb_num.groupby(['USUBJID', '_testcd']):
        if len(grp) < 3:
            continue
        vals = grp['_val']
        for idx, r in grp.iterrows():
            others = vals.drop(idx)
            if len(others) < 2:
                continue
            med = others.median()
            if pd.isna(med) or med == 0:
                continue
            v = r['_val']
            if v >= 8 * med or v <= med / 8:
                add('LAB_UNIT', subj, 'LB', as_int(r['LBSEQ']))

    # ---------------------------------------------------------------
    # LAB_VISIT_DATE: at scheduled visits only, a result dated earlier
    # than the latest date of the same test at earlier scheduled visits
    # (lower VISITNUM). Dates compared without time.
    # ---------------------------------------------------------------
    lb_vis = lb.copy()
    lb_vis['_dt'] = lb_vis['LBDTC'].map(full_date)
    lb_vis['_vnum'] = pd.to_numeric(lb_vis['VISITNUM'], errors='coerce')
    lb_vis['_testcd'] = lb_vis['LBTESTCD'].str.strip()
    lb_vis = lb_vis[lb_vis['_dt'].notna() & lb_vis['_vnum'].notna()]
    visit_up = lb_vis['VISIT'].str.strip().str.upper()
    sched = lb_vis[~visit_up.str.startswith('UNSCHEDULED')]

    for (subj, testcd), grp in sched.groupby(['USUBJID', '_testcd']):
        for idx, r in grp.iterrows():
            earlier = grp[grp['_vnum'] < r['_vnum']]
            if earlier.empty:
                continue
            latest = max(earlier['_dt'].tolist())
            if r['_dt'] < latest:
                add('LAB_VISIT_DATE', subj, 'LB', as_int(r['LBSEQ']))

    # ---------------------------------------------------------------
    # De-duplicate, sort deterministically, and write the output.
    # ---------------------------------------------------------------
    seen = set()
    rows = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        rows.append(f)

    order_idx = {c: i for i, c in enumerate(CHECK_ORDER)}

    def sort_key(f):
        check, usubjid, domain, seq = f
        return (order_idx[check], usubjid, domain, -1 if seq == '' else seq)

    rows.sort(key=sort_key)

    out = pd.DataFrame(rows, columns=['CHECK', 'USUBJID', 'DOMAIN', 'SEQ'])
    out['SEQ'] = out['SEQ'].map(lambda x: '' if x == '' else str(int(x)))
    out.to_csv(OUTPUT_FILE, index=False)


if __name__ == '__main__':
    main()
