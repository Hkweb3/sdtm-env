import os
import pandas as pd

STUDYID = "KVT-998"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}
SEX_MAP = {"Female": "F", "Male": "M"}
ETHNIC_MAP = {"Yes": "HISPANIC OR LATINO", "No": "NOT HISPANIC OR LATINO"}

COLUMNS = [
    "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "BRTHDTC", "AGE",
    "AGEU", "SEX", "RACE", "ETHNIC", "ARMCD", "ARM", "RFICDTC", "RFSTDTC",
    "RFENDTC", "COUNTRY",
]


def sval(x):
    if x is None or pd.isna(x):
        return ""
    return str(x).strip()


def parse_raw_date(value):
    """Parse 'DD MON YYYY' with UN/UNK unknowns into (year, month, day)."""
    s = sval(value)
    if not s:
        return None
    parts = s.split()
    if len(parts) != 3:
        return None
    d, m, y = parts
    year = int(y)
    month = None if m.upper() == "UNK" else MONTHS[m.upper()]
    day = None if d.upper() == "UN" else int(d)
    return (year, month, day)


def iso_date(dt):
    """Render (year, month, day) as ISO 8601, keeping only known parts."""
    if dt is None:
        return ""
    y, m, d = dt
    if m is None:
        return f"{y:04d}"
    if d is None:
        return f"{y:04d}-{m:02d}"
    return f"{y:04d}-{m:02d}-{d:02d}"


def date_key(dt):
    y, m, d = dt
    return (y, m or 0, d or 0)


def calc_age(birth, ref):
    """Completed years from birth to ref; needs both dates fully known."""
    if birth is None or ref is None:
        return None
    by, bm, bd = birth
    ry, rm, rd = ref
    if bm is None or bd is None or rm is None or rd is None:
        return None
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return age


def main():
    demog = pd.read_csv("input/raw_demog.csv", dtype=str)
    consent = pd.read_csv("input/raw_consent.csv", dtype=str)
    rand = pd.read_csv("input/raw_rand.csv", dtype=str)
    dosing = pd.read_csv("input/raw_dosing.csv", dtype=str)
    sites = pd.read_csv("input/sites.csv", dtype=str)

    consent_map = {
        sval(r["SUBJECT"]): parse_raw_date(r["ICDAT"])
        for _, r in consent.iterrows()
    }
    rand_map = {
        sval(r["SUBJECT"]): sval(r["TRT_GROUP"])
        for _, r in rand.iterrows()
    }
    site_map = {
        sval(r["SITE"]): sval(r["COUNTRY"])
        for _, r in sites.iterrows()
    }

    dosing["_subj"] = dosing["SUBJECT"].map(sval)
    dosing["_start"] = dosing["DOSE_START"].map(parse_raw_date)
    dosing["_end"] = dosing["DOSE_END"].map(parse_raw_date)

    rfstdtc_map, rfendtc_map = {}, {}
    for subj, grp in dosing.groupby("_subj"):
        starts = [d for d in grp["_start"] if d is not None]
        all_dates = starts + [d for d in grp["_end"] if d is not None]
        if starts:
            rfstdtc_map[subj] = min(starts, key=date_key)
        if all_dates:
            rfendtc_map[subj] = max(all_dates, key=date_key)

    rows = []
    for _, r in demog.iterrows():
        subject = sval(r["SUBJECT"])
        siteid, subjid = subject.split("-", 1)
        brth = parse_raw_date(r["BRTHDAT"])
        ic = consent_map.get(subject)
        age = calc_age(brth, ic)

        trt = rand_map.get(subject, "")
        if trt in ARM_MAP:
            armcd, arm = ARM_MAP[trt]
        else:
            armcd, arm = "SCRNFAIL", "Screen Failure"

        rows.append({
            "STUDYID": STUDYID,
            "DOMAIN": "DM",
            "USUBJID": f"{STUDYID}-{siteid}-{subjid}",
            "SUBJID": subjid,
            "SITEID": siteid,
            "BRTHDTC": iso_date(brth),
            "AGE": "" if age is None else str(age),
            "AGEU": "" if age is None else "YEARS",
            "SEX": SEX_MAP.get(sval(r["SEX"]), ""),
            "RACE": sval(r["RACE"]).upper(),
            "ETHNIC": ETHNIC_MAP.get(sval(r["HISPANIC"]), ""),
            "ARMCD": armcd,
            "ARM": arm,
            "RFICDTC": iso_date(ic),
            "RFSTDTC": iso_date(rfstdtc_map.get(subject)),
            "RFENDTC": iso_date(rfendtc_map.get(subject)),
            "COUNTRY": site_map.get(siteid, ""),
        })

    out = pd.DataFrame(rows, columns=COLUMNS)
    out = out.sort_values("USUBJID").reset_index(drop=True)

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/dm.csv", index=False)


if __name__ == "__main__":
    main()
