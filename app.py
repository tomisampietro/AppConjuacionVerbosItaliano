import random
import unicodedata
import pandas as pd
import streamlit as st
from streamlit.components.v1 import html
import json
import os
from datetime import datetime

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
        # Insert the global italian flag stripe (thin full-width bar)
        st.markdown("<div class='italian-flag-global'></div>", unsafe_allow_html=True)
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
    """Genera una nueva pregunta según los filtros actuales.

    Mejora: - respeta filtros al consumir repeticiones
             - evita repetir combinaciones ya acertadas en la sesión
             - si se agotan las combinaciones muestra señal de finalización
    """
    df_filtered = df.copy()

    # filtros de sesión (Allenamento)
    if st.session_state.get("selected_modes"):
        df_filtered = df_filtered[df_filtered["Modo"].isin(st.session_state["selected_modes"])]

    if st.session_state.get("selected_tiempos"):
        df_filtered = df_filtered[df_filtered["Tiempo"].isin(st.session_state["selected_tiempos"])]

    if st.session_state.get("selected_genere") and st.session_state.get("selected_genere") != "Ambos":
        df_filtered = df_filtered[df_filtered["Genere"] == st.session_state["selected_genere"]]

    if df_filtered.empty:
        st.session_state["question"] = None
        return

    # Build set of correctly answered combos in this session to avoid repeating them
    answered = set()
    for c in st.session_state.get("session_corrects", []):
        answered.add((c.get("tiempo"), c.get("nombre"), c.get("modo"), c.get("pronombre"), c.get("verb")))

    # Priorizar preguntas programadas (repeticiones) que estén 'vencidas'
    now_q = st.session_state.get("questions", 0)
    repeat_item = None
    if "repeat_queue" in st.session_state and st.session_state["repeat_queue"]:
        # buscar la primera repetición cuyo scheduled_at <= now_q que además
        # cumpla los filtros actuales y no haya sido respondida correctamente
        for i, it in enumerate(list(st.session_state.get("repeat_queue", []))):
            if it.get("scheduled_at", 0) <= now_q:
                key = (it.get("tiempo"), it.get("nombre"), it.get("modo"), it.get("pronombre"), it.get("verb"))
                # si ya fue respondida correctamente, eliminarla
                if key in answered:
                    try:
                        st.session_state["repeat_queue"].pop(i)
                        save_progress()
                    except Exception:
                        pass
                    continue
                # comprobar que la combinación exista dentro de los filtros actuales
                mask = (
                    (df_filtered["Tiempo"] == it.get("tiempo")) &
                    (df_filtered["Nombre"] == it.get("nombre")) &
                    (df_filtered["Modo"] == it.get("modo")) &
                    (df_filtered["Pronombre"] == it.get("pronombre"))
                )
                if mask.any():
                    # pop y usar
                    repeat_item = st.session_state["repeat_queue"].pop(i)
                    save_progress()
                    break

    if repeat_item:
        st.session_state["question"] = {
            "tiempo": repeat_item["tiempo"],
            "nombre": repeat_item["nombre"],
            "modo": repeat_item["modo"],
            "pronombre": repeat_item["pronombre"],
            "verb": repeat_item.get("verb", random.choice(st.session_state.get("selected_verbs", list(VERB_COLUMNS.keys())))),
            "correct": repeat_item.get("correct"),
            "genere": repeat_item.get("genere", "M"),
            "is_repeat": True,
        }
        st.session_state["feedback"] = ""
        st.session_state["validated"] = False
        return

    # Pregunta aleatoria normal (evitar repeticiones inmediatas y combos ya acertados)
    max_attempts = 200
    attempt = 0
    chosen = None
    selected_verbs = st.session_state.get("selected_verbs") or list(VERB_COLUMNS.keys())
    last_qs = set(st.session_state.get("last_questions", []))
    while attempt < max_attempts:
        r = df_filtered.sample(1).iloc[0]
        for verb in random.sample(list(selected_verbs), k=len(selected_verbs)):
            key = (r.get("Tiempo"), r.get("Nombre"), r.get("Modo"), r.get("Pronombre"), verb)
            if key in last_qs:
                continue
            if key in answered:
                continue
            chosen = (r, verb)
            break
        if chosen:
            break
        attempt += 1

    if chosen is None:
        # buscar todas las combinaciones disponibles (filtradas) que no estén ya acertadas
        available = []
        for _, row in df_filtered.iterrows():
            for verb in selected_verbs:
                k = (row.get("Tiempo"), row.get("Nombre"), row.get("Modo"), row.get("Pronombre"), verb)
                if k not in answered and k not in last_qs:
                    available.append((row, verb))
        if not available:
            # Todas las combinaciones posibles fueron contestadas correctamente
            st.session_state["question"] = None
            st.session_state["all_done"] = True
            return
        r, verb = random.choice(available)
    else:
        r, verb = chosen

    col = VERB_COLUMNS[verb]

    st.session_state["question"] = {
        "tiempo": r["Tiempo"],
        "nombre": r["Nombre"],
        "modo": r["Modo"],
        "pronombre": r["Pronombre"],
        "verb": verb,
        "correct": r[col],
        "genere": r["Genere"],
    }

    # registrar en historial para evitar repeticiones próximas
    last = st.session_state.setdefault("last_questions", [])
    last.append((st.session_state["question"]["tiempo"], st.session_state["question"]["nombre"], st.session_state["question"]["modo"], st.session_state["question"]["pronombre"], st.session_state["question"]["verb"]))
    # mantener sólo últimas N
    if len(last) > 50:
        st.session_state["last_questions"] = last[-50:]
    st.session_state["feedback"] = ""
    st.session_state["validated"] = False


