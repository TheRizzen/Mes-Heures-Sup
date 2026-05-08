import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
import base64
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Mes Heures Sup", page_icon="⏱️")
st.title("⏱️ Suivi des Heures")

# --- CONNEXION BLINDÉE ---
conn = None
try:
    s = dict(st.secrets["connections"]["gsheets"])
    
    # On décode la clé Base64 pour qu'elle soit parfaite en mémoire
    try:
        decoded_key = base64.b64decode(s["private_key"]).decode("utf-8")
    except:
        # Au cas où tu n'as pas encore mis le base64
        decoded_key = s["private_key"].replace("\\n", "\n").strip()

    # On crée les credentials sans le champ 'type' pour éviter l'autre erreur
    creds = {k: v for k, v in s.items() if k not in ["type", "spreadsheet"]}
    creds["private_key"] = decoded_key

    conn = st.connection("gsheets", type=GSheetsConnection, **creds)
    df_existant = conn.read(spreadsheet=s["spreadsheet"], ttl=0)
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
    taux_base = st.number_input("Taux horaire", value=15.0)
    pays = st.selectbox("Pays", ["France", "Belgique", "Suisse"])
    feries = holidays.CountryHoliday(pays)

with st.form("saisie"):
    col1, col2, col3 = st.columns(3)
    d = col1.date_input("Date", datetime.now())
    h1 = col2.time_input("Début", time(18,0))
    h2 = col3.time_input("Fin", time(22,0))
    if st.form_submit_button("Enregistrer"):
        # Calcul simple pour valider
        start = datetime.combine(d, h1)
        end = datetime.combine(d, h2)
        if end <= start: end += timedelta(days=1)
        duree = (end - start).total_seconds() / 3600
        gain = duree * taux_base * 1.5
        
        nouvelle_ligne = pd.DataFrame([{"Date": str(d), "Heures": float(duree), "Gain": float(gain)}])
        df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
        conn.update(spreadsheet=st.secrets["connections"]["gsheets"]["spreadsheet"], data=df_final)
        st.success("C'est enregistré !")
        st.rerun()

if not df_existant.empty:
    st.divider()
    st.dataframe(df_existant.sort_values('Date', ascending=False), use_container_width=True, hide_index=True)
