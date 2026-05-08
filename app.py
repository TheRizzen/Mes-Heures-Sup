import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Suivi Heures Sup Enedis", page_icon="⚡", layout="wide")

# CSS pour forcer la lisibilité et le look "Pro"
st.markdown("""
    <style>
    /* Force le texte en noir et les titres en bleu Enedis */
    h1, h2, h3 { color: #005BB7 !important; }
    .stMetric label { color: #555555 !important; font-weight: bold !important; }
    .stMetric div { color: #000000 !important; }
    
    /* Style des cadres de résultats */
    div[data-testid="metric-container"] {
        background-color: #FFFFFF;
        border: 1px solid #E0E0E0;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

TX_HORAIRE_DEFAUT = 14.18
TX_RETENUE_HS = 0.067

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}
JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

def nettoyer_dataframe(df):
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
        for c in ['H_50', 'H_75', 'H_100', 'H_125', 'Taux_Base', 'Repas']:
            if c not in df_raw.columns: 
                df_raw[c] = 0.0 if c != 'Taux_Base' else TX_HORAIRE_DEFAUT
    else:
        df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas", "H_50", "H_75", "H_100", "H_125"])
except Exception as e:
    st.error(f"⚠️ Erreur de connexion : {e}")
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
        if est_special:
            mult, maj = (2.25, 125) if est_nuit else (1.75, 75)
        else:
            mult, maj = (2.00, 100) if est_nuit else (1.50, 50)
        ventilation[maj] += (pas / 60)
        gain_total += (pas / 60) * (t_base * mult)
        current += timedelta(minutes=pas)
    
    def verifier_plage(p_start, p_end):
        p_s, p_e = datetime.combine(date_j, p_start), datetime.combine(date_j, p_end)
        inter_s, inter_e = max(start, p_s), min(end, p_e)
        return max(0, (inter_e - inter_s).total_seconds() / 3600)

    nb_repas = 0
    if verifier_plage(time(11, 0), time(13, 0)) >= 2.0: nb_repas += 1
    if verifier_plage(time(19, 0), time(21, 0)) >= 2.0: nb_repas += 1
    return round((end - start).total_seconds()/3600, 2), round(gain_total, 2), nb_repas, ventilation

# --- 4. INTERFACE ---
with st.sidebar:
    # Logo Enedis (via URL officielle ou texte stylisé)
    st.image("https://upload.wikimedia.org/wikipedia/fr/a/a7/Enedis_logo_2016.svg", width=150)
    st.title("⏱️ Pilotage Heures")
    taux_actuel = st.number_input("Taux horaire (€)", value=TX_HORAIRE_DEFAUT, step=0.01)
    mode = st.radio("Menu", ["Saisie", "Gestion", "Récapitulatif"])

# --- MODE : SAISIE ---
if mode == "Saisie":
    st.header("➕ Enregistrer une intervention")
    with st.container():
        with st.form("f_saisie", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            d = col1.date_input("Date", datetime.now())
            h1 = col2.time_input("Début", time(10, 0))
            h2 = col3.time_input("Fin", time(14, 0))
            if st.form_submit_button("Valider la saisie"):
                h_tot, g_tot, repas_count, vent = calculer_session(d, h1, h2, taux_actuel, holidays.CountryHoliday("France"))
                new_row = pd.DataFrame([{
                    "Date": d.strftime('%d/%m/%Y'), "Heures": h_tot, "Gain": g_tot, 
                    "Taux_Base": taux_actuel, "Repas": repas_count,
                    "H_50": vent[50], "H_75": vent[75], "H_100": vent[100], "H_125": vent[125]
                }])
                df_export = df_raw.copy()
                df_export['Date'] = df_export['Date'].dt.strftime('%d/%m/%Y')
                conn.update(spreadsheet=url, data=pd.concat([df_export, new_row], ignore_index=True))
                st.success(f"✅ Enregistré ! Gain Brut : {g_tot}€")
                st.rerun()

# --- MODE : GESTION ---
elif mode == "Gestion":
    st.header("⚙️ Historique & Modifications")
    if not df_raw.empty:
        df_edit = df_raw.copy().sort_values("Date", ascending=False)
        edited = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True,
                               column_config={"Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY")})
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
        
        c1, c2 = st.columns(2)
        sel_an = c1.selectbox("Année", sorted(df['Année'].unique(), reverse=True))
        sel_m_nom = c2.selectbox("Mois", [MOIS_FR[m] for m in sorted(df[df['Année']==sel_an]['Mois_Num'].unique())])
        
        sel_m_num = [k for k, v in MOIS_FR.items() if v == sel_m_nom][0]
        df_m = df[(df['Année'] == sel_an) & (df['Mois_Num'] == sel_m_num)]

        brut_total = df_m['Gain'].sum()
        net_estime = brut_total * (1 - TX_RETENUE_HS)

        # Affichage des scores
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Gain Brut HS", f"{brut_total:.2f} €")
        m2.metric("Net HS (estimé)", f"{net_estime:.2f} €")
        m3.metric("Total Heures", f"{df_m['Heures'].sum():.2f} h")
        m4.metric("Total Repas", f"{int(df_m['Repas'].sum())}")
        
        st.write("---")
        for s in sorted(df_m['Semaine'].unique(), reverse=True):
            df_s = df_m[df_m['Semaine'] == s].copy()
            titre = f"Semaine {s} — Brut : {df_s['Gain'].sum():.2f} €"
            with st.expander(titre):
                df_s['Jour'] = df_s['Date'].apply(lambda x: f"{JOURS_FR[x.weekday()]} {x.day}")
                st.table(df_s[['Jour', 'H_50', 'H_75', 'H_100', 'H_125', 'Gain', 'Repas']].set_index('Jour'))
