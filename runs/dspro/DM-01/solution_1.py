import csv
import os
from datetime import date

MONTHS = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}


def parse_date(raw):
    """Parse a raw date like '07 MAR 2014', 'UN MAR 2014', or 'UN UNK 2014'."""
    if not raw:
        return None
    parts = raw.strip().split()
    if len(parts) != 3:
        return None

    day_s, mon_s, year_s = parts
    try:
        year = int(year_s)
    except ValueError:
        return None

    month = MONTHS.get(mon_s.upper())

    if day_s.upper() == 'UN':
        day = None
    else:
        try:
            day = int(day_s)
        except ValueError:
            day = None

    return (year, month, day)


def to_iso(d):
    """Convert parsed date tuple to SDTM ISO 8601-like date string."""
    if d is None:
        return ''
    year, month, day = d
    if month is not None and day is not None:
        return f"{year:04d}-{month:02d}-{day:02d}"
    elif month is not None:
        return f"{year:04d}-{month:02d}"
    else:
        return f"{year:04d}"


def sort_key(d):
    if d is None:
        return (0, 0, 0)
    year, month, day = d
    return (year, month if month is not None else 0, day if day is not None else 0)


def completed_years(birth_tuple, rfic_tuple):
    if birth_tuple is None or rfic_tuple is None:
        return ''
    if birth_tuple[1] is None or birth_tuple[2] is None:
        return ''
    if rfic_tuple[1] is None or rfic_tuple[2] is None:
        return ''

    bdate = date(birth_tuple[0], birth_tuple[1], birth_tuple[2])
    cdate = date(rfic_tuple[0], rfic_tuple[1], rfic_tuple[2])
    return cdate.year - bdate.year - ((cdate.month, cdate.day) < (bdate.month, bdate.day))


def main():
    sites = {}
    with open('input/sites.csv', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sites[row['SITE'].strip()] = row['COUNTRY'].strip()

    consents = {}
    with open('input/raw_consent.csv', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            consents[row['SUBJECT'].strip()] = row['ICDAT'].strip()

    rands = {}
    with open('input/raw_rand.csv', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rands[row['SUBJECT'].strip()] = row['TRT_GROUP'].strip()

    dosing = {}
    with open('input/raw_dosing.csv', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            subject = row['SUBJECT'].strip()
            start_tuple = parse_date(row['DOSE_START'])
            end_tuple = parse_date(row['DOSE_END'])
            dosing.setdefault(subject, []).append((start_tuple, end_tuple))

    arm_map = {
        'A': ('PBO', 'Placebo'),
        'B': ('XANLO', 'Xanomeline Low Dose'),
        'C': ('XANHI', 'Xanomeline High Dose'),
    }

    rows = []

    with open('input/raw_demog.csv', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            subject = row['SUBJECT'].strip()
            site, subjid = subject.split('-', 1)
            usubjid = f"KVT-998-{site}-{subjid}"

            birth_tuple = parse_date(row['BRTHDAT'])
            birth_iso = to_iso(birth_tuple)

            consent_raw = consents.get(subject, '')
            rfic_tuple = parse_date(consent_raw) if consent_raw else None
            rfic_iso = to_iso(rfic_tuple) if rfic_tuple else ''

            age = completed_years(birth_tuple, rfic_tuple)

            sex_raw = row['SEX'].strip().lower()
            if sex_raw == 'female':
                sex = 'F'
            elif sex_raw == 'male':
                sex = 'M'
            else:
                sex = row['SEX'].strip()

            race = row['RACE'].strip().upper()

            hispanic = row['HISPANIC'].strip()
            if hispanic.upper() == 'YES':
                ethnic = 'HISPANIC OR LATINO'
            elif hispanic.upper() == 'NO':
                ethnic = 'NOT HISPANIC OR LATINO'
            else:
                ethnic = ''

            trt = rands.get(subject, '').strip().upper()
            if trt in arm_map:
                armcd, arm = arm_map[trt]
            else:
                armcd, arm = 'SCRNFAIL', 'Screen Failure'

            subj_dosing = dosing.get(subject, [])
            rfstdtc = ''
            rfendtc = ''

            if subj_dosing:
                starts = [item[0] for item in subj_dosing if item[0] is not None]
                if starts:
                    rfstdtc = to_iso(min(starts, key=sort_key))

                all_dates = []
                for start_tuple, end_tuple in subj_dosing:
                    if start_tuple is not None:
                        all_dates.append(start_tuple)
                    if end_tuple is not None:
                        all_dates.append(end_tuple)

                if all_dates:
                    rfendtc = to_iso(max(all_dates, key=sort_key))

            country = sites.get(site, '')

            rows.append({
                'STUDYID': 'KVT-998',
                'DOMAIN': 'DM',
                'USUBJID': usubjid,
                'SUBJID': subjid,
                'SITEID': site,
                'BRTHDTC': birth_iso,
                'AGE': age,
                'AGEU': 'YEARS',
                'SEX': sex,
                'RACE': race,
                'ETHNIC': ethnic,
                'ARMCD': armcd,
                'ARM': arm,
                'RFICDTC': rfic_iso,
                'RFSTDTC': rfstdtc,
                'RFENDTC': rfendtc,
                'COUNTRY': country,
            })

    rows.sort(key=lambda r: r['USUBJID'])

    os.makedirs('output', exist_ok=True)

    fieldnames = [
        'STUDYID', 'DOMAIN', 'USUBJID', 'SUBJID', 'SITEID', 'BRTHDTC',
        'AGE', 'AGEU', 'SEX', 'RACE', 'ETHNIC', 'ARMCD', 'ARM',
        'RFICDTC', 'RFSTDTC', 'RFENDTC', 'COUNTRY'
    ]

    with open('output/dm.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    main()
