import streamlit as st
from google import genai
from google.genai import types
import json
from streamlit_mic_recorder import speech_to_text

# Konfiguracja strony musi być pierwszym wywołaniem st.*
st.set_page_config(page_title="AI Szef Kuchni", page_icon="🍳", layout="centered")

# Wstrzykiwanie własnego CSS dla tła i kontenera
st.markdown("""
<style>
.stApp {
    /* Gradient od ciemnej zieleni na górze do jasnej na dole */
    background: linear-gradient(180deg, #1B5E20 0%, #A5D6A7 100%);
    background-attachment: fixed;
}

/* Upewniamy się, że nasze "okno" z aplikacją jest czytelne */
.block-container {
    background-color: rgba(255, 255, 255, 0.95);
    padding: 2rem;
    border-radius: 15px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
}
</style>
""", unsafe_allow_html=True)

# Konfiguracja klienta nowej biblioteki google-genai
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

st.title("AI Szef Kuchni")
st.write("Podaj składniki i preferencje, a wygenerujemy dla Ciebie idealny przepis!")

# Inicjalizacja stanu aplikacji
if "lodowka_tekst" not in st.session_state:
    st.session_state["lodowka_tekst"] = ""
if "wynik" not in st.session_state:
    st.session_state["wynik"] = None
if "pomin_brak" not in st.session_state:
    st.session_state["pomin_brak"] = False
if "last_audio" not in st.session_state:
    st.session_state["last_audio"] = ""
if "poprzednie_przepisy" not in st.session_state:
    st.session_state["poprzednie_przepisy"] = []
if "last_photo_hash" not in st.session_state:
    st.session_state["last_photo_hash"] = None

# Przycisk mikrofonu
text_glosowy = speech_to_text(
    start_prompt="🎤 Włącz mikrofon",
    stop_prompt="🛑 Zatrzymaj i dodaj",
    language="pl",
    key="mikrofon"
)

# Jeśli dyktowanie się powiodło i nie jest to samo zduplikowane nagranie przy przeładowaniu
if text_glosowy and text_glosowy != st.session_state["last_audio"]:
    if st.session_state["lodowka_tekst"]:
        st.session_state["lodowka_tekst"] += ", " + text_glosowy
    else:
        st.session_state["lodowka_tekst"] = text_glosowy
    st.session_state["last_audio"] = text_glosowy

# Zdjęcie lodówki
zdjecie = st.file_uploader("📷 Wgraj zdjęcie lodówki lub składników", type=["png", "jpg", "jpeg"])

if zdjecie is not None:
    photo_hash = hash(zdjecie.getvalue())
    if photo_hash != st.session_state["last_photo_hash"]:
        with st.spinner("Analizuję zdjęcie wnętrza lodówki..."):
            try:
                obraz_bytes = zdjecie.getvalue()
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Part.from_bytes(data=obraz_bytes, mime_type=zdjecie.type),
                        types.Part.from_text(text="Przeanalizuj to zdjęcie i wypisz wszystkie widoczne na nim składniki spożywcze. Zwróć TYLKO nazwy składników po polsku, oddzielone przecinkami, bez żadnego dodatkowego tekstu ani wstępu.")
                    ]
                )
                skladniki_ze_zdjecia = response.text.strip()
                if st.session_state["lodowka_tekst"]:
                    st.session_state["lodowka_tekst"] += ", " + skladniki_ze_zdjecia
                else:
                    st.session_state["lodowka_tekst"] = skladniki_ze_zdjecia
                st.session_state["last_photo_hash"] = photo_hash
                st.success(f"Rozpoznano: {skladniki_ze_zdjecia}")
            except Exception as e:
                st.error(f"Nie udało się przeanalizować zdjęcia: {e}")

# Przypisujemy aktualny stan jako domyślną wartość (value)
fridge_contents = st.text_area("🛒 Zawartość lodówki (co masz do dyspozycji?)", value=st.session_state["lodowka_tekst"])

# Uaktualniamy stan w przypadku, gdy użytkownik dopisze coś ręcznie z klawiatury
st.session_state["lodowka_tekst"] = fridge_contents

cravings = st.text_input("✨ Na co masz ochotę? (np. kuchnia azjatycka, coś na szybko)")
allergies = st.text_input("⚠️ Alergie i wykluczenia (czego unikać?)")
portions = st.number_input("🍽️ Liczba porcji", min_value=1, max_value=10, value=2)

generate_btn = st.button("Wygeneruj przepis")

