import csv
import calendar
from pathlib import Path

STUDYID = "MRN-319"
DOMAIN = "DM"

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}

RACE_TEXT_MAP = {
    "WHITE": "1",
    "BLACK OR AFRICAN AMERICAN": "2",
    "ASIAN": "3",
    "AMERICAN INDIAN OR ALASKA NATIVE": "4",
    "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER": "5",
}

FIELDNAMES = [
    "STUDYID",
    "DOMAIN",
    "USUBJID",
    "SUBJID",
    "SITEID",
    "BRTHDTC",
    "AGE",
    "AGEU",
    "SEX",
    "RACE",
    "ETHNIC",
    "ARMCD",
    "ARM",
    "RFICDTC",
    "RFSTDTC",
    "RFENDTC",
    "COUNTRY",
]


def parse_date(value):
    if value is None:
        return None

    s = str(value).strip().upper()
    if not s or s in {"NA", "NULL", "."}:
        return None

    if "-" in s:
        parts = s.split("-")
        try:
            year = int(parts[0])
        except ValueError:
            return None

        month = None
        day = None

        if len(parts) > 1 and parts[1]:
            try:
                month = int(parts[1])
            except ValueError:
                month = None

        if len(parts) > 2 and parts[2]:
            try:
                day = int(parts[2])
            except ValueError:
                day = None

        return (year, month, day)

    if len(s) < 9:
        if s.isdigit():
            return (int(s), None, None)
        return None

    day_s = s[:2]
    mon_s = s[2:5]
    year_s = s[5:9]

    if day_s == "UN":
        day = None
    elif day_s.isdigit():
        day = int(day_s)
    else:
        day = None

    if mon_s == "UNK":
        month = None
    else:
        month = MONTHS.get(mon_s)

    if year_s.isdigit():
        year = int(year_s)
    else:
        year = None

    if year is None:
        return None

    return (year, month, day)


def format_date(date):
    if not date:
        return ""

    year, month, day = date
    if year is None:
        return ""

    if month is None:
        return f"{year:04d}"

    if day is None:
        return f"{year:04d}-{month:02d}"

    return f"{year:04d}-{month:02d}-{day:02d}"


def min_key(date):
    year, month, day = date
    return (
        year if year is not None else 0,
        month if month is not None else 1,
        day if day is not None else 1,
    )


def max_key(date):
    year, month, day = date
    return (
        year if year is not None else 9999,
        month if month is not None else 12,
        day if day is not None else 31,
    )


def month_day_range(year, month, day):
    if year is None:
        return None

    if month is not None:
        if not 1 <= month <= 12:
            return None

        if day is not None:
            last_day = calendar.monthrange(year, month)[1]
            if not 1 <= day <= last_day:
                return None
            return ((month, day), (month, day))

        last_day = calendar.monthrange(year, month)[1]
        return ((month, 1), (month, last_day))

    if day is not None:
        if not 1 <= day <= 31:
            return None

        valid = []
        for m in range(1, 13):
            last_day = calendar.monthrange(year, m)[1]
            if day <= last_day:
                valid.append((m, day))

        if not valid:
            return None

        return (valid[0], valid[-1])

    return ((1, 1), (12, 31))


def compute_age(birth_date, consent_date):
    if not birth_date or not consent_date:
        return ""

    birth_year, birth_month, birth_day = birth_date
    consent_year, consent_month, consent_day = consent_date

    if birth_year is None or consent_year is None:
        return ""

    birth_range = month_day_range(birth_year, birth_month, birth_day)
    consent_range = month_day_range(consent_year, consent_month, consent_day)

    if not birth_range or not consent_range:
        return ""

    birth_min, birth_max = birth_range
    consent_min, consent_max = consent_range

    if consent_min >= birth_max:
        age = consent_year - birth_year
    elif consent_max < birth_min:
        age = consent_year - birth_year - 1
    else:
        return ""

    if age < 0:
        return ""

    return str(age)


def normalize_sex(value):
    s = str(value or "").strip().upper()
    if not s:
        return ""

    if s.isdigit():
        code = int(s)
        if code == 1:
            return "1"
        if code == 2:
            return "2"
        return ""

    if s in {"M", "MALE"}:
        return "1"
    if s in {"F", "FEMALE"}:
        return "2"

    return ""


