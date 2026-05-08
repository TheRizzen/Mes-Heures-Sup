import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURATION DE L'INTERFACE ---
st.set_page_config(
    page_title="Mes Heures Sup", 
    page_icon="⏱️", 
    layout="centered"
)

st.title("⏱️ Suivi des Heures Supplémentaires")

# --- 2. PRÉPARATION DE LA CONNEXION (CORRECTIF) ---
# Au lieu de modifier st.secrets, on crée une configuration propre pour la connexion
conf_gsheets = dict(st.secrets["connections"]["gsheets"])
if "private_key" in conf_gsheets:
    conf_gsheets["private_key"] = conf_gsheets["private_key"].replace("\\n", "\n")

# Connexion en utilisant notre configuration nettoyée
conn = st.connection("gsheets", type=GSheetsConnection, **conf_gsheets)

# --- 3. LECTURE DES DONNÉES ---
try:
    df_existant = conn.read(ttl=0)
    df_existant = df_existant.dropna(how="all")
except Exception:
    df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# --- 4. CONFIGURATION DU CONTRAT ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    taux_base = st.number_input("Taux horaire de base (€)", value=15.0)
    pays = st.selectbox("Pays (Jours fériés)", ["France", "Belgique", "Suisse"])
    feries = holidays.CountryHoliday(pays)

# --- 5. LOGIQUE DE CALCUL ---
def calculer_gain_reel(date_j, debut, fin, t_base):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start:
        end += timedelta(days=1)
    
    est_special = (date_j.weekday() == 6 or date_j in feries)
    gain_total = 0
    current_time = start
    while current_time < end:
        h = current_time.hour
        est_nuit = (h >= 20 or h < 6)
        if not est_special:
            taux_final = 2.0 if est_nuit else 1.50
        else:
            taux_final = 2.25 if est_nuit else 1.75
        gain_total += 0.25 * (t_base * taux_final)
        current_time += timedelta(minutes=15)
        
    duree_totale = (end - start).total_seconds() / 3600
    return duree_totale, round(gain_total, 2)

# --- 6. FORMULAIRE DE SAISIE ---
with st.form("form_saisie", clear_on_submit=True):
    st.subheader("➕ Ajouter une session")
    col1, col2, col3 = st.columns(3)
    d = col1.date_input("Date", datetime.now())
    h1 = col2.time_input("Heure Début", time(18, 0))
    h2 = col3.time_input("Heure Fin", time(22, 0))
    submit = st.form_submit_button("Enregistrer définitivement")

if submit:
    h_tot, g_tot = calculer_gain_reel(d, h1, h2, taux_base)
    nouvelle_ligne = pd.DataFrame([{
        "Date": d.strftime('%Y-%m-%d'),
        "Heures": float(h_tot),
        "Gain": float(g_tot)
    }])
    df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
    
    try:
        conn.update(data=df_final)
        st.success(f"✅ Enregistré : {h_tot}h pour {g_tot}€")
        st.rerun()
    except Exception as e:
        st.error(f"Erreur d'écriture : {e}")

# --- 7. AFFICHAGE ---
if not df_existant.empty:
    df_existant['Date'] = pd.to_datetime(df_existant['Date'])
    st.divider()
    st.metric("Gain Cumulé", f"{df_existant['Gain'].sum():.2f} €")
    
    tab1, tab2 = st.tabs(["📅 Historique", "📈 Statistiques"])
    with tab1:
        st.dataframe(df_existant.sort_values('Date', ascending=False), use_container_width=True, hide_index=True)
    with tab2:
        recap_mensuel = df_existant.set_index('Date').resample('ME').sum()
        st.bar_chart(recap_mensuel['Gain'])
else:
    st.info("👋 Saisis tes premières heures pour commencer !")
