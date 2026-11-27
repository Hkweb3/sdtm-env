import os
import pandas as pd

CUTOFF = pd.Timestamp('2014-09-08')
ARMS = {'Placebo', 'Xanomeline Low Dose', 'Xanomeline High Dose'}
SER_COLS = ['AESDTH', 'AESLIFE', 'AESHOSP', 'AESDISAB', 'AESCONG', 'AESCAN', 'AESOD']

# Wide physiologically-possible limits in SI units. Values outside are
# impossible or indicate a wrong unit of measure (not ordinary abnormalities).
LB_RANGES = {
    'GLUC': (1.5, 40.0), 'CREAT': (15.0, 1200.0), 'BILI': (1.0, 400.0),
    'ALT': (1.0, 5000.0), 'AST': (1.0, 5000.0), 'ALP': (10.0, 3000.0),
    'GGT': (1.0, 3000.0), 'LDH': (20.0, 5000.0), 'CK': (5.0, 50000.0),
    'SODIUM': (100.0, 180.0), 'NA': (100.0, 180.0),
    'POTASSIUM': (1.5, 10.0), 'K': (1.5, 10.0),
    'CHLORIDE': (70.0, 140.0), 'CL': (70.0, 140.0),
    'BICARB': (5.0, 45.0), 'CO2': (5.0, 45.0),
    'UREA': (0.5, 60.0), 'BUN': (0.5, 60.0),
    'CALCIUM': (1.0, 4.0), 'CA': (1.0, 4.0),
    'PHOS': (0.2, 4.0), 'PHOSPHATE': (0.2, 4.0),
    'MAGNESIUM': (0.2, 2.5), 'MG': (0.2, 2.5),
    'HGB': (50.0, 220.0), 'HCT': (0.15, 0.70), 'RBC': (1.5, 8.0),
    'WBC': (0.5, 100.0), 'PLAT': (10.0, 1500.0),
    'NEUT': (0.05, 100.0), 'LYMPH': (0.05, 100.0),
    'MONO': (0.0, 100.0), 'EOS': (0.0, 100.0), 'BASO': (0.0, 100.0),
    'CHOL': (1.0, 20.0), 'HDL': (0.2, 6.0), 'LDL': (0.2, 15.0),
    'TRIG': (0.1, 30.0), 'ALB': (10.0, 70.0), 'PROT': (20.0, 120.0),
    'URATE': (50.0, 1500.0), 'TSH': (0.01, 200.0), 'CRP': (0.0, 500.0),
    'PH': (4.0, 9.5), 'SG': (1.0, 1.1),
}

os.makedirs('output', exist_ok=True)

dm = pd.read_csv('input/dm.csv', dtype=str).fillna('')
ae = pd.read_csv('input/ae.csv', dtype=str).fillna('')
ex = pd.read_csv('input/ex.csv', dtype=str).fillna('')
ds = pd.read_csv('input/ds.csv', dtype=str).fillna('')
lb = pd.read_csv('input/lb.csv', dtype=str).fillna('')

for c in ['BRTHDTC', 'RFSTDTC', 'RFENDTC', 'DTHDTC']:
    dm[c + '_dt'] = pd.to_datetime(dm[c], errors='coerce')
ae['AESTDTC_dt'] = pd.to_datetime(ae['AESTDTC'], errors='coerce')
ae['AEENDTC_dt'] = pd.to_datetime(ae['AEENDTC'], errors='coerce')
ex['EXSTDTC_dt'] = pd.to_datetime(ex['EXSTDTC'], errors='coerce')
ex['EXENDTC_dt'] = pd.to_datetime(ex['EXENDTC'], errors='coerce')
ds['DSSTDTC_dt'] = pd.to_datetime(ds['DSSTDTC'], errors='coerce')
lb['LBDTC_dt'] = pd.to_datetime(lb['LBDTC'], errors='coerce')

dmi = dm.set_index('USUBJID')
arm_map = dmi['ARM'].to_dict()
rfst_map = dmi['RFSTDTC_dt'].to_dict()
rfend_map = dmi['RFENDTC_dt'].to_dict()
dth_map = dmi['DTHDTC_dt'].to_dict()

findings = []

