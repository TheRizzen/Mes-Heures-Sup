import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Mes Heures Sup", page_icon="⏱️")
st.title("⏱️ Suivi des Heures")

# --- 2. CONNEXION (Méthode Native) ---
# On ne passe aucun argument supplémentaire ici. 
# Streamlit va chercher automatiquement la section [connections.gsheets] dans tes secrets.
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    
    df_existant = conn.read(spreadsheet=url, ttl=0)
    if df_existant is not None:
        df_existant = df_existant.dropna(how="all")
    else:
        df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])
except Exception as e:
    st.error(f"⚠️ Erreur de connexion : {e}")
    df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# --- 3. PARAMÈTRES & FORMULAIRE ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    t_base = st.number_input("Taux horaire base (€)", value=15.0)
    pays = st.selectbox("Pays", ["France", "Belgique", "Suisse"])
    feries = holidays.CountryHoliday(pays)

with st.form("form_saisie", clear_on_submit=True):
    st.subheader("➕ Ajouter une session")
    col1, col2, col3 = st.columns(3)
    d = col1.date_input("Date", datetime.now())
    h1 = col2.time_input("Début", time(18, 0))
    h2 = col3.time_input("Fin", time(22, 0))
    submit = st.form_submit_button("Enregistrer")

if submit:
    start = datetime.combine(d, h1)
    end = datetime.combine(d, h2)
    if end <= start: end += timedelta(days=1)
    h_tot = (end - start).total_seconds() / 3600
    g_tot = round(h_tot * t_base * 1.5, 2)
    
    nouvelle_ligne = pd.DataFrame([{"Date": d.strftime('%Y-%m-%d'), "Heures": float(h_tot), "Gain": float(g_tot)}])
    df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
    
    try:
        conn.update(spreadsheet=url, data=df_final)
        st.success(f"✅ Enregistré : {h_tot}h")
        st.rerun()
    except Exception as e:
        st.error(f"Erreur enregistrement : {e}")

# --- 4. AFFICHAGE ---
if not df_existant.empty:
    st.divider()
    df_tri = df_existant.sort_values('Date', ascending=False)
    st.dataframe(df_tri, use_container_width=True, hide_index=True)
