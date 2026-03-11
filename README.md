# Overblik webapp

Denne projektmappe laver en lille Streamlit-webapp, som:

- læser et Excel-ark med rådata
- bruger `ATC_txt` som virksomt stof
- grupperer data efter `Dosf_LT`, `streng` og `packtext`
- viser antal pakninger og omsætning for 2020-2024
- forsøger at hente AIP og konkurrenter fra medicinpriser.dk
- giver mulighed for at downloade resultatet som Excel

## Forventet Excel-struktur
Filen skal indeholde disse kolonner:

- vnr
- aar
- Sektor
- ATC
- ATC_txt
- Pname
- Dosf_LT
- streng
- packtext
- ApkSum
- volsum
- VolType
- EkspSum
- imp_name
- Tilsk
- Udlev
- regsit

## Filer i projektet

- `app.py` - Streamlit-webappen
- `logic.py` - databehandling og tabelopbygning
- `medicin_api.py` - opslag mod medicinpriser API
- `requirements.txt` - Python-pakker

## Sådan kommer du i gang

1. Opret et virtuelt miljø hvis du vil.
2. Installer afhængigheder:

```bash
pip install -r requirements.txt
```

3. Læg Excel-filen i samme mappe og kald den `data.xlsx`.
   Alternativt kan du skrive en fuld filsti i appens sidebar.

4. Start appen:

```bash
streamlit run app.py
```

5. Åbn linket i browseren.

## Output-kolonner

Appen laver disse kolonner:

- Dosageform
- Styrke
- Pakningstørrelse
- antal pakninger i 2020
- antal pakninger i 2021
- antal pakninger i 2022
- antal pakninger i 2023
- antal pakninger i 2024
- AIP
- konkurrenter
- Omsætning pakningssalg 2020
- Omsætning pakningssalg 2021
- Omsætning pakningssalg 2022
- Omsætning pakningssalg 2023
- Omsætning pakningssalg 2024

## Bemærkninger

- `ATC_txt` bruges som søgefelt for virksomt stof.
- AIP og konkurrenter afhænger af, om match mod medicinpriser lykkes.
- Hvis du oplever langsomme opslag, kan næste trin være at cache API-resultater lokalt.
