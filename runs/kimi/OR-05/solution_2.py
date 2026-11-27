import os
import re
import traceback
import pandas as pd

CUTOFF = pd.Timestamp('2014-12-17')
IN_DIR = 'input'
OUT_DIR = 'output'
os.makedirs(OUT_DIR, exist_ok=True)


def load(name):
    df = pd.read_csv(os.path.join(IN_DIR, name), dtype=str, encoding='utf-8-sig')
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df


def to_dt(s):
    s = s.astype('string')
    try:
        out = pd.to_datetime(s, errors='coerce', format='mixed')
    except Exception:
        out = pd.to_datetime(s, errors='coerce')
    nonempty = (s.notna() & (s.str.strip() != '')).fillna(False)
    if bool(nonempty.any()) and bool(out[nonempty].isna().all()):
        try:
            out = pd.to_datetime(s, errors='coerce')
        except Exception:
            pass
    return out


def txt(v):
    try:
        if v is None or pd.isna(v):
            return ''
    except Exception:
        pass
    return str(v).strip()


findings = []
_seen = set()


def add(sub, domain, seq, issue, prio):
    sub = txt(sub)
    if not sub:
        return
    if seq is None:
        seqs, seqn = '', float('inf')
    else:
        try:
            f = float(seq)
            if f != f:
                seqs, seqn = '', float('inf')
            elif f == int(f):
                seqs, seqn = str(int(f)), f
            else:
                seqs, seqn = str(f), f
        except Exception:
            seqs, seqn = txt(seq), float('inf')
    key = (sub, domain, seqs, issue)
    if key in _seen:
        return
    _seen.add(key)
    findings.append({'PRIO': float(prio), 'USUBJID': sub, 'DOMAIN': domain,
                     'SEQ': seqs, 'SEQN': seqn, 'ISSUE': issue})


dm = load('dm.csv')
ae = load('ae.csv')
ex = load('ex.csv')
ds = load('ds.csv')
lb = load('lb.csv')

dm['RFST'] = to_dt(dm['RFSTDTC'])
dm['RFEN'] = to_dt(dm['RFENDTC'])
dm['BRTH'] = to_dt(dm['BRTHDTC'])
dm['DTH'] = to_dt(dm['DTHDTC'])
dm['AGEN'] = pd.to_numeric(dm['AGE'], errors='coerce')

ae['ST'] = to_dt(ae['AESTDTC'])
ae['EN'] = to_dt(ae['AEENDTC'])
ae['SEQN'] = pd.to_numeric(ae['AESEQ'], errors='coerce')

ex['ST'] = to_dt(ex['EXSTDTC'])
ex['EN'] = to_dt(ex['EXENDTC'])
ex['DOSE'] = pd.to_numeric(ex['EXDOSE'], errors='coerce')
ex['SEQN'] = pd.to_numeric(ex['EXSEQ'], errors='coerce')

ds['ST'] = to_dt(ds['DSSTDTC'])
ds['SEQN'] = pd.to_numeric(ds['DSSEQ'], errors='coerce')

lb['DT'] = to_dt(lb['LBDTC'])
lb['VAL'] = pd.to_numeric(lb['LBSTRESN'], errors='coerce')
lb['SEQN'] = pd.to_numeric(lb['LBSEQ'], errors='coerce')

dmi = dm.set_index('USUBJID')
ARM = {txt(k): txt(v) for k, v in dmi['ARM'].items()}
SEX = {txt(k): txt(v).upper() for k, v in dmi['SEX'].items()}
RFST = {txt(k): v for k, v in dmi['RFST'].items()}
RFEN = {txt(k): v for k, v in dmi['RFEN'].items()}
DTH = {txt(k): v for k, v in dmi['DTH'].items()}


def calc_age(b, d):
    return d.year - b.year - ((d.month, d.day) < (b.month, b.day))


