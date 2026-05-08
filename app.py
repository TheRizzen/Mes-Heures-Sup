import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CORRECTEUR DE SÉCURITÉ (INDISPENSABLE) ---
# Ce bloc répare la clé privée avant que la connexion ne soit tentée
if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
    raw_key = st.secrets["connections"]["gsheets"]["private_key"]
    # On force le remplacement des \n textuels par de vrais sauts de ligne
    st.secrets["connections"]["gsheets"]["private_key"] = raw_key.replace("\\n", "\n")

# --- 2. CONFIGURATION DE L'INTERFACE ---
st.set_page_config(
    page_title="Mes Heures Sup", 
    page_icon="⏱️", 
    layout="centered"
)

st.title("⏱️ Suivi des Heures Supplémentaires")

# --- 3. CONNEXION À LA BASE DE DONNÉES ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Lecture des données (on gère le cas où la feuille est vide)
try:
    df_existant = conn.read(ttl=0)
    # Nettoyage des lignes vides si nécessaire
    df_existant = df_existant.dropna(how="all")
except Exception:
    df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# --- 4. CONFIGURATION DU CONTRAT (BARRE LATÉRALE) ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    taux_base = st.number_input("Taux horaire de base (€)", value=15.0)
    pays = st.selectbox("Pays (Jours fériés)", ["France", "Belgique", "Suisse"])
    feries = holidays.CountryHoliday(pays)
    st.info("Les majorations (50%, 75%, 100%, 125%) sont appliquées selon tes paragraphes 1 à 4.")

# --- 5. LOGIQUE DE CALCUL DES MAJORATIONS ---
def calculer_gain_reel(date_j, debut, fin, t_base):
    # Transformation en objets datetime
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    
    # Si le travail finit le lendemain (ex: 22h -> 02h)
    if end <= start:
        end += timedelta(days=1)
    
    # Vérification Dimanche ou Férié
    est_special = (date_j.weekday() == 6 or date_j in feries)
    
    gain_total = 0
    # On analyse le temps par tranches de 15 minutes pour la précision
    current_time = start
    while current_time < end:
        h = current_time.hour
        # Paragraphe 3 : Nuit = 20h à 06h
        est_nuit = (h >= 20 or h < 6)
        
        # Paragraphe 1 : Application des taux
        if not est_special:
            # Semaine
            taux_final = 2.0 if est_nuit else 1.50  # 100% ou 50%
        else:
            # Dimanche ou Férié
            taux_final = 2.25 if est_nuit else 1.75 # 125% ou 75%
            
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
    
    # Préparation de la ligne
    nouvelle_ligne = pd.DataFrame([{
        "Date": d.strftime('%Y-%m-%d'),
        "Heures": float(h_tot),
        "Gain": float(g_tot)
    }])
    
    # Mise à jour de la base
    df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
    
    # Envoi vers Google Sheets
    try:
        conn.update(data=df_final)
        st.success(f"✅ Session enregistrée : {h_tot}h pour {g_tot}€")
        st.balloons()
        st.rerun()
    except Exception as e:
        st.error(f"Erreur d'écriture : {e}")

# --- 7. AFFICHAGE DES RÉSULTATS ---
if not df_existant.empty:
    # On s'assure que les dates sont bien lues
    df_existant['Date'] = pd.to_datetime(df_existant['Date'])
    
    st.divider()
    col_res1, col_res2 = st.columns(2)
    col_res1.metric("Total Heures", f"{df_existant['Heures'].sum()} h")
    col_res2.metric("Gain Cumulé", f"{df_existant['Gain'].sum():.2f} €")
    
    tab1, tab2 = st.tabs(["📅 Historique", "📈 Statistiques"])
    
    with tab1:
        st.dataframe(
            df_existant.sort_values('Date', ascending=False), 
            use_container_width=True,
            hide_index=True
        )
        
    with tab2:
        # Groupement par mois (ME = Month End)
        recap_mensuel = df_existant.set_index('Date').resample('ME').sum()
        st.write("Gains par mois :")
        st.bar_chart(recap_mensuel['Gain'])
else:
    st.info("👋 Bienvenue ! Saisis tes premières heures supplémentaires pour commencer le suivi.")
