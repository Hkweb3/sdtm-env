import os

import pandas as pd

INPUT_DIR = "input"
OUTPUT_DIR = "output"


def load(name):
    return pd.read_csv(os.path.join(INPUT_DIR, name), dtype=str)


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def complete_date(value):
    """Return a Timestamp for a complete (day-level) date, else None."""
    s = clean(value)
    if len(s) < 10:
        return None
    try:
        return pd.to_datetime(s[:10], format="%Y-%m-%d")
    except (ValueError, TypeError):
        return None


dm = load("dm.csv")
ae = load("ae.csv")
ex = load("ex.csv")
ds = load("ds.csv")
lb = load("lb.csv")

findings = []


def add(check, usubjid, domain, seq):
    findings.append({"CHECK": check, "USUBJID": usubjid, "DOMAIN": domain, "SEQ": seq})


# ---------------------------------------------------------------- AE_DATE_ORDER
for _, row in ae.iterrows():
    start = complete_date(row["AESTDTC"])
    end = complete_date(row["AEENDTC"])
    if start is not None and end is not None and end < start:
        add("AE_DATE_ORDER", row["USUBJID"], "AE", str(int(clean(row["AESEQ"]))))

# ---------------------------------------------------------------- AE_DUPLICATE
ae["_stdtc"] = ae["AESTDTC"].map(clean)
ae["_decod"] = ae["AEDECOD"].map(clean)
ae_with_start = ae[ae["_stdtc"] != ""]
for (usubjid, _, _), grp in ae_with_start.groupby(["USUBJID", "_decod", "_stdtc"]):
    if len(grp) > 1:
        seqs = sorted(int(clean(s)) for s in grp["AESEQ"])
        for seq in seqs[1:]:  # every copy except the lowest AESEQ
            add("AE_DUPLICATE", usubjid, "AE", str(seq))

# --------------------------------------------------------------- SAE_CRITERIA
CRITERIA = ["AESCAN", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE", "AESOD"]
for _, row in ae.iterrows():
    any_criterion = any(clean(row[c]).upper() == "Y" for c in CRITERIA)
    serious = clean(row["AESER"]).upper() == "Y"
    if serious != any_criterion:
        add("SAE_CRITERIA", row["USUBJID"], "AE", str(int(clean(row["AESEQ"]))))

# ---------------------------------------------------------- DEATH_CONSISTENCY
has_death_date = {}
death_date = {}
for _, row in dm.iterrows():
    subj = row["USUBJID"]
    has_death_date[subj] = clean(row["DTHDTC"]) != ""
    death_date[subj] = complete_date(row["DTHDTC"])

fatal_subjects = set()
for _, row in ae.iterrows():
    if clean(row["AEOUT"]).upper() == "FATAL":
        fatal_subjects.add(row["USUBJID"])

for _, row in ae.iterrows():
    subj = row["USUBJID"]
    seq = str(int(clean(row["AESEQ"])))
    if clean(row["AEOUT"]).upper() == "FATAL" and not has_death_date.get(subj, False):
        add("DEATH_CONSISTENCY", subj, "AE", seq)
    start = complete_date(row["AESTDTC"])
    dth = death_date.get(subj)
    if start is not None and dth is not None and start > dth:
        add("DEATH_CONSISTENCY", subj, "AE", seq)

for _, row in dm.iterrows():
    subj = row["USUBJID"]
    if has_death_date.get(subj, False) and subj not in fatal_subjects:
        add("DEATH_CONSISTENCY", subj, "DM", "")

# ------------------------------------------------------------ DOSE_AFTER_DISC
disc_date = {}
is_disp = ds["DSCAT"].map(lambda v: clean(v).upper()) == "DISPOSITION EVENT"
is_early = ~ds["DSDECOD"].map(lambda v: clean(v).upper()).isin(
    ["COMPLETED", "SCREEN FAILURE"]
)
for _, row in ds[is_disp & is_early].iterrows():
    d = complete_date(row["DSSTDTC"])
    if d is None:
        continue
    subj = row["USUBJID"]
    if subj not in disc_date or d < disc_date[subj]:
        disc_date[subj] = d

for _, row in ex.iterrows():
    subj = row["USUBJID"]
    if subj not in disc_date:
        continue
    start = complete_date(row["EXSTDTC"])
    if start is not None and start > disc_date[subj]:
        add("DOSE_AFTER_DISC", subj, "EX", str(int(clean(row["EXSEQ"]))))

# --------------------------------------------------------------------- LAB_UNIT
lb_numeric = lb.copy()
lb_numeric["_value"] = pd.to_numeric(lb_numeric["LBSTRESN"], errors="coerce")
lb_numeric = lb_numeric[lb_numeric["_value"].notna()]

for (usubjid, _), grp in lb_numeric.groupby(["USUBJID", "LBTESTCD"]):
    if len(grp) < 3:  # need at least two other results
        continue
    for idx, row in grp.iterrows():
        median = grp.drop(index=idx)["_value"].median()
        if pd.isna(median) or median == 0:
            continue
        value = row["_value"]
        if value >= 8 * median or value <= median / 8:
            add("LAB_UNIT", usubjid, "LB", str(int(clean(row["LBSEQ"]))))

# -------------------------------------------------------------- LAB_VISIT_DATE
lb_dates = lb.copy()
lb_dates["_visit"] = lb_dates["VISIT"].map(lambda v: clean(v).upper())
lb_dates["_date"] = lb_dates["LBDTC"].map(lambda v: clean(v)[:10])
lb_dates["_vnum"] = pd.to_numeric(lb_dates["VISITNUM"], errors="coerce")
scheduled = lb_dates[
    (~lb_dates["_visit"].str.startswith("UNSCHEDULED"))
    & (lb_dates["_date"] != "")
    & lb_dates["_vnum"].notna()
]

for (usubjid, _), grp in scheduled.groupby(["USUBJID", "LBTESTCD"]):
    for idx, row in grp.iterrows():
        earlier = grp[grp["_vnum"] < row["_vnum"]]
        if earlier.empty:
            continue
        if row["_date"] < earlier["_date"].max():
            add("LAB_VISIT_DATE", usubjid, "LB", str(int(clean(row["LBSEQ"]))))

# ----------------------------------------------------------------------- output
result = pd.DataFrame(findings, columns=["CHECK", "USUBJID", "DOMAIN", "SEQ"])
result = result.drop_duplicates()
result["_seqnum"] = pd.to_numeric(result["SEQ"], errors="coerce")
result = result.sort_values(
    ["CHECK", "USUBJID", "DOMAIN", "_seqnum"], na_position="first"
).drop(columns="_seqnum")

os.makedirs(OUTPUT_DIR, exist_ok=True)
result.to_csv(os.path.join(OUTPUT_DIR, "findings.csv"), index=False)
