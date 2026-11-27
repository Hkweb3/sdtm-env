import csv
import os
import pandas as pd

STUDYID = "PLX-295"
DOMAIN = "DM"

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}
SCREEN_FAIL = ("SCRNFAIL", "Screen Failure")

COLUMNS = [
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


def clean(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    if s in {"", "NA", "NULL", "None", "nan", "."}:
        return ""
    return s


def _int_or_none(value):
    s = str(value).strip()
    if not s:
        return None
    if not s.isdigit():
        return None
    return int(s)


def _make_date(year, month, day):
    if year is None:
        return None
    if month is None:
        day = None
    if month is not None and not 1 <= month <= 12:
        return None
    if day is not None and not 1 <= day <= 31:
        return None
    return {"year": year, "month": month, "day": day}


def parse_date(value):
    s = clean(value)
    if not s:
        return None

    if "-" in s:
        parts = s.split("-")
        if len(parts) == 3:
            year = _int_or_none(parts[0])
            month = _int_or_none(parts[1])
            day = _int_or_none(parts[2])
            return _make_date(year, month, day)
        if len(parts) == 2:
            year = _int_or_none(parts[0])
            month = _int_or_none(parts[1])
            return _make_date(year, month, None)
        if len(parts) == 1:
            year = _int_or_none(parts[0])
            return _make_date(year, None, None)

    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            if len(parts[0]) == 4 and parts[0].isdigit():
                year = _int_or_none(parts[0])
                month = _int_or_none(parts[1])
                day = _int_or_none(parts[2])
            else:
                month = _int_or_none(parts[0])
                day = _int_or_none(parts[1])
                year = _int_or_none(parts[2])
            return _make_date(year, month, day)

        if len(parts) == 2:
            a, b = parts
            if a and b:
                if len(a) == 4 and a.isdigit():
                    year = _int_or_none(a)
                    month = _int_or_none(b)
                else:
                    month = _int_or_none(a)
                    year = _int_or_none(b)
            elif a:
                return None
            elif b:
                year = _int_or_none(b)
                return _make_date(year, None, None)
            else:
                return None
            return _make_date(year, month, None)

        if len(parts) == 1:
            year = _int_or_none(parts[0])
            return _make_date(year, None, None)

    if s.isdigit() and len(s) == 4:
        return _make_date(int(s), None, None)

    return None


def format_date(date_value):
    if not date_value:
        return ""
    year = date_value.get("year")
    if year is None:
        return ""
    month = date_value.get("month")
    day = date_value.get("day")
    if month is not None and day is not None:
        return f"{year:04d}-{month:02d}-{day:02d}"
    if month is not None:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}"


def date_key(date_value, mode):
    year = date_value["year"]
    if mode == "min":
        month = date_value["month"] if date_value["month"] is not None else 1
        day = date_value["day"] if date_value["day"] is not None else 1
    else:
        month = date_value["month"] if date_value["month"] is not None else 12
        day = date_value["day"] if date_value["day"] is not None else 31
    return (year, month, day)


def compute_age(birth, consent):
    if not birth or not consent:
        return ""
    if (
        birth.get("month") is None
        or birth.get("day") is None
        or consent.get("month") is None
        or consent.get("day") is None
    ):
        return ""

    age = consent["year"] - birth["year"]
    if (consent["month"], consent["day"]) < (birth["month"], birth["day"]):
        age -= 1

    if age < 0:
        return ""
    return str(age)


def read_input(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def main():
    demog = read_input("input/raw_demog.csv")
    consent = read_input("input/raw_consent.csv")
    rand = read_input("input/raw_rand.csv")
    dosing = read_input("input/raw_dosing.csv")
    sites = read_input("input/sites.csv")

    consent_map = {}
    for _, row in consent.iterrows():
        subj = clean(row["SUBJECT"])
        if subj:
            consent_map[subj] = clean(row["ICDAT"])

    rand_map = {}
    for _, row in rand.iterrows():
        subj = clean(row["SUBJECT"])
        if subj:
            rand_map[subj] = clean(row["TRT_GROUP"])

    site_country = {}
    for _, row in sites.iterrows():
        site = clean(row["SITE"])
        if site:
            site_country[site] = clean(row["COUNTRY"])

    dose_starts = {}
    all_dose_dates = {}
    for _, row in dosing.iterrows():
        subj = clean(row["SUBJECT"])
        if not subj:
            continue

        start = parse_date(row["DOSE_START"])
        end = parse_date(row["DOSE_END"])

        if start is not None:
            dose_starts.setdefault(subj, []).append(start)

        if start is not None or end is not None:
            all_dose_dates.setdefault(subj, []).extend(
                [d for d in (start, end) if d is not None]
            )

    rows = []
    seen_subjects = set()

    for _, row in demog.iterrows():
        subj = clean(row["SUBJECT"])
        if not subj or subj in seen_subjects:
            continue
        seen_subjects.add(subj)

        site, _, subject = subj.partition("-")
        site = clean(site)
        subject = clean(subject)
        usubjid = f"{STUDYID}-{site}-{subject}"

        birth = parse_date(row["BRTHDAT"])
        consent_date = parse_date(consent_map.get(subj, ""))

        sex_raw = clean(row["SEX"]).lower()
        if sex_raw in {"f", "female"}:
            sex = "F"
        elif sex_raw in {"m", "male"}:
            sex = "M"
        else:
            sex = ""

        race = clean(row["RACE"]).upper()

        hisp = clean(row["HISPANIC"]).lower()
        if hisp in {"yes", "y"}:
            ethnic = "HISPANIC OR LATINO"
        elif hisp in {"no", "n"}:
            ethnic = "NOT HISPANIC OR LATINO"
        else:
            ethnic = ""

        trt = clean(rand_map.get(subj, "")).upper()
        armcd, arm = ARM_MAP.get(trt, SCREEN_FAIL)

        starts = dose_starts.get(subj, [])
        all_dates = all_dose_dates.get(subj, [])

        rfstdtc = min(starts, key=lambda d: date_key(d, "min")) if starts else None
        rfendtc = max(all_dates, key=lambda d: date_key(d, "max")) if all_dates else None

        age = compute_age(birth, consent_date)

        rows.append(
            {
                "STUDYID": STUDYID,
                "DOMAIN": DOMAIN,
                "USUBJID": usubjid,
                "SUBJID": subject,
                "SITEID": site,
                "BRTHDTC": format_date(birth),
                "AGE": age,
                "AGEU": "YEARS",
                "SEX": sex,
                "RACE": race,
                "ETHNIC": ethnic,
                "ARMCD": armcd,
                "ARM": arm,
                "RFICDTC": format_date(consent_date),
                "RFSTDTC": format_date(rfstdtc),
                "RFENDTC": format_date(rfendtc),
                "COUNTRY": site_country.get(site, ""),
            }
        )

    os.makedirs("output", exist_ok=True)
    with open("output/dm.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for record in sorted(rows, key=lambda x: x["USUBJID"]):
            writer.writerow({col: record.get(col, "") for col in COLUMNS})


if __name__ == "__main__":
    main()
