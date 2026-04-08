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



def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Overblik")
    return output.getvalue()


with st.sidebar:
    st.header("Indstillinger")
    data_path = st.text_input("Sti til Excel-fil", value=DEFAULT_DATA_FILE)
    exact_match = st.checkbox("Præcist match på ATC_txt", value=True)
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

if st.button("Generér tabel", type="primary"):
    with st.spinner("Bygger tabel..."):
        try:
            if selected_substances:
                all_results = []

                for substance in selected_substances:
                    df = build_table_from_excel(str(path_obj), substance)
                    df["Virksomt stof"] = substance 
                    all_results.append(df)
                result = pd.concat(all_results, ignore_index = True)

                result = result.sort_values(
                    ["Virksomt stof", "Antal pakninger 2025"],
                    ascending=[True, False]
                )
        except Exception as e:
            st.error(f"Fejl under generering: {e}")
        else:
            if result.empty:
                st.warning("Ingen data fundet for det valgte virksomt stof.")
            else:
                st.success(f"Fandt {len(result)} rækker.")
                def dk_format_1_decimal(x):
                    if pd.isna(x):
                        return ""
                    return f"{x:.1f}".replace(".", ",")

                def dk_format_2_decimal(x):
                    if pd.isna(x):
                        return ""
                    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                fmt = {}
                for col in result.columns:
                    if "Antal" in col or "Omsætning" in col:
                        fmt[col] = dk_format_1_decimal
                    elif col == "AIP":
                        fmt[col] = dk_format_2_decimal

                st.dataframe(
                    result.style.format(fmt),
                    use_container_width=True,
                    hide_index=True
                )

                excel_bytes = to_excel_bytes(result)
                safe_name = "_".join(selected_substances).replace("/", "-").replace(" ", "_")
                st.download_button(
                    label="Download Excel",
                    data=excel_bytes,
                    file_name=f"overblik_{safe_name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
