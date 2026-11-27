import os
import datetime as dt
import pandas as pd

STUDYID = "ALX-599"
MDY_SITES = {"179", "615", "856"}  # MM/DD/YYYY; all others DD/MM/YYYY

SEV_MAP = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
SER_MAP = {"1": "Y", "0": "N"}
REL_MAP = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}


def parse_raw_date(value, site):
    """Parse a raw numeric date using the site's locale.

    Returns (iso_dtc, full_date_or_None). Partial dates yield only the
    known parts and a None date object.
    """
    s = (value or "").strip()
    if not s:
        return "", None
    parts = [p.strip() for p in s.split("/")]
    try:
        if len(parts) == 3:
            a, b, y = parts
            if site in MDY_SITES:
                m, d = a, b
            else:
                d, m = a, b
            y, m, d = int(y), int(m), int(d)
            return f"{y:04d}-{m:02d}-{d:02d}", dt.date(y, m, d)
        if len(parts) == 2:  # month/year only
            m, y = int(parts[0]), int(parts[1])
            return f"{y:04d}-{m:02d}", None
        if len(parts) == 1:  # year only
            y = int(parts[0])
            return f"{y:04d}", None
    except ValueError:
        return "", None
    return "", None


def parse_iso(value):
    s = (value or "").strip()
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def study_day(d, ref):
    if d is None or ref is None:
        return ""
    delta = (d - ref).days
    return str(delta + 1 if delta >= 0 else delta)


def main():
    os.makedirs("output", exist_ok=True)

    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)
    rf_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    ae = pd.read_csv("input/raw_ae.csv", dtype=str, keep_default_na=False)
    for col in ae.columns:
        ae[col] = ae[col].str.strip()

    # Keep only the highest VERSION of each SUBJECT + RECID record
    ae["_ver"] = pd.to_numeric(ae["VERSION"], errors="coerce").fillna(0)
    ae = ae.sort_values("_ver", kind="mergesort")
    ae = ae.drop_duplicates(subset=["SUBJECT", "RECID"], keep="last")

    # Drop deleted records and "no adverse events" placeholder rows
    ae = ae[ae["RECORD_STATUS"] != "DELETED"]
    ae = ae[ae["AEYN"] != "No"]

    ae["STUDYID"] = STUDYID
    ae["DOMAIN"] = "AE"
    ae["USUBJID"] = STUDYID + "-" + ae["SUBJECT"]
    ae["AESPID"] = ae["RECID"]
    ae["AETERM"] = ae["AE_VERBATIM"].str.upper()
    ae["AEDECOD"] = ae["CODED_PT"]
    ae["AEBODSYS"] = ae["CODED_SOC"]
    ae["AESEV"] = ae["SEVERITY"].map(SEV_MAP).fillna("")
    ae["AESER"] = ae["SERIOUS"].map(SER_MAP).fillna("")
    ae["AEREL"] = ae["RELATIONSHIP"].map(REL_MAP).fillna("")
    ae["AEOUT"] = ae["OUTCOME"].str.upper()

    sites = ae["SUBJECT"].str.split("-").str[0]

    starts = [parse_raw_date(v, s) for v, s in zip(ae["AESTDAT"], sites)]
    ae["AESTDTC"] = [x[0] for x in starts]
    start_dates = [x[1] for x in starts]

    ends = [parse_raw_date(v, s) for v, s in zip(ae["AEENDAT"], sites)]
    ae["AEENDTC"] = [x[0] for x in ends]
    end_dates = [x[1] for x in ends]

    # Ongoing events have no end date
    ongoing = ae["AEONGO"] == "Y"
    ae.loc[ongoing, "AEENDTC"] = ""
    end_dates = [None if o else d for o, d in zip(ongoing, end_dates)]

    refs = [parse_iso(rf_map.get(u, "")) for u in ae["USUBJID"]]
    ae["AESTDY"] = [study_day(d, r) for d, r in zip(start_dates, refs)]
    ae["AEENDY"] = [study_day(d, r) for d, r in zip(end_dates, refs)]

    # AESEQ: per subject, sorted by AESTDTC (text), AETERM, AESPID
    ae = ae.sort_values(
        ["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort"
    )
    ae["AESEQ"] = ae.groupby("USUBJID").cumcount() + 1

    out = ae[[
        "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
        "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
        "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
    ]]
    out.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
