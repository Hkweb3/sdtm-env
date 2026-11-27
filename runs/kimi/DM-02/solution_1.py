import os

import pandas as pd

STUDYID = "PLX-658"
DOMAIN = "DM"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

SEX_MAP = {"1": "M", "2": "F"}

RACE_MAP = {
    "1": "WHITE",
    "2": "BLACK OR AFRICAN AMERICAN",
    "3": "ASIAN",
    "4": "AMERICAN INDIAN OR ALASKA NATIVE",
    "5": "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
}

ETHNIC_MAP = {
    "yes": "HISPANIC OR LATINO",
    "no": "NOT HISPANIC OR LATINO",
}

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}

COLUMNS = [
    "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "BRTHDTC",
    "AGE", "AGEU", "SEX", "RACE", "ETHNIC", "ARMCD", "ARM",
    "RFICDTC", "RFSTDTC", "RFENDTC", "COUNTRY",
]


def parse_raw_date(value):
    """Parse DDMONYYYY (UN day / UNK month) into (year, month, day);
    unknown parts are None. Returns None if no usable date."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if not s:
        return None
    day = s[0:2]
    mon = s[2:5]
    year = s[5:9]
    if not year.isdigit():
        return None
    y = int(year)
    m = MONTHS.get(mon)  # None when UNK or unrecognized
    d = int(day) if day.isdigit() else None  # None when UN
    return (y, m, d)


def to_iso(parsed):
    """Format (year, month, day) as ISO 8601, keeping only known parts."""
    if parsed is None:
        return ""
    y, m, d = parsed
    if m is None:
        return "%04d" % y
    if d is None:
        return "%04d-%02d" % (y, m)
    return "%04d-%02d-%02d" % (y, m, d)


def date_key(parsed):
    y, m, d = parsed
    return (y, m if m is not None else 0, d if d is not None else 0)


def compute_age(birth, ref):
    """Completed years from birth to ref; blank if either date is partial/missing."""
    if birth is None or ref is None:
        return ""
    by, bm, bd = birth
    ry, rm, rd = ref
    if bm is None or bd is None or rm is None or rd is None:
        return ""
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return str(age)


def main():
    demog = pd.read_csv("input/raw_demog.csv", dtype=str).fillna("")
    consent = pd.read_csv("input/raw_consent.csv", dtype=str).fillna("")
    rand = pd.read_csv("input/raw_rand.csv", dtype=str).fillna("")
    dosing = pd.read_csv("input/raw_dosing.csv", dtype=str).fillna("")
    sites = pd.read_csv("input/sites.csv", dtype=str).fillna("")

    consent_map = {r["SUBJECT"].strip(): r["ICDAT"].strip()
                   for _, r in consent.iterrows()}
    rand_map = {r["SUBJECT"].strip(): r["TRT_GROUP"].strip()
                for _, r in rand.iterrows()}
    site_map = {r["SITE"].strip(): r["COUNTRY"].strip()
                for _, r in sites.iterrows()}

    dose_map = {}
    for _, r in dosing.iterrows():
        subj = r["SUBJECT"].strip()
        ds = parse_raw_date(r["DOSE_START"])
        de = parse_raw_date(r["DOSE_END"])
        dose_map.setdefault(subj, []).append((ds, de))

    rows = []
    for _, r in demog.iterrows():
        subject = r["SUBJECT"].strip()
        site, subjid = subject.split("-", 1)
        usubjid = "%s-%s-%s" % (STUDYID, site, subjid)

        birth = parse_raw_date(r["BRTHDAT"])
        ic = parse_raw_date(consent_map.get(subject, ""))

        age = compute_age(birth, ic)
        ageu = "YEARS" if age != "" else ""

        trt = rand_map.get(subject, "")
        if trt in ARM_MAP:
            armcd, arm = ARM_MAP[trt]
        else:
            armcd, arm = "SCRNFAIL", "Screen Failure"

        records = dose_map.get(subject, [])
        starts = [ds for ds, _ in records if ds is not None]
        all_dates = [p for pair in records for p in pair if p is not None]
        rfstdtc = to_iso(min(starts, key=date_key)) if starts else ""
        rfendtc = to_iso(max(all_dates, key=date_key)) if all_dates else ""

        rows.append({
            "STUDYID": STUDYID,
            "DOMAIN": DOMAIN,
            "USUBJID": usubjid,
            "SUBJID": subjid,
            "SITEID": site,
            "BRTHDTC": to_iso(birth),
            "AGE": age,
            "AGEU": ageu,
            "SEX": SEX_MAP.get(r["SEX"].strip(), ""),
            "RACE": RACE_MAP.get(r["RACE"].strip(), ""),
            "ETHNIC": ETHNIC_MAP.get(r["HISPANIC"].strip().lower(), ""),
            "ARMCD": armcd,
            "ARM": arm,
            "RFICDTC": to_iso(ic),
            "RFSTDTC": rfstdtc,
            "RFENDTC": rfendtc,
            "COUNTRY": site_map.get(site, ""),
        })

    out = pd.DataFrame(rows, columns=COLUMNS)
    out = out.sort_values("USUBJID", kind="mergesort").reset_index(drop=True)

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/dm.csv", index=False)


if __name__ == "__main__":
    main()
