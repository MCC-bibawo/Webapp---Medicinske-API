import math
import pandas as pd
from medicin_api import get_aip_and_competitors

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

def load_data(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Pakninger 2020_2025")

    # Standardiser kolonnenavne fra din Excel-fil
    df = df.rename(columns={
        "dosf_LT": "Dosf_LT",
        "Streng": "streng",
    })

    expected_cols = [
        "vnr", "aar", "Sektor", "ATC", "ATC_txt", "Pname", "Dosf_LT", "streng",
        "packtext", "ApkSum", "volsum", "VolType", "EkspSum", "imp_name",
        "Tilsk", "Udlev", "regsit"
    ]

    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Mangler disse kolonner i Excel-filen: {missing}")

    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["aar"] = pd.to_numeric(out["aar"], errors="coerce").astype("Int64")
    out["ApkSum"] = pd.to_numeric(out["ApkSum"], errors="coerce").fillna(0)
    out["EkspSum"] = pd.to_numeric(out["EkspSum"], errors="coerce").fillna(0)

    text_cols = ["ATC_txt", "Dosf_LT", "streng"]
    for col in text_cols:
        out[col] = out[col].fillna("").astype(str).str.strip()

        out["packtext"] = normalize_packtext(
            out["packtext"].fillna("").astype(str)
            )

    return out

def normalize_packtext(series: pd.Series) -> pd.Series:
    return (
        series
        .str.replace(r"\(.*?\)", "", regex=True)  # fjerner fx "(blister)"
        .str.replace(r"\s+", " ", regex=True)     # rydder ekstra mellemrum
        .str.strip()
    )


def list_active_substances(path: str) -> list[str]:
    df = load_data(path)
    df = clean_data(df)

    values = (
        df["ATC_txt"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    return sorted([v for v in values.unique() if v])


def filter_by_active_substance(
    df: pd.DataFrame,
    active_name: str,
    exact_match: bool = True
) -> pd.DataFrame:
    active_name = str(active_name).strip()

    if exact_match:
        mask = df["ATC_txt"].str.casefold() == active_name.casefold()
    else:
        mask = df["ATC_txt"].str.contains(active_name, case=False, na=False)

    return df.loc[mask].copy()


def build_base_table(df_filtered: pd.DataFrame) -> pd.DataFrame:
    if df_filtered.empty:
        return pd.DataFrame(columns=[
            "Dosageform", "Styrke", "Pakningstørrelse",
            "Antal pakninger 2020", "Antal pakninger 2021", "Antal pakninger 2022",
            "Antal pakninger 2023", "Antal pakninger 2024","Antal pakninger 2025",
            "AIP", "Konkurrenter",
            "Omsætning 2020", "Omsætning 2021",
            "Omsætning 2022", "Omsætning 2023",
            "Omsætning 2024" , "Omsætning 2025"
        ])

    grouped = (
        df_filtered.groupby(["Dosf_LT", "streng", "packtext", "aar"], dropna=False, as_index=False)
        .agg({
            "ApkSum": "sum",
            "EkspSum": "sum"
        })
    )

    qty_pivot = (
        grouped.pivot_table(
            index=["Dosf_LT", "streng", "packtext"],
            columns="aar",
            values="ApkSum",
            aggfunc="sum",
            fill_value=0
        )
        .reindex(columns=YEARS, fill_value=0)
        .reset_index()
    )

    rev_pivot = (
        grouped.pivot_table(
            index=["Dosf_LT", "streng", "packtext"],
            columns="aar",
            values="EkspSum",
            aggfunc="sum",
            fill_value=0
        )
        .reindex(columns=YEARS, fill_value=0)
        .reset_index()
    )

    qty_pivot.columns = [
        "Dosageform", "Styrke", "Pakningstørrelse",
        "Antal pakninger 2020", "Antal pakninger 2021", "Antal pakninger 2022",
        "Antal pakninger 2023", "Antal pakninger 2024", "Antal pakninger 2025"
    ]

    rev_pivot.columns = [
        "Dosageform", "Styrke", "Pakningstørrelse",
        "Omsætning 2020", "Omsætning 2021",
        "Omsætning 2022", "Omsætning 2023",
        "Omsætning 2024", "Omsætning 2025"
    ]

    merged = qty_pivot.merge(
        rev_pivot,
        on=["Dosageform", "Styrke", "Pakningstørrelse"],
        how="outer"
    )

    return merged


def enrich_with_api(table_df: pd.DataFrame, active_name: str) -> pd.DataFrame:
    if table_df.empty:
        result = table_df.copy()
        result["AIP"] = pd.Series(dtype="float")
        result["Konkurrenter"] = pd.Series(dtype="Int64")
        return result

    cache = {}

    def enrich_row(row):
        key = (
            active_name.strip().lower(),
            str(row["Dosageform"]).strip().lower(),
            str(row["Styrke"]).strip().lower(),
            str(row["Pakningstørrelse"]).strip().lower(),
        )

        if key not in cache:
            try:
                cache[key] = get_aip_and_competitors(
                    active_name=active_name,
                    dosageform=row["Dosageform"],
                    strength=row["Styrke"],
                    pack=row["Pakningstørrelse"]
                )
            except Exception:
                cache[key] = {"AIP": math.nan, "Konkurrenter": 0}

        return pd.Series(cache[key])

    enriched = table_df.apply(enrich_row, axis=1)
    result = pd.concat([table_df, enriched], axis=1)

    ordered_cols = [
        "Dosageform",
        "Styrke",
        "Pakningstørrelse",
        "Antal pakninger 2020",
        "Antal pakninger 2021",
        "Antal pakninger 2022",
        "Antal pakninger 2023",
        "Antal pakninger 2024",
        "Antal pakninger 2025",
        "AIP",
        "Konkurrenter",
        "Omsætning 2020",
        "Omsætning 2021",
        "Omsætning 2022",
        "Omsætning 2023",
        "Omsætning 2024",
        "Omsætning 2025",
    ]

    result = result[ordered_cols].copy()

    numeric_cols = [c for c in result.columns if c not in ["Dosageform", "Styrke", "Pakningstørrelse"]]
    result[numeric_cols] = result[numeric_cols].apply(pd.to_numeric, errors="coerce")

    # divider antal pakninger med 1.000
    qty_cols = [c for c in result.columns if "Antal pakninger" in c]
    result[qty_cols] = result[qty_cols] / 1000

# divider omsætning med 1.000
    rev_cols = [c for c in result.columns if "Omsætning" in c]
    result[rev_cols] = result[rev_cols] / 1000

    if "Konkurrenter" in result.columns:
        result["Konkurrenter"] = result["Konkurrenter"].fillna(0).astype("Int64")

    if "Antal pakninger 2025" in result.columns:
        result = result.sort_values("Antal pakninger 2025", ascending=False, na_position="last")
        
        

    return result.reset_index(drop=True)


def build_table_from_excel(path: str, active_name: str, exact_match: bool = True) -> pd.DataFrame:
    df = load_data(path)
    df = clean_data(df)
    df = filter_by_active_substance(df, active_name, exact_match=exact_match)
    table_df = build_base_table(df)
    table_df = enrich_with_api(table_df, active_name)
    return table_df