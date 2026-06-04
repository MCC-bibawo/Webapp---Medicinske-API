import pandas as pd
import numpy as np


def find_competitor_column(df: pd.DataFrame) -> str:
    """
    Finder konkurrent-kolonnen uanset om den hedder 'Konkurrenter' eller 'konkurrenter'.
    """
    if "Konkurrenter" in df.columns:
        return "Konkurrenter"
    if "konkurrenter" in df.columns:
        return "konkurrenter"
    raise ValueError("Kunne ikke finde kolonnen 'Konkurrenter'.")


def minmax_score(series: pd.Series) -> pd.Series:
    """
    Omdanner en numerisk kolonne til score fra 0-100.
    Højere værdi = højere score.
    """
    s = pd.to_numeric(series, errors="coerce")

    min_val = s.min()
    max_val = s.max()

    if pd.isna(min_val) or pd.isna(max_val) or min_val == max_val:
        return pd.Series(50, index=series.index)

    return ((s - min_val) / (max_val - min_val) * 100).clip(0, 100)


def competitor_score(series: pd.Series) -> pd.Series:
    """
    Lavt antal konkurrenter giver høj score.
    """
    s = pd.to_numeric(series, errors="coerce").fillna(0)

    score = 100 - (s * 20)

    return score.clip(lower=0, upper=100)


def add_period_growth(
    df: pd.DataFrame,
    metric_prefix: str,
    start_year: str,
    end_year: str,
    annualized: bool = True
) -> tuple[pd.DataFrame, str]:
    """
    Tilføjer en vækstkolonne fra start_year til end_year.

    metric_prefix kan fx være:
    - 'Omsætning'
    - 'Antal pakninger'

    annualized=True betyder årlig gennemsnitlig vækst.
    """
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


def calculate_opportunity_score(
    df: pd.DataFrame,
    revenue_col: str,
    growth_col: str | None = None,
    aip_col: str = "AIP",
    competitor_weight: float = 35,
    revenue_weight: float = 30,
    growth_weight: float = 20,
    aip_weight: float = 15,
) -> pd.DataFrame:
    """
    Beregner en Opportunity Score fra 0-100 baseret på:
    - få konkurrenter
    - høj omsætning
    - høj vækst
    - høj AIP
    """

    out = df.copy()

    competitor_col = find_competitor_column(out)

    # Sikr numeriske kolonner
    out[competitor_col] = pd.to_numeric(out[competitor_col], errors="coerce").fillna(0)

    if revenue_col in out.columns:
        out[revenue_col] = pd.to_numeric(out[revenue_col], errors="coerce").fillna(0)
    else:
        out[revenue_col] = 0

    if aip_col in out.columns:
        out[aip_col] = pd.to_numeric(out[aip_col], errors="coerce")
    else:
        out[aip_col] = np.nan

    if growth_col and growth_col in out.columns:
        out[growth_col] = pd.to_numeric(out[growth_col], errors="coerce")
    else:
        growth_col = None

    # Del-scores
    out["Score konkurrence"] = competitor_score(out[competitor_col])
    out["Score omsætning"] = minmax_score(out[revenue_col])
    out["Score AIP"] = minmax_score(out[aip_col].fillna(0))

    if growth_col:
        out["Score vækst"] = minmax_score(out[growth_col].fillna(0))
    else:
        out["Score vækst"] = 50

    # Normalisér vægte, så de ikke behøver summere til 100
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

    return out.sort_values("Opportunity Score", ascending=False, na_position="last")


def build_top_opportunities(
    df: pd.DataFrame,
    top_n: int,
    revenue_year: str,
    growth_start_year: str,
    growth_end_year: str,
    growth_metric: str = "Omsætning",
    annualized_growth: bool = True,
    competitor_weight: float = 35,
    revenue_weight: float = 30,
    growth_weight: float = 20,
    aip_weight: float = 15,
    min_revenue: float = 0,
    max_competitors: int | None = None,
) -> pd.DataFrame:
    """
    Bygger en top-liste over de mest interessante muligheder.
    """

    out = df.copy()

    competitor_col = find_competitor_column(out)

    revenue_col = f"Omsætning {revenue_year}"

    out, growth_col = add_period_growth(
        out,
        metric_prefix=growth_metric,
        start_year=growth_start_year,
        end_year=growth_end_year,
        annualized=annualized_growth
    )

    # Basisfiltre
    if revenue_col in out.columns:
        out[revenue_col] = pd.to_numeric(out[revenue_col], errors="coerce").fillna(0)
        out = out[out[revenue_col] >= min_revenue]

    if max_competitors is not None:
        out[competitor_col] = pd.to_numeric(out[competitor_col], errors="coerce").fillna(0)
        out = out[out[competitor_col] <= max_competitors]

    scored = calculate_opportunity_score(
        out,
        revenue_col=revenue_col,
        growth_col=growth_col,
        competitor_weight=competitor_weight,
        revenue_weight=revenue_weight,
        growth_weight=growth_weight,
        aip_weight=aip_weight,
    )

    scored.insert(0, "Rank", range(1, len(scored) + 1))

    return scored.head(top_n).copy()
