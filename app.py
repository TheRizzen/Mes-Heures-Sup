import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
import base64
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Mes Heures Sup", page_icon="⏱️")
st.title("⏱️ Suivi des Heures")

# --- CONNEXION MANUELLE ---
@st.cache_resource
def get_connection():
    s = st.secrets["connections"]["gsheets"]
    
    # 1. Décodage de la clé (méthode Base64 pour éviter l'erreur PEM)
    try:
        raw_key = s["private_key"].strip()
        decoded_key = base64.b64decode(raw_key).decode("utf-8")
    except:
        decoded_key = raw_key.replace("\\n", "\n")

    # 2. On construit l'objet de credentials SANS 'type' ni 'spreadsheet'
    # pour éviter l'erreur 'unexpected keyword argument'
    credentials_dict = {
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
    
    # On crée la connexion de manière isolée
    return st.connection("gsheets", type=GSheetsConnection, **credentials_dict)

try:
    conn = get_connection()
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    df_existant = conn.read(spreadsheet=url, ttl=0)
    if df_existant is not None:
        df_existant = df_existant.dropna(how="all")
    else:
        df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])
except Exception as e:
    st.error(f"⚠️ Erreur de connexion : {e}")
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
        # Calcul de base
        start = datetime.combine(d, h1)
        end = datetime.combine(d, h2)
        if end <= start: end += timedelta(days=1)
        duree = (end - start).total_seconds() / 3600
        gain = duree * taux_base * 1.5 # Estimation
        
        nouvelle_ligne = pd.DataFrame([{"Date": str(d), "Heures": float(duree), "Gain": float(gain)}])
        df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
        
        try:
            conn.update(spreadsheet=url, data=df_final)
            st.success("C'est enregistré !")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur update : {e}")

if not df_existant.empty:
    st.divider()
    st.dataframe(df_existant.sort_values('Date', ascending=False), use_container_width=True, hide_index=True)
