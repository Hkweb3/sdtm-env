import csv
import os
from collections import defaultdict
from datetime import date, datetime

STUDYID = "ALX-878"
DOMAIN = "AE"

MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

REL_MAP = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}

SERIOUS_MAP = {
    "YES": "Y",
    "NO": "N",
}


def parse_raw_date(s):
    """Convert raw DDMONYYYY to ISO 8601 and a date object if complete."""
    if not s or not str(s).strip():
        return "", None

    s = str(s).strip()
    if len(s) < 9:
        return "", None

    day_raw = s[:2]
    mon_raw = s[2:5].upper()
    year_raw = s[5:9]

    if not year_raw.isdigit():
        return "", None

    year = int(year_raw)
    month = MONTH_MAP.get(mon_raw) if mon_raw != "UNK" else None
    day = int(day_raw) if day_raw.isdigit() else None

    if day is not None and month is not None:
        try:
            dt = date(year, month, day)
            return dt.isoformat(), dt
        except ValueError:
            return f"{year:04d}-{month:02d}", None
    elif month is not None:
        return f"{year:04d}-{month:02d}", None
    else:
        return f"{year:04d}", None


def calc_study_day(iso_date, date_obj, rfst_dtc):
    """Calculate study day relative to RFSTDTC.

    Returns empty string when either date is partial or missing.
    """
    if not iso_date or date_obj is None or not rfst_dtc:
        return ""

    try:
        rf_date = datetime.strptime(rfst_dtc, "%Y-%m-%d").date()
    except ValueError:
        return ""

    diff = (date_obj - rf_date).days
    if diff >= 0:
        return diff + 1
    return diff


def main():
    # Read DM reference start dates
    rfst_map = {}
    with open("input/dm.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            usubjid = row["USUBJID"].strip()
            rfst_map[usubjid] = row["RFSTDTC"].strip()

    # Read raw AE data
    records = []
    with open("input/raw_ae.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            subject = raw["SUBJECT"].strip()
            usubjid = f"{STUDYID}-{subject}"
            rfst_dtc = rfst_map.get(usubjid, "")

            start_iso, start_dt = parse_raw_date(raw.get("AESTDAT", ""))
            end_iso, end_dt = parse_raw_date(raw.get("AEENDAT", ""))

            if raw.get("AEONGO", "").strip().upper() == "Y":
                end_iso = ""
                end_dt = None

            serious_raw = raw.get("SERIOUS", "").strip().upper()
            aeser = SERIOUS_MAP.get(serious_raw, "")

            relationship = raw.get("RELATIONSHIP", "").strip()
            aerel = REL_MAP.get(relationship, "")

            records.append(
                {
                    "STUDYID": STUDYID,
                    "DOMAIN": DOMAIN,
                    "USUBJID": usubjid,
                    "AESEQ": 0,
                    "AESPID": raw.get("RECID", "").strip(),
                    "AETERM": raw.get("AE_VERBATIM", "").strip().upper(),
                    "AEDECOD": raw.get("CODED_PT", "").strip(),
                    "AEBODSYS": raw.get("CODED_SOC", "").strip(),
                    "AESEV": raw.get("SEVERITY", "").strip().upper(),
                    "AESER": aeser,
                    "AEREL": aerel,
                    "AEOUT": raw.get("OUTCOME", "").strip().upper(),
                    "AESTDTC": start_iso or "",
                    "AEENDTC": end_iso or "",
                    "AESTDY": calc_study_day(start_iso, start_dt, rfst_dtc),
                    "AEENDY": calc_study_day(end_iso, end_dt, rfst_dtc),
                }
            )

    # Assign AESEQ within subject after sorting
    grouped = defaultdict(list)
    for record in records:
        grouped[record["USUBJID"]].append(record)

    final_records = []
    for usubjid, recs in grouped.items():
        recs.sort(
            key=lambda r: (r["AESTDTC"] or "", r["AETERM"] or "", r["AESPID"] or "")
        )
        for idx, rec in enumerate(recs, start=1):
            rec["AESEQ"] = idx
            final_records.append(rec)

    final_records.sort(key=lambda r: (r["USUBJID"], r["AESEQ"]))

    output_columns = [
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

    os.makedirs("output", exist_ok=True)
    with open("output/ae.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns)
        writer.writeheader()
        for record in final_records:
            writer.writerow({col: record[col] for col in output_columns})


if __name__ == "__main__":
    main()
