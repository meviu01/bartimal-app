import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import io
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- KONFIGURACJA ---
NAZWA_ARKUSZA_GOOGLE = 'Produkcja_BartiMal' # Musi być identyczna jak nazwa Twojego pliku na Drive

# Słownik elementów
ELEMENTY = {
    "Przelot": 38,
    "U": 40,
    "Narożna-krótka": 40,
    "Narożna-długa": 30,
    "Start": 30,
    "Ceowniki": 16
}

# --- POŁĄCZENIE Z GOOGLE SHEETS ---
def polacz_z_google():
    # Pobieramy klucz z "Secrets" (to ustawisz na stronie Streamlit)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def wczytaj_dane():
    try:
        client = polacz_z_google()
        sheet = client.open(NAZWA_ARKUSZA_GOOGLE).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        # Zabezpieczenie na wypadek pustego arkusza
        if df.empty:
            return pd.DataFrame(columns=["Data", "Czas", "Nazwa_Pieca", "Element", "Mnoznik", "Ilosc_Wpisana", "Wynik_Sztuki"])
        return df
    except Exception as e:
        # Jeśli arkusz jest pusty lub błąd połączenia
        # st.error(f"Błąd połączenia: {e}") # Do debugowania
        return pd.DataFrame(columns=["Data", "Czas", "Nazwa_Pieca", "Element", "Mnoznik", "Ilosc_Wpisana", "Wynik_Sztuki"])

def zapisz_wiersz_do_google(wiersz_dict):
    client = polacz_z_google()
    sheet = client.open(NAZWA_ARKUSZA_GOOGLE).sheet1
    # Konwersja na listę w odpowiedniej kolejności
    lista_wartosci = [
        wiersz_dict["Data"],
        wiersz_dict["Czas"],
        wiersz_dict["Nazwa_Pieca"],
        wiersz_dict["Element"],
        wiersz_dict["Mnoznik"],
        wiersz_dict["Ilosc_Wpisana"],
        wiersz_dict["Wynik_Sztuki"]
    ]
    sheet.append_row(lista_wartosci)

def znajdz_nastepny_numer_pieca():
    df = wczytaj_dane()
    if df.empty:
        return 1
    
    nazwy = df["Nazwa_Pieca"].unique()
    max_numer = 0
    for nazwa in nazwy:
        dopasowanie = re.search(r"PIEC\s*(\d+)", str(nazwa), re.IGNORECASE)
        if dopasowanie:
            numer = int(dopasowanie.group(1))
            if numer > max_numer:
                max_numer = numer
    
    nastepny = max_numer + 1
    if nastepny > 999: return 1
    return nastepny

# --- INTERFEJS APLIKACJI ---
st.set_page_config(page_title="Kalkulator Produkcji BARTI-MAL", page_icon="🏭")
st.title("🏭 Rejestrator Produkcji (Online)")

tab1, tab2 = st.tabs(["📝 Dodaj Piec / Odpad", "📊 Raporty i Historia"])

