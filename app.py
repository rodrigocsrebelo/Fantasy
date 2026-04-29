import os
from datetime import datetime
import pandas as pd
import streamlit as st

# =========================
# Config
# =========================
st.set_page_config(page_title="Fantasy Mundial", layout="wide")

DATA_FILE = "data.xlsx"

# Password do Admin:
# - Podes definir em .streamlit/secrets.toml como:
#   ADMIN_PASSWORD="a_tua_password"
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD", "admin"))

# Regras default (se a sheet "Regras" não existir/estiver estranha)
DEFAULT_RULES = {
    "Resultado Exato": 10,
    "Acertar Vencedor/Empate": 4,
    "Acertar Golos Marcados (uma equipa)": 1
}

# =========================
# Helpers - Leitura robusta (algumas sheets podem ter uma linha "## ...")
# =========================
def read_sheet_robust(file_path: str, sheet_name: str, expected_cols=None) -> pd.DataFrame:
    """
    Lê uma sheet do Excel e tenta adaptar-se caso exista uma linha inicial tipo '## ...'.
    """
    expected_cols = expected_cols or []
    # Tentativa normal
    df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
    if expected_cols and not set(expected_cols).issubset(set(df.columns)):
        # Tentativa com header na linha seguinte
        df2 = pd.read_excel(file_path, sheet_name=sheet_name, header=1, engine="openpyxl")
        if set(expected_cols).issubset(set(df2.columns)):
            return df2
    return df


@st.cache_data(show_spinner=False)
def load_all_data():
    equipas = read_sheet_robust(
        DATA_FILE, "Equipas",
        expected_cols=["ID_Participante", "Nome_Participante", "Nome_Equipa"]
    )
    jogos = read_sheet_robust(
        DATA_FILE, "Jogos",
        expected_cols=["ID_Jogo", "Data", "Fase", "Cidade", "Equipa_A", "Equipa_B"]
    )
    apostas = read_sheet_robust(
        DATA_FILE, "Apostas",
        expected_cols=["ID_Aposta", "ID_Participante", "ID_Jogo", "Aposta_Golos_A", "Aposta_Golos_B"]
    )
    resultados = read_sheet_robust(
        DATA_FILE, "Resultados",
        expected_cols=["ID_Jogo", "Resultado_Golos_A", "Resultado_Golos_B"]
    )
    regras = None
    try:
        regras = read_sheet_robust(DATA_FILE, "Regras", expected_cols=["Condicao", "Pontos"])
    except Exception:
        regras = pd.DataFrame({"Condicao": list(DEFAULT_RULES.keys()), "Pontos": list(DEFAULT_RULES.values())})

    # Normalizações
    # Datas de jogos
    if "Data" in jogos.columns:
        jogos["Data"] = pd.to_datetime(jogos["Data"], errors="coerce")

    # Garantir que colunas numéricas são numéricas (apostas/resultados podem vir como object)
    for col in ["Aposta_Golos_A", "Aposta_Golos_B"]:
        if col in apostas.columns:
            apostas[col] = pd.to_numeric(apostas[col], errors="coerce")

    for col in ["Resultado_Golos_A", "Resultado_Golos_B"]:
        if col in resultados.columns:
            resultados[col] = pd.to_numeric(resultados[col], errors="coerce")

    return equipas, jogos, apostas, resultados, regras


