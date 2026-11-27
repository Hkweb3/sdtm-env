import pandas as pd
import os

STUDYID = "CTN-248"

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_mh.csv", dtype=str)

# Build USUBJID from raw SUBJECT
raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

# Validate against DM
valid_ids = set(dm["USUBJID"])
raw = raw[raw["USUBJID"].isin(valid_ids)].copy()

# RFSTDTC lookup
rfstdtc_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def parse_visit_date(s):
    if not isinstance(s, str) or not s.strip():
        return None
    parts = s.strip().split()
    if len(parts) != 3:
        return None
    dd, mon, yyyy = parts
    dd_out = dd if dd.isdigit() else None
    mon_out = MONTHS.get(mon.upper()) if mon.upper() in MONTHS else None
    yyyy_out = yyyy if yyyy.isdigit() else None
    if yyyy_out is None:
        return None
    if mon_out is None:
        return yyyy_out
    if dd_out is None:
        return f"{yyyy_out}-{mon_out}"
    return f"{yyyy_out}-{mon_out}-{dd_out}"


def parse_start_date(dd, mm, yyyy):
    def clean(v):
        if v is None:
            return None
        v = str(v).strip()
        if v == "" or v.lower() == "nan":
            return None
        return v

    dd = clean(dd)
    mm = clean(mm)
    yyyy = clean(yyyy)

    if yyyy is None:
        return None
    yyyy = yyyy.zfill(4)
    if mm is None:
        return yyyy
    mm = mm.zfill(2)
    if dd is None:
        return f"{yyyy}-{mm}"
    dd = dd.zfill(2)
    return f"{yyyy}-{mm}-{dd}"


def to_date(s):
    if s is None:
        return None
    parts = s.split("-")
    if len(parts) != 3:
        return None
    try:
        return pd.Timestamp(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return None


def study_day(dtc, rfstdtc):
    d = to_date(dtc)
    r = to_date(rfstdtc)
    if d is None or r is None:
        return None
    delta = (d - r).days
    if delta >= 0:
        return delta + 1
    return delta


rows = []
for _, r in raw.iterrows():
    usubjid = r["USUBJID"]
    rfstdtc = rfstdtc_map.get(usubjid)

    mhstdtc = parse_start_date(r.get("MHSTDAT_DD"), r.get("MHSTDAT_MM"), r.get("MHSTDAT_YYYY"))
    mhdtc = parse_visit_date(r.get("VISIT_DATE"))

    mhdy = study_day(mhdtc, rfstdtc)

    mhcat = r["CATEGORY"].upper() if isinstance(r["CATEGORY"], str) else ""

    rows.append({
        "STUDYID": STUDYID,
        "DOMAIN": "MH",
        "USUBJID": usubjid,
        "MHSPID": r["RECID"],
        "MHTERM": r["MH_VERBATIM"],
        "MHDECOD": r["CODED_PT"] if isinstance(r["CODED_PT"], str) and r["CODED_PT"].strip() else "",
        "MHCAT": mhcat,
        "MHBODSYS": r["CODED_SOC"] if isinstance(r["CODED_SOC"], str) and r["CODED_SOC"].strip() else "",
        "MHDTC": mhdtc if mhdtc else "",
        "MHSTDTC": mhstdtc if mhstdtc else "",
        "MHDY": mhdy if mhdy is not None else "",
    })

out = pd.DataFrame(rows)

# Sort for MHSEQ
out["_sort_stdtc"] = out["MHSTDTC"].fillna("")
out = out.sort_values(
    by=["USUBJID", "MHCAT", "_sort_stdtc", "MHTERM", "MHSPID"],
    kind="mergesort",
).reset_index(drop=True)

out["MHSEQ"] = out.groupby("USUBJID").cumcount() + 1

out = out.drop(columns=["_sort_stdtc"])

cols = ["STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM", "MHDECOD",
        "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY"]
out = out[cols]

os.makedirs("output", exist_ok=True)
out.to_csv("output/mh.csv", index=False)
