from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from logic import build_table_from_excel, clean_data, list_active_substances, load_data

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
    return list_active_substances(path)


@st.cache_data(ttl=3600, show_spinner=False)
def build_result_for_substances(
    path: str,
    selected_substances_tuple: tuple,
    exact_match: bool
) -> pd.DataFrame:
    """
    Bygger én samlet tabel for ét eller flere virksomme stoffer.
    Caches i 1 time, så appen ikke henter API-data unødigt ofte.
    """
    all_results = []

    for substance in selected_substances_tuple:
        df = build_table_from_excel(
            path,
            substance,
            exact_match=exact_match
        )
        df["Virksomt stof"] = substance
        all_results.append(df)

    if not all_results:
        return pd.DataFrame()

    result = pd.concat(all_results, ignore_index=True)

    sort_cols = ["Virksomt stof"]
    ascending = [True]

    if "Antal pakninger 2025" in result.columns:
        sort_cols.append("Antal pakninger 2025")
        ascending.append(False)

    result = result.sort_values(
        sort_cols,
        ascending=ascending,
        na_position="last"
    )

    return result.reset_index(drop=True)


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
        if "Antal" in col or "Omsætning" in col:
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

current_key = (
    str(path_obj),
    tuple(selected_substances),
    exact_match
)

tab_overblik, tab_analyse = st.tabs(["Overblik", "Analyse"])


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
                            tuple(selected_substances),
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

                    analysis_df = result.copy()

                    numeric_candidates = [
                        "konkurrenter",
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

                    mask = analysis_df["konkurrenter"].fillna(0) <= max_competitors

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

                        if "konkurrenter" in opportunities.columns:
                            sort_options.append("konkurrenter")

                        if sort_options:
                            sort_by = st.selectbox(
                                "Sortér analyseresultat efter",
                                sort_options,
                                index=0
                            )

                            ascending = sort_by == "konkurrenter"

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
                            "konkurrenter",
                            revenue_col,
                        ]

                        display_cols = [
                            col for col in display_cols
                            if col in opportunities.columns
                        ]

                        fmt = make_format_dict(opportunities)

                        st.info(
                            "Analysen bruger samme datagrundlag som overblikket. "
                            "Antal pakninger og omsætning er angivet i 1.000."
                        )

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