def save_sheets_to_excel(apostas_df: pd.DataFrame, resultados_df: pd.DataFrame):
    """
    Escreve apenas as sheets 'Apostas' e 'Resultados' no mesmo data.xlsx, substituindo-as.
    Mantém as restantes sheets.
    """
    # Lemos o workbook existente e substituímos sheets específicas
    with pd.ExcelWriter(DATA_FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        apostas_df.to_excel(writer, sheet_name="Apostas", index=False)
        resultados_df.to_excel(writer, sheet_name="Resultados", index=False)


def get_rules_dict(regras_df: pd.DataFrame) -> dict:
    rules = DEFAULT_RULES.copy()
    if regras_df is not None and {"Condicao", "Pontos"}.issubset(regras_df.columns):
        for _, row in regras_df.iterrows():
            cond = str(row["Condicao"]).strip()
            try:
                pts = int(row["Pontos"])
                rules[cond] = pts
            except Exception:
                pass
    return rules


def match_sign(a: float, b: float) -> int:
    """1 se A ganha, 0 se empate, -1 se B ganha"""
    if a > b:
        return 1
    if a == b:
        return 0
    return -1


def calc_points(ap_a, ap_b, res_a, res_b, rules: dict) -> int:
    """
    Regras:
      - Exato: 10 (substitui tudo)
      - Acertar vencedor/empate: 4
      - +1 se acertar golos de A
      - +1 se acertar golos de B
    """
    if pd.isna(ap_a) or pd.isna(ap_b) or pd.isna(res_a) or pd.isna(res_b):
        return 0

    ap_a, ap_b, res_a, res_b = int(ap_a), int(ap_b), int(res_a), int(res_b)

    exato = rules.get("Resultado Exato", 10)
    vencedor = rules.get("Acertar Vencedor/Empate", 4)
    golos_eq = rules.get("Acertar Golos Marcados (uma equipa)", 1)

    if ap_a == res_a and ap_b == res_b:
        return exato

    pts = 0
    if match_sign(ap_a, ap_b) == match_sign(res_a, res_b):
        pts += vencedor

    # 1 ponto por equipa (A e B)
    if ap_a == res_a:
        pts += golos_eq
    if ap_b == res_b:
        pts += golos_eq

    return pts


def format_game_row(row):
    date_str = row["Data"].strftime("%d/%m/%Y") if pd.notna(row["Data"]) else "—"
    return f'#{int(row["ID_Jogo"])} • {date_str} • {row["Fase"]} • {row["Equipa_A"]} vs {row["Equipa_B"]} ({row["Cidade"]})'


# =========================
# App - Carregar dados
# =========================
equipas_df, jogos_df, apostas_df, resultados_df, regras_df = load_all_data()
rules = get_rules_dict(regras_df)

# =========================
# Sidebar - Login simples (selectbox)
# =========================
st.sidebar.title("Login")
user_name = st.sidebar.selectbox("Escolhe o teu nome", equipas_df["Nome_Participante"].dropna().unique())

# Guardar sessão
if "user_name" not in st.session_state:
    st.session_state.user_name = user_name
else:
    st.session_state.user_name = user_name

# Obter ID do participante
user_row = equipas_df.loc[equipas_df["Nome_Participante"] == st.session_state.user_name].head(1)
if user_row.empty:
    st.error("Utilizador não encontrado no ficheiro de participantes.")
    st.stop()

user_id = int(user_row["ID_Participante"].iloc[0])
user_team = str(user_row["Nome_Equipa"].iloc[0]) if "Nome_Equipa" in user_row.columns else ""

st.sidebar.success(f"👤 {st.session_state.user_name}  |  🛡️ {user_team}")

menu = st.sidebar.radio("Menu", ["Apostas", "Resultados", "Ranking"])

# =========================
# Menu: Apostas
# =========================
if menu == "Apostas":
    st.title("📝 Apostas")
    st.caption("Faz a tua aposta por jogo (podes editar e guardar novamente).")

    # Filtros
    colf1, colf2, colf3 = st.columns([1, 1, 1])

    fases = ["(todas)"] + sorted([x for x in jogos_df["Fase"].dropna().unique()])
    with colf1:
        fase_sel = st.selectbox("Filtrar por Fase", fases)

    with colf2:
        datas = jogos_df["Data"].dropna().dt.date.unique()
        datas = sorted(list(datas))
        data_options = ["(todas)"] + [d.strftime("%d/%m/%Y") for d in datas]
        data_sel = st.selectbox("Filtrar por Data", data_options)

    with colf3:
        equipas = sorted(pd.unique(jogos_df[["Equipa_A", "Equipa_B"]].values.ravel("K")))
        equipas = ["(todas)"] + [e for e in equipas if pd.notna(e)]
        equipa_sel = st.selectbox("Filtrar por Equipa", equipas)

    # Aplicar filtros
    jogos_view = jogos_df.copy()
    if fase_sel != "(todas)":
        jogos_view = jogos_view[jogos_view["Fase"] == fase_sel]
    if data_sel != "(todas)":
        d = datetime.strptime(data_sel, "%d/%m/%Y").date()
        jogos_view = jogos_view[jogos_view["Data"].dt.date == d]
    if equipa_sel != "(todas)":
        jogos_view = jogos_view[(jogos_view["Equipa_A"] == equipa_sel) | (jogos_view["Equipa_B"] == equipa_sel)]

    jogos_view = jogos_view.sort_values(["Data", "ID_Jogo"])

    # Minhas apostas (para mostrar/usar como default)
    minhas = apostas_df[apostas_df["ID_Participante"] == user_id].copy()
    minhas_map = {
        int(r["ID_Jogo"]): (r["Aposta_Golos_A"], r["Aposta_Golos_B"], int(r["ID_Aposta"]))
        for _, r in minhas.dropna(subset=["ID_Jogo"]).iterrows()
    }

    st.subheader("Jogos")
    if jogos_view.empty:
        st.info("Não há jogos com esses filtros.")
    else:
        for _, game in jogos_view.iterrows():
            game_id = int(game["ID_Jogo"])
            label = format_game_row(game)
            with st.expander(label, expanded=False):
                # defaults se já houver aposta
                default_a, default_b = 0, 0
                aposta_id_existente = None
                if game_id in minhas_map:
                    default_a = int(minhas_map[game_id][0]) if pd.notna(minhas_map[game_id][0]) else 0
                    default_b = int(minhas_map[game_id][1]) if pd.notna(minhas_map[game_id][1]) else 0
                    aposta_id_existente = int(minhas_map[game_id][2])

                c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
                with c1:
                    st.markdown(f"**{game['Equipa_A']}**")
                    gols_a = st.number_input(
                        "Golos A",
                        min_value=0, max_value=20, value=default_a,
                        key=f"bet_a_{game_id}"
                    )
                with c2:
                    st.markdown("vs")
                with c3:
                    st.markdown(f"**{game['Equipa_B']}**")
                    gols_b = st.number_input(
                        "Golos B",
                        min_value=0, max_value=20, value=default_b,
                        key=f"bet_b_{game_id}"
                    )

                with c4:
                    if aposta_id_existente:
                        st.info("Já tens uma aposta guardada — ao guardar vais atualizar.")
                    else:
                        st.info("Ainda não apostaste neste jogo.")

                    if st.button("💾 Guardar aposta", key=f"save_bet_{game_id}"):
                        # Recarregar os dados para evitar sobrescrever com cache antigo
                        equipas_df2, jogos_df2, apostas_df2, resultados_df2, regras_df2 = load_all_data()

                        # Ver se já existe aposta
                        mask = (apostas_df2["ID_Participante"] == user_id) & (apostas_df2["ID_Jogo"] == game_id)
                        if mask.any():
                            apostas_df2.loc[mask, "Aposta_Golos_A"] = int(gols_a)
                            apostas_df2.loc[mask, "Aposta_Golos_B"] = int(gols_b)
                        else:
                            next_id = 1
                            if "ID_Aposta" in apostas_df2.columns and not apostas_df2["ID_Aposta"].dropna().empty:
                                next_id = int(apostas_df2["ID_Aposta"].max()) + 1

                            new_row = {
                                "ID_Aposta": next_id,
                                "ID_Participante": user_id,
                                "ID_Jogo": game_id,
                                "Aposta_Golos_A": int(gols_a),
                                "Aposta_Golos_B": int(gols_b),
                            }
                            apostas_df2 = pd.concat([apostas_df2, pd.DataFrame([new_row])], ignore_index=True)

                        save_sheets_to_excel(apostas_df2, resultados_df2)
                        st.success("Aposta guardada com sucesso ✅")

                        # limpar cache para refletir logo
                        st.cache_data.clear()
                        st.rerun()

    st.divider()
    st.subheader("📌 As minhas apostas")
    # Mostra apostas do utilizador com info do jogo
    minhas2 = apostas_df[apostas_df["ID_Participante"] == user_id].merge(
        jogos_df[["ID_Jogo", "Data", "Fase", "Equipa_A", "Equipa_B"]],
        on="ID_Jogo",
        how="left"
    )
    if minhas2.empty:
        st.write("Ainda não tens apostas.")
    else:
        minhas2 = minhas2.sort_values(["Data", "ID_Jogo"])
        show = minhas2[["ID_Jogo", "Data", "Fase", "Equipa_A", "Equipa_B", "Aposta_Golos_A", "Aposta_Golos_B"]].copy()
        show["Data"] = show["Data"].dt.strftime("%d/%m/%Y")
        st.dataframe(show, use_container_width=True)


# =========================
# Menu: Resultados (Admin)
# =========================
elif menu == "Resultados":
    st.title("📊 Resultados (Admin)")
    st.caption("Inserção/edição de resultados reais. Protegido por password.")

    pwd = st.text_input("Password de Admin", type="password")
    if pwd != ADMIN_PASSWORD:
        st.warning("Acesso restrito. Introduz a password correta.")
        st.stop()

    # Mostrar jogos e estado (com/sem resultado)
    res_map = resultados_df.set_index("ID_Jogo")[["Resultado_Golos_A", "Resultado_Golos_B"]].to_dict("index")

    jogos_admin = jogos_df.sort_values(["Data", "ID_Jogo"]).copy()
    jogos_admin["TemResultado"] = jogos_admin["ID_Jogo"].apply(
        lambda x: (x in res_map) and pd.notna(res_map[x]["Resultado_Golos_A"]) and pd.notna(res_map[x]["Resultado_Golos_B"])
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        jogo_sel = st.selectbox(
            "Escolhe o jogo",
            jogos_admin["ID_Jogo"].tolist(),
            format_func=lambda gid: format_game_row(jogos_admin[jogos_admin["ID_Jogo"] == gid].iloc[0])
        )
    with col2:
        st.metric("Jogos com resultado", int(jogos_admin["TemResultado"].sum()))

    game = jogos_admin[jogos_admin["ID_Jogo"] == jogo_sel].iloc[0]
    gid = int(game["ID_Jogo"])

    # defaults
    default_ra, default_rb = 0, 0
    if gid in res_map:
        if pd.notna(res_map[gid]["Resultado_Golos_A"]):
            default_ra = int(res_map[gid]["Resultado_Golos_A"])
        if pd.notna(res_map[gid]["Resultado_Golos_B"]):
            default_rb = int(res_map[gid]["Resultado_Golos_B"])

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        st.markdown(f"**{game['Equipa_A']}**")
        ra = st.number_input("Golos A (real)", min_value=0, max_value=20, value=default_ra, key="res_a")
    with c2:
        st.markdown(f"**{game['Equipa_B']}**")
        rb = st.number_input("Golos B (real)", min_value=0, max_value=20, value=default_rb, key="res_b")

    with c3:
        st.write("")
        st.write("")
        if st.button("💾 Guardar resultado"):
            # Recarregar para evitar conflitos com cache
            equipas_df2, jogos_df2, apostas_df2, resultados_df2, regras_df2 = load_all_data()

            # garantir linha existe
            if (resultados_df2["ID_Jogo"] == gid).any():
                resultados_df2.loc[resultados_df2["ID_Jogo"] == gid, "Resultado_Golos_A"] = int(ra)
                resultados_df2.loc[resultados_df2["ID_Jogo"] == gid, "Resultado_Golos_B"] = int(rb)
            else:
                new_row = {"ID_Jogo": gid, "Resultado_Golos_A": int(ra), "Resultado_Golos_B": int(rb)}
                resultados_df2 = pd.concat([resultados_df2, pd.DataFrame([new_row])], ignore_index=True)

            save_sheets_to_excel(apostas_df2, resultados_df2)
            st.success("Resultado guardado ✅")
            st.cache_data.clear()
            st.rerun()

    st.divider()
    st.subheader("📋 Estado dos resultados")
    status = jogos_admin[["ID_Jogo", "Data", "Fase", "Equipa_A", "Equipa_B", "TemResultado"]].copy()
    status["Data"] = status["Data"].dt.strftime("%d/%m/%Y")
    status["TemResultado"] = status["TemResultado"].apply(lambda x: "✅" if x else "—")
    st.dataframe(status, use_container_width=True)


# =========================
# Menu: Ranking
# =========================
elif menu == "Ranking":
    st.title("🏆 Ranking")
    st.caption("Ranking calculado a partir de apostas e resultados inseridos.")

    # Jogos com resultados completos
    resultados_ok = resultados_df.dropna(subset=["Resultado_Golos_A", "Resultado_Golos_B"]).copy()
    if resultados_ok.empty:
        st.info("Ainda não há resultados inseridos. Vai a 'Resultados' (Admin) para adicionar.")
        st.stop()

    # Junta apostas + resultados
    bets = apostas_df.merge(resultados_ok, on="ID_Jogo", how="inner")

    if bets.empty:
        st.info("Ainda não há apostas associadas a jogos com resultados.")
        st.stop()

    # Calcular pontos
    bets["Pontos"] = bets.apply(
        lambda r: calc_points(
            r["Aposta_Golos_A"], r["Aposta_Golos_B"],
            r["Resultado_Golos_A"], r["Resultado_Golos_B"],
            rules
        ),
        axis=1
    )

    # Juntar nome participante e info do jogo
    bets = bets.merge(equipas_df[["ID_Participante", "Nome_Participante", "Nome_Equipa"]], on="ID_Participante", how="left")
    bets = bets.merge(jogos_df[["ID_Jogo", "Data", "Fase", "Equipa_A", "Equipa_B"]], on="ID_Jogo", how="left")

    # Ranking por participante
    ranking = bets.groupby(["ID_Participante", "Nome_Participante", "Nome_Equipa"], as_index=False)["Pontos"].sum()
    ranking = ranking.sort_values(["Pontos", "Nome_Participante"], ascending=[False, True])
    ranking.insert(0, "Posição", range(1, len(ranking) + 1))

    st.subheader("📌 Tabela de Ranking")
    st.dataframe(ranking, use_container_width=True)

    st.divider()
    st.subheader("🔎 Detalhe por jogo (opcional)")
    with st.expander("Ver detalhe de pontuação por aposta"):
        det = bets[[
            "Nome_Participante", "Nome_Equipa", "ID_Jogo", "Data", "Fase",
            "Equipa_A", "Equipa_B",
            "Aposta_Golos_A", "Aposta_Golos_B",
            "Resultado_Golos_A", "Resultado_Golos_B",
            "Pontos"
        ]].copy()
        det["Data"] = det["Data"].dt.strftime("%d/%m/%Y")
        det = det.sort_values(["Data", "ID_Jogo", "Nome_Participante"])
        st.dataframe(det, use_container_width=True)

    st.divider()
    st.subheader("ℹ️ Regras em vigor")
    st.write(rules)
