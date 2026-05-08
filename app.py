import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
import json
import os
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Mes Heures Sup", page_icon="⏱️")
st.title("⏱️ Suivi des Heures")

# --- CONNEXION VIA FICHIER TEMPORAIRE ---
@st.cache_resource
def initialiser_connexion():
    # 1. On récupère les secrets
    s = st.secrets["connections"]["gsheets"]
    
    # 2. On crée un dictionnaire propre au format Google
    # On nettoie la clé au passage
    google_dict = {
        "type": "service_account",
        "project_id": s["project_id"],
        "private_key_id": s["private_key_id"],
        "private_key": s["private_key"].replace("\\n", "\n").strip(),
        "client_email": s["client_email"],
        "client_id": s["client_id"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": s["client_x509_cert_url"]
    }
    
    # 3. On écrit ce dictionnaire dans un fichier temporaire
    with open("google_creds.json", "w") as f:
        json.dump(google_dict, f)
    
    # 4. On connecte Streamlit en pointant vers ce fichier
    return st.connection("gsheets", type=GSheetsConnection, credentials="google_creds.json")

try:
    conn = initialiser_connexion()
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    df_existant = conn.read(spreadsheet=url, ttl=0)
    if df_existant is not None:
        df_existant = df_existant.dropna(how="all")
    else:
        df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])
except Exception as e:
    st.error(f"⚠️ Erreur de connexion : {e}")
    df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# --- INTERFACE ET LOGIQUE ---
# (Le reste du code reste identique pour la saisie et les calculs)
with st.sidebar:
    st.header("⚙️ Paramètres")
    t_base = st.number_input("Taux horaire", value=15.0)
    feries = holidays.CountryHoliday(st.selectbox("Pays", ["France", "Belgique", "Suisse"]))

with st.form("saisie"):
    col1, col2, col3 = st.columns(3)
    d = col1.date_input("Date", datetime.now())
    h1 = col2.time_input("Début", time(18,0))
    h2 = col3.time_input("Fin", time(22,0))
    if st.form_submit_button("Enregistrer"):
        # Calcul rapide
        diff = datetime.combine(d, h2) - datetime.combine(d, h1)
        h_tot = diff.total_seconds() / 3600
        if h_tot < 0: h_tot += 24
        
        nouvelle_ligne = pd.DataFrame([{"Date": str(d), "Heures": h_tot, "Gain": h_tot * t_base * 1.5}])
        df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
        conn.update(spreadsheet=url, data=df_final)
        st.success("Enregistré !")
        st.rerun()

if not df_existant.empty:
    st.divider()
    st.dataframe(df_existant.sort_values('Date', ascending=False), use_container_width=True, hide_index=True)