def add(prio, subj, domain, seq, issue):
    findings.append({'PRIO': prio, 'USUBJID': subj, 'DOMAIN': domain,
                     'SEQ': str(seq), 'ISSUE': issue})

def after_cutoff(d):
    return pd.notna(d) and d.normalize() > CUTOFF

def after_death(d, dth):
    return pd.notna(d) and pd.notna(dth) and d.normalize() > dth.normalize()

# ---------------- DM ----------------
ds_death_subj = set(ds.loc[ds['DSDECOD'].str.upper().str.contains('DEATH'), 'USUBJID'])
for _, r in dm.iterrows():
    s = r['USUBJID']
    age = pd.to_numeric(r['AGE'], errors='coerce')
    brth, rfst, rfend, dth = r['BRTHDTC_dt'], r['RFSTDTC_dt'], r['RFENDTC_dt'], r['DTHDTC_dt']
    if pd.notna(age) and age < 50:
        add(7, s, 'DM', '', f"AGE {int(age)} at entry violates the protocol inclusion criterion of age >= 50")
    if pd.notna(age) and pd.notna(brth) and pd.notna(rfst):
        calc = rfst.year - brth.year - ((rfst.month, rfst.day) < (brth.month, brth.day))
        if int(age) != calc:
            add(7, s, 'DM', '', f"AGE {int(age)} is inconsistent with birth date {r['BRTHDTC']} and start date {r['RFSTDTC']} (expected {calc})")
    if r['SEX'] not in ('M', 'F'):
        add(7, s, 'DM', '', f"SEX '{r['SEX']}' is not a valid value")
    if r['ARM'] not in ARMS:
        add(4, s, 'DM', '', f"ARM '{r['ARM']}' is not one of the protocol treatment arms")
    if pd.notna(rfst) and pd.notna(rfend) and rfend < rfst:
        add(6, s, 'DM', '', f"RFENDTC {r['RFENDTC']} is before RFSTDTC {r['RFSTDTC']}")
    if after_cutoff(rfend):
        add(5, s, 'DM', '', f"RFENDTC {r['RFENDTC']} is after the data cutoff 2014-09-08")
    if after_cutoff(dth):
        add(5, s, 'DM', '', f"DTHDTC {r['DTHDTC']} is after the data cutoff 2014-09-08")
    if r['DTHFL'].upper() == 'Y' and r['DTHDTC'] == '':
        add(1, s, 'DM', '', "DTHFL=Y but no death date (DTHDTC) is recorded")
    if r['DTHFL'].upper() != 'Y' and r['DTHDTC'] != '':
        add(1, s, 'DM', '', f"Death date {r['DTHDTC']} recorded but DTHFL is not Y")
    if r['DTHFL'].upper() == 'Y' and s not in ds_death_subj:
        add(1, s, 'DM', '', "Subject has DTHFL=Y but no death disposition record in DS")

# ---------------- AE ----------------
# data-driven body-system consistency: modal AEBODSYS per AEDECOD
ae_mode = ae.groupby('AEDECOD')['AEBODSYS'].agg(lambda x: x.value_counts().idxmax() if len(x) else '')
ae_cnt = ae.groupby(['AEDECOD', 'AEBODSYS']).size()

