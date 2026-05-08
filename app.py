import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
import json
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Mes Heures Sup", page_icon="⏱️")
st.title("⏱️ Suivi des Heures")

# --- CONNEXION ---
@st.cache_resource
def connect_gsheets():
    # On récupère tout le bloc des secrets
    s = dict(st.secrets["connections"]["gsheets"])
    # On nettoie la clé (indispensable)
    s["private_key"] = s["private_key"].replace("\\n", "\n").strip()
    
    # On crée la connexion en passant le dictionnaire directement
    return st.connection("gsheets", type=GSheetsConnection, **s)

try:
    conn = connect_gsheets()
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    df_existant = conn.read(spreadsheet=url, ttl=0)
    if df_existant is not None:
        df_existant = df_existant.dropna(how="all")
    else:
        df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])
except Exception as e:
    st.error(f"⚠️ Erreur : {e}")
    df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# --- INTERFACE ---
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
    # Calcul simple
    start = datetime.combine(d, h1)
    end = datetime.combine(d, h2)
    if end <= start: end += timedelta(days=1)
    h_tot = (end - start).total_seconds() / 3600
    
    # Majorations (Règle standard pour le test)
    g_tot = round(h_tot * t_base * 1.5, 2)
    
    nouvelle_ligne = pd.DataFrame([{"Date": d.strftime('%Y-%m-%d'), "Heures": float(h_tot), "Gain": float(g_tot)}])
    df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
    
    try:
        conn.update(spreadsheet=url, data=df_final)
        st.success(f"✅ Enregistré : {h_tot}h")
        st.rerun()
    except Exception as e:
        st.error(f"Erreur enregistrement : {e}")

if not df_existant.empty:
    st.divider()
    st.dataframe(df_existant.sort_values('Date', ascending=False), use_container_width=True, hide_index=True)
