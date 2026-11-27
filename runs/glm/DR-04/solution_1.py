import re
from pathlib import Path

import pandas as pd

INPUT_DIR = Path('input')
OUTPUT_DIR = Path('output')
OUTPUT_FILE = OUTPUT_DIR / 'findings.csv'

FULL_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

CRIT_COLS = ['AESCAN', 'AESCONG', 'AESDISAB', 'AESDTH', 'AESHOSP', 'AESLIFE', 'AESOD']
CHECK_ORDER = ['AE_DATE_ORDER', 'AE_DUPLICATE', 'SAE_CRITERIA', 'DEATH_CONSISTENCY',
               'DOSE_AFTER_DISC', 'LAB_UNIT', 'LAB_VISIT_DATE']


def date_part(value):
    """Return the complete YYYY-MM-DD date a value starts with, else None."""
    if value is None:
        return None
    s = str(value).strip()
    if len(s) >= 10 and FULL_DATE_RE.match(s[:10]):
        return s[:10]
    return None


def is_after(complete_date, reference):
    """True if a complete ISO date is strictly after `reference` (ISO date, maybe partial)."""
    reference = str(reference).strip()
    if not complete_date or not reference:
        return False
    if len(reference) >= 10:
        return complete_date > reference[:10]
    if len(reference) in (4, 7):
        return complete_date[:len(reference)] > reference
    return False


