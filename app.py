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

# --- 2. LOGIQUE DE CONNEXION SÉCURISÉE ---
try:
    # On récupère les secrets dans un dictionnaire modifiable
    creds_dict = dict(st.secrets["connections"]["gsheets"])
    
    # Nettoyage de la clé privée pour interpréter correctement les sauts de ligne (\n)
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    # Initialisation de la connexion avec les paramètres nettoyés
    # On ne précise pas 'type' ici car il est déjà dans creds_dict
    conn = st.connection("gsheets", **creds_dict)
    
    # Lecture des données existantes
    df_existant = conn.read(ttl=0)
    if df_existant is not None:
        df_existant = df_existant.dropna(how="all")
    else:
        df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])
        
except Exception as e:
    # Message discret en cas de feuille vide ou première connexion
    st.info("Prêt pour la première saisie !")
    df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# --- 3. CONFIGURATION DU CONTRAT (BARRE LATÉRALE) ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    taux_base = st.number_input("Taux horaire de base (€)", value=15.0)
    pays = st.selectbox("Pays (Jours fériés)", ["France", "Belgique", "Suisse"])
    feries = holidays.CountryHoliday(pays)

# --- 4. LOGIQUE DE CALCUL DES MAJORATIONS ---
def calculer_gain_reel(date_j, debut, fin, t_base):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    
    # Gestion du passage à minuit
    if end <= start:
        end += timedelta(days=1)
    
    # Vérification Dimanche (6) ou Jour Férié
    est_special = (date_j.weekday() == 6 or date_j in feries)
    
    gain_total = 0
    current_time = start
    
    # Calcul par tranches de 15 minutes
    while current_time < end:
        h = current_time.hour
        # Nuit définie entre 20h et 06h
        est_nuit = (h >= 20 or h < 6)
        
        if not est_special:
            # En semaine
            taux_final = 2.0