def check_dm():
    for _, r in dm.iterrows():
        sub = txt(r['USUBJID'])
        br, st, en, dt = r['BRTH'], r['RFST'], r['RFEN'], r['DTH']
        age = r['AGEN']
        if pd.notna(br) and pd.notna(st):
            ac = calc_age(br, st)
            if pd.notna(age) and abs(ac - age) > 1:
                add(sub, 'DM', None,
                    f"AGE {txt(r['AGE'])} inconsistent with BRTHDTC {txt(r['BRTHDTC'])} and RFSTDTC {txt(r['RFSTDTC'])} (computed age {ac})",
                    3.2)
            if ac < 50:
                add(sub, 'DM', None,
                    f"Computed age at entry is {ac} (BRTHDTC {txt(r['BRTHDTC'])}, RFSTDTC {txt(r['RFSTDTC'])}); key inclusion criterion requires age >= 50",
                    3.0)
        if pd.notna(age) and age < 50:
            add(sub, 'DM', None,
                f"AGE {int(age)} at entry violates key inclusion criterion (age 50 or older)", 3.0)
        if pd.notna(br) and pd.notna(st) and br >= st:
            add(sub, 'DM', None,
                f"BRTHDTC {txt(r['BRTHDTC'])} is on or after RFSTDTC {txt(r['RFSTDTC'])}", 6.0)
        if pd.notna(st) and pd.notna(en) and en < st:
            add(sub, 'DM', None,
                f"RFENDTC {txt(r['RFENDTC'])} is before RFSTDTC {txt(r['RFSTDTC'])}", 6.0)
        for col, d in (('RFSTDTC', st), ('RFENDTC', en), ('DTHDTC', dt)):
            if pd.notna(d) and d > CUTOFF:
                add(sub, 'DM', None,
                    f"{col} {txt(r[col])} is after the data cutoff 2014-12-17", 4.0)
        dthfl = txt(r.get('DTHFL')).upper()
        if dthfl == 'Y' and pd.isna(dt):
            add(sub, 'DM', None, "DTHFL is Y but DTHDTC is missing", 1.0)
        if dthfl != 'Y' and pd.notna(dt):
            add(sub, 'DM', None,
                f"DTHDTC {txt(r['DTHDTC'])} is recorded but DTHFL is not Y", 1.0)
        if pd.notna(dt) and pd.notna(st) and dt < st:
            add(sub, 'DM', None,
                f"DTHDTC {txt(r['DTHDTC'])} is before RFSTDTC {txt(r['RFSTDTC'])}", 1.0)


SER_COLS = [c for c in ['AESCONG', 'AESDISAB', 'AESDTH', 'AESHOSP', 'AESLIFE', 'AESOD']
            if c in ae.columns]


def check_ae():
    for _, r in ae.iterrows():
        sub = txt(r['USUBJID'])
        seq = r['SEQN']
        st, en = r['ST'], r['EN']
        if pd.notna(st) and pd.notna(en) and en < st:
            add(sub, 'AE', seq,
                f"AEENDTC {txt(r['AEENDTC'])} is before AESTDTC {txt(r['AESTDTC'])}", 6.0)
        if pd.notna(st) and st > CUTOFF:
            add(sub, 'AE', seq,
                f"AESTDTC {txt(r['AESTDTC'])} is after the data cutoff 2014-12-17", 4.0)
        if pd.notna(en) and en > CUTOFF:
            add(sub, 'AE', seq,
                f"AEENDTC {txt(r['AEENDTC'])} is after the data cutoff 2014-12-17", 4.0)
        dth = DTH.get(sub)
        if dth is not None and pd.notna(dth) and pd.notna(st) and st.normalize() > dth.normalize():
            add(sub, 'AE', seq,
                f"AE starts {txt(r['AESTDTC'])} after subject's death on {dth.date()}", 0.0)
        aesdth = txt(r.get('AESDTH')).upper()
        aeout = txt(r.get('AEOUT')).upper()
        aeser = txt(r.get('AESER')).upper()
        if aesdth == 'Y' and aeout != 'FATAL':
            add(sub, 'AE', seq, "AESDTH is Y but AEOUT is not FATAL", 1.0)
        if aeout == 'FATAL' and aesdth != 'Y':
            add(sub, 'AE', seq, "AEOUT is FATAL but AESDTH is not Y", 1.0)
        if (aesdth == 'Y' or aeout == 'FATAL') and (dth is None or pd.isna(dth)):
            add(sub, 'AE', seq, "AE indicates death but DM has no DTHDTC for the subject", 1.0)
        if aeout.startswith('RECOVERED/RESOLVED') and pd.isna(en):
            add(sub, 'AE', seq, "AEOUT is recovered/resolved but AEENDTC is missing", 8.0)
        if pd.notna(en) and aeout in ('NOT RECOVERED/NOT RESOLVED', 'RECOVERING/RESOLVING'):
            add(sub, 'AE', seq,
                f"AEENDTC {txt(r['AEENDTC'])} present but AEOUT is {txt(r.get('AEOUT'))}", 8.0)
        crit = [txt(r.get(c)).upper() for c in SER_COLS]
        if aeser == 'Y' and crit and all(c != 'Y' for c in crit):
            add(sub, 'AE', seq,
                "AESER is Y but no seriousness criterion (death/life-threatening/hospitalization/disability/congenital/other) is Y", 7.0)
        if aeser == 'N' and any(c == 'Y' for c in crit):
            add(sub, 'AE', seq, "A seriousness criterion is Y but AESER is N", 7.0)
        term = (txt(r.get('AETERM')) + ' ' + txt(r.get('AEDECOD'))).upper()
        if 'PREGNAN' in term and SEX.get(sub) == 'M':
            add(sub, 'AE', seq, "Pregnancy-related AE reported for a male subject", 1.5)
    d = ae[ae['AESTDTC'].notna() & ae['AETERM'].notna()]
    dup = d[d.duplicated(subset=['USUBJID', 'AETERM', 'AESTDTC'], keep='first')]
    for _, r in dup.iterrows():
        add(txt(r['USUBJID']), 'AE', r['SEQN'],
            f"Possible duplicate AE: same term '{txt(r.get('AETERM'))}' and start date {txt(r.get('AESTDTC'))} as another record for this subject", 8.0)


