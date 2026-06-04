import re
import numpy as np
import pandas as pd


# ============================================================
# 1. Eksklusionsord og feasibility-logik
# ============================================================

DEFAULT_EXCLUDE_KEYWORDS = [
    # Vacciner / pandemiprodukter
    "vaccine",
    "vaccin",
    "covid",
    "corona",

    # Store/komplekse GLP-1 markeder
    "semaglutid",
    "tirzepatid",
    "liraglutid",
    "dulaglutid",

    # Biologiske / komplekse produkter
    "insulin",
    "monoklonal",
    "antikrop",
    "biologisk",
    "radiofarmaka",
    "radiofarmaceutisk",

    # Meget komplekse/typisk hospitalsorienterede former
    "infusion",
    "infusionsvæske",
    "implantat",
]


def apply_exclusion_filter(
    df: pd.DataFrame,
    exclude_keywords: list[str] | None = None
) -> pd.DataFrame:
    """
    Fjerner produkter der matcher bestemte ord, fx vaccine, covid,
    semaglutid, insulin osv.

    Filteret kigger i tekstkolonner som:
    - Virksomt stof
    - Dosageform
    - Styrke
    - Pakningstørrelse
    """

    if exclude_keywords is None:
        exclude_keywords = DEFAULT_EXCLUDE_KEYWORDS

    if not exclude_keywords:
        return df.copy()

    out = df.copy()

    text_cols = [
        col for col in [
            "Virksomt stof",
            "Dosageform",
            "Styrke",
            "Pakningstørrelse",
        ]
        if col in out.columns
    ]

    if not text_cols:
        return out

    combined_text = (
        out[text_cols]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.lower()
    )

    escaped_keywords = [re.escape(str(keyword).lower()) for keyword in exclude_keywords]
    pattern = "|".join(escaped_keywords)

    keep_mask = ~combined_text.str.contains(pattern, regex=True, na=False)

    return out.loc[keep_mask].copy()


def feasibility_score_from_form(series: pd.Series) -> pd.Series:
    """
    Giver en score fra 0-100 for hvor realistisk produktformen typisk er.

    Dette er en simpel første model:
    - tablet/kapsel = meget realistisk
    - creme/salve/gel = relativt realistisk
    - orale væsker/dråber = middel
    - injektion/pen = lavere
    - infusion/vaccine/implantat = meget lav
    """

    form = series.fillna("").astype(str).str.lower()

    score = pd.Series(50, index=series.index, dtype="float")

    # Mest realistiske klassiske generikaformer
    score[form.str.contains("tablet|tabletter|kapsel|kapsler", regex=True, na=False)] = 100

    # Semisolide produkter
    score[form.str.contains("creme|salve|gel|liniment", regex=True, na=False)] = 80

    # Orale væsker / dråber / suspensioner
    score[form.str.contains(
        "dråber|draaber|opløsning|oplosning|mikstur|suspension|oral",
        regex=True,
        na=False
    )] = 70

    # Injektioner / penne kan være interessante, men er ofte mere komplekse
    score[form.str.contains(
        "injektion|injektions|sprøjte|sproejte|pen",
        regex=True,
        na=False
    )] = 30

    # Meget komplekse/hospitalsnære former
    score[form.str.contains(
        "infusion|infusions|implantat|vaccine|vaccin",
        regex=True,
        na=False
    )] = 0

    return score.clip(0, 100)


# ============================================================
# 2. Generelle scorefunktioner
# ============================================================

def minmax_score(series: pd.Series) -> pd.Series:
    """
    Omdanner en numerisk kolonne til en score fra 0-100.
    Højere værdi = højere score.
    """

    s = pd.to_numeric(series, errors="coerce")

    min_val = s.min()
    max_val = s.max()

    if pd.isna(min_val) or pd.isna(max_val) or min_val == max_val:
        return pd.Series(50, index=series.index, dtype="float")

    return ((s - min_val) / (max_val - min_val) * 100).clip(0, 100)


def competitor_score(series: pd.Series) -> pd.Series:
    """
    Lavt antal konkurrenter giver høj score.

    Simpel model:
    0 konkurrenter = 100
    1 konkurrent  = 80
    2 konkurrenter = 60
    3 konkurrenter = 40
    4 konkurrenter = 20
    5+ konkurrenter = 0
    """

    s = pd.to_numeric(series, errors="coerce").fillna(0)

    return (100 - s * 20).clip(lower=0, upper=100)


def find_competitor_column(df: pd.DataFrame) -> str | None:
    """
    Finder konkurrent-kolonnen uanset om den hedder
    'Konkurrenter' eller 'konkurrenter'.
    """

    if "Konkurrenter" in df.columns:
        return "Konkurrenter"

    if "konkurrenter" in df.columns:
        return "konkurrenter"

    return None


