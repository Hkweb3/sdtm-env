import pandas as pd
import os

STUDYID = "TQR-883"

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_mh.csv", dtype=str)

# Drop deleted records
raw = raw[raw["RECORD_STATUS"] != "DELETED"].copy()

# Build USUBJID
raw["USUBJID"] = STUDYID + "-" + raw["SUBJECT"]

# Validate against DM
valid_ids = set(dm["USUBJID"])
raw = raw[raw["USUBJID"].isin(valid_ids)].copy()

# Map columns
raw["STUDYID"] = STUDYID
raw["DOMAIN"] = "MH"
raw["MHSPID"] = raw["RECID"]
raw["MHTERM"] = raw["MH_VERBATIM"]
raw["MHDECOD"] = raw["CODED_PT"]
raw["MHBODSYS"] = raw["CODED_SOC"]
raw["MHCAT"] = raw["CATEGORY"].str.upper()
raw["MHSTDTC"] = raw["MHSTDAT"]
raw["MHDTC"] = raw["VISIT_DATE"]

# Clean empty strings to NaN
for col in ["MHDECOD", "MHBODSYS", "MHCAT", "MHSTDTC", "MHDTC"]:
    raw[col] = raw[col].replace("", pd.NA)

# Sort for MHSEQ
raw = raw.sort_values(
    by=["USUBJID", "MHCAT", "MHSTDTC", "MHTERM", "MHSPID"],
    na_position="last"
).reset_index(drop=True)

raw["MHSEQ"] = raw.groupby("USUBJID").cumcount() + 1

# Study day calculation
def parse_date(s):
    """Return (year, month, day) or None if unparseable."""
    if pd.isna(s) or s == "":
        return None
    parts = str(s).split("-")
    try:
        y = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else None
        d = int(parts[2]) if len(parts) > 2 else None
        return (y, m, d)
    except (ValueError, IndexError):
        return None

def to_ordinal(y, m, d):
    import datetime
    return datetime.date(y, m, d).toordinal()

# Build RFSTDTC lookup
rfstdtc_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

def compute_mhdy(row):
    mhdtc = row["MHDTC"]
    usubjid = row["USUBJID"]
    rf = rfstdtc_map.get(usubjid)
    if pd.isna(mhdtc) or pd.isna(rf):
        return pd.NA
    mh_parts = parse_date(mhdtc)
    rf_parts = parse_date(rf)
    if mh_parts is None or rf_parts is None:
        return pd.NA
    # Both must be complete dates
    if None in mh_parts or None in rf_parts:
        return pd.NA
    mh_ord = to_ordinal(*mh_parts)
    rf_ord = to_ordinal(*rf_parts)
    if mh_ord >= rf_ord:
        return mh_ord - rf_ord + 1
    else:
        return mh_ord - rf_ord

raw["MHDY"] = raw.apply(compute_mhdy, axis=1)

# Select output columns
out_cols = ["STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHSPID", "MHTERM",
            "MHDECOD", "MHCAT", "MHBODSYS", "MHDTC", "MHSTDTC", "MHDY"]
out = raw[out_cols].copy()

# Ensure MHSEQ is integer
out["MHSEQ"] = out["MHSEQ"].astype(int)

# Write output
os.makedirs("output", exist_ok=True)
out.to_csv("output/mh.csv", index=False)
