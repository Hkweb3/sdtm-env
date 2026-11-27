```python
import os
import pandas as pd

CUTOFF = pd.Timestamp('2014-09-08')
ARMS = {'Placebo', 'Xanomeline Low Dose', 'Xanomeline High Dose'}
SER_COLS = ['AESDTH', 'AESLIFE', 'AESHOSP', 'AESDISAB', 'AESCONG', 'AESOD']
AEOUT_CT = {'RECOVERED/RESOLVED', 'RECOVERING/RESOLVING', 'NOT RECOVERED/NOT RESOLVED',
            'RECOVERED/RESOLVED WITH SEQUELAE', 'FATAL', 'UNKNOWN'}

# Wide physiologically-possible limits in SI units; values outside are
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
}

os.makedirs('output', exist_ok=True)

dm = pd.read_csv('input/dm.csv', dtype=str).fillna('')
ae = pd.read_csv('input/ae.csv', dtype=str).fillna('')
ex = pd.read_csv('input/ex.csv', dtype=str).fillna('')
ds = pd.read_csv('input/ds.csv', dtype=str).fillna('')
lb = pd.read_csv('input/lb.csv', dtype=str).fillna('')

def to_dt(s):
    return pd.to_datetime(s, errors='coerce')

for c in ['BRTHDTC', 'RFSTDTC', 'RFENDTC', 'DTHDTC']:
    dm[c + '_dt'] = to_dt(dm[c])
dm['AGE_n'] = pd.to_numeric(dm['AGE'], errors='coerce')
ae['AESTDTC_dt'] = to_dt(ae['AESTDTC'])
ae['AEENDTC_dt'] = to_dt(ae['AEENDTC'])
ex['EXSTD