for _, r in ae.iterrows():
    s, q = r['USUBJID'], r['AESEQ']
    st, en = r['AESTDTC_dt'], r['AEENDTC_dt']
    dth = dth_map.get(s)
    if pd.notna(st) and pd.notna(en) and en < st:
        add(6, s, 'AE', q, f"AE end date {r['AEENDTC']} is before start date {r['AESTDTC']}")
    if after_cutoff(st):
        add(5, s, 'AE', q, f"AE start date {r['AESTDTC']} is after the data cutoff 2014-09-08")
    if after_cutoff(en):
        add(5, s, 'AE', q, f"AE end date {r['AEENDTC']} is after the data cutoff 2014-09-08")
    if after_death(st, dth):
        add(1, s, 'AE', q, f"AE start date {r['AESTDTC']} is after the subject's death date")
    crit_yes = any(r[c].upper() == 'Y' for c in SER_COLS)
    if r['AESER'].upper() == 'Y' and not crit_yes:
        add(3, s, 'AE', q, "AESER=Y but none of the seriousness criteria (death/life-threat/hosp/disab/cong/other) is checked")
    if r['AESER'].upper() != 'Y' and crit_yes:
        add(3, s, 'AE', q, "A seriousness criterion is checked but AESER is not Y")
    if (r['AEOUT'].upper() == 'FATAL' or r['AESDTH'].upper() == 'Y') and pd.isna(dth):
        add(1, s, 'AE', q, "AE is fatal (AEOUT/AESDTH) but no death date is recorded in DM")
    if r['AEOUT'].upper() == 'RECOVERED/RESOLVED' and pd.isna(en):
        add(10, s, 'AE', q, "Outcome is RECOVERED/RESOLVED but no AE end date is recorded")
    bod = r['AEBODSYS'].upper()
    decod = r['AEDECOD'].upper()
    if 'PREGNANCY' in bod and not any(k in decod for k in ('PREGN', 'FOET', 'FET', 'LABOUR', 'ABORT')):
        add(8, s, 'AE', q, f"AEBODSYS '{r['AEBODSYS']}' is implausible for AEDECOD '{r['AEDECOD']}'")
    else:
        m = ae_mode.get(r['AEDECOD'])
        if m and r['AEBODSYS'] != m and ae_cnt.get((r['AEDECOD'], m), 0) >= 2 \
                and ae_cnt.get((r['AEDECOD'], r['AEBODSYS']), 0) < ae_cnt.get((r['AEDECOD'], m), 0):
            add(8, s, 'AE', q, f"AEBODSYS '{r['AEBODSYS']}' inconsistent with other '{r['AEDECOD']}' records ('{m}')")

# ---------------- EX ----------------
for _, r in ex.iterrows():
    s, q = r['USUBJID'], r['EXSEQ']
    arm = arm_map.get(s, '')
    visit = r['VISIT'].upper()
    dose = pd.to_numeric(r['EXDOSE'], errors='coerce')
    trt = r['EXTRT'].upper()
    exp_trt = exp_dose = None
    if arm == 'Placebo':
        exp_trt, exp_dose = 'PLACEBO', 0
    elif arm == 'Xanomeline Low Dose':
        exp_trt, exp_dose = 'XANOMELINE', 54
    elif arm == 'Xanomeline High Dose':
        exp_trt = 'XANOMELINE'
        exp_dose = 81 if visit == 'WEEK 2' else 54
    if exp_trt and trt != exp_trt:
        add(4, s, 'EX', q, f"EXTRT '{r['EXTRT']}' is inconsistent with randomized arm '{arm}'")
    elif exp_dose is not None and pd.notna(dose) and dose != exp_dose:
        add(4, s, 'EX', q, f"EXDOSE {r['EXDOSE']} mg at {r['VISIT']} does not match the protocol schedule for arm '{arm}' (expected {exp_dose} mg)")
    st, en = r['EXSTDTC_dt'], r['EXENDTC_dt']
    if pd.notna(st) and pd.notna(en) and en < st:
        add(6, s, 'EX', q, f"EX end date {r['EXENDTC']} is before start date {r['EXSTDTC']}")
    if after_cutoff(st):
        add(5, s, 'EX', q, f"EX start date {r['EXSTDTC']} is after the data cutoff 2014-09-08")
    if after_cutoff(en):
        add(5, s, 'EX', q, f"EX end date {r['EXENDTC']} is after the data cutoff 2014-09-08")
    rfst, rfend = rfst_map.get(s), rfend_map.get(s)
    if pd.notna(st) and pd.notna(rfst) and st < rfst:
        add(11, s, 'EX', q, f"Dosing start {r['EXSTDTC']} is before the subject's reference start date {dmi.loc[s, 'RFSTDTC']}")
    if pd.notna(en) and pd.notna(rfend) and en.normalize() > rfend.normalize():
        add(11, s, 'EX', q, f"Dosing end {r['EXENDTC']} is after the subject's reference end date {dmi.loc[s, 'RFENDTC']}")
    if after_death(st, dth_map.get(s)):
        add(1, s, 'EX', q, f"Dosing start {r['EXSTDTC']} is after the subject's death date")

