import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays

# Configuration de la page
st.set_page_config(page_title="Mes Heures Sup", page_icon="⏱️")

# --- PARAMETRES ---
st.title("⏱️ Calculateur d'Heures Sup")

with st.expander("⚙️ Configuration de mon contrat"):
    taux_base = st.number_input("Taux horaire de base (€)", value=12.0)
    pays = st.selectbox("Pays (pour les jours fériés)", ["France", "Belgique", "Suisse"])
    feries = holidays.CountryHoliday(pays)

# --- LOGIQUE DE CALCUL ---
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
        
        # Application des taux (Paragraphes 1 & 3)
        if not est_special:
            taux = 2.0 if est_nuit else 1.50 # Nuit 100%, Jour 50%
        else:
            taux = 2.25 if est_nuit else 1.75 # Nuit 125%, Jour 75%
            
        total_gain += duree * (t_base * taux)
        curr = prochain
    return total_h, total_gain

# --- SAISIE ---
st.subheader("➕ Ajouter des heures")
col1, col2, col3 = st.columns(3)
with col1: d = st.date_input("Jour")
with col2: h1 = st.time_input("Début", time(18, 0))
with col3: h2 = st.time_input("Fin", time(21, 0))

if st.button("Enregistrer la session"):
    h_tot, gain_tot = calculer_tranches(d, h1, h2, taux_base)
    # Note: Dans cette version Cloud, on utilise le 'session_state' pour stocker
    if 'data' not in st.session_state:
        st.session_state.data = []
    
    st.session_state.data.append({
        "Date": d, "Heures": h_tot, "Gain": round(gain_tot, 2)
    })
    st.success(f"Ajouté : {h_tot}h pour {gain_tot:.2f}€")

# --- AFFICHAGE ---
if 'data' in st.session_state and st.session_state.data:
    df = pd.DataFrame(st.session_state.data)
    df['Date'] = pd.to_datetime(df['Date'])
    
    st.divider()
    st.metric("Total à percevoir", f"{df['Gain'].sum():.2f} €")
    
    choix = st.segmented_control("Récapitulatif par :", ["Jour", "Mois", "Année"], default="Jour")
    
    if choix == "Jour":
        st.dataframe(df)
    elif choix == "Mois":
        recap_m = df.resample('M', on='Date').sum()
        st.bar_chart(recap_m['Gain'])