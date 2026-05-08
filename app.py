import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Suivi Heures Sup Enedis", page_icon="⏱️", layout="wide")

# Paramètres extraits de ton bulletin de paie [cite: 28, 63, 67]
TX_HORAIRE_DEFAUT = 14.18  # Taux horaire de base [cite: 28]
TX_RETENUE_HS = 0.067      # Retenue réelle de 6.7% sur les HS défiscalisées [cite: 63, 67]

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}
JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

def nettoyer_dataframe(df):
    """Force la conversion des dates et des types pour éviter les erreurs de format"""
    if 'Date' in df.columns:
        df['Date'] = df['Date'].astype(str)
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Date'])
    if 'Repas' in df.columns:
        df['Repas'] = pd.to_numeric(df['Repas'], errors='coerce').fillna(0)
    return df

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
        df_raw = nettoyer_dataframe(df_raw)
        
        # Initialisation des colonnes si vide
        for c in ['H_50', 'H_75', 'H_100', 'H_125', 'Taux_Base', 'Repas']:
            if c not in df_raw.columns: 
                df_raw[c] = 0.0 if c != 'Taux_Base' else TX_HORAIRE_DEFAUT
    else:
        df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas", "H_50", "H_75", "H_100", "H_125"])
except Exception as e:
    st.error(f"⚠️ Erreur de connexion au Sheets : {e}")
    df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas", "H_50", "H_75", "H_100", "H_125"])

# --- 3. LOGIQUE DE CALCUL ---
def calculer_session(date_j, debut, fin, t_base, feries):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    
    gain_total, ventilation = 0, {50: 0.0, 75: 0.0, 100: 0.0, 125: 0.0}
    current, pas = start, 15
    
    while current < end:
        est_special = (current.weekday() == 6 or current.date() in feries)
        h = current.hour
        est_nuit = (h >= 20 or h < 6)
        
        # Majorations Statutaires
        if est_special:
            mult = 2.25 if est_nuit else 1.75
            maj = 125 if est_nuit else 75
        else:
            mult = 2.00 if est_nuit else 1.50
            maj = 100 if est_nuit else 50
            
        ventilation[maj] += (pas / 60)
        gain_total += (pas / 60) * (t_base * mult)
        current += timedelta(minutes=pas)
    
    # Logique Repas Cumulable (Midi 11-13h et Soir 19-21h)
    def verifier_plage(p_start_time, p_end_time):
        p_start = datetime.combine(date_j, p_start_time)
        p_end = datetime.combine(date_j, p_end_time)
        inter_s, inter_e = max(start, p_start), min(end, p_end)
        if inter_e > inter_s:
            return (inter_e - inter_s).total_seconds() / 3600
        return 0

    nb_repas = 0
    if verifier_plage(time(11, 0), time(13, 0)) >= 2.0: nb_repas += 1
    if verifier_plage(time(19, 0), time(21, 0)) >= 2.0: nb_repas += 1
            
    return round((end - start).total_seconds()/3600, 2), round(gain_total, 2), nb_repas, ventilation

# --- 4. INTERFACE ---
with st.sidebar:
    st.title("⏱️ Pilotage Heures")
    taux_actuel = st.number_input("Taux horaire (€)", value=TX_HORAIRE_DEFAUT, step=0.01)
    pays = st.selectbox("Jours fériés", ["France", "Belgique", "Suisse"])
    feries_liste = holidays.CountryHoliday(pays)
    mode = st.radio("Menu", ["Saisie", "Gestion", "Récapitulatif"])