# ---------------- LB ----------------
for _, r in lb.iterrows():
    s, q = r['USUBJID'], r['LBSEQ']
    val = pd.to_numeric(r['LBSTRESN'], errors='coerce')
    tc = r['LBTESTCD'].upper().strip()
    if pd.notna(val):
        if val < 0:
            add(2, s, 'LB', q, f"{r['LBTEST']} result {val} {r['LBSTRESU']} is negative, which is not physiologically possible")
        elif tc in LB_RANGES:
            lo, hi = LB_RANGES[tc]
            if not (lo <= val <= hi):
                add(2, s, 'LB', q, f"{r['LBTEST']} {val} {r['LBSTRESU']} is outside the plausible SI range ({lo}-{hi}); likely a unit-of-measure or transcription error")
    d = r['LBDTC_dt']
    if after_cutoff(d):
        add(5, s, 'LB', q, f"Lab collection date {r['LBDTC']} is after the data cutoff 2014-09-08")
    if after_death(d, dth_map.get(s)):
        add(1, s, 'LB', q, f"Lab collection date {r['LBDTC']} is after the subject's death date")

# LB unit consistency: modal unit per test
if len(lb):
    umode = lb.groupby('LBTESTCD')['LBSTRESU'].agg(lambda x: x.value_counts().idxmax() if len(x) else '')
    ucnt = lb.groupby(['LBTESTCD', 'LBSTRESU']).size()
    utot = lb.groupby('LBTESTCD').size()
    for _, r in lb.iterrows():
        tc, u = r['LBTESTCD'], r['LBSTRESU']
        m = umode.get(tc)
        if m and u != m and utot.get(tc, 0) >= 10 and ucnt.get((tc, u), 0) <= 0.1 * utot[tc]:
            add(9, s if False else r['USUBJID'], 'LB', r['LBSEQ'],
                f"Unit '{u}' for {r['LBTEST']} differs from the unit used for this test throughout the study ('{m}')")

# LB duplicates: same subject, test, visit and collection datetime
dup = lb.duplicated(subset=['USUBJID', 'LBTESTCD', 'VISIT', 'LBDTC'], keep='first')
for i in lb.index[dup]:
    r = lb.loc[i]
    add(9, r['USUBJID'], 'LB', r['LBSEQ'],
        f"Duplicate record: same {r['LBTESTCD']} result collected at {r['VISIT']} on {r['LBDTC']} appears more than once")

# ---------------- DS ----------------
for _, r in ds.iterrows():
    s, q = r['USUBJID'], r['DSSEQ']
    d = r['DSSTDTC_dt']
    dth = dth_map.get(s)
    if after_cutoff(d):
        add(5, s, 'DS', q, f"Disposition date {r['DSSTDTC']} is after the data cutoff 2014-09-08")
    if 'DEATH' in r['DSDECOD'].upper():
        if pd.isna(dth):
            add(1, s, 'DS', q, "Death disposition recorded but DM has no death date for this subject")
    elif after_death(d, dth):
        add(1, s, 'DS', q, f"Disposition date {r['DSSTDTC']} is after the subject's death date")
    rfst = rfst_map.get(s)
    if pd.notna(d) and pd.notna(rfst) and d < rfst:
        add(6, s, 'DS', q, f"Disposition date {r['DSSTDTC']} is before the subject's reference start date {dmi.loc[s, 'RFSTDTC']}")

# ---------------- output ----------------
out = pd.DataFrame(findings, columns=['PRIO', 'USUBJID', 'DOMAIN', 'SEQ', 'ISSUE'])
if len(out):
    out = out.drop_duplicates(subset=['USUBJID', 'DOMAIN', 'SEQ', 'ISSUE'])
    out['_seq'] = pd.to_numeric(out['SEQ'], errors='coerce').fillna(0)
    out = out.sort_values(['PRIO', 'USUBJID', 'DOMAIN', '_seq']).head(25)
    out = out[['USUBJID', 'DOMAIN', 'SEQ', 'ISSUE']]
else:
    out = pd.DataFrame(columns=['USUBJID', 'DOMAIN', 'SEQ', 'ISSUE'])
out.to_csv('output/findings.csv', index=False)
