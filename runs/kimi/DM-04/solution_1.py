import os

import pandas as pd

STUDYID = "PLX-826"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
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

COLUMNS = [
    "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "BRTHDTC",
    "AGE", "AGEU", "SEX", "RACE", "ETHNIC", "ARMCD", "ARM",
    "RFICDTC", "RFSTDTC", "RFENDTC", "COUNTRY",
]


def read_input(name):
    df = pd.read_csv(os.path.join("input", name), dtype=str,
                     keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df


def parse_raw_date(value):
    """Parse 'DD MON YYYY' (UN/UNK for unknown parts).

    Returns (year, month, day) with None for unknown parts.
    """
    s = (value or "").strip()
    if not s:
        return (None, None, None)
    parts = s.split()
    if len(parts) != 3:
        return (None, None, None)
    d_raw, m_raw, y_raw = (p.upper() for p in parts)
    year = int(y_raw) if y_raw.isdigit() else None
    month = MONTHS.get(m_raw)
    day = int(d_raw) if d_raw.isdigit() else None
    return (year, month, day)


def to_dtc(ymd):
    """Format (year, month, day) as ISO 8601, keeping only known parts."""
    y, m, d = ymd
    if y is None:
        return ""
    if m is None:
        return "%04d" % y
    if d is None:
        return "%04d-%02d" % (y, m)
    return "%04d-%02d-%02d" % (y, m, d)


def calc_age(birth, ref):
    """Completed years from birth to ref; blank if either date is partial."""
    by, bm, bd = birth
    ry, rm, rd = ref
    if None in (by, bm, bd) or None in (ry, rm, rd):
        return ""
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return str(age)


def min_key(ymd):
    y, m, d = ymd
    return (y, m if m is not None else 1, d if d is not None else 1)


def max_key(ymd):
    y, m, d = ymd
    return (y, m if m is not None else 12, d if d is not None else 31)


def main():
    demog = read_input("raw_demog.csv")
    consent = read_input("raw_consent.csv")
    rand = read_input("raw_rand.csv")
    dosing = read_input("raw_dosing.csv")
    sites = read_input("sites.csv")

    site_country = dict(zip(sites["SITE"], sites["COUNTRY"]))
    consent_map = dict(zip(consent["SUBJECT"], consent["ICDAT"]))
    rand_map = dict(zip(rand["SUBJECT"], rand["TRT_GROUP"]))

    dose_starts = {}
    dose_all = {}
    for _, row in dosing.iterrows():
        subj = row["SUBJECT"]
        ds = parse_raw_date(row["DOSE_START"])
        de = parse_raw_date(row["DOSE_END"])
        dose_starts.setdefault(subj, []).append(ds)
        dose_all.setdefault(subj, []).extend([ds, de])

    rows = []
    for _, drow in demog.iterrows():
        subject = drow["SUBJECT"]
        siteid, subjid = subject.split("-", 1)
        usubjid = "%s-%s-%s" % (STUDYID, siteid, subjid)

        birth = parse_raw_date(drow["BRTHDAT"])
        ic = parse_raw_date(consent_map.get(subject, ""))

        age = calc_age(birth, ic)

        sex = {"Female": "F", "Male": "M"}.get(drow["SEX"], "")
        race = RACE_MAP.get(drow["RACE"], "")

        hisp = drow["HISPANIC"].strip().lower()
        if hisp == "yes":
            ethnic = "HISPANIC OR LATINO"
        elif hisp == "no":
            ethnic = "NOT HISPANIC OR LATINO"
        else:
            ethnic = ""

        if subject in rand_map:
            armcd, arm = ARM_MAP.get(rand_map[subject], ("", ""))
        else:
            armcd, arm = "SCRNFAIL", "Screen Failure"

        starts = [x for x in dose_starts.get(subject, []) if x[0] is not None]
        all_dates = [x for x in dose_all.get(subject, []) if x[0] is not None]
        rfstdtc = to_dtc(min(starts, key=min_key)) if starts else ""
        rfendtc = to_dtc(max(all_dates, key=max_key)) if all_dates else ""

        rows.append({
            "STUDYID": STUDYID,
            "DOMAIN": "DM",
            "USUBJID": usubjid,
            "SUBJID": subjid,
            "SITEID": siteid,
            "BRTHDTC": to_dtc(birth),
            "AGE": age,
            "AGEU": "YEARS" if age != "" else "",
            "SEX": sex,
            "RACE": race,
            "ETHNIC": ethnic,
            "ARMCD": armcd,
            "ARM": arm,
            "RFICDTC": to_dtc(ic),
            "RFSTDTC": rfstdtc,
            "RFENDTC": rfendtc,
            "COUNTRY": site_country.get(siteid, ""),
        })

    out = pd.DataFrame(rows, columns=COLUMNS)
    out = out.sort_values("USUBJID").reset_index(drop=True)

    os.makedirs("output", exist_ok=True)
    out.to_csv(os.path.join("output", "dm.csv"), index=False)


if __name__ == "__main__":
    main()
