import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import holidays
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
st.set_page_config(page_title="Gestion Heures Sup", page_icon="⏱️", layout="wide")

# --- CONNEXION ---
@st.cache_resource
def connect_gsheets():
    conn = st.connection("gsheets", type=GSheetsConnection)
    return conn

try:
    conn = connect_gsheets()
    url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    df_existant = conn.read(spreadsheet=url, ttl=0)
    if df_existant is not None:
        df_existant = df_existant.dropna(how="all")
        # Conversion de la colonne Date en datetime pour les calculs
        df_existant['Date'] = pd.to_datetime(df_existant['Date'])
    else:
        df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])
except Exception as e:
    st.error(f"⚠️ Erreur de connexion : {e}")
    df_existant = pd.DataFrame(columns=["Date", "Heures", "Gain"])

# --- LOGIQUE DE CALCUL ---
def calculer_gain_reglementaire(date_j, debut, fin, t_base, feries):
    start = datetime.combine(date_j, debut)
    end = datetime.combine(date_j, fin)
    if end <= start: end += timedelta(days=1)
    
    gain_total = 0
    current = start
    pas = 15 # On calcule par tranche de 15 min pour la précision
    
    while current < end:
        # Est-ce un dimanche ou férié ?
        est_special = (current.weekday() == 6 or current.date() in feries)
        # Est-ce la nuit (20h - 06h) ?
        h = current.hour
        est_nuit = (h >= 20 or h < 6)
        
        # Application des taux
        if est_special:
            taux = 2.25 if est_nuit else 1.75 # 125% ou 75% de majoration
        else:
            taux = 2.00 if est_nuit else 1.50 # 100% ou 50% de majoration
            
        gain_total += (pas / 60) * (t_base * taux)
        current += timedelta(minutes=pas)
        
    duree = (end - start).total_seconds() / 3600
    return round(duree, 2), round(gain_total, 2)

# --- INTERFACE : BARRE LATÉRALE ---
with st.sidebar:
    st.title("⚙️ Réglages")
    t_base = st.number_input("Taux horaire de base (€)", value=15.0)
    pays = st.selectbox("Pays pour jours fériés", ["France", "Belgique", "Suisse"])
    feries_liste = holidays.CountryHoliday(pays)
    
    st.divider()
    mode = st.radio("Aller vers :", ["Saisie", "Historique & Gestion", "Récapitulatif"])

# --- MODE 1 : SAISIE ---
if mode == "Saisie":
    st.header("➕ Nouvelle Saisie")
    with st.form("form_saisie", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        d = col1.date_input("Date", datetime.now())
        h1 = col2.time_input("Début", time(18, 0))
        h2 = col3.time_input("Fin", time(22, 0))
        
        if st.form_submit_button("Enregistrer la session"):
            h_tot, g_tot = calculer_gain_reglementaire(d, h1, h2, t_base, feries_liste)
            nouvelle_ligne = pd.DataFrame([{"Date": pd.to_datetime(d), "Heures": h_tot, "Gain": g_tot}])
            df_final = pd.concat([df_existant, nouvelle_ligne], ignore_index=True)
            conn.update(spreadsheet=url, data=df_final)
            st.success(f"Enregistré : {h_tot}h pour un gain de {g_tot}€")
            st.rerun()

# --- MODE 2 : HISTORIQUE & GESTION ---
elif mode == "Historique & Gestion":
    st.header("📝 Historique et Modifications")
    if not df_existant.empty:
        # Formatage pour affichage en français
        df_display = df_existant.copy()
        df_display['Date_FR'] = df_display['Date'].dt.strftime('%d/%m/%Y')
        
        # Utilisation de data_editor pour modifier ou supprimer
        st.subheader("Modifier directement dans le tableau :")
        edited_df = st.data_editor(
            df_display[['Date', 'Heures', 'Gain']], 
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "Heures": st.column_config.NumberColumn("Heures", format="%.2f h"),
                "Gain": st.column_config.NumberColumn("Gain", format="%.2f €")
            }
        )
        
        if st.button("Sauvegarder les modifications"):
            conn.update(spreadsheet=url, data=edited_df)
            st.success("Données mises à jour !")
            st.rerun()
    else:
        st.info("Aucune donnée enregistrée.")

# --- MODE 3 : RÉCAPITULATIF ---
elif mode == "Récapitulatif":
    st.header("📊 Récapitulatif des Gains")
    if not df_existant.empty:
        df_existant['Semaine'] = df_existant['Date'].dt.isocalendar().week
        df_existant['Mois'] = df_existant['Date'].dt.strftime('%B %Y')
        df_existant['Année'] = df_existant['Date'].dt.year

        c1, c2, c3 = st.columns(3)
        
        with c1:
            st.metric("Total Année", f"{df_existant['Gain'].sum():.2f} €")
        with c2:
            mois_actuel = datetime.now().strftime('%B %Y')
            gain_mois = df_existant[df_existant['Mois'] == mois_actuel]['Gain'].sum()
            st.metric(f"Mois ({mois_actuel})", f"{gain_mois:.2f} €")
        with c3:
            sem_actuelle = datetime.now().isocalendar()[1]
            gain_sem = df_existant[df_existant['Semaine'] == sem_actuelle]['Gain'].sum()
            st.metric("Semaine Actuelle", f"{gain_sem:.2f} €")

        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Gains par Mois")
            recap_mois = df_existant.groupby('Mois')['Gain'].sum()
            st.bar_chart(recap_mois)
        with col_b:
            st.subheader("Heures par Semaine")
            recap_sem = df_existant.groupby('Semaine')['Heures'].sum()
            st.line_chart(recap_sem)
