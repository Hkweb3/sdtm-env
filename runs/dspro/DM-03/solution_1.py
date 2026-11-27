import os
from datetime import datetime

import pandas as pd

STUDYID = "PLX-295"
DOMAIN = "DM"

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
    if not value or not str(value).strip():
        return None
    value = str(value).strip()
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def to_iso(d):
    if d is None:
        return ""
    return d.isoformat()


def calc_age(birth_date, consent_date):
    if birth_date is None or consent_date is None:
        return ""
    years = consent_date.year - birth_date.year
    if (consent_date.month, consent_date.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def main():
    demog = pd.read_csv("input/raw_demog.csv", dtype=str, keep_default_na=False)
    consent = pd.read_csv("input/raw_consent.csv", dtype=str, keep_default_na=False)
    rand = pd.read_csv("input/raw_rand.csv", dtype=str, keep_default_na=False)
    dosing = pd.read_csv("input/raw_dosing.csv", dtype=str, keep_default_na=False)
    sites = pd.read_csv("input/sites.csv", dtype=str, keep_default_na=False)

    consent_dict = {}
    for _, row in consent.iterrows():
        subject = str(row["SUBJECT"]).strip()
        if subject:
            consent_dict[subject] = str(row["ICDAT"]).strip()

    rand_dict = {}
    for _, row in rand.iterrows():
        subject = str(row["SUBJECT"]).strip()
        if subject:
            rand_dict[subject] = str(row["TRT_GROUP"]).strip()

    site_dict = {}
    for _, row in sites.iterrows():
        site = str(row["SITE"]).strip()
        country = str(row["COUNTRY"]).strip()
        site_dict[site] = country

    dosing_by_subject = {}
    for _, row in dosing.iterrows():
        subject = str(row["SUBJECT"]).strip()
        if subject:
            dosing_by_subject.setdefault(subject, []).append(
                (str(row["DOSE_START"]).strip(), str(row["DOSE_END"]).strip())
            )

    arm_map = {
        "A": ("PBO", "Placebo"),
        "B": ("XANLO", "Xanomeline Low Dose"),
        "C": ("XANHI", "Xanomeline High Dose"),
    }

    records = []

    for _, row in demog.iterrows():
        subject = str(row["SUBJECT"]).strip()

        if "-" in subject:
            site, subj = subject.split("-", 1)
        else:
            site = ""
            subj = subject

        usubjid = f"{STUDYID}-{site}-{subj}" if site and subj else STUDYID

        birth = parse_date(row["BRTHDAT"])
        consent_date = parse_date(consent_dict.get(subject, ""))

        age = calc_age(birth, consent_date)
        ageu = "YEARS" if age != "" else ""

        sex_raw = str(row["SEX"]).strip()
        if sex_raw == "Female":
            sex = "F"
        elif sex_raw == "Male":
            sex = "M"
        else:
            sex = ""

        race = str(row["RACE"]).strip().upper()

        hisp_raw = str(row["HISPANIC"]).strip().upper()
        if hisp_raw == "YES":
            ethnic = "HISPANIC OR LATINO"
        elif hisp_raw == "NO":
            ethnic = "NOT HISPANIC OR LATINO"
        else:
            ethnic = ""

        trt_group = rand_dict.get(subject, "")
        if trt_group in arm_map:
            armcd, arm = arm_map[trt_group]
        else:
            armcd = "SCRNFAIL"
            arm = "Screen Failure"

        start_dates = []
        end_dates = []
        for start_raw, end_raw in dosing_by_subject.get(subject, []):
            start_date = parse_date(start_raw)
            end_date = parse_date(end_raw)
            if start_date:
                start_dates.append(start_date)
            if end_date:
                end_dates.append(end_date)

        if start_dates:
            rfstdtc = to_iso(min(start_dates))
        else:
            rfstdtc = ""

        if start_dates or end_dates:
            rfendtc = to_iso(max(start_dates + end_dates))
        else:
            rfendtc = ""

        country = site_dict.get(site, "")

        records.append(
            {
                "STUDYID": STUDYID,
                "DOMAIN": DOMAIN,
                "USUBJID": usubjid,
                "SUBJID": subj,
                "SITEID": site,
                "BRTHDTC": to_iso(birth),
                "AGE": age,
                "AGEU": ageu,
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

    output_df = pd.DataFrame(records, columns=OUTPUT_COLUMNS)
    output_df = output_df.sort_values("USUBJID")

    os.makedirs("output", exist_ok=True)
    output_df.to_csv("output/dm.csv", index=False)


if __name__ == "__main__":
    main()
