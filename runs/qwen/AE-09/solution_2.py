import pandas as pd
from pathlib import Path
from datetime import date


def main():
    input_dir = Path("input")
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(
        input_dir / "raw_ae.csv",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    dm = pd.read_csv(
        input_dir / "dm.csv",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    raw["VERSION_NUM"] = pd.to_numeric(raw["VERSION"], errors="coerce").fillna(0)
    raw = raw.sort_values(
        ["SUBJECT", "RECID", "VERSION_NUM"],
        ascending=[True, True, False],
        kind="mergesort",
    )
    raw = raw.drop_duplicates(subset=["SUBJECT", "RECID"], keep="first")
    raw = raw.drop(columns=["VERSION_NUM"])

    def build_usubjid(subject):
        subject = str(subject).strip()
        if "-" in subject:
            site, subj = subject.split("-", 1)
        else:
            site, subj = "", subject
        return f"TQR-448-{site.strip()}-{subj.strip()}"

    raw["USUBJID"] = raw["SUBJECT"].map(build_usubjid)

    dm["USUBJID"] = dm["USUBJID"].str.strip()
    dm = dm[["USUBJID", "RFSTDTC"]].drop_duplicates(subset=["USUBJID"], keep="first")

    df = raw.merge(dm, on="USUBJID", how="left")
    df["RFSTDTC"] = df["RFSTDTC"].fillna("")

    def clean_date_part(x):
        x = str(x).strip()
        if x.upper() in {"", "NA", "NULL", "."}:
            return ""
        if x in {"0", "00"}:
            return ""
        return x

    def build_dtc(dd, mm, yyyy):
        dd = clean_date_part(dd)
        mm = clean_date_part(mm)
        yyyy = str(yyyy).strip()

        if yyyy.upper() in {"", "NA", "NULL", "."} or yyyy in {"0", "00", "000", "0000"}:
            return ""

        yyyy = yyyy.zfill(4)

        if not mm:
            return yyyy
        if not dd:
            return f"{yyyy}-{mm.zfill(2)}"
        return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"

    df["AESTDTC"] = [
        build_dtc(dd, mm, yyyy)
        for dd, mm, yyyy in zip(
            df["AESTDAT_DD"],
            df["AESTDAT_MM"],
            df["AESTDAT_YYYY"],
        )
    ]
    df["AEENDTC"] = [
        build_dtc(dd, mm, yyyy)
        for dd, mm, yyyy in zip(
            df["AEENDAT_DD"],
            df["AEENDAT_MM"],
            df["AEENDAT_YYYY"],
        )
    ]

    ongoing = df["AEONGO"].str.strip().str.upper().eq("Y")
    df.loc[ongoing, "AEENDTC"] = ""

    def map_code(series, mapping):
        def _map(x):
            x = str(x).strip()
            if x.endswith(".0"):
                x = x[:-2]
            return mapping.get(x, "")

        return series.map(_map)

    df["AESEV"] = map_code(
        df["SEVERITY"],
        {"1": "MILD", "2": "MODERATE", "3": "SEVERE"},
    )
    df["AESER"] = map_code(df["SERIOUS"], {"1": "Y", "0": "N"})

    rel_map = {
        "Not related": "NONE",
        "Unlikely related": "REMOTE",
        "Possibly related": "POSSIBLE",
        "Probably related": "PROBABLE",
    }

    def map_rel(x):
        x = str(x).strip()
        if x in rel_map:
            return rel_map[x]

        xl = x.lower()
        for k, v in rel_map.items():
            if k.lower() == xl:
                return v
        return ""

    df["AEREL"] = df["RELATIONSHIP"].map(map_rel)

    df["AETERM"] = df["AE_VERBATIM"].str.strip().str.upper()
    df["AEDECOD"] = df["CODED_PT"].str.strip()
    df["AEBODSYS"] = df["CODED_SOC"].str.strip()
    df["AEOUT"] = df["OUTCOME"].str.strip().str.upper()
    df["AESPID"] = df["RECID"].str.strip()

    def parse_full_date(s):
        s = str(s).strip()
        parts = s.split("-")
        if len(parts) != 3:
            return None
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return date(y, m, d)
        except ValueError:
            return None

    def study_day(dtc, ref):
        d = parse_full_date(dtc)
        r = parse_full_date(ref)

        if d is None or r is None:
            return ""

        delta = (d - r).days
        if d >= r:
            return str(delta + 1)
        return str(delta)

    df["AESTDY"] = [
        study_day(aestdtc, rfstdtc)
        for aestdtc, rfstdtc in zip(df["AESTDTC"], df["RFSTDTC"])
    ]
    df["AEENDY"] = [
        study_day(aeendtc, rfstdtc)
        for aeendtc, rfstdtc in zip(df["AEENDTC"], df["RFSTDTC"])
    ]

    for col in ["AESTDTC", "AETERM", "AESPID"]:
        df[col] = df[col].fillna("").astype(str)

    df = df.sort_values(
        ["USUBJID", "AESTDTC", "AETERM", "AESPID"],
        kind="mergesort",
    )
    df["AESEQ"] = df.groupby("USUBJID", sort=False).cumcount() + 1
    df = df.sort_values(["USUBJID", "AESEQ"], kind="mergesort")

    df["STUDYID"] = "TQR-448"
    df["DOMAIN"] = "AE"

    out_cols = [
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

    out = df[out_cols].copy()
    out = out.fillna("").astype(str)

    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].str.strip()

    out.to_csv(output_dir / "ae.csv", index=False)


if __name__ == "__main__":
    main()
