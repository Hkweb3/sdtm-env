import os
import datetime
import pandas as pd

STUDYID = "PLX-326"

REL_MAP = {
    "Not related": "NONE",
    "Unlikely related": "REMOTE",
    "Possibly related": "POSSIBLE",
    "Probably related": "PROBABLE",
}

SER_MAP = {"Yes": "Y", "No": "N"}


def build_dtc(dd, mm, yyyy):
    """Build an ISO 8601 (possibly partial) date from raw parts."""
    dd = (dd or "").strip()
    mm = (mm or "").strip()
    yyyy = (yyyy or "").strip()
    if yyyy == "":
        return ""
    dtc = yyyy.zfill(4)
    if mm == "":
        return dtc
    dtc += "-" + mm.zfill(2)
    if dd == "":
        return dtc
    dtc += "-" + dd.zfill(2)
    return dtc


def study_day(dtc, rfstdtc):
    """Study day relative to RFSTDTC; blank unless both dates are complete."""
    if not dtc or len(dtc) != 10 or not rfstdtc or len(rfstdtc) != 10:
        return ""
    try:
        d = datetime.date.fromisoformat(dtc)
        r = datetime.date.fromisoformat(rfstdtc)
    except ValueError:
        return ""
    diff = (d - r).days
    return str(diff + 1 if diff >= 0 else diff)


def main():
    dm = pd.read_csv("input/dm.csv", dtype=str, keep_default_na=False)
    ae = pd.read_csv("input/raw_ae.csv", dtype=str, keep_default_na=False)

    rfstdtc_map = dict(zip(dm["USUBJID"], dm["RFSTDTC"]))

    out = pd.DataFrame(index=ae.index)
    out["STUDYID"] = STUDYID
    out["DOMAIN"] = "AE"

    subj = ae["SUBJECT"].str.split("-", n=1, expand=True)
    out["USUBJID"] = STUDYID + "-" + subj[0].str.strip() + "-" + subj[1].str.strip()

    out["AESPID"] = ae["RECID"]
    out["AETERM"] = ae["AE_VERBATIM"].str.upper()
    out["AEDECOD"] = ae["CODED_PT"]
    out["AEBODSYS"] = ae["CODED_SOC"]
    out["AESEV"] = ae["SEVERITY"].str.upper()
    out["AESER"] = ae["SERIOUS"].str.strip().map(SER_MAP).fillna("")
    out["AEREL"] = ae["RELATIONSHIP"].str.strip().map(REL_MAP).fillna("")
    out["AEOUT"] = ae["OUTCOME"].str.upper()

    out["AESTDTC"] = [
        build_dtc(d, m, y)
        for d, m, y in zip(ae["AESTDAT_DD"], ae["AESTDAT_MM"], ae["AESTDAT_YYYY"])
    ]
    endtc = [
        build_dtc(d, m, y)
        for d, m, y in zip(ae["AEENDAT_DD"], ae["AEENDAT_MM"], ae["AEENDAT_YYYY"])
    ]
    ongoing = ae["AEONGO"].str.strip().str.upper() == "Y"
    out["AEENDTC"] = ["" if o else e for o, e in zip(ongoing, endtc)]

    rf = out["USUBJID"].map(rfstdtc_map).fillna("")
    out["AESTDY"] = [study_day(d, r) for d, r in zip(out["AESTDTC"], rf)]
    out["AEENDY"] = [study_day(d, r) for d, r in zip(out["AEENDTC"], rf)]

    out = out.sort_values(
        ["USUBJID", "AESTDTC", "AETERM", "AESPID"], kind="mergesort"
    )
    out["AESEQ"] = out.groupby("USUBJID").cumcount() + 1

    cols = [
        "STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AESPID", "AETERM", "AEDECOD",
        "AEBODSYS", "AESEV", "AESER", "AEREL", "AEOUT", "AESTDTC", "AEENDTC",
        "AESTDY", "AEENDY",
    ]
    out = out[cols]

    os.makedirs("output", exist_ok=True)
    out.to_csv("output/ae.csv", index=False)


if __name__ == "__main__":
    main()
