import numpy as np
import pandas as pd


def minmax_score(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")

    min_val = s.min()
    max_val = s.max()

    if pd.isna(min_val) or pd.isna(max_val) or min_val == max_val:
        return pd.Series(50, index=series.index)

    return ((s - min_val) / (max_val - min_val) * 100).clip(0, 100)


def competitor_score(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0)

    # 0 konkurrenter = 100, 1 = 80, 2 = 60, 3 = 40, 4 = 20, 5+ = 0
    return (100 - s * 20).clip(lower=0, upper=100)


def add_period_growth(
    df: pd.DataFrame,
    metric_prefix: str,
    start_year: str,
    end_year: str,
    annualized: bool = True
) -> tuple[pd.DataFrame, str]:
    out = df.copy()

    start_col = f"{metric_prefix} {start_year}"
    end_col = f"{metric_prefix} {end_year}"

    if annualized:
        growth_col = f"Årlig vækst {start_year}-{end_year} (%)"
    else:
        growth_col = f"Samlet vækst {start_year}-{end_year} (%)"

    if start_col not in out.columns or end_col not in out.columns:
        out[growth_col] = np.nan
        return out, growth_col

    start_values = pd.to_numeric(out[start_col], errors="coerce")
    end_values = pd.to_numeric(out[end_col], errors="coerce")

    if annualized:
        number_of_years = int(end_year) - int(start_year)

        if number_of_years <= 0:
            out[growth_col] = np.nan
            return out, growth_col

        out[growth_col] = ((end_values / start_values) ** (1 / number_of_years) - 1) * 100
    else:
        out[growth_col] = ((end_values / start_values) - 1) * 100

    out.loc[
        (start_values <= 0) | start_values.isna() | end_values.isna(),
        growth_col
    ] = np.nan

    return out, growth_col


def build_shortlist_without_api(
    market_df: pd.DataFrame,
    shortlist_n: int,
    revenue_year: str,
    growth_start_year: str,
    growth_end_year: str,
    growth_metric: str = "Omsætning",
    min_revenue: float = 0,
) -> tuple[pd.DataFrame, str]:
    """
    Finder en shortlist uden API baseret på:
    - omsætning
    - vækst
    - antal pakninger

    Returnerer shortlist + navnet på vækstkolonnen.
    """

    out = market_df.copy()

    revenue_col = f"Omsætning {revenue_year}"
    quantity_col = f"Antal pakninger {revenue_year}"

    out, growth_col = add_period_growth(
        out,
        metric_prefix=growth_metric,
        start_year=growth_start_year,
        end_year=growth_end_year,
        annualized=True
    )

    for col in [revenue_col, quantity_col, growth_col]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if revenue_col in out.columns:
        out = out[out[revenue_col].fillna(0) >= min_revenue]

    # Grov score uden API
    out["Shortlist score omsætning"] = minmax_score(out[revenue_col]) if revenue_col in out.columns else 50
    out["Shortlist score vækst"] = minmax_score(out[growth_col].fillna(0)) if growth_col in out.columns else 50
    out["Shortlist score antal"] = minmax_score(out[quantity_col]) if quantity_col in out.columns else 50

    out["Shortlist Score"] = (
        out["Shortlist score omsætning"] * 0.55
        + out["Shortlist score vækst"] * 0.30
        + out["Shortlist score antal"] * 0.15
    )

    out = out.sort_values("Shortlist Score", ascending=False, na_position="last")

    return out.head(shortlist_n).copy(), growth_col


def build_final_opportunity_score(
    enriched_df: pd.DataFrame,
    revenue_year: str,
    growth_col: str,
    competitor_weight: float = 35,
    revenue_weight: float = 30,
    growth_weight: float = 20,
    aip_weight: float = 15,
    min_competitors: int | None = None,
    max_competitors: int | None = None,
) -> pd.DataFrame:
    """
    Beregner endelig Opportunity Score efter AIP/Konkurrenter er hentet.
    """

    out = enriched_df.copy()

    revenue_col = f"Omsætning {revenue_year}"

    if "Konkurrenter" in out.columns:
    out["Konkurrenter"] = pd.to_numeric(out["Konkurrenter"], errors="coerce").fillna(0)

    if min_competitors is not None:
        out = out[out["Konkurrenter"] >= min_competitors]

    if max_competitors is not None:
        out = out[out["Konkurrenter"] <= max_competitors]

    for col in ["Konkurrenter", "AIP", revenue_col, growth_col]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out["Score konkurrence"] = competitor_score(out["Konkurrenter"]) if "Konkurrenter" in out.columns else 50
    out["Score omsætning"] = minmax_score(out[revenue_col]) if revenue_col in out.columns else 50
    out["Score vækst"] = minmax_score(out[growth_col].fillna(0)) if growth_col in out.columns else 50
    out["Score AIP"] = minmax_score(out["AIP"].fillna(0)) if "AIP" in out.columns else 50

    total_weight = competitor_weight + revenue_weight + growth_weight + aip_weight

    if total_weight == 0:
        total_weight = 1

    out["Opportunity Score"] = (
        out["Score konkurrence"] * competitor_weight
        + out["Score omsætning"] * revenue_weight
        + out["Score vækst"] * growth_weight
        + out["Score AIP"] * aip_weight
    ) / total_weight

    out["Opportunity Score"] = out["Opportunity Score"].round(1)

    out = out.sort_values("Opportunity Score", ascending=False, na_position="last")
    out.insert(0, "Rank", range(1, len(out) + 1))

    return out
