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

# --- FONCTION DE NETTOYAGE DES DATES ---
def harmoniser_dates(df):
    """Force toutes les dates du DataFrame au format datetime Python propre"""
    if 'Date' in df.columns:
        # On essaie d'abord le format ISO (AAAA-MM-JJ), puis le format FR (JJ/MM/AAAA)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        # Si après ça il reste des erreurs, on tente avec le format jour en premier
        mask = df['Date'].isna()
        if mask.any():
             df.loc[mask, 'Date'] = pd.to_datetime(df.loc[mask, 'Date'], dayfirst=True, errors='coerce')
        # On supprime les lignes où la date est vraiment illisible
        df = df.dropna(subset=['Date'])
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
        # NETTOYAGE CRUCIAL
        df_raw = harmoniser_dates(df_raw)
        
        # Vérification des colonnes
        for c in ['H_50', 'H_75', 'H_100', 'H_125', 'Taux_Base', 'Repas']:
            if c not in df_raw.columns: 
                df_raw[c] = 0.0 if 'H_' in c else ("Non" if c=='Repas' else 15.0)
    else:
        df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas", "H_50", "H_75", "H_100", "H_125"])
except Exception as e:
    st.error(f"⚠️ Erreur : {e}")
    df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain", "Taux_Base", "Repas", "H_50", "H_75", "H_100", "H_125"])

# --- 3. LOGIQUE DE CALCUL ---
def calculer_session_detaillee(date_j, debut, fin, t_base, feries):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    
    gain_total = 0
    ventilation = {50: 0.0, 75: 0.0, 100: 0.0, 125: 0.0}
    current = start
    pas = 15
    while current < end:
        est_special = (current.weekday() == 6 or current.date() in feries)
        h = current.hour
        est_nuit = (h >= 20 or h < 6)
        if est_special:
            maj = 125 if est_nuit else 75
            taux_mult = 2.25 if est_nuit else 1.75
        else:
            maj = 100 if est_nuit else 50
            taux_mult = 2.00 if est_nuit else 1.50
        ventilation[maj] += (pas / 60)
        gain_total += (pas / 60) * (t_base * taux_mult)
        current += timedelta(minutes=pas)
    
    repas_start, repas_end = datetime.combine(date_j, time(19, 0)), datetime.combine(date_j, time(21, 0))
    inter_start, inter_end = max(start, repas_start), min(end, repas_end)
    repas_valide = "Oui" if (inter_end > inter_start and (inter_end - inter_start).total_seconds()/3600 >= 2.0) else "Non"
            
    return round((end - start).total_seconds()/3600, 2), round(gain_total, 2), repas_valide, ventilation

# --- 4. INTERFACE ---
with st.sidebar:
    st.title("⏱️ Menu")
    taux_actuel = st.number_input("Taux horaire actuel (€)", value=15.0)
    pays = st.selectbox("Jours fériés", ["France", "Belgique", "Suisse"])
    feries_liste = holidays.CountryHoliday(pays)
    mode = st.radio("Navigation", ["Saisie", "Gestion", "Récapitulatif"])

# --- MODE : SAISIE ---
if mode == "Saisie":
    st.header("➕ Nouvelle Saisie")
    with st.form("f_saisie", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        d, h1, h2 = col1.date_input("Date", datetime.now()), col2.time_input("Début", time(18, 0)), col3.time_input("Fin", time(22, 0))
        if st.form_submit_button("Enregistrer"):
            h_tot, g_tot, repas, ventile = calculer_session_detaillee(d, h1, h2, taux_actuel, feries_liste)
            
            # On enregistre TOUJOURS en format texte AAAA-MM-JJ pour Google
            new_row = pd.DataFrame([{
                "Date": d.strftime('%Y-%m-%d'), 
                "Heures": h_tot, "Gain": g_tot, "Taux_Base": taux_actuel, "Repas": repas,
                "H_50": ventile[50], "H_75": ventile[75], "H_100": ventile[100], "H_125": ventile[125]
            }])
            
            # On prépare le DataFrame final en forçant le format texte pour la colonne Date
            df_final = pd.concat([df_raw, new_row], ignore_index=True)
            df_final['Date'] = pd.to_datetime(df_final['Date']).dt.strftime('%Y-%m-%d')
            
            conn.update(spreadsheet=url, data=df_final)
            st.success(f"Enregistré !")
            st.rerun()

# --- MODE : GESTION ---
elif mode == "Gestion":
    st.header("⚙️ Modifier / Supprimer")
    if not df_raw.empty:
        df_edit = df_raw.copy()
        # On s'assure que l'éditeur voit de vraies dates
        df_edit['Date'] = pd.to_datetime(df_edit['Date'])
        
        edited = st.data_editor(
            df_edit, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={"Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY")}
        )
        
        if st.button("Sauvegarder"):
            # Avant l'envoi, on re-transforme en texte ISO
            edited['Date'] = pd.to_datetime(edited['Date']).dt.strftime('%Y-%m-%d')
            conn.update(spreadsheet=url, data=edited)
            st.success("Données synchronisées")
            st.rerun()

# --- MODE : RÉCAPITULATIF ---
elif mode == "Récapitulatif":
    st.header("📊 Analyse Mensuelle")
    if not df_raw.empty:
        df = df_raw.copy()
        # On force la conversion pour le tri et le filtrage
        df['Date'] = pd.to_datetime(df['Date'])
        df['Année'], df['Mois_Num'], df['Semaine'] = df['Date'].dt.year, df['Date'].dt.month, df['Date'].dt.isocalendar().week
        
        sel_an = st.selectbox("📅 Année", sorted(df['Année'].unique(), reverse=True))
        df_ans = df[df['Année'] == sel_an]
        
        mois_dispo_num = sorted(df_ans['Mois_Num'].unique())
        sel_mois_nom = st.selectbox("🌙 Mois", [MOIS_FR[m] for m in mois_dispo_num])
        sel_m_num = [k for k, v in MOIS_FR.items() if v == sel_mois_nom][0]
        df_m = df_ans[df_ans['Mois_Num'] == sel_m_num]

        st.subheader(f"📈 {sel_mois_nom} {sel_an}")
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("H à 50%", f"{df_m['H_50'].sum()} h")
        v2.metric("H à 75%", f"{df_m['H_75'].sum()} h")
        v3.metric("H à 100%", f"{df_m['H_100'].sum()} h")
        v4.metric("H à 125%", f"{df_m['H_125'].sum()} h")
        
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Gains", f"{df_m['Gain'].sum():.2f} €")
        c2.metric("Heures", f"{df_m['Heures'].sum():.2f} h")
        c3.metric("Repas", len(df_m[df_m['Repas'] == "Oui"]))

        for s in sorted(df_m['Semaine'].unique()):
            df_s = df_m[df_m['Semaine'] == s].copy()
            with st.expander(f"Semaine {s} — {df_s['Gain'].sum():.2f} €"):
                df_s['Jour'] = df_s['Date'].apply(lambda x: f"{JOURS_FR[x.weekday()]} {x.day}")
                st.table(df_s[['Jour', 'H_50', 'H_75', 'H_100', 'H_125', 'Gain', 'Repas']].set_index('Jour'))
