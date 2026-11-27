import os
import pandas as pd
from datetime import date

STUDYID = "MRN-319"
DOMAIN = "DM"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
}

def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def parse_raw_dtc(raw):
    value = clean(raw)
    if not value or len(value) < 9:
        return ""
    day_part = value[:2].upper()
    mon_part = value[2:5].upper()
    year_part = value[5:9]

    if mon_part == "UNK":
        return year_part
    if mon_part not in MONTHS:
        return year_part

    month = MONTHS[mon_part]
    if day_part == "UN":
        return f"{year_part}-{month:02d}"
    if day_part.isdigit():
        return f"{year_part}-{month:02d}-{int(day_part):02d}"
    return f"{year_part}-{month:02d}"

def parse_full_date(raw):
    value = clean(raw)
    if not value or len(value) < 9:
        return None
    day_part = value[:2].upper()
    mon_part = value[2:5].upper()
    year_part = value[5:9]

    if day_part == "UN" or mon_part == "UNK" or mon_part not in MONTHS:
        return None
    if not day_part.isdigit() or not year_part.isdigit():
        return None
    try:
        return date(int(year_part), MONTHS[mon_part], int(day_part))
    except ValueError:
        return None

def completed_years(birth_raw, consent_raw):
    birth_date = parse_full_date(birth_raw)
    consent_date = parse_full_date(consent_raw)
    if not birth_date or not consent_date:
        return ""
    return consent_date.year - birth_date.year - (
        (consent_date.month, consent_date.day) < (birth_date.month, birth_date.day)
    )

def dtc_sort_key(iso, for_max=False):
    parts = str(iso).split("-")
    try:
        if len(parts) == 3:
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            return (int(parts[0]), int(parts[1]), 99 if for_max else 0)
        if len(parts) == 1:
            return (int(parts[0]), 99 if for_max else 0, 99 if for_max else 0)
    except ValueError:
        pass
    return (9999, 99, 99) if for_max else (0, 0, 0)

def main():
    df_demog = pd.read_csv("./input/raw_demog.csv", dtype=str)
    df_consent = pd.read_csv("./input/raw_consent.csv", dtype=str)
    df_rand = pd.read_csv("./input/raw_rand.csv", dtype=str)
    df_dosing = pd.read_csv("./input/raw_dosing.csv", dtype=str)
    df_sites = pd.read_csv("./input/sites.csv", dtype=str)

    consent_map = {}
    for _, row in df_consent.iterrows():
        key = clean(row["SUBJECT"])
        if key:
            consent_map[key] = clean(row["ICDAT"])

    rand_map = {}
    for _, row in df_rand.iterrows():
        key = clean(row["SUBJECT"])
        if key:
            rand_map[key] = clean(row["TRT_GROUP"])

    site_map = {}
    for _, row in df_sites.iterrows():
        key = clean(row["SITE"])
        if key:
            site_map[key] = clean(row["COUNTRY"])

    dosing_by_subject = {}
    for _, row in df_dosing.iterrows():
        key = clean(row["SUBJECT"])
        if key:
            dosing_by_subject.setdefault(key, []).append(row)

    sex_map = {"1": "M", "2": "F"}
    race_map = {
        "1": "WHITE",
        "2": "BLACK OR AFRICAN AMERICAN",
        "3": "ASIAN",
        "4": "AMERICAN INDIAN OR ALASKA NATIVE",
        "5": "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
    }
    arm_map = {
        "A": ("PBO", "Placebo"),
        "B": ("XANLO", "Xanomeline Low Dose"),
        "C": ("XANHI", "Xanomeline High Dose"),
    }

    output_columns = [
        "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID",
        "BRTHDTC", "AGE", "AGEU", "SEX", "RACE", "ETHNIC",
        "ARMCD", "ARM", "RFICDTC", "RFSTDTC", "RFENDTC", "COUNTRY"
    ]

    rows_out = []
    for _, row in df_demog.iterrows():
        subject_raw = clean(row["SUBJECT"])
        if "-" in subject_raw:
            site_id, subject_id = subject_raw.split("-", 1)
        else:
            site_id, subject_id = subject_raw, ""

        usubjid = f"{STUDYID}-{site_id}-{subject_id}" if subject_id else f"{STUDYID}-{site_id}"

        birth_raw = clean(row["BRTHDAT"])
        birth_dtc = parse_raw_dtc(birth_raw)
        consent_raw = consent_map.get(subject_raw, "")
        rfic_dtc = parse_raw_dtc(consent_raw)
        age = completed_years(birth_raw, consent_raw)

        sex = sex_map.get(clean(row["SEX"]), "")
        race = race_map.get(clean(row["RACE"]), "")

        ethnic_raw = clean(row["HISPANIC"]).lower()
        if ethnic_raw == "yes":
            ethnic = "HISPANIC OR LATINO"
        elif ethnic_raw == "no":
            ethnic = "NOT HISPANIC OR LATINO"
        else:
            ethnic = ""

        if subject_raw in rand_map:
            trt_group = rand_map[subject_raw].upper()
            armcd, arm = arm_map.get(trt_group, ("", ""))
        else:
            armcd, arm = "SCRNFAIL", "Screen Failure"

        rfst_dtc = ""
        rfend_dtc = ""
        if subject_raw in dosing_by_subject:
            start_entries = []
            end_entries = []
            for drow in dosing_by_subject[subject_raw]:
                dose_start = clean(drow["DOSE_START"])
                if dose_start:
                    start_iso = parse_raw_dtc(dose_start)
                    if start_iso:
                        start_entries.append((dtc_sort_key(start_iso, False), start_iso))
                        end_entries.append((dtc_sort_key(start_iso, True), start_iso))

                dose_end = clean(drow["DOSE_END"])
                if dose_end:
                    end_iso = parse_raw_dtc(dose_end)
                    if end_iso:
                        end_entries.append((dtc_sort_key(end_iso, True), end_iso))

            if start_entries:
                rfst_dtc = min(start_entries, key=lambda x: x[0])[1]
            if end_entries:
                rfend_dtc = max(end_entries, key=lambda x: x[0])[1]

        country = site_map.get(site_id, "")

        rows_out.append({
            "STUDYID": STUDYID,
            "DOMAIN": DOMAIN,
            "USUBJID": usubjid,
            "SUBJID": subject_id,
            "SITEID": site_id,
            "BRTHDTC": birth_dtc,
            "AGE": age,
            "AGEU": "YEARS",
            "SEX": sex,
            "RACE": race,
            "ETHNIC": ethnic,
            "ARMCD": armcd,
            "ARM": arm,
            "RFICDTC": rfic_dtc,
            "RFSTDTC": rfst_dtc,
            "RFENDTC": rfend_dtc,
            "COUNTRY": country,
        })

    rows_out.sort(key=lambda x: x["USUBJID"])
    df_out = pd.DataFrame(rows_out, columns=output_columns)
    df_out.fillna("", inplace=True)

    os.makedirs("./output", exist_ok=True)
    df_out.to_csv("./output/dm.csv", index=False)

if __name__ == "__main__":
    main()
