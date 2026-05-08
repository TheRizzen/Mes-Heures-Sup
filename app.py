import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURATION & DESIGN TOTAL (Haute Lisibilité) ---
st.set_page_config(page_title="Enedis Focus Pro", page_icon="⚡", layout="wide")

# CSS pour une esthétique Totale et lisible (Contraste Maximum)
st.markdown("""
    <style>
    /* Fond global de l'application (Gris très clair pour détacher les cartes) */
    .stApp {
        background-color: #F8F9FA;
    }
    
    /* Couleur de base du texte pour toute l'app (Noir profond pour lisibilité) */
    p, label, span, p {
        color: #1A1A1A !important;
        font-family: 'Segoe UI', sans-serif;
    }

    /* Titres principaux (Bleu Enedis) */
    h1, h2, h3 {
        color: #005BB7 !important; /* Bleu Enedis */
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-weight: 700 !important;
    }

    /* Cartes blanches pour le contenu (Cards) */
    div.stBlock {
        background-color: #FFFFFF;
        padding: 25px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        margin-bottom: 20px;
        border: 1px solid #EAEAEA;
    }

    /* Métriques (KPIs) : Texte Noir Fort */
    div[data-testid="stMetricValue"] {
        font-size: 32px !important;
        font-weight: 800 !important;
        color: #005BB7 !important; /* Chiffres en Bleu Enedis */
    }
    
    div[data-testid="stMetricLabel"] {
        font-size: 16px !important;
        color: #333333 !important; /* Labels en Gris foncé */
        font-weight: 600 !important;
    }

    /* Boutons personnalisés (Bleu Enedis, texte blanc) */
    .stButton>button {
        width: 100%;
        border-radius: 12px;
        height: 3.5em;
        background-color: #005BB7;
        color: white !important;
        font-weight: bold;
        border: none;
        transition: 0.3s;
    }
    
    .stButton>button:hover {
        background-color: #003F7D;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        color: white !important;
    }

    /* Sidebar stylisée (Texte blanc sur fond bleu Enedis) */
    section[data-testid="stSidebar"] {
        background-color: #005BB7;
        color: white !important;
    }
    section[data-testid="stSidebar"] p, 
    section[data-testid="stSidebar"] label, 
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] span {
        color: white !important;
    }
    section[data-testid="stSidebar"] .stMarkdown p {
        color: white !important;
    }
    
    /* Correction pour le champ Taux Horaire dans la sidebar */
    section[data-testid="stSidebar"] input {
        color: #1A1A1A !important;
    }
    
    /* Style des expanders (Semaines) */
    div[data-testid="stExpander"] {
        background-color: white !important;
        border: 1px solid #EAEAEA !important;
        border-radius: 10px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# Paramètres Enedis
TX_HORAIRE_DEFAUT = 14.18  
TX_RETENUE_HS = 0.067
MOIS_FR = {1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
           7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"}
JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# --- 2. FONCTIONS CORE ---
def nettoyer_dataframe(df):
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Date'])
    if 'Repas' in df.columns:
        df['Repas'] = pd.to_numeric(df['Repas'], errors='coerce').fillna(0)
    return df

@st.cache_resource
def connect_gsheets():
    return st.connection("gsheets", type=GSheetsConnection)

try:
    conn = connect_gsheets()
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    df_raw = conn.read(spreadsheet=url, ttl=0)
    if df_raw is not None:
        df_raw = nettoyer_dataframe(df_raw.dropna(how="all"))
    else:
        df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas", "H_50", "H_75", "H_100", "H_125"])
except:
    df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas", "H_50", "H_75", "H_100", "H_125"])

def calculer_session(date_j, debut, fin, t_base, feries):
    start, end = datetime.combine(date_j, debut), datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    g_tot, vent = 0, {50: 0.0, 75: 0.0, 100: 0.0, 125: 0.0}
    current, pas = start, 15
    while current < end:
        est_spé = (current.weekday() == 6 or current.date() in feries)
        h = current.hour
        est_nuit = (h >= 20 or h < 6)
        mult = (2.25 if est_nuit else 1.75) if est_spé else (2.00 if est_nuit else 1.50)
        maj = (125 if est_nuit else 75) if est_spé else (100 if est_nuit else 50)
        vent[maj] += (pas / 60); g_tot += (pas / 60) * (t_base * mult)
        current += timedelta(minutes=pas)
    
    nb_r = 0
    def check_p(s_p, e_p):
        is_s, is_e = max(start, datetime.combine(date_j, s_p)), min(end, datetime.combine(date_j, e_p))
        return (is_e - is_s).total_seconds()/3600 if is_e > is_s else 0
    if check_p(time(11,0), time(13,0)) >= 2.0: nb_r += 1
    if check_p(time(19,0), time(21,0)) >= 2.0: nb_r += 1
    return round((end-start).total_seconds()/3600, 2), round(g_tot, 2), nb_r, vent

# --- 3. INTERFACE ---
with st.sidebar:
    # AJOUT DU LOGO ENEDIS (Texte blanc car sidebar bleu Enedis)
    st.markdown("## ⚡ Enedis Focus Pro")
    st.write("---")
    taux_horaire = st.number_input("Taux Horaire de Référence (€)", value=TX_HORAIRE_DEFAUT, step=0.01)
    st.write("---")
    menu = st.radio("NAVIGATION", ["📊 Mon Tableau de Bord", "➕ Saisir une Intervention", "📝 Voir l'Historique"], label_visibility="collapsed")
    st.write("---")
    st.write("Calculateur d'Heures Supplémentaires IEG")

# --- MODE DASHBOARD ---
if "Dashboard" in menu:
    st.title("📊 Votre Tableau de Bord")
    if not df_raw.empty:
        df = df_raw.copy()
        df['Mois'] = df['Date'].dt.month
        sel_m_nom = st.selectbox("Mois à afficher", [MOIS_FR[m] for m in sorted(df['Mois'].unique(), reverse=True)])
        sel_m_num = [k for k, v in MOIS_FR.items() if v == sel_m_nom][0]
        df_m = df[df['Mois'] == sel_m_num]

        # Container des KPIs (Texte noir sur fond blanc garanti)
        with st.container():
            st.markdown('<div class="stBlock">', unsafe_allow_html=True)
            st.markdown("### Synthèse du mois")
            k1, k2, k3, k4 = st.columns(4)
            brut = df_m['Gain'].sum()
            # Métriques affichées en Bleu Enedis pour la valeur
            k1.metric("GAINS BRUTS", f"{brut:.2f} €")
            k2.metric("GAINS NETS (estim.)", f"{brut * (1 - TX_RETENUE_HS):.2f} €")
            k3.metric("HEURES SUPPLÉMENTAIRES", f"{df_m['Heures'].sum():.2f} h")
            k4.metric("REPAS REPAS", f"{int(df_m['Repas'].sum())}")
            st.markdown('</div>', unsafe_allow_html=True)

        st.write("### 📅 Détail jour par jour")
        df_m['Semaine'] = df_m['Date'].dt.isocalendar().week
        for s in sorted(df_m['Semaine'].unique(), reverse=True):
            df_s = df_m[df_m['Semaine'] == s].copy()
            b_s = df_s['Gain'].sum()
            with st.expander(f"SEMAINE {s} • Gains Bruts de la période : {b_s:.2f} €"):
                df_s['Jour'] = df_s['Date'].apply(lambda x: f"{JOURS_FR[x.weekday()]} {x.day}")
                # Affichage des tableaux en texte noir
                st.dataframe(df_s[['Jour', 'H_50', 'H_75', 'H_100', 'H_125', 'Gain', 'Repas']].set_index('Jour'), use_container_width=True)

# --- MODE SAISIE ---
elif "Saisir" in menu:
    st.title("➕ Enregistrer des heures")
    with st.container():
        st.markdown('<div class="stBlock">', unsafe_allow_html=True)
        st.markdown("### Nouvelle Intervention")
        st.write("Entrez vos horaires de début et de fin. L'application calcule automatiquement les majorations Enedis (nuit, dimanche, fériés).")
        with st.form("form_saisie", clear_on_submit=True):
            col_d, col_h1, col_h2 = st.columns(3)
            date_s = col_d.date_input("Date de l'intervention", datetime.now())
            h_deb = col_h1.time_input("Heure de début", time(10, 0))
            h_fin = col_h2.time_input("Heure de fin", time(14, 0))
            
            # Bouton de validation large
            submit = st.form_submit_button("AJOUTER AU COMPTEUR")
            
            if submit:
                h_t, g_t, r_t, v_t = calculer_session(date_s, h_deb, h_fin, taux_horaire, holidays.CountryHoliday("France"))
                new_data = pd.DataFrame([{"Date": date_s, "Heures": h_t, "Gain": g_t, "Taux_Base": taux_horaire, "Repas": r_t, **{f"H_{k}": v for k, v in v_t.items()}}])
                df_to_save = pd.concat([df_raw, new_data], ignore_index=True)
                df_to_save['Date'] = df_to_save['Date'].dt.strftime('%d/%m/%Y')
                conn.update(spreadsheet=url, data=df_to_save)
                st.success(f"Bravo ! Votre compteur de gains bruts a augmenté de {g_t} €.")
        st.markdown('</div>', unsafe_allow_html=True)

# --- MODE HISTORIQUE ---
elif "Voir l'Historique" in menu:
    st.title("📝 Gestion de vos données")
    st.info("Vous pouvez modifier une erreur directement dans le tableau ci-dessous et cliquer sur 'Sauvegarder'.")
    with st.container():
        st.markdown('<div class="stBlock">', unsafe_allow_html=True)
        if not df_raw.empty:
            df_edit = df_raw.copy().sort_values("Date", ascending=False)
            edited_df = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True, column_config={"Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY")})
            
            if st.button("SAUVEGARDER LES MODIFICATIONS"):
                edited_df['Date'] = pd.to_datetime(edited_df['Date']).dt.strftime('%d/%m/%Y')
                conn.update(spreadsheet=url, data=edited_df)
                st.success("Base de données synchronisée !")
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
