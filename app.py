import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Mes Heures Sup", page_icon="⏱️")
st.title("⏱️ Suivi des Heures")

# --- 2. CONFIGURATION DU CONTRAT (SIDEBAR) ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    taux_base = st.number_input("Taux horaire de base (€)", value=15.0)
    pays = st.selectbox("Pays", ["France", "Belgique", "Suisse"])
    feries = holidays.CountryHoliday(pays)

# --- 3. INTERFACE DE SAISIE ---
with st.form("form_saisie", clear_on_submit=True):
    st.subheader("➕ Ajouter une session")
    col1, col2, col3 = st.columns(3)
    d = col1.date_input("Date", datetime.now())
    h1 = col2.time_input("Début", time(18, 0))
    h2 = col3.time_input("Fin", time(22, 0))
    submit = st.form_submit_button("Enregistrer")

# --- 4. LOGIQUE DE CALCUL ---
def calculer_gain_reel(date_j, debut, fin, t_base):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    
    est_special = (date_j.weekday() == 6 or date_j in feries)
    gain_total = 0
    current_time = start
    while current_time < end:
        h = current_time.hour
        est_nuit = (h >= 20 or h < 6)
        taux = (2.25 if est_nuit else 1.75) if est_special else (2.0 if est_nuit else 1.50)
        gain_total += 0.25 * (t_base * taux)
        current_time += timedelta(minutes=15)
    return (end - start).total_seconds() / 3600, round(gain_total, 2)

# --- 5. CONNEXION (VÉRIFICATION DES SECRETS) ---
conn = None
df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

try:
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        creds = dict(st.secrets["connections"]["gsheets"])
        if "private_key" in creds:
            creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        
        conn = st.connection("gsheets", **creds)
        df_existant = conn.read(ttl=0)
        if df_existant is not None:
            df_existant = df_existant.dropna(how="all")
    else:
        st.error("❌ Erreur : Les Secrets 'connections.gsheets' sont introuvables dans Streamlit Cloud.")
except Exception as e:
    st.error(f"⚠️ Erreur de connexion : {e}")

# --- 6. ACTION D'ENREGISTREMENT ---
if submit:
    if conn is None:
        st.error("Impossible d'enregistrer : La connexion n'est pas établie.")
    else:
        h_tot, g_tot = calculer_gain_reel(d, h1, h2, taux_base)
        nouvelle_ligne = pd.DataFrame([{"Date": d.strftime('%Y-%m-%d'), "Heures": float(h_tot), "Gain": float(g_tot)}])
        df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
        
        try:
            conn.update(data=df_final)
            st.success("✅ Enregistré !")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur lors de l'envoi vers Google : {e}")

# --- 7. AFFICHAGE DES RÉSULTATS ---
if not df_existant.empty:
    df_existant['Date'] = pd.to_datetime(df_existant['Date'])
    st.divider()
    st.metric("Gain Cumulé", f"{df_existant['Gain'].sum():.2f} €")
    
    tab1, tab2 = st.tabs(["📅 Historique", "📈 Stats"])
    with tab1:
        st.dataframe(df_existant.sort_values('Date', ascending=False), use_container_width=True, hide_index=True)
    with tab2:
        df_m = df_existant.set_index('Date').resample('ME').sum()
        st.bar_chart(df_m['Gain'])
