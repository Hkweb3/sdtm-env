import os
import datetime
import pandas as pd

STUDYID = "PLX-658"
DOMAIN = "DM"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
}

SEX_MAP = {"1": "M", "2": "F"}

RACE_MAP = {
    "1": "WHITE",
    "2": "BLACK OR AFRICAN AMERICAN",
    "3": "ASIAN",
    "4": "AMERICAN INDIAN OR ALASKA NATIVE",
    "5": "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER"
}

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose")
}

OUTPUT_COLUMNS = [
    "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID",
    "BRTHDTC", "AGE", "AGEU", "SEX", "RACE", "ETHNIC",
    "ARMCD", "ARM", "RFICDTC", "RFSTDTC", "RFENDTC", "COUNTRY"
]


def raw_to_iso(raw_date):
    """Convert DDMONYYYY raw date to ISO 8601 partial string."""
    if not raw_date:
        return ""
    raw_date = raw_date.strip()
    if len(raw_date) < 7:
        return ""
    day = raw_date[:2].upper()
    mon = raw_date[2:5].upper()
    year = raw_date[5:].strip()

    if mon == "UNK":
        return year

    month_num = MONTHS.get(mon)
    if month_num is None:
        return ""

    if day == "UN":
        return f"{year}-{month_num:02d}"

    try:
        day_num = int(day)
        return f"{year}-{month_num:02d}-{day_num:02d}"
    except ValueError:
        return ""


def raw_to_date(raw_date):
    """Parse a complete DDMONYYYY raw date to datetime.date, or None."""
    if not raw_date:
        return None
    raw_date = raw_date.strip()
    if len(raw_date) < 7:
        return None
    day = raw_date[:2].upper()
    mon = raw_date[2:5].upper()
    year = raw_date[5:].strip()

    if day == "UN" or mon == "UNK":
        return None

    month_num = MONTHS.get(mon)
    if month_num is None:
        return None

    try:
        return datetime.date(int(year), month_num, int(day))
    except ValueError:
        return None


def compute_age(birth_date, consent_date):
    """Completed years from birth date to consent date."""
    if birth_date is None or consent_date is None:
        return ""
    age = consent_date.year - birth_date.year
    if (consent_date.month, consent_date.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def main():
    demog = pd.read_csv("input/raw_demog.csv", dtype=str, keep_default_na=False)
    consent = pd.read_csv("input/raw_consent.csv", dtype=str, keep_default_na=False)
    rand = pd.read_csv("input/raw_rand.csv", dtype=str, keep_default_na=False)
    dosing = pd.read_csv("input/raw_dosing.csv", dtype=str, keep_default_na=False)
    sites = pd.read_csv("input/sites.csv", dtype=str, keep_default_na=False)

    consent_map = dict(zip(consent["SUBJECT"], consent["ICDAT"]))
    rand_map = dict(zip(rand["SUBJECT"], rand["TRT_GROUP"]))
    site_map = dict(zip(sites["SITE"], sites["COUNTRY"]))

    dosing_map = {}
    for _, row in dosing.iterrows():
        subject = row["SUBJECT"]
        start_date = raw_to_date(row["DOSE_START"])
        end_date = raw_to_date(row["DOSE_END"])
        if subject not in dosing_map:
            dosing_map[subject] = {"starts": [], "ends": []}
        if start_date is not None:
            dosing_map[subject]["starts"].append(start_date)
        if end_date is not None:
            dosing_map[subject]["ends"].append(end_date)

    rows = []

    for _, row in demog.iterrows():
        raw_subject = row["SUBJECT"]
        site, subj = raw_subject.split("-", 1)

        birth_raw = row.get("BRTHDAT", "")
        consent_raw = consent_map.get(raw_subject, "")

        birth_iso = raw_to_iso(birth_raw)
        consent_iso = raw_to_iso(consent_raw)

        birth_date = raw_to_date(birth_raw)
        consent_date = raw_to_date(consent_raw)

        age = compute_age(birth_date, consent_date)
        ageu = "YEARS" if age != "" else ""

        sex = SEX_MAP.get(row.get("SEX", "").strip(), "")
        race = RACE_MAP.get(row.get("RACE", "").strip(), "")

        hispanic = row.get("HISPANIC", "").strip().upper()
        if hispanic == "YES":
            ethnic = "HISPANIC OR LATINO"
        elif hispanic == "NO":
            ethnic = "NOT HISPANIC OR LATINO"
        else:
            ethnic = ""

        trt_group = rand_map.get(raw_subject, "")
        armcd, arm = ARM_MAP.get(trt_group, ("SCRNFAIL", "Screen Failure"))

        if raw_subject in dosing_map:
            starts = dosing_map[raw_subject]["starts"]
            ends = dosing_map[raw_subject]["ends"]
            all_dates = starts + ends

            rfstdtc = min(starts).isoformat() if starts else ""
            rfendtc = max(all_dates).isoformat() if all_dates else ""
        else:
            rfstdtc = ""
            rfendtc = ""

        country = site_map.get(site, "")

        rows.append({
            "STUDYID": STUDYID,
            "DOMAIN": DOMAIN,
            "USUBJID": f"{STUDYID}-{site}-{subj}",
            "SUBJID": subj,
            "SITEID": site,
            "BRTHDTC": birth_iso,
            "AGE": age,
            "AGEU": ageu,
            "SEX": sex,
            "RACE": race,
            "ETHNIC": ethnic,
            "ARMCD": armcd,
            "ARM": arm,
            "RFICDTC": consent_iso,
            "RFSTDTC": rfstdtc,
            "RFENDTC": rfendtc,
            "COUNTRY": country
        })

    rows.sort(key=lambda x: x["USUBJID"])

    out_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

    os.makedirs("output", exist_ok=True)
    out_df.to_csv("output/dm.csv", index=False, na_rep="")


if __name__ == "__main__":
    main()
