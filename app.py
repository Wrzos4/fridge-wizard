import streamlit as st
from google import genai
from google.genai import types
import json
import datetime
import os
from streamlit_mic_recorder import speech_to_text

# Konfiguracja strony musi być pierwszym wywołaniem st.*
st.set_page_config(page_title="AI Szef Kuchni", page_icon="🍳", layout="centered")

# Wstrzykiwanie własnego CSS dla tła i kontenera
st.markdown("""
<style>
.stApp {
    background: linear-gradient(180deg, #1B5E20 0%, #A5D6A7 100%);
    background-attachment: fixed;
}
.block-container {
    background-color: rgba(255, 255, 255, 0.95);
    padding: 2rem;
    border-radius: 15px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
}
</style>
""", unsafe_allow_html=True)

# Konfiguracja klienta
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# Limity tokenów (konfigurowalne przez secrets.toml)
LIMIT_SESJA  = int(st.secrets.get("LIMIT_TOKENOW_SESJA", 30000))   # per użytkownik / sesja
LIMIT_DZIENNY = int(st.secrets.get("LIMIT_TOKENOW_DZIEN", 300000))  # globalny dzienny

# ── Globalny licznik dzienny (plik JSON) ──────────────────────────────────────
COUNTER_FILE = os.path.join(os.path.dirname(__file__), "token_counter.json")

def wczytaj_licznik_dzienny() -> int:
    """Zwraca liczbę tokenów zużytych dzisiaj globalnie."""
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, "r") as f:
                data = json.load(f)
            if data.get("data") == str(datetime.date.today()):
                return int(data.get("tokeny", 0))
    except Exception:
        pass
    return 0

def zapisz_licznik_dzienny(tokeny: int):
    """Zapisuje aktualny globalny licznik tokenów na dziś."""
    try:
        with open(COUNTER_FILE, "w") as f:
            json.dump({"data": str(datetime.date.today()), "tokeny": tokeny}, f)
    except Exception:
        pass

def dodaj_tokeny(ile: int):
    """Dolicza zużyte tokeny do sesji i globalnego licznika."""
    st.session_state["tokeny_sesja"] += ile
    nowy_stan = wczytaj_licznik_dzienny() + ile
    zapisz_licznik_dzienny(nowy_stan)

def sprawdz_limity() -> bool:
    """
    Zwraca True jeśli można wysłać zapytanie.
    Wyświetla błąd i zwraca False jeśli limit przekroczony.
    """
    if st.session_state["tokeny_sesja"] >= LIMIT_SESJA:
        st.error(
            f"🚫 Osiągnąłeś limit **{LIMIT_SESJA:,} tokenów** na tę sesję. "
            "Odśwież stronę, aby rozpocząć nową."
        )
        return False
    if wczytaj_licznik_dzienny() >= LIMIT_DZIENNY:
        st.error(
            f"🚫 Aplikacja osiągnęła dzienny limit **{LIMIT_DZIENNY:,} tokenów**. "
            "Wróć jutro!"
        )
        return False
    return True

# ── Inicjalizacja stanu aplikacji ─────────────────────────────────────────────
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
if "tokeny_sesja" not in st.session_state:
    st.session_state["tokeny_sesja"] = 0

# ── Nagłówek ──────────────────────────────────────────────────────────────────
st.title("AI Szef Kuchni")
st.write("Podaj składniki i preferencje, a wygenerujemy dla Ciebie idealny przepis!")

# Pasek zużycia tokenów w sidebarze
with st.sidebar:
    st.markdown("### 📊 Zużycie tokenów")
    tokeny_sesja = st.session_state["tokeny_sesja"]
    tokeny_dzien = wczytaj_licznik_dzienny()

    st.progress(min(tokeny_sesja / LIMIT_SESJA, 1.0), text=f"Sesja: {tokeny_sesja:,} / {LIMIT_SESJA:,}")
    st.progress(min(tokeny_dzien / LIMIT_DZIENNY, 1.0), text=f"Dziś (globalnie): {tokeny_dzien:,} / {LIMIT_DZIENNY:,}")

# ── Wejście głosowe ───────────────────────────────────────────────────────────
text_glosowy = speech_to_text(
    start_prompt="🎤 Włącz mikrofon",
    stop_prompt="🛑 Zatrzymaj i dodaj",
    language="pl",
    key="mikrofon"
)

if text_glosowy and text_glosowy != st.session_state["last_audio"]:
    if st.session_state["lodowka_tekst"]:
        st.session_state["lodowka_tekst"] += ", " + text_glosowy
    else:
        st.session_state["lodowka_tekst"] = text_glosowy
    st.session_state["last_audio"] = text_glosowy

