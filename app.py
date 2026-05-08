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
        # On force la conversion en s'assurant que le jour est bien interprété en premier
        df_raw['Date'] = pd.to_datetime(df_raw['Date'], dayfirst=True, errors='coerce')
    else:
        df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain"])
except Exception as e:
    st.error(f"⚠️ Erreur : {e}")
    df_raw = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# --- 3. LOGIQUE DE CALCUL ---
def calculer_gain(date_j, debut, fin, t_base, feries):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    gain_total, current, pas = 0, start, 15
    while current < end:
        est_special = (current.weekday() == 6 or current.date() in feries)
        h = current.hour
        est_nuit = (h >= 20 or h < 6)
        taux = (2.25 if est_nuit else 1.75) if est_special else (2.00 if est_nuit else 1.50)
        gain_total += (pas / 60) * (t_base * taux)
        current += timedelta(minutes=pas)
    return round((end - start).total_seconds() / 3600, 2), round(gain_total, 2)

# --- 4. INTERFACE ---
with st.sidebar:
    st.title("⏱️ Menu")
    t_base = st.number_input("Taux horaire (€)", value=15.0)
    pays = st.selectbox("Jours fériés", ["France", "Belgique", "Suisse"])
    feries_liste = holidays.CountryHoliday(pays)
    mode = st.radio("Navigation", ["Saisie", "Gestion", "Récapitulatif Détaillé"])

# --- MODE : SAISIE ---
if mode == "Saisie":
    st.header("➕ Ajouter des Heures")
    with st.form("f_saisie", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        d = col1.date_input("Date", datetime.now())
        h1 = col2.time_input("Début", time(18, 0))
        h2 = col3.time_input("Fin", time(22, 0))
        if st.form_submit_button("Enregistrer"):
            h_tot, g_tot = calculer_gain(d, h1, h2, t_base, feries_liste)
            # ON FORCE LE FORMAT ISO ICI (YYYY-MM-DD)
            new_row = pd.DataFrame([{"Date": d.strftime('%Y-%m-%d'), "Heures": h_tot, "Gain": g_tot}])
            df_raw['Date'] = df_raw['Date'].dt.strftime('%Y-%m-%d') # On uniformise l'existant
            df_final = pd.concat([df_raw, new_row], ignore_index=True)
            conn.update(spreadsheet=url, data=df_final)
            st.success("Validé !")
            st.rerun()

# --- MODE : GESTION ---
elif mode == "Gestion":
    st.header("⚙️ Modifier / Supprimer")
    if not df_raw.empty:
        # On prépare pour l'éditeur
        df_edit = df_raw.copy()
        df_edit['Date'] = pd.to_datetime(df_edit['Date'])
        
        edited = st.data_editor(
            df_edit, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={"Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY")}
        )
        
        if st.button("Sauvegarder les changements"):
            # On reconvertit en texte ISO avant d'envoyer à Google
            edited['Date'] = pd.to_datetime(edited['Date']).dt.strftime('%Y-%m-%d')
            conn.update(spreadsheet=url, data=edited)
            st.success("Mise à jour réussie")
            st.rerun()

# --- MODE : RÉCAPITULATIF DÉTAILLÉ ---
elif mode == "Récapitulatif Détaillé":
    st.header("📊 Analyse des revenus")
    if not df_raw.empty:
        df = df_raw.copy()
        df['Date'] = pd.to_datetime(df['Date'])
        df['Année'] = df['Date'].dt.year
        df['Mois_Num'] = df['Date'].dt.month
        df['Semaine'] = df['Date'].dt.isocalendar().week
        
        c1, c2 = st.columns(2)
        with c1:
            list_ans = sorted(df['Année'].unique(), reverse=True)
            sel_an = st.selectbox("📅 Année", list_ans)
            df_ans = df[df['Année'] == sel_an]
        with c2:
            list_mois_num = sorted(df_ans['Mois_Num'].unique())
            list_mois_nom = [MOIS_FR[m] for m in list_mois_num]
            sel_mois_nom = st.selectbox("🌙 Mois", list_mois_nom)
            sel_m_num = [k for k, v in MOIS_FR.items() if v == sel_mois_nom][0]
            df_m = df_ans[df_ans['Mois_Num'] == sel_m_num]

        st.divider()
        st.metric(f"Total {sel_mois_nom}", f"{df_m['Gain'].sum():.2f} €")

        st.subheader("📁 Détail par semaine")
        sems = sorted(df_m['Semaine'].unique())
        for s in sems:
            df_s = df_m[df_m['Semaine'] == s].copy()
            total_s = df_s['Gain'].sum()
            with st.expander(f"Semaine {s} — Total : {total_s:.2f} €"):
                df_s['Jour'] = df_s['Date'].apply(lambda x: f"{JOURS_FR[x.weekday()]} {x.day}")
                st.table(df_s[['Jour', 'Heures', 'Gain']].set_index('Jour'))
