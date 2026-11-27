import csv
import os

INPUT_DIR = "input"
OUTPUT_DIR = "output"
STUDYID = "MRN-319"

MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
          "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

SEX_MAP = {"1": "M", "2": "F"}
RACE_MAP = {"1": "WHITE",
            "2": "BLACK OR AFRICAN AMERICAN",
            "3": "ASIAN",
            "4": "AMERICAN INDIAN OR ALASKA NATIVE",
            "5": "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER"}
ETHNIC_MAP = {"YES": "HISPANIC OR LATINO", "NO": "NOT HISPANIC OR LATINO"}
ARM_MAP = {"A": ("PBO", "Placebo"),
           "B": ("XANLO", "Xanomeline Low Dose"),
           "C": ("XANHI", "Xanomeline High Dose")}

COLUMNS = ["STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "BRTHDTC", "AGE", "AGEU",
           "SEX", "RACE", "ETHNIC", "ARMCD", "ARM", "RFICDTC", "RFSTDTC", "RFENDTC", "COUNTRY"]


def read_csv(name):
    with open(os.path.join(INPUT_DIR, name), newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_dtc(raw):
    """Parse DDMONYYYY (day may be 'UN', month may be 'UNK') -> (year, month, day, iso) or None."""
    s = (raw or "").strip().upper()
    if len(s) != 9:
        return None
    day_s, mon_s, year_s = s[0:2], s[2:5], s[5:9]
    if not year_s.isdigit():
        return None
    year = int(year_s)
    month = MONTHS.get(mon_s)
    day = int(day_s) if day_s.isdigit() else None
    if day is not None and month is not None:
        iso = "%04d-%02d-%02d" % (year, month, day)
    elif month is not None:
        iso = "%04d-%02d" % (year, month)
    else:
        iso = "%04d" % year
    return (year, month, day, iso)


def sort_key(p):
    """Comparable key for partial dates (missing parts sort lowest)."""
    return (p[0], p[1] or 0, p[2] or 0)


def completed_years(birth, ref):
    """Completed years from birth to ref; birthday on ref date counts. Blank if either is partial/missing."""
    if birth is None or ref is None:
        return ""
    by, bm, bd = birth[0], birth[1], birth[2]
    ry, rm, rd = ref[0], ref[1], ref[2]
    if bm is None or bd is None or rm is None or rd is None:
        return ""
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return str(age)


def main():
    consent = {r["SUBJECT"].strip(): r["ICDAT"].strip() for r in read_csv("raw_consent.csv")}
    rand = {r["SUBJECT"].strip(): r["TRT_GROUP"].strip() for r in read_csv("raw_rand.csv")}
    sites = {r["SITE"].strip(): r["COUNTRY"].strip() for r in read_csv("sites.csv")}

    dosing = {}
    for r in read_csv("raw_dosing.csv"):
        dosing.setdefault(r["SUBJECT"].strip(), []).append(r)

    rows = []
    for r in read_csv("raw_demog.csv"):
        subject = r["SUBJECT"].strip()
        site, subjid = subject.split("-", 1)
        usubjid = "-".join([STUDYID, site, subjid])

        brth = parse_dtc(r["BRTHDAT"])
        ic = parse_dtc(consent.get(subject, ""))

        trt = rand.get(subject, "").upper()
        if trt in ARM_MAP:
            armcd, arm = ARM_MAP[trt]
        else:
            armcd, arm = "SCRNFAIL", "Screen Failure"

        rfstdtc = ""
        rfendtc = ""
        intervals = dosing.get(subject, [])
        if intervals:
            starts = [p for p in (parse_dtc(d["DOSE_START"]) for d in intervals) if p]
            ends = [p for p in (parse_dtc(d["DOSE_END"]) for d in intervals) if p]
            if starts:
                rfstdtc = min(starts, key=sort_key)[3]
                rfendtc = max(starts + ends, key=sort_key)[3]

        rows.append({
            "STUDYID": STUDYID,
            "DOMAIN": "DM",
            "USUBJID": usubjid,
            "SUBJID": subjid,
            "SITEID": site,
            "BRTHDTC": brth[3] if brth else "",
            "AGE": completed_years(brth, ic),
            "AGEU": "YEARS",
            "SEX": SEX_MAP.get(r["SEX"].strip(), ""),
            "RACE": RACE_MAP.get(r["RACE"].strip(), ""),
            "ETHNIC": ETHNIC_MAP.get(r["HISPANIC"].strip().upper(), ""),
            "ARMCD": armcd,
            "ARM": arm,
            "RFICDTC": ic[3] if ic else "",
            "RFSTDTC": rfstdtc,
            "RFENDTC": rfendtc,
            "COUNTRY": sites.get(site, ""),
        })

    rows.sort(key=lambda x: x["USUBJID"])

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "dm.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
