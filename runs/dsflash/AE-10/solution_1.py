import pandas as pd
import os

os.makedirs("output", exist_ok=True)

dm = pd.read_csv("input/dm.csv", dtype=str)
raw = pd.read_csv("input/raw_ae.csv", dtype=str)

# Build USUBJID
raw["USUBJID"] = "ALX-599-" + raw["SUBJECT"]

# Keep only subjects in DM
dm_usubjids = set(dm["USUBJID"])
raw = raw[raw["USUBJID"].isin(dm_usubjids)].copy()

# Drop deleted
raw = raw[raw["RECORD_STATUS"].str.upper() != "DELETED"].copy()

# Drop placeholder rows (AEYN == No)
raw = raw[~raw["AEYN"].str.strip().str.upper().eq("NO")].copy()

# Keep highest VERSION per SUBJECT + RECID
raw["VERSION"] = pd.to_numeric(raw["VERSION"], errors="coerce")
raw = raw.sort_values("VERSION", ascending=False)
raw = raw.drop_duplicates(subset=["SUBJECT", "RECID"], keep="first").copy()

# Date parsing per site
site_formats = {
    "179": "%m/%d/%Y",
    "271": "%d/%m/%Y",
    "589": "%d/%m/%Y",
    "615": "%m/%d/%Y",
    "635": "%d/%m/%Y",
    "856": "%m/%d/%Y",
    "983": "%d/%m/%Y",
    "997": "%d/%m/%Y",
}

def parse_date(val, site):
    if pd.isna(val) or str(val).strip() == "":
        return None
    fmt = site_formats.get(site)
    if fmt is None:
        return None
    try:
        return pd.to_datetime(str(val).strip(), format=fmt)
    except Exception:
        return None

def to_iso(dt):
    if dt is None or pd.isna(dt):
        return ""
    return dt.strftime("%Y-%m-%d")

raw["SITE"] = raw["SUBJECT"].str.split("-").str[0]

raw["_STDT"] = [parse_date(v, s) for v, s in zip(raw["AESTDAT"], raw["SITE"])]
raw["_ENDT"] = [parse_date(v, s) for v, s in zip(raw["AEENDAT"], raw["SITE"])]

# AEONGO = Y means no end date
ongo = raw["AEONGO"].fillna("").str.strip().str.upper().eq("Y")
raw.loc[ongo, "_ENDT"] = None

raw["AESTDTC"] = raw["_STDT"].apply(to_iso)
raw["AEENDTC"] = raw["_ENDT"].apply(to_iso)

# RFSTDTC lookup
rf_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

def rf_date(usubjid):
    v = rf_map.get(usubjid)
    if v is None or pd.isna(v) or str(v).strip() == "":
        return None
    try:
        return pd.to_datetime(str(v).strip(), format="%Y-%m-%d")
    except Exception:
        return None

def study_day(dt, rf):
    if dt is None or pd.isna(dt) or rf is None or pd.isna(rf):
        return ""
    delta = (dt - rf).days
    if delta >= 0:
        return str(delta + 1)
    else:
        return str(delta)

raw["AESTDY"] = [study_day(dt, rf_date(u)) for dt, u in zip(raw["_STDT"], raw["USUBJID"])]
raw["AEENDY"] = [study_day(dt, rf_date(u)) for dt, u in zip(raw["_ENDT"], raw["USUBJID"])]

# Severity
sev_map = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
raw["AESEV"] = raw["SEVERITY"].astype(str).str.strip().map(sev_map).fillna("")

# Serious
ser_map = {"1": "Y", "0": "N"}
raw["AESER"] = raw["SERIOUS"].astype(str).str.strip().map(ser_map).fillna("")

# Relationship
rel_map = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}
raw["AEREL"] = raw["RELATIONSHIP"].astype(str).str.strip().map(rel_map).fillna("")

# Output fields
raw["STUDYID"] = "ALX-599"
raw["DOMAIN"] = "AE"
raw["AESPID"] = raw["RECID"]
raw["AETERM"] = raw["AE_VERBATIM"].astype(str).str.upper()
raw["AEDECOD"] = raw["CODED_PT"]
raw["AEBODSYS"] = raw["CODED_SOC"]
raw["AEOUT"] = raw["OUTCOME"].astype(str).str.upper()

# Sort for AESEQ
raw = raw.sort_values(
    by=["USUBJID", "AESTDTC", "AETERM", "AESPID"],
    kind="mergesort"
).reset_index(drop=True)

raw["AESEQ"] = raw.groupby("USUBJID").cumcount() + 1
raw["AESEQ"] = raw["AESEQ"].astype(str)

out_cols = [
    "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
    "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
    "AESTDTC", "AEENDTC", "AESTDY", "AEENDY",
]

out = raw[out_cols].copy()
out = out.fillna("")

out.to_csv("output/ae.csv", index=False)
