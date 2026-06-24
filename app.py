from io import BytesIO
from pathlib import Path


import pandas as pd
import streamlit as st

from logic import (build_market_base_table_from_clean_data, build_table_from_clean_data, build_table_from_excel, clean_data, load_data, enrich_shortlist_using_overview_api) 
from analysis import (build_final_opportunity_score, build_shortlist_without_api,)


DEFAULT_DATA_FILE = "data.xlsx"

st.set_page_config(page_title="Paknings-overblik", layout="wide")

st.title("Paknings-overblik")
st.caption("Søg på virksomt stof via ATC_txt og få tabellen vist direkte i browseren.")


@st.cache_data
def get_clean_data(path: str) -> pd.DataFrame:
    df = load_data(path)
    return clean_data(df)


@st.cache_data
def get_active_substances(path: str) -> list[str]:
    df = get_clean_data(path)

    values = (
        df["ATC_txt"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    return sorted([v for v in values.unique() if v])


@st.cache_data(ttl=3600, show_spinner=False)
def build_result_for_substances(
    path: str,
    selected_substances_tuple: tuple,
    exact_match: bool
) -> pd.DataFrame:
    """
    Bygger én samlet tabel for ét eller flere virksomme stoffer.
    Excel-filen læses kun én gang.
    """
    df_clean = get_clean_data(path)

    all_results = []

    for substance in selected_substances_tuple:
        df = build_table_from_clean_data(
            df_clean,
            substance,
            exact_match=exact_match
        )

        df["Virksomt stof"] = substance
        all_results.append(df)

    if not all_results:
        return pd.DataFrame()

    result = pd.concat(all_results, ignore_index=True)

    sort_cols = []
    ascending = []

    if "Virksomt stof" in result.columns:
        sort_cols.append("Virksomt stof")
        ascending.append(True)

    if "Antal pakninger 2025" in result.columns:
        sort_cols.append("Antal pakninger 2025")
        ascending.append(False)

    if sort_cols:
        result = result.sort_values(
            sort_cols,
            ascending=ascending,
            na_position="last"
        )

    if "Virksomt stof" in result.columns:
        cols = ["Virksomt stof"] + [
            c for c in result.columns
            if c != "Virksomt stof"
        ]
        result = result[cols]

    if "Virksomt stof" in result.columns:
        cols = ["Virksomt stof"] + [c for c in result.columns if c != "Virksomt stof"]
        result = result[cols]

    result = result.sort_values(
        sort_cols,
        ascending=ascending,
        na_position="last"
    )

    return result.reset_index(drop=True)
    
@st.cache_data(ttl=86400, show_spinner=False)
def build_market_result(path: str, exact_match: bool) -> pd.DataFrame:
    """
    Bygger én samlet tabel for ALLE virksomme stoffer i datafilen.
    Bruges til toplisten, så brugeren ikke skal vælge stoffer manuelt.
    Caches i 24 timer.
    """
    df_clean = get_clean_data(path)

    substances = (
        df_clean["ATC_txt"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    substances = sorted([s for s in substances.unique() if s])

    all_results = []

    for substance in substances:
        df = build_table_from_clean_data(
            df_clean,
            substance,
            exact_match=True
        )

        if not df.empty:
            df["Virksomt stof"] = substance
            all_results.append(df)

    if not all_results:
        return pd.DataFrame()

    result = pd.concat(all_results, ignore_index=True)

    if "Antal pakninger 2025" in result.columns:
        result = result.sort_values(
            ["Virksomt stof", "Antal pakninger 2025"],
            ascending=[True, False],
            na_position="last"
        )

    return result.reset_index(drop=True)

@st.cache_data(ttl=86400, show_spinner=False)
def build_market_base_result(path: str) -> pd.DataFrame:
    """
    Bygger hele markedstabellen uden API.
    Caches i 24 timer.
    """
    df_clean = get_clean_data(path)
    return build_market_base_table_from_clean_data(df_clean)


def enrich_shortlist_with_api(shortlist_df: pd.DataFrame) -> pd.DataFrame:
    """
    Beriger shortlisten med AIP og Konkurrenter via samme API-logik
    som den oprindelige Overblik-tabel, men viser progress i appen.
    """

    progress_bar = st.progress(0)
    progress_text = st.empty()

    def update_progress(i, total, active_name):
        progress = i / total if total else 0
        progress_bar.progress(progress)
        progress_text.write(
            f"Henter AIP og konkurrenter: {i}/{total} virksomme stoffer — {active_name}"
        )

    result = enrich_shortlist_using_overview_api(
        shortlist_df,
        progress_callback=update_progress
    )

    progress_bar.empty()
    progress_text.empty()

    return result

def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Overblik") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()


def make_safe_name(selected_substances: list[str]) -> str:
    if len(selected_substances) == 1:
        safe_name = selected_substances[0]
    else:
        safe_name = f"{len(selected_substances)}_stoffer"

    return (
        safe_name
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
    )


def dk_format_1_decimal(x):
    if pd.isna(x):
        return ""
    return f"{x:.1f}".replace(".", ",")


def dk_format_2_decimal(x):
    if pd.isna(x):
        return ""
    return f"{x:.2f}".replace(".", ",")


def make_format_dict(df: pd.DataFrame) -> dict:
    fmt = {}

    for col in df.columns:
        if "Antal" in col or "Omsætning" in col or "Vækst" in col:
            fmt[col] = dk_format_1_decimal
        elif col == "AIP":
            fmt[col] = dk_format_2_decimal

    return fmt


def get_revenue_years(df: pd.DataFrame) -> list[str]:
    years = []

    for col in df.columns:
        if col.startswith("Omsætning "):
            year = col.replace("Omsætning ", "").strip()
            if year.isdigit():
                years.append(year)

    return sorted(years, key=int)

def get_years_for_metric(df: pd.DataFrame, metric_prefix: str) -> list[str]:
    """
    Finder årskolonner for fx:
    - 'Omsætning 2020', 'Omsætning 2021', ...
    - 'Antal pakninger 2020', 'Antal pakninger 2021', ...
    """
    years = []

    for col in df.columns:
        if col.startswith(metric_prefix + " "):
            year = col.replace(metric_prefix, "").strip()
            if year.isdigit():
                years.append(year)

    return sorted(years, key=int)


def add_yoy_growth_columns(
    df: pd.DataFrame,
    metric_prefix: str,
    years: list[str]
) -> tuple[pd.DataFrame, list[str]]:
    """
    Tilføjer år-til-år vækstkolonner i procent.
    Fx:
    Vækst 2020-2021 (%)
    Vækst 2021-2022 (%)
    """
    out = df.copy()
    growth_cols = []

    for prev_year, current_year in zip(years[:-1], years[1:]):
        prev_col = f"{metric_prefix} {prev_year}"
        current_col = f"{metric_prefix} {current_year}"
        growth_col = f"Vækst {prev_year}-{current_year} (%)"

        prev_values = pd.to_numeric(out[prev_col], errors="coerce")
        current_values = pd.to_numeric(out[current_col], errors="coerce")

        out[growth_col] = ((current_values / prev_values) - 1) * 100

        # Hvis tidligere år er 0 eller mangler, kan væksten ikke beregnes meningsfuldt
        out.loc[
            (prev_values <= 0) | prev_values.isna() | current_values.isna(),
            growth_col
        ] = float("nan")

        growth_cols.append(growth_col)

    return out, growth_cols


def filter_by_yoy_growth(
    df: pd.DataFrame,
    metric_prefix: str,
    min_growth: float,
    max_growth: float
) -> tuple[pd.DataFrame, list[str]]:
    """
    Beholder kun rækker hvor ALLE år-til-år vækstrater ligger mellem
    min_growth og max_growth.
    """
    years = get_years_for_metric(df, metric_prefix)

    if len(years) < 2:
        return df.copy(), []

    out, growth_cols = add_yoy_growth_columns(df, metric_prefix, years)

    mask = out[growth_cols].notna().all(axis=1)

    for col in growth_cols:
        mask = mask & (out[col] >= min_growth) & (out[col] <= max_growth)

    return out.loc[mask].copy(), growth_cols

def get_current_result(current_key):
    if st.session_state.get("result_key") == current_key:
        return st.session_state.get("result")
    return None


with st.sidebar:
    st.header("Indstillinger")

    data_path = st.text_input("Sti til Excel-fil", value=DEFAULT_DATA_FILE)

    exact_match = st.checkbox(
        "Præcist match på ATC_txt",
        value=True
    )

    st.markdown(
        "Læg din fil i samme mappe som appen og kald den `data.xlsx`, "
        "eller skriv den fulde sti her."
    )

path_obj = Path(data_path)

if not path_obj.exists():
    st.warning(f"Filen blev ikke fundet: {path_obj}")
    st.stop()

try:
    substances = get_active_substances(str(path_obj))
except Exception as e:
    st.error(f"Kunne ikke læse datafilen: {e}")
    st.stop()

if not substances:
    st.warning("Der blev ikke fundet nogen værdier i ATC_txt.")
    st.stop()


selected_substances = st.multiselect(
    "Vælg virksomt stof",
    substances
)
selected_substances_key = tuple(sorted(selected_substances))

current_key = (
    str(path_obj),
    selected_substances_key,
    exact_match
)

tab_overblik, tab_analyse, tab_topliste = st.tabs(["Overblik", "Analyse", "Topliste"])


with tab_overblik:
    st.subheader("Overblik")

    if st.button("Generér tabel", type="primary", key="generate_overview"):
        if not selected_substances:
            st.warning("Vælg mindst ét virksomt stof.")
        else:
            with st.spinner("Bygger tabel..."):
                try:
                    result = build_result_for_substances(
                        str(path_obj),
                        tuple(selected_substances),
                        exact_match
                    )

                    st.session_state["result"] = result
                    st.session_state["result_key"] = current_key

                except Exception as e:
                    st.error(f"Fejl under generering: {e}")

    result = get_current_result(current_key)

    if result is None:
        st.info("Vælg ét eller flere virksomme stoffer og klik på 'Generér tabel'.")
    elif result.empty:
        st.warning("Ingen data fundet for det valgte virksomt stof.")
    else:
        st.success(f"Fandt {len(result)} rækker.")
        st.info("Alle tal er angivet i 1.000 (antal pakninger og omsætning).")

        fmt = make_format_dict(result)

        st.dataframe(
            result.style.format(fmt),
            use_container_width=True,
            hide_index=True
        )

        excel_bytes = to_excel_bytes(result, sheet_name="Overblik")
        safe_name = make_safe_name(selected_substances)

        st.download_button(
            label="Download Excel",
            data=excel_bytes,
            file_name=f"overblik_{safe_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


with tab_analyse:
    st.subheader("Analyse")

    st.markdown(
        "Her kan du finde interessante kombinationer baseret på fx lav konkurrence "
        "og høj omsætning."
    )

    if not selected_substances:
        st.warning("Vælg mindst ét virksomt stof øverst for at kunne lave analyse.")
    else:
        result = get_current_result(current_key)

        if result is None:
            st.info(
                "Der er endnu ikke bygget et datagrundlag for de valgte stoffer. "
                "Klik på knappen herunder for at hente data og lave analysen."
            )

            if st.button("Byg datagrundlag til analyse", key="generate_analysis"):
                with st.spinner("Bygger datagrundlag til analyse..."):
                    try:
                        result = build_result_for_substances(
                            str(path_obj),
                            selected_substances_key,
                            exact_match
                        )

                        st.session_state["result"] = result
                        st.session_state["result_key"] = current_key

                    except Exception as e:
                        st.error(f"Fejl under generering af analysegrundlag: {e}")
                        result = None

        if result is not None:
            if result.empty:
                st.warning("Ingen data fundet for de valgte stoffer.")
            else:
                years = get_revenue_years(result)

                if not years:
                    st.error("Kunne ikke finde omsætningskolonner i tabellen.")
                else:
                    st.markdown("### Analysefiltre")

                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        analysis_year = st.selectbox(
                            "Analyser år",
                            years,
                            index=len(years) - 1
                        )

                    revenue_col = f"Omsætning {analysis_year}"
                    quantity_col = f"Antal pakninger {analysis_year}"

                    with col2:
                        max_competitors = st.number_input(
                            "Maks konkurrenter",
                            min_value=0,
                            max_value=50,
                            value=2,
                            step=1
                        )

                    with col3:
                        min_revenue = st.number_input(
                            f"Minimum omsætning {analysis_year} (1.000)",
                            min_value=0.0,
                            value=0.0,
                            step=100.0
                        )

                    with col4:
                        min_aip = st.number_input(
                            "Minimum AIP",
                            min_value=0.0,
                            value=0.0,
                            step=1.0
                        )

                    only_with_sales = st.checkbox(
                        "Kun rækker med salg i valgt år",
                        value=True
                    )

                    
                    st.markdown("### Vækstfilter")

                    use_growth_filter = st.checkbox(
                        "Kun rækker med årlig vækst inden for et bestemt interval",
                        value=False
                    )

                    growth_cols = []

                    if use_growth_filter:
                        col_growth_1, col_growth_2, col_growth_3 = st.columns(3)

                        with col_growth_1:
                            growth_metric_label = st.selectbox(
                                "Vækst måles på",
                                 ["Omsætning", "Antal pakninger"]
                        )

                        with col_growth_2:
                            min_growth = st.number_input(
                              "Minimum årlig vækst (%)",
                            value=5.0,
                            step=0.5
                        )

                        with col_growth_3:
                            max_growth = st.number_input(
                                "Maksimum årlig vækst (%)",
                                value=10.0,
                                step=0.5
                        )
                    analysis_df = result.copy()
                    if "Konkurrenter" in analysis_df.columns:
                        competitor_col = "Konkurrenter"
                    elif "konkurrenter" in analysis_df.columns:
                        competitor_col = "konkurrenter"
                    else:
                        st.error("Kunne ikke finde kolonnen 'Konkurrenter' i tabellen.")
                        st.stop()
                    
                    numeric_candidates = [
                        competitor_col,
                        "AIP",
                        revenue_col,
                        quantity_col
                    ]

                    for col in numeric_candidates:
                        if col in analysis_df.columns:
                            analysis_df[col] = pd.to_numeric(
                                analysis_df[col],
                                errors="coerce"
                            )

                    mask = analysis_df[competitor_col].fillna(0) <= max_competitors
                    
                    if revenue_col in analysis_df.columns:
                        mask = mask & (
                            analysis_df[revenue_col].fillna(0) >= min_revenue
                        )

                    if min_aip > 0 and "AIP" in analysis_df.columns:
                        mask = mask & (
                            analysis_df["AIP"].fillna(-1) >= min_aip
                        )

                    if only_with_sales and quantity_col in analysis_df.columns:
                        mask = mask & (
                            analysis_df[quantity_col].fillna(0) > 0
                        )

                    opportunities = analysis_df.loc[mask].copy()

                    if use_growth_filter and not opportunities.empty:
                        metric_prefix = growth_metric_label

                        opportunities, growth_cols = filter_by_yoy_growth(
                            opportunities,
                            metric_prefix=metric_prefix,
                            min_growth=min_growth,
                            max_growth=max_growth
                    )

                    st.markdown("### Resultat af analyse")

                    metric1, metric2, metric3 = st.columns(3)

                    with metric1:
                        st.metric("Fundne muligheder", len(opportunities))

                    with metric2:
                        if revenue_col in opportunities.columns:
                            total_revenue = opportunities[revenue_col].sum()
                            st.metric(
                                f"Samlet omsætning {analysis_year} (1.000)",
                                dk_format_1_decimal(total_revenue)
                            )

                    with metric3:
                        if "konkurrenter" in opportunities.columns and not opportunities.empty:
                            avg_comp = opportunities["konkurrenter"].mean()
                            st.metric(
                                "Gns. konkurrenter",
                                dk_format_1_decimal(avg_comp)
                            )

                    if opportunities.empty:
                        st.warning("Ingen rækker matcher de valgte analysefiltre.")
                    else:
                        sort_options = []

                        if revenue_col in opportunities.columns:
                            sort_options.append(revenue_col)

                        if quantity_col in opportunities.columns:
                            sort_options.append(quantity_col)

                        if "AIP" in opportunities.columns:
                            sort_options.append("AIP")

                        if competitor_col in opportunities.columns and not opportunities.empty:
                            avg_comp = opportunities[competitor_col].mean()

                        if sort_options:
                            sort_by = st.selectbox(
                                "Sortér analyseresultat efter",
                                sort_options,
                                index=0
                            )

                            ascending = sort_by == competitor_col

                            opportunities = opportunities.sort_values(
                                sort_by,
                                ascending=ascending,
                                na_position="last"
                            )

                        display_cols = [
                            "Virksomt stof",
                            "Dosageform",
                            "Styrke",
                            "Pakningstørrelse",
                            quantity_col,
                            "AIP",
                            competitor_col,
                            revenue_col,
                        ]

                        if use_growth_filter:
                            display_cols = display_cols + growth_cols

                        display_cols = [
                            col for col in display_cols
                            if col in opportunities.columns
                        ]

                        fmt = make_format_dict(opportunities)

                        st.info(
                            "Analysen bruger samme datagrundlag som overblikket. "
                            "Antal pakninger og omsætning er angivet i 1.000."
                        )
                        st.write(top_df.columns.tolist())
                        
                        st.dataframe(
                            opportunities[display_cols].style.format(fmt),
                            use_container_width=True,
                            hide_index=True
                        )

                        analysis_excel = to_excel_bytes(
                            opportunities[display_cols],
                            sheet_name="Analyse"
                        )

                        safe_name = make_safe_name(selected_substances)

                        st.download_button(
                            label="Download analyseresultat",
                            data=analysis_excel,
                            file_name=f"analyse_{safe_name}_{analysis_year}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                st.markdown("## Top opportunities")

with tab_topliste:
    st.subheader("Topliste")

    st.markdown(
        "Toplisten kigger på hele markedet. Først laves en hurtig shortlist uden API, "
        "derefter hentes AIP og konkurrenter kun for shortlisten."
    )

    st.info(
        "Første kørsel kan tage lidt tid, men den bør være langt hurtigere end at hente "
        "AIP og konkurrenter for hele markedet."
    )

    st.markdown("### Indstillinger")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        top_n = st.selectbox(
            "Antal på toplisten",
            [10, 20, 50, 100],
            index=0
        )

    with c2:
        shortlist_n = st.selectbox(
            "Shortlist-størrelse før API",
            [100, 250, 500, 1000],
            index=1
        )

    with c3:
        revenue_year = st.selectbox(
            "Omsætningsår",
            ["2020", "2021", "2022", "2023", "2024", "2025"],
            index=5
        )

    with c4:
        min_revenue_top = st.number_input(
            "Minimum omsætning i valgt år (1.000)",
            min_value=0.0,
            value=0.0,
            step=100.0
        )

    c5, c6, c7 = st.columns(3)

    with c5:
        growth_start_year = st.selectbox(
            "Vækst startår",
            ["2020", "2021", "2022", "2023", "2024"],
            index=0
        )

    with c6:
        possible_end_years = [
            year for year in ["2021", "2022", "2023", "2024", "2025"]
            if int(year) > int(growth_start_year)
        ]

        growth_end_year = st.selectbox(
            "Vækst slutår",
            possible_end_years,
            index=len(possible_end_years) - 1
        )

    with c7:
        growth_metric = st.selectbox(
            "Vækst måles på",
            ["Omsætning", "Antal pakninger"],
            index=0
        )

    comp_col1, comp_col2 = st.columns(2)

    with comp_col1:
        min_competitors_top = st.number_input(
            "Minimum konkurrenter efter API-opslag",
            min_value=0,
            max_value=50,
            value=1,
            step=1
        )

    with comp_col2:
        max_competitors_top = st.number_input(
            "Maksimum konkurrenter efter API-opslag",
            min_value=0,
            max_value=50,
            value=5,
            step=1
        )

    if min_competitors_top > max_competitors_top:
        st.error("Minimum konkurrenter må ikke være større end maksimum konkurrenter.")
        st.stop()

    st.markdown("### Vægte i endelig score")

    w1, w2, w3, w4 = st.columns(4)

    with w1:
        competitor_weight = st.slider("Vægt: lav konkurrence", 0, 100, 35)

    with w2:
        revenue_weight = st.slider("Vægt: omsætning", 0, 100, 30)

    with w3:
        growth_weight = st.slider("Vægt: vækst", 0, 100, 20)

    with w4:
        aip_weight = st.slider("Vægt: AIP", 0, 100, 0)

    if st.button("Lav topliste", key="make_shortlist_toplist"):
        with st.spinner("Bygger markedstabel uden API..."):
            try:
                market_base = build_market_base_result(str(path_obj))
            except Exception as e:
                st.error(f"Kunne ikke bygge markedstabel: {e}")
                market_base = None

        if market_base is not None and not market_base.empty:
            with st.spinner("Finder shortlist uden API..."):
                shortlist, growth_col = build_shortlist_without_api(
                    market_base,
                    shortlist_n=shortlist_n,
                    revenue_year=revenue_year,
                    growth_start_year=growth_start_year,
                    growth_end_year=growth_end_year,
                    growth_metric=growth_metric,
                    min_revenue=min_revenue_top,
                )

            if shortlist.empty:
                st.warning("Shortlisten blev tom. Prøv lavere minimum omsætning.")
            else:
                st.success(f"Shortlist lavet: {len(shortlist)} kandidater.")

                with st.spinner("Henter AIP og konkurrenter for shortlisten..."):
                    enriched_shortlist = enrich_shortlist_with_api(shortlist)

                top_df = build_final_opportunity_score(
                    enriched_shortlist,
                    revenue_year=revenue_year,
                    growth_col=growth_col,
                    competitor_weight=competitor_weight,
                    revenue_weight=revenue_weight,
                    growth_weight=growth_weight,
                    aip_weight=aip_weight,
                    min_competitors=min_competitors_top,
                    max_competitors=max_competitors_top,
                    )

                top_df = top_df.head(top_n).copy()

                if top_df.empty:
                    st.warning("Ingen kandidater matcher de endelige kriterier.")
                else:
                    revenue_col = f"Omsætning {revenue_year}"
                    quantity_col = f"Antal pakninger {revenue_year}"

                    display_cols = [
                        "Rank",
                        "Opportunity Score",
                        "Virksomt stof",
                        "Dosageform",
                        "Styrke",
                        "Pakningstørrelse",
                        quantity_col,
                        "AIP",
                        "Konkurrenter",
                        revenue_col,
                        growth_col,
                        "Shortlist Score",
                        "Score konkurrence",
                        "Score omsætning",
                        "Score vækst",
                        "Score AIP",
                    ]

                    display_cols = [
                        col for col in display_cols
                        if col in top_df.columns
                    ]

                    fmt = make_format_dict(top_df)

                    for col in [
                        "Opportunity Score",
                        "Shortlist Score",
                        "Score konkurrence",
                        "Score omsætning",
                        "Score vækst",
                        "Score AIP",
                        growth_col,
                    ]:
                        if col in top_df.columns:
                            fmt[col] = dk_format_1_decimal

                    st.success(f"Top {len(top_df)} muligheder fundet.")

                    st.dataframe(
                        top_df[display_cols].style.format(fmt),
                        use_container_width=True,
                        hide_index=True
                    )

                    top_excel = to_excel_bytes(
                        top_df[display_cols],
                        sheet_name="Topliste"
                    )

                    st.download_button(
                        label="Download topliste",
                        data=top_excel,
                        file_name=f"top_{top_n}_marked.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
