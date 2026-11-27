import pandas as pd
import os

STUDYID = "ALX-334"

site_date_formats = {
    "100": "MM/DD/YYYY",
    "112": "MM/DD/YYYY",
    "310": "DD/MM/YYYY",
    "314": "DD/MM/YYYY",
    "430": "MM/DD/YYYY",
    "554": "DD/MM/YYYY",
    "691": "MM/DD/YYYY",
    "775": "MM/DD/YYYY",
    "884": "MM/DD/YYYY",
}

rel_map = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}


def parse_date(raw, fmt):
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if s == "" or s.lower() in ("nan", "na", "null", "."):
        return None
    # raw is numeric but format depends on site locale
    # try to parse as string date
    try:
        if fmt == "MM/DD/YYYY":
            parts = s.split("/")
            if len(parts) == 3:
                mm, dd, yyyy = parts
                return (yyyy, mm, dd)
        else:
            parts = s.split("/")
            if len(parts) == 3:
                dd, mm, yyyy = parts
                return (yyyy, mm, dd)
    except Exception:
        return None
    return None


def to_iso(parts):
    if parts is None:
        return ""
    yyyy, mm, dd = parts
    if not yyyy:
        return ""
    if not mm:
        return yyyy
    if not dd:
        return f"{yyyy}-{mm}"
    return f"{yyyy}-{mm}-{dd}"


def study_day(dtc, rfstdtc):
    if not dtc or not rfstdtc:
        return ""
    # both must be full dates
    if len(dtc) != 10 or len(rfstdtc) != 10:
        return ""
    try:
        d = pd.Timestamp(dtc)
        r = pd.Timestamp(rfstdtc)
    except Exception:
        return ""
    delta = (d - r).days
    if d >= r:
        return str(delta + 1)
    else:
        return str(delta)


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str)
    raw = pd.read_csv("input/raw_ae.csv", dtype=str)

    dm_map = {}
    for _, row in dm.iterrows():
        dm_map[row["USUBJID"]] = row["RFSTDTC"]

    rows = []
    for _, r in raw.iterrows():
        subject = str(r["SUBJECT"]).strip()
        site, subj = subject.split("-", 1)
        usubjid = f"{STUDYID}-{site}-{subj}"

        fmt = site_date_formats.get(site, "MM/DD/YYYY")

        start_parts = parse_date(r.get("AESTDAT"), fmt)
        end_parts = parse_date(r.get("AEENDAT"), fmt)

        aestdtc = to_iso(start_parts)
        aeendtc = to_iso(end_parts)

        ongo = str(r.get("AEONGO", "")).strip().upper()
        if ongo == "Y":
            aeendtc = ""

        severity = str(r.get("SEVERITY", "")).strip().upper()

        serious_raw = str(r.get("SERIOUS", "")).strip()
        if serious_raw == "Yes":
            aeser = "Y"
        elif serious_raw == "No":
            aeser = "N"
        else:
            aeser = ""

        rel_raw = str(r.get("RELATIONSHIP", "")).strip()
        aerel = rel_map.get(rel_raw, "")

        aeout = str(r.get("OUTCOME", "")).strip().upper()

        aeterm = str(r.get("AE_VERBATIM", "")).strip().upper()
        aedecod = str(r.get("CODED_PT", "")).strip()
        aebodsys = str(r.get("CODED_SOC", "")).strip()

        rfstdtc = dm_map.get(usubjid, "")

        aestdy = study_day(aestdtc, rfstdtc)
        aeendy = study_day(aeendtc, rfstdtc)

        rows.append({
            "STUDYID": STUDYID,
            "DOMAIN": "AE",
            "USUBJID": usubjid,
            "AESPID": str(r.get("RECID", "")).strip(),
            "AETERM": aeterm,
            "AEDECOD": aedecod,
            "AEBODSYS": aebodsys,
            "AESEV": severity,
            "AESER": aeser,
            "AEREL": aerel,
            "AEOUT": aeout,
            "AESTDTC": aestdtc,
            "AEENDTC": aeendtc,
            "AESTDY": aestdy,
            "AEENDY": aeendy,
        })

    df = pd.DataFrame(rows)

    # sort by USUBJID, AESTDTC (text), AETERM, AESPID
    df = df.sort_values(
        by=["USUBJID", "AESTDTC", "AETERM", "AESPID"],
        kind="mergesort",
    ).reset_index(drop=True)

    # assign AESEQ per subject
    df["AESEQ"] = df.groupby("USUBJID").cumcount() + 1
    df["AESEQ"] = df["AESEQ"].astype(int)

    cols = [
        "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
        "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
        "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
    ]
    df = df[cols]

    os.makedirs("output", exist_ok=True)
    df.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