def expected_dose(arm, visit):
    a = arm.lower()
    v = visit.upper()
    if a == 'placebo':
        return 0.0
    if a == 'xanomeline low dose':
        return 54.0
    if a == 'xanomeline high dose':
        return {'BASELINE': 54.0, 'WEEK 2': 81.0, 'WEEK 24': 54.0}.get(v)
    return None


def check_ex():
    for _, r in ex.iterrows():
        sub = txt(r['USUBJID'])
        seq = r['SEQN']
        st, en, dose = r['ST'], r['EN'], r['DOSE']
        visit = txt(r.get('VISIT'))
        arm = ARM.get(sub, '')
        exp = expected_dose(arm, visit) if arm else None
        if exp is not None and pd.notna(dose) and abs(dose - exp) > 0.001:
            if arm.lower() == 'placebo':
                add(sub, 'EX', seq,
                    f"Placebo-arm subject dosed with {dose:g} mg {txt(r.get('EXTRT'))} at {visit}; expected 0 mg (possible wrong treatment/unblinding)", 2.0)
            else:
                add(sub, 'EX', seq,
                    f"{arm} arm: EXDOSE {dose:g} mg at {visit} does not match protocol-expected {exp:g} mg", 2.2)
        if pd.notna(dose) and dose < 0:
            add(sub, 'EX', seq, f"EXDOSE {dose:g} mg is negative (impossible dose)", 5.0)
        if pd.isna(dose):
            add(sub, 'EX', seq, "EXDOSE is missing", 8.0)
        if pd.notna(st) and pd.notna(en) and en < st:
            add(sub, 'EX', seq,
                f"EXENDTC {txt(r['EXENDTC'])} is before EXSTDTC {txt(r['EXSTDTC'])}", 6.0)
        if pd.notna(st) and st > CUTOFF:
            add(sub, 'EX', seq,
                f"EXSTDTC {txt(r['EXSTDTC'])} is after the data cutoff 2014-12-17", 4.0)
        if pd.notna(en) and en > CUTOFF:
            add(sub, 'EX', seq,
                f"EXENDTC {txt(r['EXENDTC'])} is after the data cutoff 2014-12-17", 4.0)
        dth = DTH.get(sub)
        if dth is not None and pd.notna(dth):
            if pd.notna(en) and en.normalize() > dth.normalize():
                add(sub, 'EX', seq,
                    f"Dosing ends {txt(r['EXENDTC'])} after subject's death on {dth.date()}", 0.0)
            elif pd.notna(st) and st.normalize() > dth.normalize():
                add(sub, 'EX', seq,
                    f"Dosing starts {txt(r['EXSTDTC'])} after subject's death on {dth.date()}", 0.0)
        rst = RFST.get(sub)
        if rst is not None and pd.notna(rst) and pd.notna(st) and st.normalize() < rst.normalize():
            add(sub, 'EX', seq,
                f"EXSTDTC {txt(r['EXSTDTC'])} is before study reference start date {rst.date()}", 6.5)
        ren = RFEN.get(sub)
        if ren is not None and pd.notna(ren) and pd.notna(en) and en.normalize() > ren.normalize():
            add(sub, 'EX', seq,
                f"EXENDTC {txt(r['EXENDTC'])} is after study reference end date {ren.date()}", 6.5)
    for sub, g in ex.dropna(subset=['SEQN']).groupby('USUBJID'):
        g = g.sort_values('SEQN')
        prev_en, prev_seq = None, None
        for _, r in g.iterrows():
            if prev_en is not None and pd.notna(r['ST']) and pd.notna(prev_en):
                gap = (r['ST'].normalize() - prev_en.normalize()).days
                if gap <= 0:
                    add(txt(sub), 'EX', r['SEQN'],
                        f"Dosing record overlaps previous record (EXSEQ {int(prev_seq)} ended {prev_en.date()})", 8.0)
                elif gap > 3:
                    add(txt(sub), 'EX', r['SEQN'],
                        f"Gap of {gap} days since end of previous dosing record (EXSEQ {int(prev_seq)})", 8.0)
            if pd.notna(r['EN']):
                prev_en, prev_seq = r['EN'], r['SEQN']


