import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# Apparence
st.set_page_config(page_title="Mes Heures", layout="centered")
st.title("⏱️ Suivi des Heures Supplémentaires")

# Connexion à la base Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Chargement des données (sécurisé)
try:
    df_existant = conn.read(ttl=0)
except Exception:
    df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# Configuration du contrat (Barre latérale)
with st.sidebar:
    st.header("⚙️ Configuration")
    t_base = st.number_input("Taux horaire (€)", value=15.0)
    feries = holidays.CountryHoliday('France')

# Formulaire de saisie
with st.form("ajout_heure", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    date_travail = col1.date_input("Date")
    h_deb = col2.time_input("Début", time(18, 0))
    h_fin = col3.time_input("Fin", time(22, 0))
    bouton = st.form_submit_button("Enregistrer sur mon iPhone")

# Logique de calcul (Règles Paragraphe 1 à 4)
def calculer_gain(date_j, debut, fin, taux):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    
    est_special = (date_j.weekday() == 6 or date_j in feries)
    gain_total = 0
    temp = start
    while temp < end:
        h = temp.hour
        nuit = (h >= 20 or h < 6)
        # Application des taux demandés
        if not est_special:
            mult = 2.0 if nuit else 1.50
        else:
            mult = 2.25 if nuit else 1.75
        gain_total += 0.25 * (taux * mult) # Calcul par tranche de 15min
        temp += timedelta(minutes=15)
    return (end - start).total_seconds() / 3600, gain_total

if bouton:
    h_tot, g_tot = calculer_gain(date_travail, h_deb, h_fin, t_base)
    nouvelle_donnee = pd.DataFrame([{
        "Date": date_travail.strftime('%Y-%m-%d'),
        "Heures": float(h_tot),
        "Gain": float(g_tot)
    }])
    df_maj = pd.concat([df_existant, nouvelle_donnee], ignore_index=True)
    conn.update(data=df_maj)
    st.success(f"Sauvegardé ! +{g_tot:.2f}€")
    st.rerun()

# Affichage des récapitulatifs
if not df_existant.empty:
    df_existant['Date'] = pd.to_datetime(df_existant['Date'])
    st.divider()
    st.metric("Total cumulé", f"{df_existant['Gain'].sum():.2f} €")
    
    tab1, tab2 = st.tabs(["Historique", "Stats par Mois"])
    with tab1:
        st.dataframe(df_existant.sort_values('Date', ascending=False), use_container_width=True)
    with tab2:
        df_m = df_existant.set_index('Date').resample('ME').sum()
        st.bar_chart(df_m['Gain'])
