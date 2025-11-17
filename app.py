import random
import unicodedata
import pandas as pd
import streamlit as st
from streamlit.components.v1 import html

# ============================================================
#                 CONFIGURACIÓN DE PÁGINA
# ============================================================
st.set_page_config(
    page_title="Conjugazioni - TomiSampietro",
    page_icon="🇮🇹",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
#                   CARGAR CSS EXTERNO
# ============================================================
try:
    with open("style.css", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except Exception as e:
    st.error(f"⚠️ Error cargando style.css: {e}")

# ============================================================
#                     CARGA DE CSV
# ============================================================
@st.cache_data
def load_data(path: str = "conjugazioni.csv") -> pd.DataFrame:
    return pd.read_csv(path)


df = load_data()

# ============================================================
#          LIMPIEZA DEL CSV + ORDEN DE PRONOMBRES
# ============================================================

# Orden fijo Ferrari F1 😉
PRON_ORDER = ["Io", "Tu", "Lui", "Lei", "Noi", "Voi", "Loro"]

# Eliminar femenino
df = df[df["Genere"] != "F"].copy()

# Eliminar 'Lei' (si querías eliminarlo para Allenamento)
df = df[df["Pronombre"] != "Lei"].copy()

# Configurar orden categórico de pronombres
df["Pronombre"] = pd.Categorical(df["Pronombre"], categories=PRON_ORDER, ordered=True)

# Asegurar limpieza básica
for col in ["Modo", "Tiempo", "Nombre", "Pronombre", "Genere"]:
    df[col] = df[col].astype(str).str.strip()

# ============================================================
#                        VERBOS
# ============================================================
VERB_COLUMNS = {
    "essere": "essere",
    "avere": "avere",
    "mangiare": "mangiare",
    "credere": "credere",
    "dormire": "dormire",
}

# ============================================================
#                 FUNCIONES AUXILIARES
# ============================================================
def normalize(text: str) -> str:
    """Normaliza texto para comparar acentos."""
    text = str(text).strip()
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()


def new_question() -> None:
    """Genera una nueva pregunta según los filtros actuales."""
    df_filtered = df.copy()

    # filtros de sesión (Allenamento)
    if st.session_state["selected_modes"]:
        df_filtered = df_filtered[df_filtered["Modo"].isin(st.session_state["selected_modes"])]

    if st.session_state["selected_tiempos"]:
        df_filtered = df_filtered[df_filtered["Tiempo"].isin(st.session_state["selected_tiempos"])]

    if st.session_state["selected_genere"] != "Ambos":
        df_filtered = df_filtered[df_filtered["Genere"] == st.session_state["selected_genere"]]

    if df_filtered.empty:
        st.session_state["question"] = None
        return

    row = df_filtered.sample(1).iloc[0]
    verb = random.choice(st.session_state["selected_verbs"])
    col = VERB_COLUMNS[verb]

    st.session_state["question"] = {
        "tiempo": row["Tiempo"],
        "nombre": row["Nombre"],
        "modo": row["Modo"],
        "pronombre": row["Pronombre"],
        "verb": verb,
        "correct": row[col],
        "genere": row["Genere"],
    }
    st.session_state["feedback"] = ""
    st.session_state["validated"] = False


# ============================================================
#               INICIALIZACIÓN DE ESTADO
# ============================================================
if "score" not in st.session_state:
    st.session_state["score"] = 0
    st.session_state["questions"] = 0

if "selected_verbs" not in st.session_state:
    st.session_state["selected_verbs"] = list(VERB_COLUMNS.keys())

if "selected_modes" not in st.session_state:
    st.session_state["selected_modes"] = sorted(df["Modo"].unique())

if "selected_tiempos" not in st.session_state:
    st.session_state["selected_tiempos"] = sorted(df["Tiempo"].unique())

if "selected_genere" not in st.session_state:
    st.session_state["selected_genere"] = "Ambos"

if "question" not in st.session_state:
    new_question()

if "feedback" not in st.session_state:
    st.session_state["feedback"] = ""
if "validated" not in st.session_state:
    st.session_state["validated"] = False

# ============================================================
#                SELECTOR DE SECCIÓN (SIDEBAR)
# ============================================================
st.sidebar.markdown("### 🎯 Modalità")
page = st.sidebar.radio(
    "",
    ["Allenamento", "Ripasso"],
    index=0,
)

st.sidebar.markdown("---")

# ============================================================
#                     PAGINA: ALLENAMENTO
# ============================================================
if page == "Allenamento":
    # -------------------- CONTROLES SIDEBAR --------------------
    st.sidebar.markdown("## 🎨 Opzioni di Pratica")

    st.sidebar.markdown("### 📚 Verbi")
    st.session_state["selected_verbs"] = st.sidebar.multiselect(
        "Scegli verbi:",
        VERB_COLUMNS.keys(),
        default=st.session_state["selected_verbs"],
    )

    st.sidebar.markdown("### 🎭 Modi")
    st.session_state["selected_modes"] = st.sidebar.multiselect(
        "Scegli modo:",
        sorted(df["Modo"].unique()),
        default=st.session_state["selected_modes"],
    )

    st.sidebar.markdown("### ⏳ Tempi")
    st.session_state["selected_tiempos"] = st.sidebar.multiselect(
        "Scegli tempo:",
        sorted(df["Tiempo"].unique()),
        default=st.session_state["selected_tiempos"],
    )

    st.sidebar.markdown("### 👤 Genere")
    st.session_state["selected_genere"] = st.sidebar.radio(
        "Seleziona genere:",
        ["M", "F", "Ambos"],
        index=["M", "F", "Ambos"].index(st.session_state["selected_genere"]),
    )

    if st.sidebar.button("🔄 Nuova domanda"):
        new_question()

    # --------------------------- UI PRINCIPAL ------------------
    q = st.session_state["question"]

    if q is None:
        st.error("⚠ Nessuna combinazione valida con questi filtri.")
    else:
        # HERO
        st.markdown(
            """
        <div class="hero">
            <div class="hero-left">
                <div class="hero-title">CONIUGAZIONI ITALIANO</div>
            </div>
            <div class="hero-right">
                <div class="flag-wrap"><div class="italian-flag"></div></div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("<div class='grid-2'>", unsafe_allow_html=True)

        # --------- CARD PRINCIPAL: DETALLES DE LA PREGUNTA ---------
        st.markdown("<div class='mod-card'>", unsafe_allow_html=True)
        st.markdown(
            f"""
        <div style="display:flex; gap:1rem; align-items:flex-start; justify-content:space-between;">
            <div>
                <div class="key">Tempo</div>
                <div class="val">{q['tiempo']} – <span style='font-weight:600; color:var(--accent-2);'>{q['nombre']}</span></div>
                <div style='height:10px'></div>
                <div class="key">Modo</div>
                <div class="val">{q['modo']} • Genere: {q['genere']}</div>
            </div>
            <div style="text-align:right;">
                <div class="key">Pronome</div>
                <div class="val">{q['pronombre']}</div>
                <div style='height:10px'></div>
                <span class="tag-verb">{q['verb']}</span>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # ---------- FORM: RESPUESTA ----------
        with st.form(key="answer_form"):
            st.markdown(
                "<div class='key' style='margin-bottom:4px;'>Risposta</div>",
                unsafe_allow_html=True,
            )
            user_input = st.text_input(
                "",
                placeholder="Inserisci la coniugazione corretta...",
                label_visibility="collapsed",
            )

            submitted = st.form_submit_button(label="🎯 CONTROLLA LA RISPOSTA")

            if submitted:
                ans = user_input
                st.session_state["validated"] = True
                st.session_state["questions"] += 1

                if normalize(ans) == normalize(q["correct"]):
                    st.session_state["score"] += 1
                    st.session_state["feedback"] = (
                        f"<div class='feedback-correct'>✅ PERFETTO! 🎉<br>La risposta corretta è: <strong>{q['correct']}</strong></div>"
                    )
                else:
                    st.session_state["feedback"] = (
                        f"<div class='feedback-incorrect'>❌ SBAGLIATO<br>La forma corretta è: <strong>{q['correct']}</strong></div>"
                    )

        if st.session_state["feedback"]:
            st.markdown(st.session_state["feedback"], unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)  # cierre mod-card principal

        # ------------- CARD LATERAL: STATS + BOTONES -------------
        st.markdown("<div class='mod-card'>", unsafe_allow_html=True)

        pct = (
            (st.session_state["score"] / st.session_state["questions"]) * 100
            if st.session_state["questions"] > 0
            else 0
        )

        st.markdown(
            f"""
        <div style="display:flex; align-items:center; gap:1.25rem; justify-content:space-between;">
            <div style="flex:1;">
                <div class="key">Sessione</div>
                <div class="val">Domande: {st.session_state['questions']}</div>
                <div style="height:10px"></div>
                <div class="key">Precisione</div>
                <div class="val">{pct:.1f}%</div>
            </div>
            <div style="width:84px;">
                <div class="progress-ring" style="--pct:{pct};">
                    <div class="inner">{int(pct)}%</div>
                </div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("➡️ PROSSIMA DOMANDA", use_container_width=True):
                new_question()
        with col2:
            if st.button("🔄 RICOMINCIA", use_container_width=True):
                st.session_state["score"] = 0
                st.session_state["questions"] = 0
                new_question()

        st.markdown("</div>", unsafe_allow_html=True)  # cierre mod-card lateral
        st.markdown("</div>", unsafe_allow_html=True)  # cierre grid-2

# ============================================================
#                     PAGINA: RIPASSO
# ============================================================
if page == "Ripasso":

    st.markdown("""
        <h1 style='text-align:center; margin-bottom:0.3rem;'>📘 Modalità Ripasso</h1>
        <p style='text-align:center; margin-top:-6px; opacity:0.8;'>
            Consulta, filtra e osserva tutti i tempi verbali come in Excel.
        </p>
    """, unsafe_allow_html=True)

    st.sidebar.markdown("## 🔍 Filtri Ripasso")

    # Limpieza para evitar errores de filtrado
    for col in ["Modo", "Tiempo", "Nombre", "Pronombre", "Genere"]:
        df[col] = df[col].astype(str).str.strip()

    # Base para calcular opciones dependientes
    df_base = df.copy()

    # ------------------------------------------------------
    #  Opciones dependientes: recalculamos las opciones de cada
    #  multiselect en función de las selecciones previas para
    #  mantener coherencia entre filtros (cascading filters)
    # ------------------------------------------------------
    # Modo (primer nivel)
    modo_options = sorted(df_base["Modo"].unique())
    modo_default = st.session_state.get("rip_modo", [])
    modo_f = st.sidebar.multiselect("Modo", modo_options, default=[m for m in modo_default if m in modo_options])
    st.session_state["rip_modo"] = modo_f

    # Tiempo depende de Modo
    if modo_f:
        tempo_options = sorted(df_base[df_base["Modo"].isin(modo_f)]["Tiempo"].unique())
    else:
        tempo_options = sorted(df_base["Tiempo"].unique())
    tempo_default = st.session_state.get("rip_tempo", [])
    tempo_f = st.sidebar.multiselect("Tempo", tempo_options, default=[t for t in tempo_default if t in tempo_options])
    st.session_state["rip_tempo"] = tempo_f

    # Nome depende de Modo + Tempo
    df_for_nome = df_base
    if modo_f:
        df_for_nome = df_for_nome[df_for_nome["Modo"].isin(modo_f)]
    if tempo_f:
        df_for_nome = df_for_nome[df_for_nome["Tiempo"].isin(tempo_f)]
    nome_options = sorted(df_for_nome["Nombre"].unique())
    nome_default = st.session_state.get("rip_nome", [])
    nome_f = st.sidebar.multiselect("Nome", nome_options, default=[n for n in nome_default if n in nome_options])
    st.session_state["rip_nome"] = nome_f

    # Pronome depende de los filtros anteriores
    df_for_pron = df_base
    if modo_f:
        df_for_pron = df_for_pron[df_for_pron["Modo"].isin(modo_f)]
    if tempo_f:
        df_for_pron = df_for_pron[df_for_pron["Tiempo"].isin(tempo_f)]
    if nome_f:
        df_for_pron = df_for_pron[df_for_pron["Nombre"].isin(nome_f)]
    # Mantener un orden humano para pronombres
    pron_order = ["Io", "Tu", "Lui", "Noi", "Voi", "Loro"]
    pron_options_raw = sorted(df_for_pron["Pronombre"].unique())
    pron_options = [p for p in pron_order if p in pron_options_raw] + [p for p in pron_options_raw if p not in pron_order]
    pron_default = st.session_state.get("rip_pron", [])
    pron_f = st.sidebar.multiselect("Pronome", pron_options, default=[p for p in pron_default if p in pron_options])
    st.session_state["rip_pron"] = pron_f

    # Genere depende de todo lo anterior
    df_for_gen = df_base
    if modo_f:
        df_for_gen = df_for_gen[df_for_gen["Modo"].isin(modo_f)]
    if tempo_f:
        df_for_gen = df_for_gen[df_for_gen["Tiempo"].isin(tempo_f)]
    if nome_f:
        df_for_gen = df_for_gen[df_for_gen["Nombre"].isin(nome_f)]
    if pron_f:
        df_for_gen = df_for_gen[df_for_gen["Pronombre"].isin(pron_f)]
    gen_options = sorted(df_for_gen["Genere"].unique())
    gen_default = st.session_state.get("rip_gen", [])
    gen_f = st.sidebar.multiselect("Genere", gen_options, default=[g for g in gen_default if g in gen_options])
    st.session_state["rip_gen"] = gen_f

    # ------------------------------------------------------
    #                FILTROS DE RIPASSO (aplicar)
    # ------------------------------------------------------
    df_filtered = df_base.copy()

    if modo_f:
        df_filtered = df_filtered[df_filtered["Modo"].isin(modo_f)]
    if tempo_f:
        df_filtered = df_filtered[df_filtered["Tiempo"].isin(tempo_f)]
    if nome_f:
        df_filtered = df_filtered[df_filtered["Nombre"].isin(nome_f)]
    if pron_f:
        df_filtered = df_filtered[df_filtered["Pronombre"].isin(pron_f)]
    if gen_f:
        df_filtered = df_filtered[df_filtered["Genere"].isin(gen_f)]

    # ------------------------------------------------------
    #    ORDEN FINAL CON PRONOMBRES EN ORDEN CORRECTO
    # ------------------------------------------------------
    # Re-aplicar el orden categórico después de filtrar
    df_filtered["Pronombre"] = pd.Categorical(
        df_filtered["Pronombre"], 
        categories=["Io", "Tu", "Lui", "Noi", "Voi", "Loro"], 
        ordered=True
    )
    
    # Ordenar por Tiempo, Nombre, Modo y Pronombre
    df_filtered = df_filtered.sort_values(
        by=["Tiempo", "Nombre", "Modo", "Pronombre"]
    ).reset_index(drop=True)

    st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)

    if df_filtered.empty:
        st.warning("Nessun risultato con questi filtri.")
    else:

        table_html = df_filtered.to_html(
            classes="excel-table",
            index=False,
            escape=False
        )

        table_js = """
        <script>
        const tbl = document.querySelector('.excel-table');
        if (tbl){
            tbl.querySelectorAll('td, th').forEach(cell => {

                cell.addEventListener('mouseover', e => {
                    let col = e.target.cellIndex;
                    let row = e.target.parentNode.rowIndex;

                    tbl.querySelectorAll('td, th').forEach(c =>
                        c.classList.remove('xl-row','xl-col','xl-selected')
                    );

                    // fila
                    tbl.rows[row].querySelectorAll('td, th').forEach(c => c.classList.add('xl-row'));

                    // columna
                    [...tbl.rows].forEach(r => {
                        if (r.children[col])
                            r.children[col].classList.add('xl-col');
                    });
                });

                cell.addEventListener('click', e => {
                    tbl.querySelectorAll('td, th').forEach(c =>
                        c.classList.remove('xl-selected')
                    );
                    e.target.classList.add('xl-selected');
                });
            });
        }
        </script>
        """

        # Inline CSS for the table must be injected here because `components.html`
        # renders inside an iframe and does not inherit the app's `style.css`.
        table_style_inline = """
        <style>
        .excel-wrapper{overflow:auto; height:750px; border-radius:14px; border:1px solid rgba(255,255,255,0.06); background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(6,8,10,0.35)); backdrop-filter:blur(8px) saturate(120%); padding:14px; box-shadow: 0 8px 30px rgba(2,6,23,0.6);}
        .excel-table{width:100%; border-collapse:separate; border-spacing:0; font-size:0.98rem; letter-spacing:0.2px; color:#e9f0f3; font-family:'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; text-align:center;}
        .excel-table th, .excel-table td{ padding:12px 14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; vertical-align:middle; }
        .excel-table thead th{ background: rgba(18,20,22,0.6); backdrop-filter: blur(6px); color: #ffffff !important; font-family: 'Montserrat', 'Inter', sans-serif; font-weight:700; font-size:0.85rem; text-transform:uppercase; letter-spacing:1px; position:sticky; top:0; z-index:4; border-bottom: 1px solid rgba(255,255,255,0.04); }
        .excel-table tbody tr td{ background: rgba(255,255,255,0.01); border-bottom: 1px solid rgba(255,255,255,0.03); }
        .excel-table tbody tr:nth-child(even) td{ background: rgba(255,255,255,0.015); }
        .excel-table tbody tr:hover td{ transform: translateY(-2px); background: linear-gradient(90deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); box-shadow: 0 6px 20px rgba(0,0,0,0.45) inset; }
        .excel-table th:first-child, .excel-table td:first-child{ text-align:left; }
        .excel-table th:last-child, .excel-table td:last-child{ text-align:center; }
        .xl-row{ background: linear-gradient(90deg, rgba(200,220,255,0.04), rgba(200,220,255,0.02)) !important; }
        .xl-col{ background: linear-gradient(180deg, rgba(200,220,255,0.02), rgba(200,220,255,0.01)) !important; }
        .xl-selected{ background: linear-gradient(90deg, rgba(212,0,0,0.9), rgba(255,40,0,0.8)) !important; font-weight:800; color:white !important; box-shadow: 0 10px 30px rgba(212,0,0,0.18) inset; }
        </style>
        """

        # Inject the inline CSS + table HTML + JS into the iframe so styles apply.
        html(
            f"{table_style_inline}<div class='excel-wrapper'>{table_html}</div>{table_js}",
            height=850,
            scrolling=True,
        )