def check_ds():
    for _, r in ds.iterrows():
        sub = txt(r['USUBJID'])
        seq = r['SEQN']
        st = r['ST']
        decod = txt(r.get('DSDECOD')).upper()
        if pd.notna(st) and st > CUTOFF:
            add(sub, 'DS', seq,
                f"DSSTDTC {txt(r['DSSTDTC'])} is after the data cutoff 2014-12-17", 4.0)
        rst = RFST.get(sub)
        if rst is not None and pd.notna(rst) and pd.notna(st) and st.normalize() < rst.normalize():
            add(sub, 'DS', seq,
                f"DSSTDTC {txt(r['DSSTDTC'])} is before study reference start date {rst.date()}", 6.5)
        if decod == 'DEATH':
            dth = DTH.get(sub)
            if dth is None or pd.isna(dth):
                add(sub, 'DS', seq, "Disposition records DEATH but DM has no DTHDTC", 1.0)
            elif pd.notna(st) and st.normalize() != dth.normalize():
                add(sub, 'DS', seq,
                    f"Death disposition date {txt(r['DSSTDTC'])} does not match DM DTHDTC {dth.date()}", 1.0)
        if decod == 'COMPLETED':
            ren = RFEN.get(sub)
            if rst is not None and ren is not None and pd.notna(rst) and pd.notna(ren):
                days = (ren.normalize() - rst.normalize()).days
                if days < 168:
                    add(sub, 'DS', seq,
                        f"DSDECOD is COMPLETED but treatment lasted only {days} days (protocol specifies 26 weeks)", 7.5)
    ds_death = set(txt(s) for s in
                   ds.loc[ds['DSDECOD'].apply(txt).str.upper() == 'DEATH', 'USUBJID'])
    for sub, dth in DTH.items():
        if dth is not None and pd.notna(dth) and sub not in ds_death:
            add(sub, 'DM', None,
                "Subject has DTHDTC in DM but no DEATH disposition record in DS", 1.0)


RANGES = {
    'SODIUM': (100, 180), 'NA': (100, 180),
    'POTASSIUM': (2.0, 8.0), 'K': (2.0, 8.0),
    'CHLORIDE': (70, 140), 'CL': (70, 140),
    'BICARB': (8, 45), 'CO2': (8, 45),
    'GLUC': (1.0, 40.0),
    'CREAT': (10, 1500),
    'BUN': (0.5, 60.0), 'UREA': (0.5, 60.0),
    'BILI': (1.0, 400.0),
    'ALT': (1, 5000), 'AST': (1, 5000), 'ALP': (10, 3000), 'GGT': (1, 3000),
    'LDH': (20, 5000),
    'ALB': (10, 65), 'TPROT': (30, 110), 'PROT': (30, 110),
    'CHOL': (1.0, 20.0), 'TRIG': (0.1, 30.0), 'HDL': (0.2, 6.0), 'LDL': (0.2, 12.0),
    'HGB': (40, 210), 'HCT': (0.15, 0.70), 'RBC': (1.5, 8.0),
    'WBC': (0.5, 200.0), 'PLAT': (10, 1500),
    'NEUT': (0.2, 150.0), 'LYMPH': (0.1, 100.0), 'MONO': (0.0, 40.0),
    'EOS': (0.0, 40.0), 'BASO': (0.0, 20.0),
    'CA': (1.0, 4.0), 'PHOS': (0.2, 4.0), 'MG': (0.2, 2.5),
    'CK': (5, 50000), 'HBA1C': (3.0, 20.0), 'TSH': (0.01, 200.0),
    'URATE': (50, 1200), 'MCH': (15, 45), 'MCV': (50, 130),
}
NONZERO = {'SODIUM', 'NA', 'POTASSIUM', 'K', 'CHLORIDE', 'CL', 'GLUC', 'CREAT',
           'HGB', 'HCT', 'RBC', 'WBC', 'PLAT', 'ALB', 'CA', 'BUN', 'UREA', 'CHOL'}


