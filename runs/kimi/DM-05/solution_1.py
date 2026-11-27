import os

import pandas as pd

STUDYID = "MRN-319"

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
    "YES": "HISPANIC OR LATINO",
    "NO": "NOT HISPANIC OR LATINO",
}

ARM_MAP = {
    "A": ("PBO", "Placebo"),
    "B": ("XANLO", "Xanomeline Low Dose"),
    "C": ("XANHI", "Xanomeline High Dose"),
}

COLUMNS = [
    "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "BRTHDTC", "AGE",
    "AGEU", "SEX", "RACE", "ETHNIC", "ARMCD", "ARM", "RFICDTC", "RFSTDTC",
    "RFENDTC", "COUNTRY",
]


def parse_date(value):
    """Parse a DDMONYYYY date (UN = unknown day, UNK = unknown month).

    Returns a (year, month, day) tuple with None for unknown parts,
    or None if the value is missing/unusable.
    """
    if value is None:
        return None
    s = str(value).strip().upper()
    if len(s) < 9:
        return None
    day_txt, mon_txt, year_txt = s[:2], s[2:5], s[5:9]
    if not year_txt.isdigit():
        return None
    year = int(year_txt)
    month = MONTHS.get(mon_txt)
    day = int(day_txt) if day_txt.isdigit() else None
    return (year, month, day)


def iso_date(parsed):
    """Format (year, month, day) as ISO 8601, keeping only known parts."""
    if parsed is None:
        return ""
    year, month, day = parsed
    if month is None:
        return f"{year:04d}"
    if day is None:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}-{month:02d}-{day:02d}"


def compute_age(birth, ref):
    """Completed years from birth to ref; None unless both are complete."""
    if birth is None or ref is None:
        return None
    if any(part is None for part in birth + ref):
        return None
    by, bm, bd = birth
    ry, rm, rd = ref
    return ry - by - (1 if (rm, rd) < (bm, bd) else 0)


def main():
    demog = pd.read_csv("input/raw_demog.csv", dtype=str).fillna("")
    consent = pd.read_csv("input/raw_consent.csv", dtype=str).fillna("")
    rand = pd.read_csv("input/raw_rand.csv", dtype=str).fillna("")
    dosing = pd.read_csv("input/raw_dosing.csv", dtype=str).fillna("")
    sites = pd.read_csv("input/sites.csv", dtype=str).fillna("")

    ic_map = {str(k).strip(): v for k, v in zip(consent["SUBJECT"], consent["ICDAT"])}
    rand_map = {str(k).strip(): v for k, v in zip(rand["SUBJECT"], rand["TRT_GROUP"])}
    country_map = {str(k).strip(): v for k, v in zip(sites["SITE"], sites["COUNTRY"])}

    dose_map = {}
    for subject, grp in dosing.groupby("SUBJECT"):
        starts = [d for d in (parse_date(v) for v in grp["DOSE_START"]) if d]
        ends = [d for d in (parse_date(v) for v in grp["DOSE_END"]) if d]
        rfstd = (
            min(starts, key=lambda t: (t[0], t[1] or 1, t[2] or 1))
            if starts else None
        )
        all_dates = starts + ends
        rfend = (
            max(all_dates, key=lambda t: (t[0], t[1] or 12, t[2] or 31))
            if all_dates else None
        )
        dose_map[str(subject).strip()] = (rfstd, rfend)

    rows = []
    for _, rec in demog.iterrows():
        subject = rec["SUBJECT"].strip()
        site, _, subjid = subject.partition("-")

        birth = parse_date(rec["BRTHDAT"])
        consent_dt = parse_date(ic_map.get(subject, ""))
        age = compute_age(birth, consent_dt)

        trt = rand_map.get(subject)
        if trt is None:
            armcd, arm = "SCRNFAIL", "Screen Failure"
        elif str(trt).strip().upper() in ARM_MAP:
            armcd, arm = ARM_MAP[str(trt).strip().upper()]
        else:
            armcd, arm = "", ""

        rfstd, rfend = dose_map.get(subject, (None, None))

        rows.append({
            "STUDYID": STUDYID,
            "DOMAIN": "DM",
            "USUBJID": f"{STUDYID}-{site}-{subjid}",
            "SUBJID": subjid,
            "SITEID": site,
            "BRTHDTC": iso_date(birth),
            "AGE": "" if age is None else str(age),
            "AGEU": "YEARS",
            "SEX": SEX_MAP.get(rec["SEX"].strip().upper(), ""),
            "RACE": RACE_MAP.get(rec["RACE"].strip().upper(), ""),
            "ETHNIC": ETHNIC_MAP.get(rec["HISPANIC"].strip().upper(), ""),
            "ARMCD": armcd,
            "ARM": arm,
            "RFICDTC": iso_date(consent_dt),
            "RFSTDTC": iso_date(rfstd),
            "RFENDTC": iso_date(rfend),
            "COUNTRY": country_map.get(site, ""),
        })

    out = pd.DataFrame(rows, columns=COLUMNS)
    out = out.sort_values("USUBJID").reset_index(drop=True)

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/dm.csv", index=False)


if __name__ == "__main__":
    main()