# ── Zdjęcie lodówki ───────────────────────────────────────────────────────────
zdjecie = st.file_uploader("📷 Wgraj zdjęcie lodówki lub składników", type=["png", "jpg", "jpeg"])

if zdjecie is not None:
    photo_hash = hash(zdjecie.getvalue())
    if photo_hash != st.session_state["last_photo_hash"]:
        if sprawdz_limity():
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
                    uzycie = getattr(response.usage_metadata, "total_token_count", 0) or 0
                    dodaj_tokeny(uzycie)

                    if st.session_state["lodowka_tekst"]:
                        st.session_state["lodowka_tekst"] += ", " + skladniki_ze_zdjecia
                    else:
                        st.session_state["lodowka_tekst"] = skladniki_ze_zdjecia
                    st.session_state["last_photo_hash"] = photo_hash
                    st.success(f"Rozpoznano: {skladniki_ze_zdjecia}")
                except Exception as e:
                    st.error(f"Nie udało się przeanalizować zdjęcia: {e}")

# ── Formularz ─────────────────────────────────────────────────────────────────
fridge_contents = st.text_area("🛒 Zawartość lodówki (co masz do dyspozycji?)", value=st.session_state["lodowka_tekst"])
st.session_state["lodowka_tekst"] = fridge_contents

cravings  = st.text_input("✨ Na co masz ochotę? (np. kuchnia azjatycka, coś na szybko)")
allergies = st.text_input("⚠️ Alergie i wykluczenia (czego unikać?)")
portions  = st.number_input("🍽️ Liczba porcji", min_value=1, max_value=10, value=2)

generate_btn = st.button("Wygeneruj przepis")

# ── Generowanie przepisu ──────────────────────────────────────────────────────
if generate_btn or st.session_state.get("pomin_brak"):
    if sprawdz_limity():
        with st.spinner("Szef kuchni obmyśla idealny przepis..."):

            if st.session_state.get("pomin_brak"):
                zasada = """ZASADA: Użytkownik chce zrobić danie mimo braku składnika. Zignoruj brak i stwórz przepis z użyciem kreatywnych zamienników. Zwróć JSON ze statusem 'sukces': {"status": "sukces", "tytul": "...", "opis": "...", "kalorie": "...", "bialko": "...", "weglowodany": "...", "tluszcze": "...", "czas_przygotowania": "...", "czas_gotowania": "...", "skladniki": ["..."], "kroki": ["..."], "wskazowki": "..."}. Oszacuj wartości kalorie, bialko, weglowodany i tluszcze na JEDNĄ porcję i dodaj do nich jednostki (np. "450 kcal", "30 g"). Nie dodawaj znaczników markdown ```json."""
            else:
                zasada = """ZASADA: Jeśli brakuje absolutnie niezbędnego składnika do spełnienia zachcianki, zwróć CZYSTY JSON: {"status": "brak", "brakujacy_skladnik": "nazwa"}. Jeśli można gotować, zwróć CZYSTY JSON: {"status": "sukces", "tytul": "...", "opis": "...", "kalorie": "...", "bialko": "...", "weglowodany": "...", "tluszcze": "...", "czas_przygotowania": "...", "czas_gotowania": "...", "skladniki": ["..."], "kroki": ["..."], "wskazowki": "..."}. Oszacuj wartości kalorie, bialko, weglowodany i tluszcze na JEDNĄ porcję i dodaj do nich jednostki (np. "450 kcal", "30 g"). Nie dodawaj znaczników markdown ```json."""

            poprzednie = st.session_state["poprzednie_przepisy"]
            zakaz = f" Nie proponuj żadnego z tych dań, które już zostały wygenerowane: {', '.join(poprzednie)}." if poprzednie else ""
            prompt = f"Jesteś ekspertem kulinarnym. Składniki: {fridge_contents}. Zachcianka: {cravings}. Alergie: {allergies}. Porcje: {portions}.{zakaz} {zasada}"

            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )

                uzycie = getattr(response.usage_metadata, "total_token_count", 0) or 0
                dodaj_tokeny(uzycie)

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

# ── Wyświetlanie wyników ──────────────────────────────────────────────────────
if st.session_state.get("wynik"):
    result = st.session_state["wynik"]

    st.divider()

    if result.get("status") == "sukces":
        st.header(result.get("tytul", "Twój przepis"))
        st.write(f"*{result.get('opis', '')}*")

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

        st.button("🔄 Nie smakuje mi — wygeneruj inny przepis!", on_click=nowy_przepis)

    elif result.get("status") == "brak":
        brakujacy = result.get("brakujacy_skladnik", "nieznany składnik")
        st.warning(f"Zaraz, zaraz! Do tej zachcianki brakuje nam kluczowego składnika: **{brakujacy}**.")

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
