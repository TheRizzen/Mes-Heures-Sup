import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Enedis Focus - Dashboard", page_icon="⚡", layout="wide")

# CSS PERSONNALISÉ POUR LE DESIGN
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    div[data-testid="stExpander"] {
        border-radius: 10px !important;
        border: none !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
        background-color: white !important;
        margin-bottom: 10px;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        background-color: #007bff;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# Paramètres Enedis
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
    st.error(f"⚠️ Erreur : {e}")
    df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas", "H_50", "H_75", "H_100", "H_125"])

# --- 3. LOGIQUE ---
def calculer_session(date_j, debut, fin, t_base, feries):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    g_tot, vent = 0, {50: 0.0, 75: 0.0, 100: 0.0, 125: 0.0}
    current, pas = start, 15
    while current < end:
        est_special = (current.weekday() == 6 or current.date() in feries)
        h = current.hour
        est_nuit = (h >= 20 or h < 6)
        mult = (2.25 if est_nuit else 1.75) if est_special else (2.00 if est_nuit else 1.50)
        maj = (125 if est_nuit else 75) if est_special else (100 if est_nuit else 50)
        vent[maj] += (pas / 60)
        g_tot += (pas / 60) * (t_base * mult)
        current += timedelta(minutes=pas)
    
    def verifier_plage(p_s, p_e):
        ps, pe = datetime.combine(date_j, p_s), datetime.combine(date_j, p_e)
        i_s, i_e = max(start, ps), min(end, pe)
        return (i_e - i_s).total_seconds() / 3600 if i_e > i_s else 0
    
    nb_r = 0
    if verifier_plage(time(11,0), time(13,0)) >= 2.0: nb_r += 1
    if verifier_plage(time(19,0), time(21,0)) >= 2.0: nb_r += 1
    return round((end - start).total_seconds()/3600, 2), round(g_tot, 2), nb_r, vent

# --- 4. INTERFACE ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/fr/a/a7/Enedis_logo_2016.svg", width=150)
    st.title("Pilotage")
    taux_actuel = st.number_input("Taux horaire (€)", value=TX_HORAIRE_DEFAUT, step=0.01)
    st.divider()
    mode = st.selectbox("Navigation", ["📈 Dashboard", "➕ Saisie Rapide", "⚙️ Historique"], label_visibility="collapsed")

# --- MODE : DASHBOARD (Ancien récapitulatif) ---
if "Dashboard" in mode:
    st.title("📊 Tableau de Bord Mensuel")
    if not df_raw.empty:
        df = df_raw.copy()
        df['Date'] = pd.to_datetime(df['Date'])
        df['Mois_Num'] = df['Date'].dt.month
        
        col_m1, col_m2 = st.columns([1, 3])
        with col_m1:
            sel_m_nom = st.selectbox("Sélectionner un mois", [MOIS_FR[m] for m in sorted(df['Mois_Num'].unique(), reverse=True)])
        
        sel_m_num = [k for k, v in MOIS_FR.items() if v == sel_m_nom][0]
        df_m = df[df['Mois_Num'] == sel_m_num]

        brut_total = df_m['Gain'].sum()
        net_estime = brut_total * (1 - TX_RETENUE_HS)

        # KPIs avec design
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💰 Gain Brut", f"{brut_total:.2f} €")
        k2.metric("💸 Gain Net (≈)", f"{net_estime:.2f} €")
        k3.metric("⏱️ Heures", f"{df_m['Heures'].sum():.2g} h")
        k4.metric("🍱 Repas", f"{int(df_m['Repas'].sum())}")
        
        st.write("### 📅 Détail par Semaine")
        df_m['Semaine'] = df_m['Date'].dt.isocalendar().week
        for s in sorted(df_m['Semaine'].unique(), reverse=True):
            df_s = df_m[df_m['Semaine'] == s]
            b_s = df_s['Gain'].sum()
            n_s = b_s * (1 - TX_RETENUE_HS)
            with st.expander(f"SEMAINE {s} • Brut: {b_s:.2f}€ | Net: {n_s:.2f}€"):
                df_s_p = df_s.copy()
                df_s_p['Jour'] = df_s_p['Date'].apply(lambda x: f"{JOURS_FR[x.weekday()]} {x.day}")
                st.dataframe(
                    df_s_p[['Jour', 'H_50', 'H_75', 'H_100', 'H_125', 'Gain', 'Repas']].set_index('Jour'),
                    use_container_width=True
                )

# --- MODE : SAISIE ---
elif "Saisie" in mode:
    st.title("➕ Enregistrer une intervention")
    with st.container():
        st.info("Saisissez vos horaires de début et de fin, l'app calcule automatiquement les majorations Enedis.")
        with st.form("f_saisie", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            d = c1.date_input("📅 Date", datetime.now())
            h1 = c2.time_input("🛫 Début", time(10, 0))
            h2 = c3.time_input("🛬 Fin", time(14, 0))
            
            if st.form_submit_button("VALIDER L'INTERVENTION"):
                h_tot, g_tot, rep_c, vent = calculer_session(d, h1, h2, taux_actuel, holidays.CountryHoliday("France"))
                new_row = pd.DataFrame([{
                    "Date": d.strftime('%d/%m/%Y'), "Heures": h_tot, "Gain": g_tot, 
                    "Taux_Base": taux_actuel, "Repas": rep_c,
                    "H_50": vent[50], "H_75": vent[75], "H_100": vent[100], "H_125": vent[125]
                }])
                df_export = df_raw.copy()
                df_export['Date'] = df_export['Date'].dt.strftime('%d/%m/%Y')
                conn.update(spreadsheet=url, data=pd.concat([df_export, new_row], ignore_index=True))
                st.balloons()
                st.success(f"Enregistré : {g_tot}€ gagnés !")
                st.rerun()

# --- MODE : HISTORIQUE ---
elif "Historique" in mode:
    st.title("⚙️ Gestion des données")
    if not df_raw.empty:
        df_edit = df_raw.copy()
        df_edit['Date'] = pd.to_datetime(df_edit['Date'])
        edited = st.data_editor(
            df_edit, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={"Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY")}
        )
        if st.button("SAUVEGARDER LES MODIFICATIONS"):
            edited['Date'] = pd.to_datetime(edited['Date']).dt.strftime('%d/%m/%Y')
            conn.update(spreadsheet=url, data=edited)
            st.rerun()
