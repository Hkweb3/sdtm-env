import os

import pandas as pd

STUDYID = "PLX-295"

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


def _component(text, allow_zero=False):
    """Parse one raw date component; return None when it is unknown."""
    text = (text or "").strip()
    if not text or not text.isdigit():
        return None
    value = int(text)
    if value == 0 and not allow_zero:
        return None
    return value


def parse_date(value):
    """Convert a raw MM/DD/YYYY date (possibly partial) to ISO 8601.

    Returns (iso_string, (year, month, day)); unknown parts are None and
    are never imputed.
    """
    s = (value or "").strip()
    if not s:
        return "", (None, None, None)
    fields = s.split("/")
    if len(fields) == 3:
        m_txt, d_txt, y_txt = fields
    elif len(fields) == 2:
        m_txt, y_txt = fields
        d_txt = ""
    else:
        m_txt, d_txt, y_txt = "", "", fields[0]
    year = _component(y_txt, allow_zero=True)
    month = _component(m_txt)
    day = _component(d_txt)
    iso = ""
    if year is not None:
        iso = "%04d" % year
        if month is not None:
            iso = "%04d-%02d" % (year, month)
            if day is not None:
                iso = "%04d-%02d-%02d" % (year, month, day)
    return iso, (year, month, day)


def compute_age(birth, ref):
    """Completed years from birth date to reference date (both complete)."""
    by, bm, bd = birth
    ry, rm, rd = ref
    if None in (by, bm, bd, ry, rm, rd):
        return ""
    age = ry - by
    if (rm, rd) < (bm, bd):
        age -= 1
    return age


def main():
    demog = pd.read_csv("input/raw_demog.csv", dtype=str, keep_default_na=False)
    consent = pd.read_csv("input/raw_consent.csv", dtype=str, keep_default_na=False)
    rand = pd.read_csv("input/raw_rand.csv", dtype=str, keep_default_na=False)
    dosing = pd.read_csv("input/raw_dosing.csv", dtype=str, keep_default_na=False)
    sites = pd.read_csv("input/sites.csv", dtype=str, keep_default_na=False)

    ic_map = dict(zip(consent["SUBJECT"], consent["ICDAT"]))
    trt_map = dict(zip(rand["SUBJECT"], rand["TRT_GROUP"]))
    country_map = dict(zip(sites["SITE"], sites["COUNTRY"]))

    dose_map = {}
    for _, drow in dosing.iterrows():
        subj = drow["SUBJECT"].strip()
        start_iso, _ = parse_date(drow["DOSE_START"])
        end_iso, _ = parse_date(drow["DOSE_END"])
        entry = dose_map.setdefault(subj, {"starts": [], "all": []})
        if start_iso:
            entry["starts"].append(start_iso)
            entry["all"].append(start_iso)
        if end_iso:
            entry["all"].append(end_iso)

    records = []
    for _, row in demog.iterrows():
        subject = row["SUBJECT"].strip()
        siteid, subjid = subject.split("-", 1)

        brthdtc, birth = parse_date(row["BRTHDAT"])
        rficdtc, ic = parse_date(ic_map.get(subject, ""))
        age = compute_age(birth, ic)

        sex = {"Female": "F", "Male": "M"}.get(row["SEX"].strip(), "")
        race = row["RACE"].strip().upper()

        hispanic = row["HISPANIC"].strip()
        if hispanic == "Yes":
            ethnic = "HISPANIC OR LATINO"
        elif hispanic == "No":
            ethnic = "NOT HISPANIC OR LATINO"
        else:
            ethnic = ""

        trt = trt_map.get(subject, "").strip()
        if trt in ARM_MAP:
            armcd, arm = ARM_MAP[trt]
        else:
            armcd, arm = "SCRNFAIL", "Screen Failure"

        rfstdtc = ""
        rfendtc = ""
        entry = dose_map.get(subject)
        if entry:
            if entry["starts"]:
                rfstdtc = min(entry["starts"])
            if entry["all"]:
                rfendtc = max(entry["all"])

        records.append({
            "STUDYID": STUDYID,
            "DOMAIN": "DM",
            "USUBJID": "%s-%s-%s" % (STUDYID, siteid, subjid),
            "SUBJID": subjid,
            "SITEID": siteid,
            "BRTHDTC": brthdtc,
            "AGE": age,
            "AGEU": "YEARS" if age != "" else "",
            "SEX": sex,
            "RACE": race,
            "ETHNIC": ethnic,
            "ARMCD": armcd,
            "ARM": arm,
            "RFICDTC": rficdtc,
            "RFSTDTC": rfstdtc,
            "RFENDTC": rfendtc,
            "COUNTRY": country_map.get(siteid, ""),
        })

    out = pd.DataFrame(records, columns=COLUMNS)
    out = out.sort_values("USUBJID").reset_index(drop=True)

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/dm.csv", index=False)


if __name__ == "__main__":
    main()
