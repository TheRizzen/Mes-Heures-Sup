import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Suivi Heures Sup", page_icon="⏱️", layout="wide")

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}
JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# --- 2. CONNEXION ---
@st.cache_resource
def connect_gsheets():
    return st.connection("gsheets", type=GSheetsConnection)

try:
    conn = connect_gsheets()
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    df_raw = conn.read(spreadsheet=url, ttl=0)
    
    if df_raw is not None:
        df_raw = df_raw.dropna(how="all")
        df_raw['Date'] = pd.to_datetime(df_raw['Date'], dayfirst=True, errors='coerce')
        # On s'assure que les colonnes existent
        if 'Taux_Base' not in df_raw.columns: df_raw['Taux_Base'] = 15.0
        if 'Repas' not in df_raw.columns: df_raw['Repas'] = "Non"
    else:
        df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas"])
except Exception as e:
    st.error(f"⚠️ Erreur : {e}")
    df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas"])

# --- 3. LOGIQUE DE CALCUL ---
def calculer_session(date_j, debut, fin, t_base, feries):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    
    # 1. Calcul financier (Heures Sup)
    gain_total, current, pas = 0, start, 15
    while current < end:
        est_special = (current.weekday() == 6 or current.date() in feries)
        h = current.hour
        est_nuit = (h >= 20 or h < 6)
        taux_mult = (2.25 if est_nuit else 1.75) if est_special else (2.00 if est_nuit else 1.50)
        gain_total += (pas / 60) * (t_base * taux_mult)
        current += timedelta(minutes=pas)
    
    # 2. Condition Repas (2h entre 19h et 21h)
    repas_start = datetime.combine(date_j, time(19, 0))
    repas_end = datetime.combine(date_j, time(21, 0))
    
    # Calcul de l'intersection entre le travail et la plage 19h-21h
    inter_start = max(start, repas_start)
    inter_end = min(end, repas_end)
    
    repas_valide = "Non"
    if inter_end > inter_start:
        duree_dans_plage = (inter_end - inter_start).total_seconds() / 3600
        if duree_dans_plage >= 2.0: # Minimum 2 heures
            repas_valide = "Oui"
            
    return round((end - start).total_seconds() / 3600, 2), round(gain_total, 2), repas_valide

# --- 4. INTERFACE ---
with st.sidebar:
    st.title("⏱️ Menu")
    taux_actuel = st.number_input("Taux horaire actuel (€)", value=15.0)
    pays = st.selectbox("Jours fériés", ["France", "Belgique", "Suisse"])
    feries_liste = holidays.CountryHoliday(pays)
    mode = st.radio("Navigation", ["Saisie", "Gestion", "Récapitulatif Détaillé"])

# --- MODE : SAISIE ---
if mode == "Saisie":
    st.header("➕ Nouvelle Saisie")
    with st.form("f_saisie", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        d = col1.date_input("Date", datetime.now())
        h1 = col2.time_input("Début", time(18, 0))
        h2 = col3.time_input("Fin", time(22, 0))
        if st.form_submit_button("Enregistrer"):
            h_tot, g_tot, repas = calculer_session(d, h1, h2, taux_actuel, feries_liste)
            
            new_row = pd.DataFrame([{
                "Date": d.strftime('%Y-%m-%d'), 
                "Heures": h_tot, 
                "Gain": g_tot,
                "Taux_Base": taux_actuel,
                "Repas": repas
            }])
            
            df_final = pd.concat([df_raw, new_row], ignore_index=True)
            df_final['Date'] = pd.to_datetime(df_final['Date']).dt.strftime('%Y-%m-%d')
            conn.update(spreadsheet=url, data=df_final)
            st.success(f"Enregistré ! Repas validé : {repas}")
            st.rerun()

# --- MODE : GESTION ---
elif mode == "Gestion":
    st.header("⚙️ Modifier / Supprimer")
    if not df_raw.empty:
        df_edit = df_raw.copy()
        df_edit['Date'] = pd.to_datetime(df_edit['Date'])
        edited = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True)
        if st.button("Sauvegarder les changements"):
            edited['Date'] = pd.to_datetime(edited['Date']).dt.strftime('%Y-%m-%d')
            conn.update(spreadsheet=url, data=edited)
            st.success("Mise à jour réussie")
            st.rerun()

# --- MODE : RÉCAPITULATIF DÉTAILLÉ ---
elif mode == "Récapitulatif Détaillé":
    st.header("📊 Analyse")
    if not df_raw.empty:
        df = df_raw.copy()
        df['Date'] = pd.to_datetime(df['Date'])
        df['Année'] = df['Date'].dt.year
        df['Mois_Num'] = df['Date'].dt.month
        df['Semaine'] = df['Date'].dt.isocalendar().week
        
        sel_an = st.selectbox("📅 Année", sorted(df['Année'].unique(), reverse=True))
        df_ans = df[df['Année'] == sel_an]
        
        sel_mois_nom = st.selectbox("🌙 Mois", [MOIS_FR[m] for m in sorted(df_ans['Mois_Num'].unique())])
        sel_m_num = [k for k, v in MOIS_FR.items() if v == sel_mois_nom][0]
        df_m = df_ans[df_ans['Mois_Num'] == sel_m_num]

        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Gain Heures Sup", f"{df_m['Gain'].sum():.2f} €")
        c2.metric("Total Heures", f"{df_m['Heures'].sum():.2f} h")
        # On compte le nombre de "Oui" pour les repas
        nb_repas = len(df_m[df_m['Repas'] == "Oui"])
        c3.metric("Nombre de Repas", f"{nb_repas}")

        st.subheader("📁 Détail par semaine")
        for s in sorted(df_m['Semaine'].unique()):
            df_s = df_m[df_m['Semaine'] == s].copy()
            with st.expander(f"Semaine {s} — {df_s['Gain'].sum():.2f} €"):
                df_s['Jour'] = df_s['Date'].apply(lambda x: f"{JOURS_FR[x.weekday()]} {x.day}")
                st.table(df_s[['Jour', 'Heures', 'Gain', 'Repas']].set_index('Jour'))
            
