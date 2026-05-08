import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Suivi Heures Sup", page_icon="⏱️", layout="wide")

# --- 2. CONNEXION ---
@st.cache_resource
def connect_gsheets():
    return st.connection("gsheets", type=GSheetsConnection)

try:
    conn = connect_gsheets()
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    df_raw = conn.read(spreadsheet=url, ttl=0)
    if df_raw is not None:
        df_raw = df_raw.dropna(how="all")
        df_raw['Date'] = pd.to_datetime(df_raw['Date'])
    else:
        df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain"])
except Exception as e:
    st.error(f"⚠️ Erreur de connexion : {e}")
    df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# --- 3. LOGIQUE DE CALCUL ---
def calculer_gain(date_j, debut, fin, t_base, feries):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    
    gain_total = 0
    current = start
    while current < end:
        est_special = (current.weekday() == 6 or current.date() in feries)
        h = current.hour
        est_nuit = (h >= 20 or h < 6)
        
        if est_special:
            taux = 2.25 if est_nuit else 1.75
        else:
            taux = 2.00 if est_nuit else 1.50
            
        gain_total += (15 / 60) * (t_base * taux)
        current += timedelta(minutes=15)
        
    return round((end - start).total_seconds() / 3600, 2), round(gain_total, 2)

# --- 4. INTERFACE ---
with st.sidebar:
    st.title("⏱️ Menu")
    t_base = st.number_input("Taux horaire (€)", value=15.0)
    pays = st.selectbox("Jours fériés", ["France", "Belgique", "Suisse"])
    feries_liste = holidays.CountryHoliday(pays)
    mode = st.radio("Navigation", ["Saisie", "Gestion", "Récapitulatif Détaillé"])

# --- MODE : SAISIE ---
if mode == "Saisie":
    st.header("➕ Ajouter des Heures")
    with st.form("f_saisie", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        d = col1.date_input("Date", datetime.now())
        h1 = col2.time_input("Début", time(18, 0))
        h2 = col3.time_input("Fin", time(22, 0))
        if st.form_submit_button("Enregistrer"):
            h_tot, g_tot = calculer_gain(d, h1, h2, t_base, feries_liste)
            new_data = pd.DataFrame([{"Date": pd.to_datetime(d), "Heures": h_tot, "Gain": g_tot}])
            conn.update(spreadsheet=url, data=pd.concat([df_raw, new_data], ignore_index=True))
            st.success("Validé !")
            st.rerun()

# --- MODE : GESTION ---
elif mode == "Gestion":
    st.header("⚙️ Modifier / Supprimer")
    if not df_raw.empty:
        edited = st.data_editor(df_raw, num_rows="dynamic", use_container_width=True)
        if st.button("Sauvegarder les changements"):
            conn.update(spreadsheet=url, data=edited)
            st.success("Mise à jour réussie")
            st.rerun()

# --- MODE : RÉCAPITULATIF DÉTAILLÉ (NOUVEAU) ---
elif mode == "Récapitulatif Détaillé":
    st.header("📊 Analyse des revenus")
    
    if not df_raw.empty:
        # Préparation des données temporelles
        df = df_raw.copy()
        df['Année'] = df['Date'].dt.year
        df['Mois_Num'] = df['Date'].dt.month
        df['Mois_Nom'] = df['Date'].dt.strftime('%B')
        df['Semaine'] = df['Date'].dt.isocalendar().week
        df['Jour_Nom'] = df['Date'].dt.strftime('%A %d')

        # --- FILTRES HIÉRARCHIQUES ---
        col1, col2 = st.columns(2)
        
        with col1:
            annees = sorted(df['Année'].unique(), reverse=True)
            sel_annee = st.selectbox("📅 Choisir l'année", annees)
            df_annee = df[df['