def check_lb():
    for _, r in lb.iterrows():
        sub = txt(r['USUBJID'])
        seq = r['SEQN']
        test = txt(r.get('LBTESTCD')).upper()
        unit = txt(r.get('LBSTRESU'))
        raw = txt(r.get('LBSTRESN'))
        v, dt = r['VAL'], r['DT']
        if raw and pd.isna(v):
            add(sub, 'LB', seq, f"LBSTRESN '{raw}' for {test} is not numeric", 5.0)
        if pd.notna(v):
            if v < 0:
                add(sub, 'LB', seq, f"{test} result {v:g} {unit} is negative (impossible)", 5.0)
            elif v == 0 and test in NONZERO:
                add(sub, 'LB', seq, f"{test} result of 0 {unit} is incompatible with life", 5.0)
            elif test in RANGES:
                lo, hi = RANGES[test]
                if test == 'HCT' and unit == '%':
                    lo, hi = 15.0, 70.0
                if v < lo or v > hi:
                    add(sub, 'LB', seq,
                        f"{test} result {v:g} {unit} is physiologically implausible (plausible SI range {lo:g}-{hi:g})", 5.0)
        if pd.notna(v) and not unit:
            add(sub, 'LB', seq, f"LBSTRESU is missing for {test} result {v:g}", 8.0)
        if pd.notna(dt) and dt > CUTOFF:
            add(sub, 'LB', seq,
                f"LBDTC {txt(r['LBDTC'])} is after the data cutoff 2014-12-17", 4.0)
        dth = DTH.get(sub)
        if dth is not None and pd.notna(dth) and pd.notna(dt) and dt.normalize() > dth.normalize():
            add(sub, 'LB', seq,
                f"Lab collected {txt(r['LBDTC'])} after subject's death on {dth.date()}", 0.0)
        rst = RFST.get(sub)
        visit = txt(r.get('VISIT')).upper()
        if rst is not None and pd.notna(rst) and pd.notna(dt):
            if 'SCREEN' in visit and dt.normalize() > rst.normalize():
                add(sub, 'LB', seq,
                    f"Screening lab dated {txt(r['LBDTC'])} after study start {rst.date()}", 7.0)
            m = re.search(r'WEEK\s+(\d+)', visit)
            if m:
                expd = 7 * int(m.group(1))
                actd = (dt.normalize() - rst.normalize()).days
                if abs(actd - expd) > 21:
                    add(sub, 'LB', seq,
                        f"Lab for {visit} collected {actd} days after study start (expected about day {expd})", 7.0)
    d = lb.dropna(subset=['DT'])
    dup = d[d.duplicated(subset=['USUBJID', 'LBTESTCD', 'VISIT', 'LBDTC'], keep='first')]
    for _, r in dup.iterrows():
        add(txt(r['USUBJID']), 'LB', r['SEQN'],
            f"Possible duplicate lab record for {txt(r.get('LBTESTCD'))} at {txt(r.get('VISIT'))} on {txt(r.get('LBDTC'))}", 8.0)


def main():
    for fn in (check_dm, check_ae, check_ex, check_ds, check_lb):
        try:
            fn()
        except Exception:
            traceback.print_exc()
    cols = ['USUBJID', 'DOMAIN', 'SEQ', 'ISSUE']
    out = pd.DataFrame(findings)
    if out.empty:
        out = pd.DataFrame(columns=cols)
    else:
        out = out.sort_values(by=['PRIO', 'USUBJID', 'DOMAIN', 'SEQN', 'ISSUE'],
                              kind='mergesort').head(25)
        out = out[cols]
    path = os.path.join(OUT_DIR, 'findings.csv')
    out.to_csv(path, index=False)
    print(f"Wrote {len(out)} finding(s) to {path}")
    assert os.path.isfile(path), "output/findings.csv was not written"


main()