def main():
    dm = pd.read_csv(INPUT_DIR / 'dm.csv', dtype=str, keep_default_na=False)
    ae = pd.read_csv(INPUT_DIR / 'ae.csv', dtype=str, keep_default_na=False)
    ex = pd.read_csv(INPUT_DIR / 'ex.csv', dtype=str, keep_default_na=False)
    ds = pd.read_csv(INPUT_DIR / 'ds.csv', dtype=str, keep_default_na=False)
    lb = pd.read_csv(INPUT_DIR / 'lb.csv', dtype=str, keep_default_na=False)

    findings = []
    seen = set()

    def add(check, usubjid, domain, seq):
        seq = '' if seq is None else str(seq)
        key = (check, usubjid, domain, seq)
        if key in seen:
            return
        seen.add(key)
        findings.append({'CHECK': check, 'USUBJID': usubjid, 'DOMAIN': domain, 'SEQ': seq})

    # ---- AE_DATE_ORDER: AE ends before it starts (complete dates only) ----
    for _, r in ae.iterrows():
        start = date_part(r['AESTDTC'])
        end = date_part(r['AEENDTC'])
        if start and end and end < start:
            add('AE_DATE_ORDER', r['USUBJID'], 'AE', r['AESEQ'])

    # ---- AE_DUPLICATE: same AEDECOD + same non-blank AESTDTC, keep lowest AESEQ ----
    dup = ae.assign(_DEC=ae['AEDECOD'].str.strip(), _STD=ae['AESTDTC'].str.strip())
    dup = dup[dup['_STD'] != '']
    for _, g in dup.groupby(['USUBJID', '_DEC', '_STD'], sort=False):
        if len(g) > 1:
            keep_seq = g['AESEQ'].astype(int).min()
            for _, r in g.iterrows():
                if int(r['AESEQ']) != keep_seq:
                    add('AE_DUPLICATE', r['USUBJID'], 'AE', r['AESEQ'])

    # ---- SAE_CRITERIA: AESER vs seriousness criteria ----
    for _, r in ae.iterrows():
        any_crit = any(str(r[c]).strip().upper() == 'Y' for c in CRIT_COLS)
        ser = str(r['AESER']).strip().upper()
        if (ser == 'Y' and not any_crit) or (ser != 'Y' and any_crit):
            add('SAE_CRITERIA', r['USUBJID'], 'AE', r['AESEQ'])

    # ---- DEATH_CONSISTENCY ----
    dth_by_subj = {r['USUBJID']: str(r['DTHDTC']).strip() for _, r in dm.iterrows()}
    fatal_subjs = set(ae.loc[ae['AEOUT'].str.strip().str.upper() == 'FATAL', 'USUBJID'])
    for _, r in ae.iterrows():
        subj = r['USUBJID']
        dth = dth_by_subj.get(subj, '')
        start = date_part(r['AESTDTC'])
        # fatal AE but no death date in DM
        if str(r['AEOUT']).strip().upper() == 'FATAL' and not dth:
            add('DEATH_CONSISTENCY', subj, 'AE', r['AESEQ'])
        # AE starting after the death date
        if start and dth and is_after(start, dth):
            add('DEATH_CONSISTENCY', subj, 'AE', r['AESEQ'])
    for _, r in dm.iterrows():
        subj = r['USUBJID']
        # death date but no fatal AE
        if dth_by_subj.get(subj, '') and subj not in fatal_subjs:
            add('DEATH_CONSISTENCY', subj, 'DM', '')

    # ---- DOSE_AFTER_DISC: exposure starting after early discontinuation ----
    early_disc = {}
    for _, r in ds.iterrows():
        if str(r['DSCAT']).strip().upper() != 'DISPOSITION EVENT':
            continue
        if str(r['DSDECOD']).strip().upper() in ('COMPLETED', 'SCREEN FAILURE'):
            continue
        d = date_part(r['DSSTDTC'])
        if d:
            subj = r['USUBJID']
            if subj not in early_disc or d < early_disc[subj]:
                early_disc[subj] = d
    for _, r in ex.iterrows():
        subj = r['USUBJID']
        start = date_part(r['EXSTDTC'])
        if start and subj in early_disc and start > early_disc[subj]:
            add('DOSE_AFTER_DISC', subj, 'EX', r['EXSEQ'])

    # ---- LAB_UNIT & LAB_VISIT_DATE ----
    lb = lb.assign(_VAL=pd.to_numeric(lb['LBSTRESN'], errors='coerce'),
                   _VNUM=pd.to_numeric(lb['VISITNUM'], errors='coerce'))
    for (subj, test), g in lb.groupby(['USUBJID', 'LBTESTCD'], sort=False):
        # LAB_UNIT: value >= 8x or <= 1/8 of median of the subject's other results (>=2 others)
        numeric = g[g['_VAL'].notna()]
        for idx, r in numeric.iterrows():
            others = numeric.drop(index=idx)['_VAL']
            if len(others) < 2:
                continue
            med = others.median()
            val = r['_VAL']
            if val >= 8 * med or val <= med / 8:
                add('LAB_UNIT', subj, 'LB', r['LBSEQ'])

        # LAB_VISIT_DATE: scheduled visits only; date earlier than latest date of the same
        # subject/test at earlier scheduled visits (lower VISITNUM); dates only
        sched = []
        for _, r in g.iterrows():
            if str(r['VISIT']).strip().upper().startswith('UNSCHEDULED'):
                continue
            vnum = r['_VNUM']
            d = date_part(r['LBDTC'])
            if pd.isna(vnum) or d is None:
                continue
            sched.append((float(vnum), d, str(r['LBSEQ'])))
        for vnum, d, seq in sched:
            earlier = [dd for vv, dd, _ in sched if vv < vnum]
            if earlier and d < max(earlier):
                add('LAB_VISIT_DATE', subj, 'LB', seq)

    # ---- order deterministically and write ----
    rank = {c: i for i, c in enumerate(CHECK_ORDER)}

    def sort_key(f):
        seq = f['SEQ']
        return (rank.get(f['CHECK'], len(rank)), f['USUBJID'], f['DOMAIN'],
                1 if seq else 0, int(seq) if seq else 0)

    findings.sort(key=sort_key)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(findings, columns=['CHECK', 'USUBJID', 'DOMAIN', 'SEQ']).to_csv(
        OUTPUT_FILE, index=False)


if __name__ == '__main__':
    main()
