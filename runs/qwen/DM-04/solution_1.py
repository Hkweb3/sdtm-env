import calendar
import os
import pandas as pd

STUDYID = "PLX-826"
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

RACE_MAP = {
    "1": "WHITE",
    "2": "BLACK OR AFRICAN AMERICAN",
    "3": "ASIAN",
    "4": "AMERICAN INDIAN OR ALASKA NATIVE",
    "5": "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
}

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}

OUTPUT_COLUMNS = [
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

    s = str(value).strip()
    if not s:
        return None

    parts = s.split()
    if len(parts) != 3:
        return None

    day_s, mon_s, year_s = parts
    mon_s = mon_s.upper()

    try:
        year = int(year_s)
    except ValueError:
        return None

    if mon_s == "UNK":
        month = None
    elif mon_s in MONTHS:
        month = MONTHS[mon_s]
    else:
        return None

    if day_s.upper() == "UN":
        day = None
    else:
        try:
            day = int(day_s)
        except ValueError:
            return None
        if day < 1 or day > 31:
            return None

    return {"year": year, "month": month, "day": day}


def to_iso(date):
    if not date:
        return ""

    year = date.get("year")
    month = date.get("month")
    day = date.get("day")

    if year is None:
        return ""
    if month is None:
        return f"{year:04d}"
    if day is None:
        return f"{year:04d}-{month:02d}"

    return f"{year:04d}-{month:02d}-{day:02d}"


def specificity(date):
    if not date:
        return 0
    return sum(1 for key in ("year", "month", "day") if date.get(key) is not None)


def date_key(date, mode):
    year = date.get("year")
    original_year = year

    if year is None:
        year = 0 if mode == "min" else 9999

    month = date.get("month")
    if month is None:
        month = 1 if mode == "min" else 12

    day = date.get("day")
    if day is None:
        if mode == "min":
            day = 1
        else:
            if original_year is not None and month is not None:
                try:
                    day = calendar.monthrange(original_year, month)[1]
                except ValueError:
                    day = 31
            else:
                day = 31

    return (year, month, day)


def select_earliest(dates):
    best = None
    best_key = None

    for date in dates:
        if date is None:
            continue
        key = (date_key(date, "min"), -specificity(date))
        if best_key is None or key < best_key:
            best = date
            best_key = key

    return best


def select_latest(dates):
    best = None
    best_key = None

    for date in dates:
        if date is None:
            continue
        key = (date_key(date, "max"), specificity(date))
        if best_key is None or key > best_key:
            best = date
            best_key = key

    return best


def possible_month_day(date):
    if not date or date.get("year") is None:
        return []

    year = date["year"]
    month = date.get("month")
    day = date.get("day")

    if month is not None:
        if not 1 <= month <= 12:
            return []

        max_day = calendar.monthrange(year, month)[1]

        if day is not None:
            if 1 <= day <= max_day:
                return [(month, day)]
            return []

        return [(month, d) for d in range(1, max_day + 1)]

    if day is not None:
        result = []
        for m in range(1, 13):
            if 1 <= day <= calendar.monthrange(year, m)[1]:
                result.append((m, day))
        return result

    result = []
    for m in range(1, 13):
        for d in range(1, calendar.monthrange(year, m)[1] + 1):
            result.append((m, d))
    return result


def compute_age(birth, consent):
    if birth is None or consent is None:
        return ""

    birth_year = birth.get("year")
    consent_year = consent.get("year")

    if birth_year is None or consent_year is None:
        return ""

    if consent_year < birth_year:
        return ""

    birth_options = possible_month_day(birth)
    consent_options = possible_month_day(consent)

    if not birth_options or not consent_options:
        return ""

    birth_min = min(birth_options)
    birth_max = max(birth_options)
    consent_min = min(consent_options)
    consent_max = max(consent_options)

    if consent_year == birth_year:
        if consent_min >= birth_max:
            return "0"
        return ""

    if consent_min >= birth_max:
        return str(consent_year - birth_year)

    if consent_max < birth_min:
        age = consent_year - birth_year - 1
        if age >= 0:
            return str(age)
        return ""

    return ""


def map_sex(value):
    v = str(value).strip().lower()
    if v in ("female", "f"):
        return "F"
    if v in ("male", "m"):
        return "M"
    return ""


def map_race(value):
    v = str(value).strip()
    if not v:
        return ""

    if v in RACE_MAP:
        return RACE_MAP[v]

    if v.endswith(".0"):
        v2 = v[:-2]
        if v2 in RACE_MAP:
            return RACE_MAP[v2]

    upper = v.upper()
    for label in RACE_MAP.values():
        if upper == label:
            return label

    return ""


def map_ethnic(value):
    v = str(value).strip().lower()
    if v in ("yes", "y"):
        return "HISPANIC OR LATINO"
    if v in ("no", "n"):
        return "NOT HISPANIC OR LATINO"
    return ""


def map_arm(value):
    v = str(value).strip().upper()
    if v in ARM_MAP:
        return ARM_MAP[v]
    return ("SCRNFAIL", "Screen Failure")


def split_subject(value):
    s = str(value).strip()
    if "-" in s:
        site, subj = s.split("-", 1)
    else:
        site, subj = "", s
    return site.strip(), subj.strip()


def main():
    input_dir = "input"
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    demog = pd.read_csv(
        os.path.join(input_dir, "raw_demog.csv"),
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    consent = pd.read_csv(
        os.path.join(input_dir, "raw_consent.csv"),
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    rand = pd.read_csv(
        os.path.join(input_dir, "raw_rand.csv"),
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    dosing = pd.read_csv(
        os.path.join(input_dir, "raw_dosing.csv"),
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    sites = pd.read_csv(
        os.path.join(input_dir, "sites.csv"),
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    for df in (demog, consent, rand, dosing, sites):
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    consent_map = dict(zip(consent["SUBJECT"], consent["ICDAT"]))
    rand_map = dict(zip(rand["SUBJECT"], rand["TRT_GROUP"]))
    site_map = dict(zip(sites["SITE"], sites["COUNTRY"]))

    dosing_map = {}
    for _, row in dosing.iterrows():
        subj = row["SUBJECT"]
        dosing_map.setdefault(subj, []).append((row["DOSE_START"], row["DOSE_END"]))

    rows = []

    for _, row in demog.iterrows():
        subject = row["SUBJECT"]
        site, subj = split_subject(subject)
        usubjid = f"{STUDYID}-{site}-{subj}"

        birth = parse_date(row["BRTHDAT"])
        consent_raw = consent_map.get(subject, "")
        consent_date = parse_date(consent_raw)
        age = compute_age(birth, consent_date)

        sex = map_sex(row["SEX"])
        race = map_race(row["RACE"])
        ethnic = map_ethnic(row["HISPANIC"])
        armcd, arm = map_arm(rand_map.get(subject, ""))

        starts = []
        all_dosing_dates = []

        for start_raw, end_raw in dosing_map.get(subject, []):
            start = parse_date(start_raw)
            end = parse_date(end_raw)

            if start is not None:
                starts.append(start)
                all_dosing_dates.append(start)

            if end is not None:
                all_dosing_dates.append(end)

        rfstdtc = to_iso(select_earliest(starts))
        rfendtc = to_iso(select_latest(all_dosing_dates))

        country = site_map.get(site, "")

        rows.append(
            {
                "STUDYID": STUDYID,
                "DOMAIN": DOMAIN,
                "USUBJID": usubjid,
                "SUBJID": subj,
                "SITEID": site,
                "BRTHDTC": to_iso(birth),
                "AGE": age,
                "AGEU": "YEARS",
                "SEX": sex,
                "RACE": race,
                "ETHNIC": ethnic,
                "ARMCD": armcd,
                "ARM": arm,
                "RFICDTC": to_iso(consent_date),
                "RFSTDTC": rfstdtc,
                "RFENDTC": rfendtc,
                "COUNTRY": country,
            }
        )

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

    for col in OUTPUT_COLUMNS:
        df[col] = df[col].fillna("").astype(str)

    df = df.sort_values(by="USUBJID", kind="mergesort").reset_index(drop=True)
    df.to_csv(os.path.join(output_dir, "dm.csv"), index=False)


if __name__ == "__main__":
    main()
