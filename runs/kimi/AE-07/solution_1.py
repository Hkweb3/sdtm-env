import os
import datetime
import pandas as pd

STUDYID = "ALX-334"
MDY_SITES = {"100", "112", "430", "691", "775", "884"}
DMY_SITES = {"310", "314", "554"}

AEREL_MAP = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}
AESER_MAP = {"Yes": "Y", "No": "N"}

OUT_COLS = [
    "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
    "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
    "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
]


def clean(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return str(x).strip()


def parse_raw_date(raw, mdy):
    """Parse a raw locale-dependent date. Returns (ISO 8601 string, date or None)."""
    s = clean(raw)
    if not s:
        return "", None
    parts = [p.strip() for p in s.split("/")]
    dd = mm = yyyy = ""
    if len(parts) == 3:
        if mdy:
            mm, dd, yyyy = parts
        else:
            dd, mm, yyyy = parts
    elif len(parts) == 2:
        mm, yyyy = parts
    elif len(parts) == 1:
        yyyy = parts[0]
    else:
        return "", None
    if not yyyy:
        return "", None
    if not mm:
        return yyyy, None
    if not dd:
        return "%s-%02d" % (yyyy, int(mm)), None
    d = datetime.date(int(yyyy), int(mm), int(dd))
    return d.isoformat(), d


def parse_iso_date(s):
    s = clean(s)
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def study_day(d, rf):
    if d is None or rf is None:
        return ""
    delta = (d - rf).days
    return str(delta + 1) if delta >= 0 else str(delta)


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str)
    raw = pd.read_csv("input/raw_ae.csv", dtype=str)

    rf_map = {
        clean(r["USUBJID"]): parse_iso_date(r["RFSTDTC"])
        for _, r in dm.iterrows()
    }

    records = []
    for _, r in raw.iterrows():
        subject = clean(r["SUBJECT"])
        site = subject.split("-")[0]
        usubjid = "%s-%s" % (STUDYID, subject)
        mdy = site in MDY_SITES

        aestdtc, st_dt = parse_raw_date(r["AESTDAT"], mdy)
        if clean(r["AEONGO"]).upper() == "Y":
            aeendtc, en_dt = "", None
        else:
            aeendtc, en_dt = parse_raw_date(r["AEENDAT"], mdy)

        rf = rf_map.get(usubjid)

        records.append({
            "STUDYID": STUDYID,
            "DOMAIN": "AE",
            "USUBJID": usubjid,
            "AESPID": clean(r["RECID"]),
            "AETERM": clean(r["AE_VERBATIM"]).upper(),
            "AEDECOD": clean(r["CODED_PT"]),
            "AEBODSYS": clean(r["CODED_SOC"]),
            "AESEV": clean(r["SEVERITY"]).upper(),
            "AESER": AESER_MAP.get(clean(r["SERIOUS"]), ""),
            "AEREL": AEREL_MAP.get(clean(r["RELATIONSHIP"]), ""),
            "AEOUT": clean(r["OUTCOME"]).upper(),
            "AESTDTC": aestdtc,
            "AEENDTC": aeendtc,
            "AESTDY": study_day(st_dt, rf),
            "AEENDY": study_day(en_dt, rf),
        })

    out = pd.DataFrame(records)
    out = out.sort_values(
        ["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort"
    ).reset_index(drop=True)
    out.insert(3, "AESEQ", out.groupby("USUBJID").cumcount() + 1)
    out = out[OUT_COLS].fillna("")

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