def normalize_race(value):
    s = str(value or "").strip().upper()
    if not s:
        return ""

    if s.isdigit():
        code = int(s)
        if 1 <= code <= 5:
            return str(code)
        return ""

    return RACE_TEXT_MAP.get(s, "")


def normalize_ethnic(value):
    s = str(value or "").strip().upper()
    if s in {"YES", "Y"}:
        return "HISPANIC OR LATINO"
    if s in {"NO", "N"}:
        return "NOT HISPANIC OR LATINO"
    return ""


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    input_dir = Path("input")
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    demog = read_csv(input_dir / "raw_demog.csv")
    consent = read_csv(input_dir / "raw_consent.csv")
    rand = read_csv(input_dir / "raw_rand.csv")
    dosing = read_csv(input_dir / "raw_dosing.csv")
    sites = read_csv(input_dir / "sites.csv")

    consent_map = {}
    for row in consent:
        subject = str(row.get("SUBJECT") or "").strip()
        if not subject:
            continue

        date = parse_date(row.get("ICDAT"))

        if subject not in consent_map:
            consent_map[subject] = date
        elif consent_map[subject] is None and date is not None:
            consent_map[subject] = date
        elif consent_map[subject] is not None and date is not None:
            if min_key(date) < min_key(consent_map[subject]):
                consent_map[subject] = date

    rand_map = {}
    for row in rand:
        subject = str(row.get("SUBJECT") or "").strip()
        trt = str(row.get("TRT_GROUP") or "").strip().upper()
        if subject and trt and subject not in rand_map:
            rand_map[subject] = trt

    dosing_map = {}
    for row in dosing:
        subject = str(row.get("SUBJECT") or "").strip()
        if not subject:
            continue

        start = parse_date(row.get("DOSE_START"))
        end = parse_date(row.get("DOSE_END"))

        entry = dosing_map.setdefault(subject, {"starts": [], "ends": []})
        if start:
            entry["starts"].append(start)
        if end:
            entry["ends"].append(end)

    site_map = {}
    for row in sites:
        site = str(row.get("SITE") or "").strip()
        country = str(row.get("COUNTRY") or "").strip()
        if site:
            site_map[site] = country

    rows = []
    seen = set()

    for row in demog:
        subject = str(row.get("SUBJECT") or "").strip()
        if not subject or subject in seen:
            continue
        seen.add(subject)

        if "-" in subject:
            site, subjid = subject.split("-", 1)
        else:
            site, subjid = "", subject

        site = site.strip()
        subjid = subjid.strip()
        usubjid = f"{STUDYID}-{site}-{subjid}"

        birth_date = parse_date(row.get("BRTHDAT"))
        consent_date = consent_map.get(subject)

        sex = normalize_sex(row.get("SEX"))
        race = normalize_race(row.get("RACE"))
        ethnic = normalize_ethnic(row.get("HISPANIC"))

        trt = rand_map.get(subject, "")
        if trt in ARM_MAP:
            armcd, arm = ARM_MAP[trt]
        else:
            armcd, arm = "SCRNFAIL", "Screen Failure"

        rfstdtc = ""
        rfendtc = ""

        dosing_entry = dosing_map.get(subject)
        if dosing_entry:
            starts = dosing_entry["starts"]
            ends = dosing_entry["ends"]

            if starts:
                rfstdtc = format_date(min(starts, key=min_key))

            all_dates = starts + ends
            if all_dates:
                rfendtc = format_date(max(all_dates, key=max_key))

        country = site_map.get(site, "")
        age = compute_age(birth_date, consent_date)

        rows.append(
            {
                "STUDYID": STUDYID,
                "DOMAIN": DOMAIN,
                "USUBJID": usubjid,
                "SUBJID": subjid,
                "SITEID": site,
                "BRTHDTC": format_date(birth_date),
                "AGE": age,
                "AGEU": "YEARS",
                "SEX": sex,
                "RACE": race,
                "ETHNIC": ethnic,
                "ARMCD": armcd,
                "ARM": arm,
                "RFICDTC": format_date(consent_date),
                "RFSTDTC": rfstdtc,
                "RFENDTC": rfendtc,
                "COUNTRY": country,
            }
        )

    rows.sort(key=lambda r: r["USUBJID"])

    with open(output_dir / "dm.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
