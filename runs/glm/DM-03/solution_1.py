import csv
import os
import re

import pandas as pd

STUDYID = "PLX-295"
DOMAIN = "DM"
INPUT_DIR = "input"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "dm.csv")

DM_COLUMNS = [
    "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "BRTHDTC", "AGE",
    "AGEU", "SEX", "RACE", "ETHNIC", "ARMCD", "ARM", "RFICDTC", "RFSTDTC",
    "RFENDTC", "COUNTRY",
]

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}
SEX_MAP = {"female": "F", "male": "M"}
ETHNIC_MAP = {"yes": "HISPANIC OR LATINO", "no": "NOT HISPANIC OR LATINO"}


def read_input(name):
    return pd.read_csv(
        os.path.join(INPUT_DIR, name), dtype=str, keep_default_na=False
    )


def clean(value):
    return "" if value is None else str(value).strip()


def to_iso(raw):
    """Convert raw MM/DD/YYYY date to ISO 8601, keeping only known parts."""
    s = clean(raw)
    if not s or s.lower() in {"na", "nan", "null", "."}:
        return ""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return "{2}-{0:02d}-{1:02d}".format(int(m.group(1)), int(m.group(2)), m.group(3))
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        return "{1}-{0:02d}".format(int(m.group(1)), m.group(2))
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return m.group(1)
    return ""


def is_full(iso):
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso))


def completed_years(birth_iso, ref_iso):
    """Completed years from birth to reference date; birthday on ref date counts."""
    if not is_full(birth_iso) or not is_full(ref_iso):
        return ""
    by, bm, bd = (int(part) for part in birth_iso.split("-"))
    ry, rm, rd = (int(part) for part in ref_iso.split("-"))
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return str(age)


def build_dosing_maps(dosing):
    rfstdtc = {}
    rfendtc = {}
    for _, row in dosing.iterrows():
        subject = clean(row["SUBJECT"])
        start = to_iso(row.get("DOSE_START", ""))
        end = to_iso(row.get("DOSE_END", ""))
        if start and (subject not in rfstdtc or start < rfstdtc[subject]):
            rfstdtc[subject] = start
        candidates = [d for d in (start, end) if d]
        if candidates:
            rfendtc[subject] = max([rfendtc.get(subject, "")] + candidates)
    return rfstdtc, rfendtc


def main():
    demog = read_input("raw_demog.csv")
    consent = read_input("raw_consent.csv")
    rand = read_input("raw_rand.csv")
    dosing = read_input("raw_dosing.csv")
    sites = read_input("sites.csv")

    rfic_map = {clean(r["SUBJECT"]): to_iso(r["ICDAT"]) for _, r in consent.iterrows()}
    trt_map = {clean(r["SUBJECT"]): clean(r["TRT_GROUP"]) for _, r in rand.iterrows()}
    country_map = {clean(r["SITE"]): clean(r["COUNTRY"]) for _, r in sites.iterrows()}
    rfstdtc_map, rfendtc_map = build_dosing_maps(dosing)

    records = []
    for _, row in demog.iterrows():
        subject = clean(row["SUBJECT"])
        site, _, subj = subject.partition("-")
        usubjid = "-".join([STUDYID, site, subj])

        brthdtc = to_iso(row["BRTHDAT"])
        rficdtc = rfic_map.get(subject, "")

        sex = SEX_MAP.get(clean(row["SEX"]).lower(), "")
        race = clean(row["RACE"]).upper()
        ethnic = ETHNIC_MAP.get(clean(row["HISPANIC"]).lower(), "")

        trt = trt_map.get(subject)
        if trt is None:
            armcd, arm = "SCRNFAIL", "Screen Failure"
        else:
            armcd, arm = ARM_MAP.get(trt, ("", ""))

        records.append({
            "STUDYID": STUDYID,
            "DOMAIN": DOMAIN,
            "USUBJID": usubjid,
            "SUBJID": subj,
            "SITEID": site,
            "BRTHDTC": brthdtc,
            "AGE": completed_years(brthdtc, rficdtc),
            "AGEU": "YEARS",
            "SEX": sex,
            "RACE": race,
            "ETHNIC": ethnic,
            "ARMCD": armcd,
            "ARM": arm,
            "RFICDTC": rficdtc,
            "RFSTDTC": rfstdtc_map.get(subject, ""),
            "RFENDTC": rfendtc_map.get(subject, ""),
            "COUNTRY": country_map.get(site, ""),
        })

    records.sort(key=lambda rec: rec["USUBJID"])

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=DM_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)

    print(f"Wrote {len(records)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
