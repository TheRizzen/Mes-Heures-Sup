import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
import base64
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Mes Heures Sup", page_icon="⏱️")
st.title("⏱️ Suivi des Heures")

# --- CONNEXION ---
conn = None
df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

try:
    # On récupère les secrets
    s = dict(st.secrets["connections"]["gsheets"])
    
    # DÉCODAGE SÉCURISÉ
    raw_key = s["private_key"].strip()
    try:
        # On essaie de décoder le Base64 (si c'est du base64)
        decoded_key = base64.b64decode(raw_key).decode("utf-8")
    except:
        # Si ce n'est pas du base64, on nettoie juste les \n habituels
        decoded_key = raw_key.replace("\\n", "\n")

    # Reconstruction propre des credentials
    creds = {
        "project_id": s["project_id"],
        "private_key_id": s["private_key_id"],
        "private_key": decoded_key,
        "client_email": s["client_email"],
        "client_id": s["client_id"],
        "auth_uri": s["auth_uri"],
        "token_uri": s["token_uri"],
        "auth_provider_x509_cert_url": s["auth_provider_x509_cert_url"],
        "client_x509_cert_url": s["client_x509_cert_url"]
    }
    
    conn = st.connection("gsheets", type=GSheetsConnection, **creds)
    df_existant = conn.read(spreadsheet=s["spreadsheet"], ttl=0)
    if df_existant is not None:
        df_existant = df_existant.dropna(how="all")
except Exception as e:
    st.error(f"⚠️ Erreur : {e}")

# --- RESTE DU CODE (LOGIQUE & UI) ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    taux_base = st.number_input("Taux horaire", value=15.0)
    feries = holidays.CountryHoliday(st.selectbox("Pays", ["France", "Belgique", "Suisse"]))

with st.form("form_saisie", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    d = col1.date_input("Date", datetime.now())
    h1 = col2.time_input("Début", time(18, 0))
    h2 = col3.time_input("Fin", time(22, 0))
    if st.form_submit_button("Enregistrer"):
        # Calcul (Simplifié pour le test)
        start = datetime.combine(d, h1)
        end = datetime.combine(d, h2)
        if end <= start: end += timedelta(days=1)
        h_tot = (end - start).total_seconds() / 3600
        g_tot = h_tot * taux_base * 1.5 # Majorations par défaut pour le test
        
        nouvelle_ligne = pd.DataFrame([{"Date": d.strftime('%Y-%m-%d'), "Heures": float(h_tot), "Gain": float(g_tot)}])
        df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
        
        try:
            conn.update(spreadsheet=st.secrets["connections"]["gsheets"]["spreadsheet"], data=df_final)
            st.success("Enregistré !")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur update : {e}")

if not df_existant.empty:
    st.divider()
    st.dataframe(df_existant.sort_values('Date', ascending=False), use_container_width=True, hide_index=True)