# ============================================================
#               INICIALIZACIÓN DE ESTADO
# ============================================================
if "score" not in st.session_state:
    st.session_state["score"] = 0
    st.session_state["questions"] = 0

if "selected_verbs" not in st.session_state:
    # Randomize initial verb order so sessions start differently
    st.session_state["selected_verbs"] = random.sample(list(VERB_COLUMNS.keys()), k=len(VERB_COLUMNS))

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

if "all_done" not in st.session_state:
    st.session_state["all_done"] = False

# keep a short history of recent question keys to avoid immediate repeats
if "last_questions" not in st.session_state:
    st.session_state["last_questions"] = []
# Sesión: tablas temporales de aciertos / errores
if "session_corrects" not in st.session_state:
    st.session_state["session_corrects"] = []
if "session_errors" not in st.session_state:
    st.session_state["session_errors"] = []

# ============================================================
#            REPETICIONES Y REGISTRO DE ERRORES
# ============================================================
PROGRESS_PATH = "progress.json"

def load_progress():
    if os.path.exists(PROGRESS_PATH):
        try:
            with open(PROGRESS_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                st.session_state.setdefault("error_log", data.get("error_log", []))
                st.session_state.setdefault("repeat_queue", data.get("repeat_queue", []))
        except Exception:
            st.session_state.setdefault("error_log", [])
            st.session_state.setdefault("repeat_queue", [])
    else:
        st.session_state.setdefault("error_log", [])
        st.session_state.setdefault("repeat_queue", [])

def save_progress():
    payload = {
        "error_log": st.session_state.get("error_log", []),
        "repeat_queue": st.session_state.get("repeat_queue", []),
    }
    try:
        with open(PROGRESS_PATH, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass

load_progress()

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
        st.rerun()

    # --------------------------- UI PRINCIPAL ------------------
    q = st.session_state["question"]

    if q is None:
        if st.session_state.get("all_done"):
            st.success("Sei un crack — sei pronto per il livello successivo!")
            try:
                st.balloons()
            except Exception:
                pass
            # clear the flag so message is not repeated unnecessarily
            st.session_state["all_done"] = False
        else:
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
        # CRÍTICO: Generar una key única para cada pregunta
        form_key = f"answer_form_{q['tiempo']}_{q['nombre']}_{q['modo']}_{q['pronombre']}_{q['verb']}_{st.session_state['questions']}"
        
        with st.form(key=form_key):
            st.markdown(
                "<div class='key' style='margin-bottom:4px;'>Risposta</div>",
                unsafe_allow_html=True,
            )
            user_input = st.text_input(
                "",
                placeholder="Inserisci la coniugazione corretta...",
                label_visibility="collapsed",
                key=f"input_{form_key}",
            )

            # Mostrar botones: Controlla a la izquierda, Prossima a la derecha
            btn_col, next_col = st.columns([3,1])
            with btn_col:
                submitted = st.form_submit_button(label="🎯 CONTROLLA LA RISPOSTA")
            with next_col:
                next_pressed = st.form_submit_button(label="➡️ PROSSIMA DOMANDA")

            # Si se presionó 'PROSSIMA DOMANDA' avanzamos sin validar
            if next_pressed:
                try:
                    st.session_state[f"input_{form_key}"] = ""
                except Exception:
                    pass
                new_question()
                st.rerun()

            if submitted and user_input.strip():
                ans = user_input
                
                # CRÍTICO: Guardar la pregunta ACTUAL antes de validar
                current_question = st.session_state["question"].copy()
                
                st.session_state["validated"] = True
                st.session_state["questions"] += 1

                # Comprobación de respuesta usando la pregunta GUARDADA
                if normalize(ans) == normalize(current_question["correct"]):
                    st.session_state["score"] += 1
                    st.session_state["feedback"] = (
                        f"<div class='feedback-correct'>✅ PERFETTO! 🎉<br>La risposta corretta è: <strong>{current_question['correct']}</strong></div>"
                    )
                    # Registrar acierto en la sesión
                    corr = {
                        "verb": current_question.get("verb"),
                        "modo": current_question.get("modo"),
                        "tiempo": current_question.get("tiempo"),
                        "nombre": current_question.get("nombre"),
                        "pronombre": current_question.get("pronombre"),
                        "provided": ans,
                        "correct": current_question.get("correct"),
                        "is_repeat": current_question.get("is_repeat", False),
                    }
                    st.session_state.setdefault("session_corrects", []).append(corr)
                    # Eliminar cualquier repetición programada que coincida con esta combinación
                    before = len(st.session_state.get("repeat_queue", []))
                    st.session_state["repeat_queue"] = [r for r in st.session_state.get("repeat_queue", []) if not (
                        r.get("tiempo") == current_question.get("tiempo") and r.get("nombre") == current_question.get("nombre") and r.get("modo") == current_question.get("modo") and r.get("pronombre") == current_question.get("pronombre") and r.get("verb") == current_question.get("verb")
                    )]
                    if len(st.session_state.get("repeat_queue", [])) != before:
                        save_progress()
                else:
                    st.session_state["feedback"] = (
                        f"<div class='feedback-incorrect'>❌ SBAGLIATO<br>La forma corretta è: <strong>{current_question['correct']}</strong></div>"
                    )

                    # Registrar el error en el log
                    err = {
                        "verb": current_question.get("verb"),
                        "modo": current_question.get("modo"),
                        "tiempo": current_question.get("tiempo"),
                        "nombre": current_question.get("nombre"),
                        "pronombre": current_question.get("pronombre"),
                        "provided": ans,
                        "correct": current_question.get("correct"),
                    }
                    st.session_state.setdefault("error_log", []).append(err)
                    # Registrar error en la sesión (se muestra hasta 'ricomincia')
                    st.session_state.setdefault("session_errors", []).append(err)

                    # Programar repetición: aparecerá después de 3 preguntas por defecto
                    interval = 3
                    scheduled_at = st.session_state.get("questions", 0) + interval
                    repeat_item = {
                        "tiempo": current_question.get("tiempo"),
                        "nombre": current_question.get("nombre"),
                        "modo": current_question.get("modo"),
                        "pronombre": current_question.get("pronombre"),
                        "verb": current_question.get("verb"),
                        "correct": current_question.get("correct"),
                        "genere": current_question.get("genere"),
                        "scheduled_at": scheduled_at,
                        "interval": interval,
                        "attempts": 1,
                    }
                    st.session_state.setdefault("repeat_queue", []).append(repeat_item)
                    save_progress()

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

        # Los botones de navegación se manejan junto al formulario (Prossima) y
        # el botón RICOMINCIA se mostrará bajo el registro de la sessione.

        # Mostrar estado di ripetizioni nell'interfaccia
        pending = len(st.session_state.get("repeat_queue", []))
        st.markdown(f"<div style='margin-top:10px; color:var(--muted);'>Ripetizioni pendenti: <strong>{pending}</strong></div>", unsafe_allow_html=True)
        if pending > 0:
            if st.button("Vedi errori recenti / gestisci ripetizioni"):
                with st.expander("Errori recenti e ripetizioni programmate", expanded=True):
                    errs = st.session_state.get("error_log", [])
                    if errs:
                        st.write("Ultimi errori (mostrando fino a 20):")
                        st.table(pd.DataFrame(errs[-20:])[ ["verb","modo","tiempo","nombre","pronombre","provided","correct"] ])
                    else:
                        st.info("Non ci sono errori registrati al momento.")
                    st.write("Ripetizioni programmate:")
                    st.write(pd.DataFrame(st.session_state.get("repeat_queue", [])))
                    if st.button("Cancella ripetizioni" ):
                        st.session_state["repeat_queue"] = []
                        save_progress()

        st.markdown("</div>", unsafe_allow_html=True)  # cierre mod-card lateral
        st.markdown("</div>", unsafe_allow_html=True)  # cierre grid-2

        # ---------------------- REGISTRO DE SESIÓN ----------------------
        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
        st.markdown("<h3 style='margin-bottom:6px;'>Registro della sessione</h3>", unsafe_allow_html=True)
        # Pulsante RICOMINCIA sotto il titolo del registro
        if st.button("🔄 RICOMINCIA"):
            st.session_state["score"] = 0
            st.session_state["questions"] = 0
            # pulire tabelle di sessione
            st.session_state["session_corrects"] = []
            st.session_state["session_errors"] = []
            new_question()
            st.rerun()
        rc, re = st.columns(2)
        with rc:
            st.markdown("<strong>Corrette (sessione)</strong>", unsafe_allow_html=True)
            sc = st.session_state.get("session_corrects", [])
            if sc:
                df_sc = pd.DataFrame(sc)
                # SIN campo timestamp
                df_display = df_sc[["verb","modo","tiempo","nombre","pronombre","provided","correct"]].rename(columns={
                    "verb": "Verbo",
                    "modo": "Modo",
                    "tiempo": "Tempo",
                    "nombre": "Nome",
                    "pronombre": "Pronome",
                    "provided": "La tua risposta",
                    "correct": "Corretto",
                })
                html_table = df_display.to_html(index=False, classes="session-table")
                st.markdown(f"<div class='session-table-wrap'>{html_table}</div>", unsafe_allow_html=True)
            else:
                st.info("Nessuna risposta corretta in questa sessione.")
        with re:
            st.markdown("<strong>Errori (sessione)</strong>", unsafe_allow_html=True)
            se = st.session_state.get("session_errors", [])
            if se:
                df_se = pd.DataFrame(se)
                # SIN campo timestamp
                df_display_e = df_se[["verb","modo","tiempo","nombre","pronombre","provided","correct"]].rename(columns={
                    "verb": "Verbo",
                    "modo": "Modo",
                    "tiempo": "Tempo",
                    "nombre": "Nome",
                    "pronombre": "Pronome",
                    "provided": "La tua risposta",
                    "correct": "Corretto",
                })
                html_table_e = df_display_e.to_html(index=False, classes="session-table session-errors")
                st.markdown(f"<div class='session-table-wrap'>{html_table_e}</div>", unsafe_allow_html=True)
            else:
                st.info("Nessun errore in questa sessione.")

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
    # Filtros bidireccionales: cada conjunto de opciones se calcula
    # considerando las selecciones actuales en los otros filtros.
    rip_modo = st.session_state.get("rip_modo", [])
    rip_tempo = st.session_state.get("rip_tempo", [])
    rip_nome = st.session_state.get("rip_nome", [])
    rip_pron = st.session_state.get("rip_pron", [])
    rip_gen = st.session_state.get("rip_gen", [])

    def _options_for(col_name: str):
        df_tmp = df_base.copy()
        if col_name != "Modo" and rip_modo:
            df_tmp = df_tmp[df_tmp["Modo"].isin(rip_modo)]
        if col_name != "Tiempo" and rip_tempo:
            df_tmp = df_tmp[df_tmp["Tiempo"].isin(rip_tempo)]
        if col_name != "Nombre" and rip_nome:
            df_tmp = df_tmp[df_tmp["Nombre"].isin(rip_nome)]
        if col_name != "Pronombre" and rip_pron:
            df_tmp = df_tmp[df_tmp["Pronombre"].isin(rip_pron)]
        if col_name != "Genere" and rip_gen:
            df_tmp = df_tmp[df_tmp["Genere"].isin(rip_gen)]
        opts = [x for x in sorted(df_tmp[col_name].dropna().unique())]
        return opts

    modo_options = _options_for("Modo")
    modo_f = st.sidebar.multiselect(f"Modo ({len(modo_options)})", modo_options, default=[m for m in rip_modo if m in modo_options])
    st.session_state["rip_modo"] = modo_f

    tempo_options = _options_for("Tiempo")
    tempo_f = st.sidebar.multiselect(f"Tempo ({len(tempo_options)})", tempo_options, default=[t for t in rip_tempo if t in tempo_options])
    st.session_state["rip_tempo"] = tempo_f

    nome_options = _options_for("Nombre")
    nome_f = st.sidebar.multiselect(f"Nome ({len(nome_options)})", nome_options, default=[n for n in rip_nome if n in nome_options])
    st.session_state["rip_nome"] = nome_f

    # Pronombres: mantener orden humano pero calcular opciones bidireccionalmente
    pron_order = ["Io", "Tu", "Lui", "Noi", "Voi", "Loro"]
    pron_options_raw = _options_for("Pronombre")
    pron_options = [p for p in pron_order if p in pron_options_raw] + [p for p in pron_options_raw if p not in pron_order]
    pron_f = st.sidebar.multiselect(f"Pronome ({len(pron_options)})", pron_options, default=[p for p in rip_pron if p in pron_options])
    st.session_state["rip_pron"] = pron_f

    gen_options = _options_for("Genere")
    gen_f = st.sidebar.multiselect(f"Genere ({len(gen_options)})", gen_options, default=[g for g in rip_gen if g in gen_options])
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
        .excel-table{width:100%; border-collapse:separate; border-spacing:0; font-size:0.98rem; letter-spacing:0.2px; color:#e9f0f3; font-family:'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; text-align:center; table-layout: fixed;}
        .excel-table th, .excel-table td{ padding:12px 14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; vertical-align:middle; }
        .excel-table td{ white-space:normal; word-break:break-word; }
        .excel-table thead th{ background: rgba(18,20,22,0.6); backdrop-filter: blur(6px); color: #ffffff !important; font-family: 'Montserrat', 'Inter', sans-serif; font-weight:700; font-size:0.85rem; text-transform:uppercase; letter-spacing:1px; position:sticky; top:0; z-index:4; border-bottom: 1px solid rgba(255,255,255,0.04); }
        .excel-table tbody tr td{ background: rgba(255,255,255,0.01); border-bottom: 1px solid rgba(255,255,255,0.03); }
        .excel-table tbody tr:nth-child(even) td{ background: rgba(255,255,255,0.015); }
        .excel-table tbody tr:hover td{ transform: translateY(-2px); background: linear-gradient(90deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); box-shadow: 0 6px 20px rgba(0,0,0,0.45) inset; }
        .excel-table th:first-child, .excel-table td:first-child{ text-align:left; }
        .excel-table th:last-child, .excel-table td:last-child{ text-align:center; }
        .xl-row{ background: linear-gradient(90deg, rgba(200,220,255,0.04), rgba(200,220,255,0.02)) !important; }
        .xl-col{ background: linear-gradient(180deg, rgba(200,220,255,0.02), rgba(200,220,255,0.01)) !important; }
        .xl-selected{ background: linear-gradient(90deg, rgba(212,0,0,0.9), rgba(255,40,0,0.8)) !important; font-weight:800; color:white !important; box-shadow: 0 10px 30px rgba(212,0,0,0.18) inset; }

        /* Responsive tweaks inside iframe */
        @media (max-width:900px){
            .excel-wrapper{ height:55vh; padding:10px; }
            .excel-table th, .excel-table td{ padding:8px 10px; font-size:0.88rem; }
            .excel-table{ table-layout: auto; }
        }
        @media (max-width:480px){
            .excel-wrapper{ height:48vh; }
            .excel-table th, .excel-table td{ padding:6px 8px; font-size:0.82rem; }
            .excel-table{ table-layout: auto; }
        }
        </style>
        """

        # Inject the inline CSS + table HTML + JS into the iframe so styles apply.
        html(
            f"{table_style_inline}<div class='excel-wrapper'>{table_html}</div>{table_js}",
            height=850,
            scrolling=True,
        )