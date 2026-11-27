from datetime import date
from pathlib import Path
import pandas as pd

STUDYID = "MRN-326"
DOMAIN = "AE"

OUTPUT_COLUMNS = [
    "STUDYID",
    "DOMAIN",
    "USUBJID",
    "AESEQ",
    "AESPID",
    "AETERM",
    "AEDECOD",
    "AEBODSYS",
    "AESEV",
    "AESER",
    "AEREL",
    "AEOUT",
    "AESTDTC",
    "AEENDTC",
    "AESTDY",
    "AEENDY",
]

MISSING_TOKENS = {"NA", "NULL", "N/A", ".", "NAN"}


def clean(value):
    if value is None:
        return ""
    s = str(value).strip()
    if s.upper() in MISSING_TOKENS:
        return ""
    return s


def parse_raw_date(value):
    s = clean(value)
    if not s:
        return ""

    # Already ISO-like: YYYY-MM-DD, YYYY-MM, or YYYY
    if "-" in s and "/" not in s:
        parts = [p.strip() for p in s.split("-") if p.strip() != ""]

        if len(parts) == 3 and all(p.isdigit() for p in parts):
            y, m, d = map(int, parts)
            try:
                date(y, m, d)
            except ValueError:
                return ""
            return f"{y:04d}-{m:02d}-{d:02d}"

        if len(parts) == 2 and all(p.isdigit() for p in parts):
            y, m = map(int, parts)
            if 1 <= m <= 12:
                return f"{y:04d}-{m:02d}"

        if len(parts) == 1 and parts[0].isdigit():
            return f"{int(parts[0]):04d}"

        return ""

    # Raw slash dates, primarily MM/DD/YYYY, with partial MM/YYYY or YYYY.
    parts = [p.strip() for p in s.split("/") if p.strip() != ""]
    if not parts:
        return ""

    if len(parts) == 1:
        p = parts[0]
        if p.isdigit() and len(p) == 4:
            return f"{int(p):04d}"
        return ""

    if len(parts) == 2:
        a, b = parts
        if not (a.isdigit() and b.isdigit()):
            return ""

        if len(a) == 4 and len(b) == 2:
            y, m = int(a), int(b)
        elif len(a) == 2 and len(b) == 4:
            m, y = int(a), int(b)
        else:
            return ""

        if 1 <= m <= 12:
            return f"{y:04d}-{m:02d}"
        return ""

    if len(parts) == 3:
        a, b, c = parts
        if not all(p.isdigit() for p in parts):
            return ""

        if len(a) == 4 and len(c) == 2:
            y, m, d = int(a), int(b), int(c)
        else:
            m, d = int(a), int(b)
            y = int(c)
            if len(c) == 2:
                y += 2000

        try:
            date(y, m, d)
        except ValueError:
            return ""

        return f"{y:04d}-{m:02d}-{d:02d}"

    return ""


def parse_iso_date(value):
    s = clean(value)
    if not s:
        return None, False

    parts = [p.strip() for p in s.split("-") if p.strip() != ""]
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        y, m, d = map(int, parts)
        try:
            return date(y, m, d), True
        except ValueError:
            return None, False

    return None, False


def study_day(ae_date_str, rfstdtc_str):
    ae_date, ae_full = parse_iso_date(ae_date_str)
    rf_date, rf_full = parse_iso_date(rfstdtc_str)

    if not ae_full or not rf_full or ae_date is None or rf_date is None:
        return ""

    delta = (ae_date - rf_date).days
    if ae_date >= rf_date:
        return str(delta + 1)
    return str(delta)


def map_severity(value):
    s = clean(value)
    mapping = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}

    if s in mapping:
        return mapping[s]

    if s.upper() in {"MILD", "MODERATE", "SEVERE"}:
        return s.upper()

    try:
        return mapping.get(str(int(float(s))), "")
    except (ValueError, TypeError):
        return ""


def map_serious(value):
    s = clean(value).upper()
    if s in {"Y", "YES"}:
        return "Y"
    if s in {"N", "NO"}:
        return "N"
    return ""


def map_relationship(value):
    s = clean(value).lower()
    mapping = {
        "not related": "NONE",
        "unlikely related": "REMOTE",
        "possibly related": "POSSIBLE",
        "probably related": "PROBABLE",
        "none": "NONE",
        "remote": "REMOTE",
        "possible": "POSSIBLE",
        "probable": "PROBABLE",
    }
    return mapping.get(s, "")


def main():
    input_dir = Path("input")
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    dm = pd.read_csv(
        input_dir / "dm.csv",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    dm.columns = [c.strip() for c in dm.columns]

    dm_map = {}
    for _, row in dm.iterrows():
        usubjid = clean(row.get("USUBJID", ""))
        if usubjid:
            dm_map[usubjid] = parse_raw_date(row.get("RFSTDTC", ""))

    raw = pd.read_csv(
        input_dir / "raw_ae.csv",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    raw.columns = [c.strip() for c in raw.columns]

    records = []

    for _, row in raw.iterrows():
        subject = clean(row.get("SUBJECT", ""))
        usubjid = f"{STUDYID}-{subject}" if subject else ""

        aespid = clean(row.get("RECID", ""))
        aeterm = clean(row.get("AE_VERBATIM", "")).upper()
        aedecod = clean(row.get("CODED_PT", ""))
        aebodsys = clean(row.get("CODED_SOC", ""))
        aesev = map_severity(row.get("SEVERITY", ""))
        aeser = map_serious(row.get("SERIOUS", ""))
        aerel = map_relationship(row.get("RELATIONSHIP", ""))
        aeout = clean(row.get("OUTCOME", "")).upper()

        aestdtc = parse_raw_date(row.get("AESTDAT", ""))
        aeendtc = parse_raw_date(row.get("AEENDAT", ""))

        ongoing = clean(row.get("AEONGO", "")).upper()
        if ongoing in {"Y", "YES"}:
            aeendtc = ""

        rfstdtc = dm_map.get(usubjid, "")
        aestdy = study_day(aestdtc, rfstdtc)
        aeendy = study_day(aeendtc, rfstdtc)

        records.append(
            {
                "STUDYID": STUDYID,
                "DOMAIN": DOMAIN,
                "USUBJID": usubjid,
                "AESEQ": 0,
                "AESPID": aespid,
                "AETERM": aeterm,
                "AEDECOD": aedecod,
                "AEBODSYS": aebodsys,
                "AESEV": aesev,
                "AESER": aeser,
                "AEREL": aerel,
                "AEOUT": aeout,
                "AESTDTC": aestdtc,
                "AEENDTC": aeendtc,
                "AESTDY": aestdy,
                "AEENDY": aeendy,
            }
        )

    if records:
        df = pd.DataFrame(records, columns=OUTPUT_COLUMNS)
    else:
        df = pd.DataFrame(columns=OUTPUT_COLUMNS)

    if not df.empty:
        df = df.sort_values(
            by=["USUBJID", "AESTDTC", "AETERM", "AESPID"],
            kind="mergesort",
        )
        df["AESEQ"] = df.groupby("USUBJID", sort=False).cumcount() + 1

    df = df[OUTPUT_COLUMNS]
    df.to_csv(output_dir / "ae.csv", index=False, na_rep="", lineterminator="\n")


if __name__ == "__main__":
    main()