# Generowanie uruchamia się po kliknięciu głównego przycisku, lub z automatu gdy stan to wymusza
if generate_btn or st.session_state.get("pomin_brak"):
    with st.spinner("Szef kuchni obmyśla idealny przepis..."):
        
        # Sprawdzamy czy użytkownik chce pominąć braki składników
        if st.session_state.get("pomin_brak"):
            zasada = """ZASADA: Użytkownik chce zrobić danie mimo braku składnika. Zignoruj brak i stwórz przepis z użyciem kreatywnych zamienników. Zwróć JSON ze statusem 'sukces': {"status": "sukces", "tytul": "...", "opis": "...", "kalorie": "...", "bialko": "...", "weglowodany": "...", "tluszcze": "...", "czas_przygotowania": "...", "czas_gotowania": "...", "skladniki": ["..."], "kroki": ["..."], "wskazowki": "..."}. Oszacuj wartości kalorie, bialko, weglowodany i tluszcze na JEDNĄ porcję i dodaj do nich jednostki (np. "450 kcal", "30 g"). Nie dodawaj znaczników markdown ```json."""
        else:
            zasada = """ZASADA: Jeśli brakuje absolutnie niezbędnego składnika do spełnienia zachcianki, zwróć CZYSTY JSON: {"status": "brak", "brakujacy_skladnik": "nazwa"}. Jeśli można gotować, zwróć CZYSTY JSON: {"status": "sukces", "tytul": "...", "opis": "...", "kalorie": "...", "bialko": "...", "weglowodany": "...", "tluszcze": "...", "czas_przygotowania": "...", "czas_gotowania": "...", "skladniki": ["..."], "kroki": ["..."], "wskazowki": "..."}. Oszacuj wartości kalorie, bialko, weglowodany i tluszcze na JEDNĄ porcję i dodaj do nich jednostki (np. "450 kcal", "30 g"). Nie dodawaj znaczników markdown ```json."""

        poprzednie = st.session_state["poprzednie_przepisy"]
        zakaz = f" Nie proponuj żadnego z tych dań, które już zostały wygenerowane: {', '.join(poprzednie)}." if poprzednie else ""
        prompt = f"Jesteś ekspertem kulinarnym. Składniki: {fridge_contents}. Zachcianka: {cravings}. Alergie: {allergies}. Porcje: {portions}.{zakaz} {zasada}"
        
        try:
            # Wysłanie zapytania do modelu
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
                
            result = json.loads(text.strip())
            st.session_state["wynik"] = result
            if result.get("status") == "sukces" and result.get("tytul"):
                st.session_state["poprzednie_przepisy"].append(result["tytul"])

            st.session_state["pomin_brak"] = False
            
        except json.JSONDecodeError:
            st.error("Model zwrócił nieprawidłową odpowiedź. Spróbuj ponownie.")
            st.session_state["pomin_brak"] = False
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err:
                st.error("Przekroczono limit zapytań do AI. Poczekaj chwilę i spróbuj ponownie.")
            elif "503" in err or "unavailable" in err:
                st.error("Serwer AI jest chwilowo niedostępny. Spróbuj za kilka sekund.")
            elif "api_key" in err or "401" in err or "403" in err:
                st.error("Błąd autoryzacji — sprawdź klucz API w pliku secrets.toml.")
            else:
                st.error(f"Wystąpił nieoczekiwany błąd: {e}")
            st.session_state["pomin_brak"] = False

# Wyświetlanie wyników
if st.session_state.get("wynik"):
    result = st.session_state["wynik"]
    
    st.divider() # Subtelna linia przed sekcją wynikową
    
    if result.get("status") == "sukces":
        st.header(result.get("tytul", "Twój przepis"))
        st.write(f"*{result.get('opis', '')}*")
        
        # Wyświetlanie wartości odżywczych (makro i kalorie) używając st.metric w kontenerze
        with st.container():
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(label="Kalorie", value=result.get("kalorie", "Brak"))
            with col2:
                st.metric(label="Białko", value=result.get("bialko", "Brak"))
            with col3:
                st.metric(label="Węglowodany", value=result.get("weglowodany", "Brak"))
            with col4:
                st.metric(label="Tłuszcze", value=result.get("tluszcze", "Brak"))
            
        st.write("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Czas przygotowania:** {result.get('czas_przygotowania', '')}")
        with col2:
            st.markdown(f"**Czas gotowania:** {result.get('czas_gotowania', '')}")
            
        st.subheader("Składniki")
        for sk in result.get("skladniki", []):
            st.markdown(f"- {sk}")
            
        st.subheader("Kroki")
        for i, krok in enumerate(result.get("kroki", []), 1):
            st.markdown(f"**Krok {i}:** {krok}")
            
        if result.get("wskazowki"):
            st.info(f"💡 **Wskazówka:** {result.get('wskazowki')}")

        st.divider()

        def nowy_przepis():
            st.session_state["wynik"] = None
            st.session_state["pomin_brak"] = False
            # historia zostaje — model dostanie listę już wygenerowanych dań

        st.button("🔄 Nie smakuje mi — wygeneruj inny przepis!", on_click=nowy_przepis)
            
    elif result.get("status") == "brak":
        brakujacy = result.get("brakujacy_skladnik", "nieznany składnik")
        st.warning(f"Zaraz, zaraz! Do tej zachcianki brakuje nam kluczowego składnika: **{brakujacy}**.")
        
        # Funkcje Callback dla przycisków
        def add_ingredient():
            if st.session_state["lodowka_tekst"]:
                st.session_state["lodowka_tekst"] += f", {brakujacy}"
            else:
                st.session_state["lodowka_tekst"] = brakujacy
            st.session_state["wynik"] = None

        def skip_ingredient():
            st.session_state["pomin_brak"] = True
            
        col1, col2 = st.columns(2)
        with col1:
            st.button(f"Idę do sklepu po: {brakujacy}", on_click=add_ingredient)
                
        with col2:
            st.button("Zróbmy inną wersję", on_click=skip_ingredient)
