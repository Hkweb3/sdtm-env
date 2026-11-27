import os
import pandas as pd
from datetime import date

STUDYID = "MRN-326"
DOMAIN = "AE"

def parse_raw_date(s):
    """Convert raw MM/DD/YYYY to ISO 8601; keep partial dates as YYYY-MM or YYYY."""
    s = s.strip()
    if not s:
        return ""
    s = s.replace("-", "/")
    parts = [p.strip() for p in s.split("/")]

    if len(parts) == 1:
        p = parts[0]
        if len(p) == 4 and p.isdigit():
            return p
        return ""
    elif len(parts) == 2:
        p1, p2 = parts
        # Assume MM/YYYY when day is missing
        if len(p2) == 4 and p2.isdigit() and p1.isdigit() and 1 <= int(p1) <= 12:
            return f"{p2}-{int(p1):02d}"
        if len(p1) == 4 and p1.isdigit() and p2.isdigit() and 1 <= int(p2) <= 12:
            return f"{p1}-{int(p2):02d}"
        return ""
    elif len(parts) == 3:
        mm, dd, yyyy = parts
        if len(yyyy) == 4 and yyyy.isdigit():
            if mm.isdigit() and 1 <= int(mm) <= 12:
                if dd.isdigit() and 1 <= int(dd) <= 31:
                    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"
                if dd == "":
                    return f"{yyyy}-{int(mm):02d}"
            if mm == "" and dd == "":
                return yyyy
        return ""
    return ""

def calc_study_day(dtc, rfst):
    """Calculate study day relative to RFSTDTC. Blank if either date is partial/missing."""
    if not dtc or not rfst:
        return ""
    if len(dtc) != 10 or len(rfst) != 10:
        return ""
    try:
        dt = date.fromisoformat(dtc)
        rf = date.fromisoformat(rfst)
    except ValueError:
        return ""
    diff = (dt - rf).days
    if diff >= 0:
        return diff + 1
    return diff

def main():
    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    raw = pd.read_csv("input/raw_ae.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")

    rfst_map = dict(zip(dm["USUBJID"].str.strip(), dm["RFSTDTC"].str.strip()))

    sev_map = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
    ser_map = {"YES": "Y", "NO": "N"}
    rel_map = {
        "NOT RELATED": "NONE",
        "UNLIKELY RELATED": "REMOTE",
        "POSSIBLY RELATED": "POSSIBLE",
        "PROBABLY RELATED": "PROBABLE",
    }

    rows = []
    for _, r in raw.iterrows():
        subj = r["SUBJECT"].strip()
        usubjid = f"{STUDYID}-{subj}"

        aestdtc = parse_raw_date(r["AESTDAT"])
        if r["AEONGO"].strip().upper() == "Y":
            aeendtc = ""
        else:
            aeendtc = parse_raw_date(r["AEENDAT"])

        rfst = rfst_map.get(usubjid, "")

        rows.append({
            "STUDYID": STUDYID,
            "DOMAIN": DOMAIN,
            "USUBJID": usubjid,
            "AESPID": r["RECID"].strip(),
            "AETERM": r["AE_VERBATIM"].strip().upper(),
            "AEDECOD": r["CODED_PT"].strip(),
            "AEBODSYS": r["CODED_SOC"].strip(),
            "AESEV": sev_map.get(r["SEVERITY"].strip(), ""),
            "AESER": ser_map.get(r["SERIOUS"].strip().upper(), ""),
            "AEREL": rel_map.get(r["RELATIONSHIP"].strip().upper(), ""),
            "AEOUT": r["OUTCOME"].strip().upper(),
            "AESTDTC": aestdtc,
            "AEENDTC": aeendtc,
            "AESTDY": calc_study_day(aestdtc, rfst),
            "AEENDY": calc_study_day(aeendtc, rfst),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="stable")
    df["AESEQ"] = df.groupby("USUBJID").cumcount() + 1

    out_cols = [
        "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
        "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
        "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
    ]
    df = df[out_cols]
    df = df.sort_values(["USUBJID", "AESEQ"], kind="stable")

    os.makedirs("output", exist_ok=True)
    df.to_csv("output/ae.csv", index=False, na_rep="")

if __name__ == "__main__":
    main()