# ============================================================
# 3. Vækstberegning
# ============================================================

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

    annualized=True:
        Beregner årlig gennemsnitlig vækst, CAGR.

    annualized=False:
        Beregner samlet periodevækst.
    """

    out = df.copy()

    start_year = str(start_year)
    end_year = str(end_year)

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

    # Hvis startåret er 0 eller mangler, kan vækst ikke beregnes meningsfuldt
    out.loc[
        (start_values <= 0) | start_values.isna() | end_values.isna(),
        growth_col
    ] = np.nan

    return out, growth_col


# ============================================================
# 4. Shortlist uden API
# ============================================================

def build_shortlist_without_api(
    market_df: pd.DataFrame,
    shortlist_n: int,
    revenue_year: str,
    growth_start_year: str,
    growth_end_year: str,
    growth_metric: str = "Omsætning",
    min_revenue: float = 0,
    exclude_unrealistic: bool = True,
    exclude_keywords: list[str] | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    Finder en shortlist uden API baseret på:
    - omsætning
    - vækst
    - antal pakninger
    - evt. eksklusion af urealistiske produkter

    Denne bruges før AIP/Konkurrenter hentes.
    """

    out = market_df.copy()

    if exclude_unrealistic:
        out = apply_exclusion_filter(out, exclude_keywords=exclude_keywords)

    revenue_year = str(revenue_year)
    growth_start_year = str(growth_start_year)
    growth_end_year = str(growth_end_year)

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

    if out.empty:
        return out, growth_col

    # Grov score uden API
    out["Shortlist score omsætning"] = (
        minmax_score(out[revenue_col])
        if revenue_col in out.columns
        else 50
    )

    out["Shortlist score vækst"] = (
        minmax_score(out[growth_col].fillna(0))
        if growth_col in out.columns
        else 50
    )

    out["Shortlist score antal"] = (
        minmax_score(out[quantity_col])
        if quantity_col in out.columns
        else 50
    )

    if "Dosageform" in out.columns:
        out["Shortlist score feasibility"] = feasibility_score_from_form(out["Dosageform"])
    else:
        out["Shortlist score feasibility"] = 50

    # Shortlist-score uden API.
    # Her vægtes markedsstørrelse og vækst højest,
    # men feasibility hjælper med at sortere urealistiske produkter ned.
    out["Shortlist Score"] = (
        out["Shortlist score omsætning"] * 0.45
        + out["Shortlist score vækst"] * 0.25
        + out["Shortlist score antal"] * 0.15
        + out["Shortlist score feasibility"] * 0.15
    )

    out = out.sort_values("Shortlist Score", ascending=False, na_position="last")

    return out.head(shortlist_n).copy(), growth_col


# ============================================================
# 5. Endelig Opportunity Score efter API
# ============================================================

def build_final_opportunity_score(
    enriched_df: pd.DataFrame,
    revenue_year: str,
    growth_col: str,
    competitor_weight: float = 35,
    revenue_weight: float = 30,
    growth_weight: float = 20,
    aip_weight: float = 15,
    feasibility_weight: float = 0,
    min_competitors: int | None = None,
    max_competitors: int | None = None,
    exclude_unrealistic: bool = False,
    exclude_keywords: list[str] | None = None,
) -> pd.DataFrame:
    """
    Beregner endelig Opportunity Score efter AIP/Konkurrenter er hentet.

    Scoremodellen kan vægte:
    - lav konkurrence
    - høj omsætning
    - høj vækst
    - høj AIP
    - realistisk produktprofil / feasibility
    """

    out = enriched_df.copy()

    if exclude_unrealistic:
        out = apply_exclusion_filter(out, exclude_keywords=exclude_keywords)

    revenue_year = str(revenue_year)
    revenue_col = f"Omsætning {revenue_year}"

    competitor_col = find_competitor_column(out)

    if competitor_col is not None:
        out[competitor_col] = pd.to_numeric(
            out[competitor_col],
            errors="coerce"
        ).fillna(0)

        if min_competitors is not None:
            out = out[out[competitor_col] >= min_competitors]

        if max_competitors is not None:
            out = out[out[competitor_col] <= max_competitors]

    if out.empty:
        return out

    for col in [competitor_col, "AIP", revenue_col, growth_col]:
        if col and col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    # Del-scores
    out["Score konkurrence"] = (
        competitor_score(out[competitor_col])
        if competitor_col is not None and competitor_col in out.columns
        else 50
    )

    out["Score omsætning"] = (
        minmax_score(out[revenue_col])
        if revenue_col in out.columns
        else 50
    )

    out["Score vækst"] = (
        minmax_score(out[growth_col].fillna(0))
        if growth_col in out.columns
        else 50
    )

    out["Score AIP"] = (
        minmax_score(out["AIP"].fillna(0))
        if "AIP" in out.columns
        else 50
    )

    if "Dosageform" in out.columns:
        out["Score feasibility"] = feasibility_score_from_form(out["Dosageform"])
    else:
        out["Score feasibility"] = 50

    total_weight = (
        competitor_weight
        + revenue_weight
        + growth_weight
        + aip_weight
        + feasibility_weight
    )

    if total_weight == 0:
        total_weight = 1

    out["Opportunity Score"] = (
        out["Score konkurrence"] * competitor_weight
        + out["Score omsætning"] * revenue_weight
        + out["Score vækst"] * growth_weight
        + out["Score AIP"] * aip_weight
        + out["Score feasibility"] * feasibility_weight
    ) / total_weight

    out["Opportunity Score"] = out["Opportunity Score"].round(1)

    out = out.sort_values("Opportunity Score", ascending=False, na_position="last")

    out.insert(0, "Rank", range(1, len(out) + 1))

    return out
