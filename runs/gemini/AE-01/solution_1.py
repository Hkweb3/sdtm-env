from datetime import datetime
import os
import pandas as pd

MONTHS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}

REL_MAP = {
    "NOT RELATED": "NONE",
    "UNLIKELY RELATED": "REMOTE",
    "POSSIBLY RELATED": "POSSIBLE",
    "PROBABLY RELATED": "PROBABLE",
}


def parse_date(date_str):
    if pd.isna(date_str):
        return ""
    val = str(date_str).strip()
    if not val:
        return ""

    parts = val.split()
    if len(parts) == 3:
        day_raw, mon_raw, year_raw = parts
        year = year_raw if year_raw.upper() not in ("UNK", "UN", "") else None
        mon = (
            MONTHS.get(mon_raw.upper())
            if mon_raw.upper() not in ("UNK", "UN", "")
            else None
        )
        day = (
            f"{int(day_raw):02d}"
            if (day_raw.isdigit() and day_raw.upper() not in ("UN", "UNK"))
            else None
        )

        if year and mon and day:
            return f"{year}-{mon}-{day}"
        elif year and mon:
            return f"{year}-{mon}"
        elif year:
            return f"{year}"
    return ""


def calc_study_day(dt_str, rfstdtc_str):
    if not dt_str or not rfstdtc_str:
        return ""
    if len(dt_str) != 10 or len(rfstdtc_str) != 10:
        return ""
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        rf = datetime.strptime(rfstdtc_str, "%Y-%m-%d").date()
        diff = (dt - rf).days
        return str(diff + 1 if diff >= 0 else diff)
    except ValueError:
        return ""


def main():
    os.makedirs("output", exist_ok=True)

    dm_df = pd.read_csv("input/dm.csv", dtype=str)
    raw_ae = pd.read_csv("input/raw_ae.csv", dtype=str)

    rfstdtc_map = dict(zip(dm_df["USUBJID"], dm_df["RFSTDTC"].fillna("")))

    records = []
    for _, row in raw_ae.iterrows():
        studyid = "PLX-785"
        domain = "AE"
        subj = str(row["SUBJECT"]).strip() if pd.notna(row["SUBJECT"]) else ""
        usubjid = f"{studyid}-{subj}"
        aespid = str(row["RECID"]).strip() if pd.notna(row["RECID"]) else ""
        aeterm = (
            str(row["AE_VERBATIM"]).strip().upper()
            if pd.notna(row["AE_VERBATIM"])
            else ""
        )
        aedecod = (
            str(row["CODED_PT"]).strip() if pd.notna(row["CODED_PT"]) else ""
        )
        aebodsys = (
            str(row["CODED_SOC"]).strip() if pd.notna(row["CODED_SOC"]) else ""
        )

        aesev = (
            str(row["SEVERITY"]).strip().upper()
            if pd.notna(row["SEVERITY"])
            else ""
        )

        ser_raw = (
            str(row["SERIOUS"]).strip().upper()
            if pd.notna(row["SERIOUS"])
            else ""
        )
        aeser = "Y" if ser_raw in ("YES", "Y") else "N"

        rel_raw = (
            str(row["RELATIONSHIP"]).strip().upper()
            if pd.notna(row["RELATIONSHIP"])
            else ""
        )
        aerel = REL_MAP.get(rel_raw, "")

        aeout = (
            str(row["OUTCOME"]).strip().upper()
            if pd.notna(row["OUTCOME"])
            else ""
        )

        aestdtc = parse_date(row.get("AESTDAT"))

        aeongo = (
            str(row.get("AEONGO", "")).strip().upper()
            if pd.notna(row.get("AEONGO"))
            else ""
        )
        if aeongo == "Y":
            aeendtc = ""
        else:
            aeendtc = parse_date(row.get("AEENDAT"))

        rfstdtc = rfstdtc_map.get(usubjid, "")
        aestdy = calc_study_day(aestdtc, rfstdtc)
        aeendy = calc_study_day(aeendtc, rfstdtc)

        records.append(
            {
                "STUDYID": studyid,
                "DOMAIN": domain,
                "USUBJID": usubjid,
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

    out_df = pd.DataFrame(records)

    out_df = out_df.sort_values(
        by=["USUBJID", "AESTDTC", "AETERM", "AESPID"]
    ).reset_index(drop=True)
    out_df["AESEQ"] = out_df.groupby("USUBJID").cumcount() + 1

    cols = [
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

    out_df = out_df[cols]
    out_df.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
