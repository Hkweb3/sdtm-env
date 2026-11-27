```python
import os
import re
import pandas as pd
from datetime import date

NULL_TOKENS = {"", "NA", "NULL", "NAN", "N/A", "."}


def clean(v):
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    s = str(v).strip()
    if s.upper() in NULL_TOKENS:
        return ""
    return s


MMDD_SITES = {"179", "615", "856"}


def _valid_full(y, m, d):
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def parse_date(raw, site):
    s = clean(raw)
    if not s:
        return ""

    # Already ISO-like: YYYY, YYYY-MM, or YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{1,2}(-\d{1,2})?", s):
        parts = s.split("-")
        y = int(parts[0])
        if len(parts) == 1:
            return f"{y:04d}"
        m = int(parts[1])
        if not (1 <= m <= 12):
            return ""
        if len(parts) == 2:
            return f"{y:04d}-{m:02d}"
        d = int(parts[2])
        if _valid_full(y, m, d):
            return f"{y:04d}-{m:02d}-{d:02d}"
        return ""

    parts = [p for p in re.split(r"[^0-9]+", s) if p]
    if not parts:
        return ""

    if len(parts) == 1:
        num = parts[0]

        if len(num) == 4 and 1000 <= int(num) <= 2999:
            return num.zfill(4)

        if len(num) == 6:
            # YYYYMM
            y = int(num[:4])
            m = int(num[4:6])
            if 1000 <= y <= 2999 and 1 <= m <= 12:
                return f"{y:04d}-{m:02d}"

            # YYMMDD
            y = int(num[:2])
            m = int(num[2:4])
            d = int(num[4:6])
            if y < 100:
                y += 2000
            if _valid_full(y, m, d):
                return f"{y:04d}-{m:02d}-{d:02d}"
            return ""

        if len(num) == 8:
            # YYYYMMDD
            y = int(num[:4])
            m = int(num[4:6])
            d = int(num[6:8])
            if 1000 <= y <= 2999 and _valid_full(y, m, d):
                return f"{y:04d}-{m:02d}-{d:02d}"

            # Locale-based MMDDYYYY or DDMMYYYY
            if site in MMDD_SITES:
                m = int(num[:2])
                d = int(num[2:4])
                y = int(num[4:8])
            else:
                d = int(num[:2])
                m = int(num[2:4])
                y = int(num[4:8])

            if 1000 <= y <= 2999 and _valid_full(y, m, d):
                return f"{y:04d}-{m:02d}-{d:02d}"

            # Fallback swap if the locale-based interpretation is invalid
            if site in MMDD_SITES:
                d = int(num[:2])
                m = int(num[2:4])
                y = int(num[4:8])
            else:
                m = int(num[:2])
                d = int(num[2:4])
                y = int(num[4:8])

            if 1000 <= y <= 2999 and _valid_full(y, m, d):
                return f"{y:04d}-{m:02d}-{d:02d}"

        return ""

    if len(parts) == 2:
        a, b = parts

        # YYYY-MM
        if len(a) == 4 and 1000 <= int(a) <= 2999:
            y = int(a)
            m = int(b)
            if 1 <= m <= 12:
                return f"{y:04d}-{m:02d}"

        # MM/YYYY
        if len(b) == 4 and 1000 <= int(b) <= 2999:
            y = int(b)
            m = int(a)
            if 1 <= m <= 12:
                return f"{y:04d}-{m:02d}"

        return ""

    if len(parts) == 3:
        a, b, c = parts

        # YYYY-MM-DD
        if len(a) == 4 and 1000 <= int(a) <= 2999:
            y = int(a)
            m = int(b)
            d = int(c)
            if _valid_full(y, m, d):
                return f"{y:04d}-{m:02d}-{d:02d}"

        # Locale-based MM/DD/YYYY or DD/MM/YYYY
        if len(c) == 4 and 1000 <= int(c) <= 2999:
            y = int(c)

            if site in MMDD_SITES:
                m = int(a)
                d = int(b)
            else:
                d = int(a)
                m = int(b)

            if _valid_full(y, m, d):
                return f"{y:04d}-{m:02d}-{d:02d}"

            # Fallback swap if the locale-based interpretation is invalid
            if site in MMDD_SITES:
                d = int(a)
                m = int(b)
            else:
                m = int(a)
                d = int(b)

            if _valid_full(y, m, d):
                return f"{y:04d}-{m:02d}-{d:02d}"

        return ""

    return ""


def is_full_date(s):
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))


def study_day(dtc, rfstdtc):
    if not is_full_date(dtc) or not is_full_date(rfstdtc):
        return ""
    try:
        d = date.fromisoformat(dtc)
        r = date.fromisoformat(rfstdtc)
    except ValueError:
        return ""

    diff = (d - r).days
    if d >= r:
        return str(diff + 1)
    return str(diff)


def code_value(v):
    s = clean(v)
    if s in {"0", "1", "2", "3"}:
        return s
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return s


def main():
    raw = pd.read_csv(
        "input/raw_ae.csv",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    dm = pd.read_csv(
        "input/dm.csv",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    raw.columns = [c.strip() for c in raw.columns]
    dm.columns = [c.strip() for c in dm.columns]

    for col in raw.columns:
        raw[col] = raw[col].map(clean)
    for col in dm.columns:
        dm[col] = dm[col].map(clean)

    # Select the highest saved version for each record first.
    raw["VERSION_NUM"] = pd.to_numeric(raw["VERSION"], errors="coerce").fillna(0).astype(int)
    raw = raw.sort_values(["SUBJECT", "RECID", "VERSION_NUM"], kind="mergesort")
    raw = raw.groupby(["SUBJECT", "RECID"], sort=False).tail(1)

    # Then drop deleted and placeholder rows.
    raw = raw[raw["RECORD_STATUS"].str.upper() != "DELETED"]
    raw = raw[raw["AEYN"].str.upper() != "NO"]

    dm_rf = {}
    dm_lookup = {}
    for _, d in dm.iterrows():
        usubjid = d["USUBJID"]
        rf = d["RFSTDTC"]
        if usubjid:
            dm_rf[usubjid] = rf

        site = d["SITEID"]
        subj = d["SUBJID"]

        site_keys = {site}
        subj_keys = {subj}
        if site.isdigit():
            site_keys.add(str(int(site)))
        if subj.isdigit():
            subj_keys.add(str(int(subj)))

        for sk in site_keys:
            for uk in subj_keys:
                dm_lookup[(sk, uk)] = (usubjid, rf)

    sev_map = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
    ser_map = {"1": "Y", "0": "N"}
    rel_map = {
        "not related": "NONE",
        "unlikely related": "REMOTE",
        "possibly related": "POSSIBLE",
        "probably related": "PROBABLE",
    }

    records = []
    for _, r in raw.iterrows():
        subject = r["SUBJECT"]
        if not subject or "-" not in subject:
            continue

        site, subj = subject.split("-", 1)
        site = site.strip()
        subj = subj.strip()
        site_fmt = str(int(site)) if site.isdigit() else site

        usubjid = None
        rfstdtc = ""

        site_keys = {site}
        subj_keys = {subj}
        if site.isdigit():
            site_keys.add(str(int(site)))
        if subj.isdigit():
            subj_keys.add(str(int(subj)))

        for sk in site_keys:
            for uk in subj_keys:
                if (sk, uk) in dm_lookup:
                    usubjid, rfstdtc = dm_lookup[(sk, uk)]
                    break
            if usubjid is not None:
                break

        if usubjid is None:
            usubjid = f"ALX-599-{site}-{subj}"

        aestdtc = parse_date(r["AESTDAT"], site_fmt)
        if r["AEONGO"].upper() in {"Y", "YES"}:
            aeendtc = ""
        else:
            aeendtc = parse_date(r["AEENDAT"], site_fmt)

        records.append(
            {
                "STUDYID": "ALX-599",
                "DOMAIN": "AE",
                "USUBJID": usubjid,
                "AESPID": r["RECID"],
                "AETERM": r["AE_VERBATIM"].upper(),
                "AEDECOD": r["CODED_PT"],
                "AEBODSYS": r["CODED_SOC"],
                "AESEV": sev_map.get(code_value(r["SEVERITY"]), ""),
                "AESER": ser_map.get(code_value(r["SERIOUS"]), ""),
                "AEREL": rel_map.get(r["RELATIONSHIP"].lower(), ""),
                "AEOUT": r["OUTCOME"].upper(),
                "AESTDTC": aestdtc,
                "AEENDTC": aeendtc,
                "AESTDY": study_day(aestdtc, rfstdtc),
                "AEENDY": study_day(aeendtc, rfstdtc),
            }
        )

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

    if records:
        out