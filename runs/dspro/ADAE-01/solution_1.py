import csv
import os
from datetime import datetime, date, timedelta
from calendar import monthrange


def parse_complete_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        if len(s) == 10:
            return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        pass
    return None


def parse_year_month(s):
    if not s:
        return None
    s = s.strip()
    try:
        if len(s) == 7:
            dt = datetime.strptime(s, '%Y-%m')
            return dt.year, dt.month
    except ValueError:
        pass
    return None


def parse_year(s):
    if not s:
        return None
    s = s.strip()
    if len(s) == 4 and s.isdigit():
        return int(s)
    return None


def impute_end(endtc):
    s = (endtc or '').strip()
    if not s:
        return '', ''

    if len(s) == 10 and parse_complete_date(s):
        return s, ''

    ym = parse_year_month(s)
    if ym:
        y, m = ym
        return f"{y:04d}-{m:02d}-{monthrange(y, m)[1]:02d}", 'D'

    y = parse_year(s)
    if y is not None:
        return f"{y:04d}-12-31", 'M'

    return '', ''


def impute_start(starttc, trtsdt):
    s = (starttc or '').strip()
    trts_dt = parse_complete_date(trtsdt)

    if not s:
        return (trtsdt or ''), 'Y'

    if len(s) == 10 and parse_complete_date(s):
        return s, ''

    ym = parse_year_month(s)
    if ym:
        y, m = ym
        if trts_dt and trts_dt.year == y and trts_dt.month == m:
            return trtsdt, 'D'
        return f"{y:04d}-{m:02d}-01", 'D'

    y = parse_year(s)
    if y is not None:
        if trts_dt and trts_dt.year == y:
            return trtsdt, 'M'
        return f"{y:04d}-01-01", 'M'

    return '', ''


def main():
    os.makedirs('output', exist_ok=True)

    adsl = {}
    with open('input/adsl.csv', newline='') as f:
        for row in csv.DictReader(f):
            adsl[(row.get('USUBJID') or '').strip()] = {
                'TRTSDT': (row.get('TRTSDT') or '').strip(),
                'TRTEDT': (row.get('TRTEDT') or '').strip(),
            }

    records = []
    with open('input/ae.csv', newline='') as f:
        for row in csv.DictReader(f):
            usubjid = (row.get('USUBJID') or '').strip()
            trtsdt = adsl.get(usubjid, {}).get('TRTSDT', '')
            trtedt = adsl.get(usubjid, {}).get('TRTEDT', '')

            trts_dt = parse_complete_date(trtsdt)
            trted_dt = parse_complete_date(trtedt)

            aendt, aendtf = impute_end(row.get('AEENDTC'))
            astdt, astdtf = impute_start(row.get('AESTDTC'), trtsdt)

            ast_dt = parse_complete_date(astdt)
            end_dt = parse_complete_date(aendt)

            if astdtf and aendtf == '' and aendt and ast_dt and end_dt and ast_dt > end_dt:
                astdt = aendt
                ast_dt = end_dt

            astdys = ''
            aendys = ''
            if ast_dt and trts_dt:
                diff = (ast_dt - trts_dt).days
                astdys = str(diff + 1) if diff >= 0 else str(diff)
            if end_dt and trts_dt:
                diff = (end_dt - trts_dt).days
                aendys = str(diff + 1) if diff >= 0 else str(diff)

            adurns = ''
            if ast_dt and end_dt:
                adurns = str((end_dt - ast_dt).days + 1)

            trtemfl = ''
            if ast_dt and trts_dt and trted_dt:
                if trts_dt <= ast_dt <= trted_dt + timedelta(days=30):
                    trtemfl = 'Y'

            try:
                aeseq_int = int((row.get('AESEQ') or '').strip())
            except ValueError:
                aeseq_int = 0

            records.append({
                'STUDYID': (row.get('STUDYID') or '').strip(),
                'USUBJID': usubjid,
                'AESEQ': (row.get('AESEQ') or '').strip(),
                'AETERM': (row.get('AETERM') or '').strip(),
                'AEDECOD': (row.get('AEDECOD') or '').strip(),
                'AEBODSYS': (row.get('AEBODSYS') or '').strip(),
                'TRTSDT': trtsdt,
                'TRTEDT': trtedt,
                'ASTDT': astdt,
                'ASTDTF': astdtf,
                'AENDT': aendt,
                'AENDTF': aendtf,
                'ASTDY': astdys,
                'AENDY': aendys,
                'ADURN': adurns,
                'TRTEMFL': trtemfl,
                'AOCCFL': '',
                'AOCCPFL': '',
                '_astdt_dt': ast_dt,
                '_aeseq_int': aeseq_int,
            })

    sorted_for_occ = sorted(
        records,
        key=lambda r: (r['USUBJID'], r['_astdt_dt'] or date.min, r['_aeseq_int'])
    )

    first_subject = set()
    first_term = set()

    for rec in sorted_for_occ:
        if rec['TRTEMFL'] == 'Y':
            subj = rec['USUBJID']

            if subj not in first_subject:
                rec['AOCCFL'] = 'Y'
                first_subject.add(subj)

            term_key = (subj, rec['AEDECOD'])
            if term_key not in first_term:
                rec['AOCCPFL'] = 'Y'
                first_term.add(term_key)

    output_fields = [
        'STUDYID', 'USUBJID', 'AESEQ', 'AETERM', 'AEDECOD', 'AEBODSYS',
        'TRTSDT', 'TRTEDT', 'ASTDT', 'ASTDTF', 'AENDT', 'AENDTF',
        'ASTDY', 'AENDY', 'ADURN', 'TRTEMFL', 'AOCCFL', 'AOCCPFL'
    ]

    output_records = sorted(
        records,
        key=lambda r: (r['USUBJID'], r['_aeseq_int'])
    )

    with open('output/adae.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=output_fields, lineterminator='\n')
        writer.writeheader()
        for rec in output_records:
            writer.writerow({k: rec[k] for k in output_fields})


if __name__ == '__main__':
    main()
