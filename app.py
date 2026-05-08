import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# Configuration
st.set_page_config(page_title="Mes Heures Sup", page_icon="⏱️")
st.title("⏱️ Mon Suivi Permanent")

# --- CONNEXION GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Lecture des données existantes
df_existant = conn.read(ttl=0) # ttl=0 pour forcer la mise à jour réelle

# --- PARAMETRES ---
with st.sidebar:
    taux_base = st.number_input("Taux horaire de base (€)", value=12.0)
    pays = st.selectbox("Pays", ["France", "Belgique", "Suisse"])
    feries = holidays.CountryHoliday(pays)

# --- LOGIQUE DE CALCUL (Inchangée) ---
def calculer_tranches(date_choisie, h_deb, h_fin, t_base):
    debut = datetime.combine(date_choisie, h_deb)
    fin = datetime.combine(date_choisie, h_fin)
    if fin <= debut: fin += timedelta(days=1)
    est_special = (date_choisie.weekday() == 6 or date_choisie in feries)
    total_gain = 0
    total_h = (fin - debut).total_seconds() / 3600
    curr = debut
    while curr < fin:
        prochain = min(curr + timedelta(minutes=15), fin)
        duree = 0.25
        h = curr.hour
        est_nuit = (h >= 20 or h < 6)
        taux = (2.25 if est_nuit else 1.75) if est_special else (2.0 if est_nuit else 1.50)
        total_gain += duree * (t_base * taux)
        curr = prochain
    return total_h, total_gain

# --- INTERFACE DE SAISIE ---
with st.form("form_saisie"):
    col1, col2, col3 = st.columns(3)
    d = col1.date_input("Jour")
    h1 = col2.time_input("Début", time(18, 0))
    h2 = col3.time_input("Fin", time(21, 0))
    submit = st.form_submit_button("Enregistrer définitivement")

if submit:
    h_tot, gain_tot = calculer_tranches(d, h1, h2, taux_base)
    
    # Création de la nouvelle ligne
    nouvelle_ligne = pd.DataFrame([{
        "Date": d.strftime('%Y-%m-%d'),
        "Heures": h_tot,
        "Gain": round(gain_tot, 2)
    }])
    
    # Fusion avec l'ancien et envoi vers Google
    df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
    conn.update(data=df_final)
    st.success("Données sauvegardées dans Google Sheets !")
    st.rerun()

# --- AFFICHAGE ---
if not df_existant.empty:
    df_existant['Date'] = pd.to_datetime(df_existant['Date'])
    st.divider()
    st.metric("Total Cumulé", f"{df_existant['Gain'].sum():.2f} €")
    
    choix = st.radio("Récapitulatif :", ["Jour", "Mois"], horizontal=True)
    if choix == "Jour":
        st.dataframe(df_existant.sort_values('Date', ascending=False))
    else:
        recap_m = df_existant.resample('ME', on='Date').sum()
        st.bar_chart(recap_m['Gain'])
