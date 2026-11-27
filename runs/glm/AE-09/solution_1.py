import os
import pandas as pd
from datetime import date

STUDYID = "TQR-448"


def s(v):
    return "" if v is None else str(v).strip()


def build_dtc(dd, mm, yyyy):
    """Build ISO 8601 date from unpadded DD / MM / YYYY parts; keep only known parts."""
    dd, mm, yyyy = s(dd), s(mm), s(yyyy)
    if yyyy == "":
        return ""
    if mm == "":
        return yyyy
    if dd == "":
        return "{}-{}".format(yyyy, mm.zfill(2))
    return "{}-{}-{}".format(yyyy, mm.zfill(2), dd.zfill(2))


def is_full_date(dtc):
    if len(dtc) != 10:
        return False
    try:
        date.fromisoformat(dtc)
        return True
    except ValueError:
        return False


def study_day(dtc, rfstdtc):
    """No day 0: date - RFSTDTC + 1 on/after RFSTDTC, else date - RFSTDTC."""
    if not is_full_date(dtc) or not is_full_date(rfstdtc):
        return ""
    d = date.fromisoformat(dtc)
    r = date.fromisoformat(rfstdtc)
    delta = (d - r).days
    return delta + 1 if delta >= 0 else delta


def main():
    dm = pd.read_csv(os.path.join("input", "dm.csv"), dtype=str,
                     keep_default_na=False, encoding="utf-8-sig")
    ae = pd.read_csv(os.path.join("input", "raw_ae.csv"), dtype=str,
                     keep_default_na=False, encoding="utf-8-sig")

    for c in ae.columns:
        ae[c] = ae[c].astype(str).str.strip()

    # Keep only the row with the highest VERSION per SUBJECT + RECID
    ae["_ver"] = pd.to_numeric(ae["VERSION"], errors="coerce").fillna(-1)
    ae = (ae.sort_values("_ver", kind="mergesort")
            .drop_duplicates(subset=["SUBJECT", "RECID"], keep="last")
            .drop(columns="_ver"))

    rfst_map = dm.set_index("USUBJID")["RFSTDTC"].to_dict()

    sev_map = {"1": "MILD", "2": "MODERATE", "3": "SEVERE"}
    ser_map = {"1": "Y", "0": "N"}
    rel_map = {"not related": "NONE",
               "unlikely related": "REMOTE",
               "possibly related": "POSSIBLE",
               "probably related": "PROBABLE"}

    recs = []
    for _, r in ae.iterrows():
        usubjid = "{}-{}".format(STUDYID, r["SUBJECT"])
        rfst = rfst_map.get(usubjid, "")

        aestdtc = build_dtc(r["AESTDAT_DD"], r["AESTDAT_MM"], r["AESTDAT_YYYY"])
        ongoing = s(r["AEONGO"]).upper() == "Y"
        aeendtc = "" if ongoing else build_dtc(
            r["AEENDAT_DD"], r["AEENDAT_MM"], r["AEENDAT_YYYY"])

        recs.append({
            "STUDYID": STUDYID,
            "DOMAIN": "AE",
            "USUBJID": usubjid,
            "AESPID": r["RECID"],
            "AETERM": r["AE_VERBATIM"].upper(),
            "AEDECOD": r["CODED_PT"],
            "AEBODSYS": r["CODED_SOC"],
            "AESEV": sev_map.get(r["SEVERITY"], ""),
            "AESER": ser_map.get(r["SERIOUS"], ""),
            "AEREL": rel_map.get(r["RELATIONSHIP"].lower(), ""),
            "AEOUT": r["OUTCOME"].upper(),
            "AESTDTC": aestdtc,
            "AEENDTC": aeendtc,
            "AESTDY": study_day(aestdtc, rfst),
            "AEENDY": study_day(aeendtc, rfst),
        })

    out = pd.DataFrame(recs)

    # AESEQ: within subject, sort by AESTDTC (as text), AETERM, AESPID
    out = out.sort_values(["USUBJID", "AESTDTC", "AETERM", "AESPID"],
                          kind="mergesort").reset_index(drop=True)
    out["AESEQ"] = out.groupby("USUBJID", sort=False).cumcount() + 1

    cols = ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM",
            "AEDECOD", "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT",
            "AESTDTC", "AEENDTC", "AESTDY", "AEENDY"]
    out = out[cols]

    os.makedirs("output", exist_ok=True)
    out.to_csv(os.path.join("output", "ae.csv"), index=False)


if __name__ == "__main__":
    main()