# --- MODE : SAISIE ---
if mode == "Saisie":
    st.header("➕ Enregistrer une intervention")
    with st.form("f_saisie", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        d = col1.date_input("Date", datetime.now())
        h1 = col2.time_input("Début", time(10, 0))
        h2 = col3.time_input("Fin", time(14, 0))
        if st.form_submit_button("Valider la saisie"):
            h_tot, g_tot, repas_count, vent = calculer_session(d, h1, h2, taux_actuel, feries_liste)
            
            new_row = pd.DataFrame([{
                "Date": d.strftime('%d/%m/%Y'), "Heures": h_tot, "Gain": g_tot, 
                "Taux_Base": taux_actuel, "Repas": repas_count,
                "H_50": vent[50], "H_75": vent[75], "H_100": vent[100], "H_125": vent[125]
            }])
            
            df_export = df_raw.copy()
            df_export['Date'] = df_export['Date'].dt.strftime('%d/%m/%Y')
            df_final = pd.concat([df_export, new_row], ignore_index=True)
            conn.update(spreadsheet=url, data=df_final)
            st.success(f"Enregistré ! Gain Brut : {g_tot}€ | Repas : {repas_count}")
            st.rerun()

# --- MODE : GESTION ---
elif mode == "Gestion":
    st.header("⚙️ Historique & Modifications")
    if not df_raw.empty:
        df_edit = df_raw.copy()
        df_edit['Date'] = pd.to_datetime(df_edit['Date'])
        edited = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True,
                               column_config={
                                   "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                                   "Repas": st.column_config.NumberColumn("Nb Repas", min_value=0, max_value=2, step=1)
                               })
        if st.button("Enregistrer les modifications"):
            edited['Date'] = pd.to_datetime(edited['Date']).dt.strftime('%d/%m/%Y')
            conn.update(spreadsheet=url, data=edited)
            st.rerun()

# --- MODE : RÉCAPITULATIF ---
elif mode == "Récapitulatif":
    st.header("📊 Récapitulatif Mensuel")
    if not df_raw.empty:
        df = df_raw.copy()
        df['Date'] = pd.to_datetime(df['Date'])
        df['Année'], df['Mois_Num'], df['Semaine'] = df['Date'].dt.year, df['Date'].dt.month, df['Date'].dt.isocalendar().week
        
        sel_an = st.selectbox("Année", sorted(df['Année'].unique(), reverse=True))
        df_ans = df[df['Année'] == sel_an]
        sel_m_nom = st.selectbox("Mois", [MOIS_FR[m] for m in sorted(df_ans['Mois_Num'].unique())])
        sel_m_num = [k for k, v in MOIS_FR.items() if v == sel_m_nom][0]
        df_m = df_ans[df_ans['Mois_Num'] == sel_m_num]

        # Calculs totaux
        brut_total = df_m['Gain'].sum()
        net_estime = brut_total * (1 - TX_RETENUE_HS)

        st.subheader(f"📈 Bilan {sel_m_nom} {sel_an}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Gain Brut HS", f"{brut_total:.2f} €")
        m2.metric("Net HS Est. (≈)", f"{net_estime:.2f} €")
        m3.metric("Heures Total", f"{df_m['Heures'].sum():.2f} h")
        m4.metric("Total Repas", f"{int(df_m['Repas'].sum())}")
        
        st.divider()
        st.write("**Répartition des heures par majoration :**")
        v1, v2, v3, v4 = st.columns(4)
        v1.info(f"**50% :** {df_m['H_50'].sum()}h")
        v2.info(f"**75% :** {df_m['H_75'].sum()}h")
        v3.info(f"**100% :** {df_m['H_100'].sum()}h")
        v4.info(f"**125% :** {df_m['H_125'].sum()}h")

        for s in sorted(df_m['Semaine'].unique()):
            df_s = df_m[df_m['Semaine'] == s].copy()
            brut_sem = df_s['Gain'].sum()
            net_sem = brut_sem * (1 - TX_RETENUE_HS)
            
            titre = f"Semaine {s} — Brut : {brut_sem:.2f} € | Net Est. : {net_sem:.2f} €"
            
            with st.expander(titre):
                df_s['Jour'] = df_s['Date'].apply(lambda x: f"{JOURS_FR[x.weekday()]} {x.day}")
                st.table(df_s[['Jour', 'H_50', 'H_75', 'H_100', 'H_125', 'Gain', 'Repas']].set_index('Jour'))
