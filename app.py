import streamlit as st
import pandas as pd

st.set_page_config(page_title="Fantasy Mundial", layout="wide")

# --- CARREGAR PARTICIPANTES ---
users_df = pd.read_excel("data.xlsx")

# --- LOGIN SIMPLES ---
st.sidebar.title("Login")

user = st.sidebar.selectbox("Escolhe o teu nome", users_df["Nome_Participante"])

if "user" not in st.session_state:
    st.session_state.user = user

st.session_state.user = user

st.sidebar.success(f"👤 {st.session_state.user}")

# --- MENU ---
menu = st.sidebar.radio("Menu", ["Apostas", "Resultados", "Ranking"])

# --- FICHEIROS ---
APOSTAS_FILE = "apostas.xlsx"
RESULTS_FILE = "resultados.xlsx"


# ========================
# 📝 APOSTAS
# ========================
if menu == "Apostas":

    st.title("📝 Inserir Apostas")

    jogo = st.text_input("Jogo (ex: Portugal vs Espanha)")
    resultado = st.text_input("Resultado (ex: 2-1)")

    if st.button("Guardar aposta"):
        try:
            df = pd.read_excel(APOSTAS_FILE)
        except:
            df = pd.DataFrame(columns=["user", "jogo", "resultado"])

        # evitar duplicados
        df = df[~((df.user == st.session_state.user) & (df.jogo == jogo))]

        new = pd.DataFrame({
            "user": [st.session_state.user],
            "jogo": [jogo],
            "resultado": [resultado]
        })

        df = pd.concat([df, new], ignore_index=True)
        df.to_excel(APOSTAS_FILE, index=False)

        st.success("Aposta guardada!")

    # ver apostas
    try:
        df = pd.read_excel(APOSTAS_FILE)
        st.subheader("📊 As tuas apostas")
        st.dataframe(df[df.user == st.session_state.user])
    except:
        st.info("Sem apostas ainda")


# ========================
# 📊 RESULTADOS (ADMIN)
# ========================
elif menu == "Resultados":

    st.title("📊 Resultados Oficiais")

    if st.session_state.user != users_df["Nome_Participante"].iloc[0]:
        st.warning("Só o primeiro utilizador pode inserir resultados (admin)")
        st.stop()

    jogo = st.text_input("Jogo")
    real = st.text_input("Resultado real")

    if st.button("Guardar resultado"):
        try:
            df = pd.read_excel(RESULTS_FILE)
        except:
            df = pd.DataFrame(columns=["jogo", "real"])

        df = df[df.jogo != jogo]

        new = pd.DataFrame({
            "jogo": [jogo],
            "real": [real]
        })

        df = pd.concat([df, new], ignore_index=True)
        df.to_excel(RESULTS_FILE, index=False)

        st.success("Resultado guardado!")

    try:
        df = pd.read_excel(RESULTS_FILE)
        st.dataframe(df)
    except:
        st.info("Sem resultados ainda")


# ========================
# 🏆 RANKING
# ========================
elif menu == "Ranking":

    st.title("🏆 Ranking")

    def pontos(aposta, real):
        if aposta == real:
            return 3
        try:
            a1,a2 = map(int, aposta.split("-"))
            r1,r2 = map(int, real.split("-"))
        except:
            return 0

        if (a1>a2 and r1>r2) or (a1<a2 and r1<r2) or (a1==a2 and r1==r2):
            return 1
        return 0

    try:
        bets = pd.read_excel(APOSTAS_FILE)
        results = pd.read_excel(RESULTS_FILE)

        df = bets.merge(results, on="jogo", how="left")
        df["pontos"] = df.apply(lambda x: pontos(x["resultado"], x["real"]), axis=1)

        ranking = df.groupby("user")["pontos"].sum().reset_index()
        ranking = ranking.sort_values(by="pontos", ascending=False)

        st.dataframe(ranking)
        st.bar_chart(ranking.set_index("user"))

    except:
        st.warning("Ainda não há dados suficientes")