with tab1:
    st.subheader("🔥 Nowy piec")
    
    # Uwaga: przy Google Sheets pobieranie danych trwa chwilę, więc robimy to raz
    if 'nastepny_numer' not in st.session_state:
        st.session_state['nastepny_numer'] = znajdz_nastepny_numer_pieca()

    # Przycisk odświeżania numeru (bo dane są online)
    if st.button("🔄 Odśwież numer pieca"):
        st.session_state['nastepny_numer'] = znajdz_nastepny_numer_pieca()
        st.rerun()

    domyslna_nazwa = f"PIEC {st.session_state['nastepny_numer']}"

    with st.form("formularz_produkcji", clear_on_submit=True):
        col_piec, col_info = st.columns([2, 1])
        with col_piec:
            nazwa_pieca = st.text_input("Nazwa wsadu", value=domyslna_nazwa)
        with col_info:
            st.info(f"Automat: {st.session_state['nastepny_numer']}")
        
        st.write("Podaj ilości:")
        wartosci_wpisane = {}
        for nazwa, mnoznik in ELEMENTY.items():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{nazwa}** (x{mnoznik})")
            with col2:
                wartosci_wpisane[nazwa] = st.number_input(f"Ilość {nazwa}", min_value=0, step=1, label_visibility="collapsed", key=f"prod_{nazwa}")

        st.write("---")
        przycisk_zapisz = st.form_submit_button("ZAPISZ NOWY PIEC", type="primary")

        if przycisk_zapisz:
            teraz = datetime.now()
            jest_wpis = False
            
            with st.spinner("Zapisuję w chmurze Google..."):
                for nazwa, ilosc in wartosci_wpisane.items():
                    if ilosc > 0:
                        jest_wpis = True
                        wynik = ilosc * ELEMENTY[nazwa]
                        dane = {
                            "Data": teraz.strftime("%Y-%m-%d"),
                            "Czas": teraz.strftime("%H:%M"),
                            "Nazwa_Pieca": nazwa_pieca,
                            "Element": nazwa,
                            "Mnoznik": ELEMENTY[nazwa],
                            "Ilosc_Wpisana": ilosc,
                            "Wynik_Sztuki": wynik
                        }
                        zapisz_wiersz_do_google(dane)
            
            if jest_wpis:
                st.success(f"Zapisano: {nazwa_pieca}!")
                # Aktualizuj numer na przyszłość
                st.session_state['nastepny_numer'] = znajdz_nastepny_numer_pieca()
                # Nie robimy rerun automatycznie żeby user widział komunikat sukcesu
            else:
                st.warning("Wpisz ilość chociaż jednego elementu.")

    st.markdown("---")
    
    with st.expander("🗑️ ZGŁOŚ ODPAD / BRAKI", expanded=False):
        with st.form("formularz_odpadow", clear_on_submit=True):
            wartosci_odpad = {}
            for nazwa, mnoznik in ELEMENTY.items():
                col_o1, col_o2 = st.columns([3, 1])
                with col_o1:
                    st.markdown(f"🚫 Odpad: **{nazwa}**")
                with col_o2:
                    wartosci_odpad[nazwa] = st.number_input(f"Odpad {nazwa}", min_value=0, step=1, label_visibility="collapsed", key=f"odpad_{nazwa}")
            
            st.write("---")
            btn_odpad = st.form_submit_button("ZAPISZ ODPADY")
            
            if btn_odpad:
                teraz = datetime.now()
                jest_odpad = False
                with st.spinner("Zapisuję odpady..."):
                    for nazwa, ilosc in wartosci_odpad.items():
                        if ilosc > 0:
                            jest_odpad = True
                            wynik = ilosc * ELEMENTY[nazwa] 
                            dane = {
                                "Data": teraz.strftime("%Y-%m-%d"),
                                "Czas": teraz.strftime("%H:%M"),
                                "Nazwa_Pieca": "ODPAD",
                                "Element": nazwa,
                                "Mnoznik": ELEMENTY[nazwa],
                                "Ilosc_Wpisana": ilosc,
                                "Wynik_Sztuki": wynik
                            }
                            zapisz_wiersz_do_google(dane)
                
                if jest_odpad:
                    st.error(f"Zapisano odpady w bazie!")
                else:
                    st.warning("Nie wpisano żadnych braków.")

with tab2:
    st.subheader("Podsumowanie Produkcji Barti-Mal")
    
    # Przycisk odświeżania danych
    if st.button("🔄 Pobierz najnowsze dane z chmury"):
        st.rerun()

    df = wczytaj_dane()
    
    if not df.empty:
        df["Data"] = pd.to_datetime(df["Data"])
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            dni_wstecz = st.number_input("Ile dni wstecz analizować?", min_value=1, value=14)
        
        data_graniczna = datetime.now() - timedelta(days=dni_wstecz)
        df_filtered = df[df["Data"] >= data_graniczna]
        
        st.info(f"Dane od: {data_graniczna.strftime('%Y-%m-%d')}")
        
        df_prod = df_filtered[df_filtered["Nazwa_Pieca"] != "ODPAD"]
        df_waste = df_filtered[df_filtered["Nazwa_Pieca"] == "ODPAD"]

        st.markdown("### ✅ Nowy piec (Gotowe)")
        if not df_prod.empty:
            tabela_prod = df_prod.groupby("Element")["Wynik_Sztuki"].sum().reset_index()
            tabela_prod = tabela_prod.sort_values("Wynik_Sztuki", ascending=False)
            st.dataframe(tabela_prod, use_container_width=True, hide_index=True)
        else:
            st.write("Brak wsadów w wybranym okresie.")

        st.markdown("### 🚫 Zgłoszone Odpady / Braki")
        if not df_waste.empty:
            tabela_waste = df_waste.groupby("Element")[["Ilosc_Wpisana", "Wynik_Sztuki"]].sum().reset_index()
            tabela_waste.columns = ["Element", "Zmarnowane (szt)", "Strata (przeliczona)"]
            st.dataframe(tabela_waste, use_container_width=True, hide_index=True)
        else:
            st.success("Brak odpadów.")
        
        st.divider()
        with st.expander("📂 Pełna historia wpisów (Excel)"):
            st.dataframe(df_filtered.sort_values(by=["Data", "Czas"], ascending=False), use_container_width=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_filtered.to_excel(writer, index=False, sheet_name='Raport Produkcji')
            download_data = buffer.getvalue()
            
            st.download_button(
                label="📥 Pobierz raport do Excela (.xlsx)",
                data=download_data,
                file_name=f"raport_produkcja_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key='download-xlsx'
            )
    else:
        st.info("Brak danych w bazie.")

# --- STOPKA ---
st.write("")
st.write("---")
st.markdown(
    """
    <div style="text-align: center; color: #888888; font-size: 12px;">
        Program zrobiony przez <b>DROP-IT Mateusz Gruber</b>
    </div>
    """,
    unsafe_allow_html=True
)