import random
import unicodedata
import pandas as pd
import streamlit as st
from streamlit.components.v1 import html
import altair as alt
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
        # Faja superior tipo bandera italiana (si existe en tu CSS)
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
#      LIMPIEZA DEL CSV + ORDEN DE PRONOMBRES
# ============================================================

PRON_ORDER = ["Io", "Tu", "Lui", "Lei", "Noi", "Voi", "Loro"]

# Eliminar femenino (como venías usando)
df = df[df["Genere"] != "F"].copy()
# Eliminar pronombre Lei
df = df[df["Pronombre"] != "Lei"].copy()

df["Pronombre"] = pd.Categorical(df["Pronombre"], categories=PRON_ORDER, ordered=True)

for col in ["Modo", "Tiempo", "Nombre", "Pronombre", "Genere"]:
    df[col] = df[col].astype(str).str.strip()

# ============================================================
#                        VERBOS
# ============================================================
# Asegurate que estas columnas existan en el CSV
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
    """Normaliza texto para comparar acentos y mayúsculas/minúsculas."""
    text = str(text).strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.lower()


def load_progress() -> None:
    """Carga el progreso desde un JSON local, si existe."""
    if os.path.exists("progress.json"):
        try:
            with open("progress.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                st.session_state[k] = v
        except Exception:
            pass


def save_progress() -> None:
    """Guarda el progreso en un JSON local."""
    data = {
        "score": st.session_state.get("score", 0),
        "questions": st.session_state.get("questions", 0),
        "session_corrects": st.session_state.get("session_corrects", []),
        "session_errors": st.session_state.get("session_errors", []),
        "repeat_queue": st.session_state.get("repeat_queue", []),
        "all_done": st.session_state.get("all_done", False),
        "selected_verbs": st.session_state.get("selected_verbs", []),
        "selected_modes": st.session_state.get("selected_modes", []),
        "selected_tiempos": st.session_state.get("selected_tiempos", []),
        "selected_nombre": st.session_state.get("selected_nombre", "Tutti"),
        "selected_genere": st.session_state.get("selected_genere", "Ambos"),
    }
    try:
        with open("progress.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================
#               FUNCIÓN PARA NUEVA PREGUNTA
# ============================================================
def new_question() -> None:
    """
    Genera una nueva pregunta según los filtros actuales.
    - Respeta filtros (modo, tempo, nome, genere)
    - Usa cola de repetición si hay
    - Evita repetir combinaciones ya acertadas
    """
    df_filtered = df.copy()

    # filtros de sesión (Allenamento)
    if st.session_state.get("selected_modes"):
        df_filtered = df_filtered[df_filtered["Modo"].isin(st.session_state["selected_modes"])]

    if st.session_state.get("selected_tiempos"):
        df_filtered = df_filtered[df_filtered["Tiempo"].isin(st.session_state["selected_tiempos"])]

    if st.session_state.get("selected_nombre") and st.session_state["selected_nombre"] != "Tutti":
        df_filtered = df_filtered[df_filtered["Nombre"] == st.session_state["selected_nombre"]]

    if st.session_state.get("selected_genere") and st.session_state["selected_genere"] != "Ambos":
        df_filtered = df_filtered[df_filtered["Genere"] == st.session_state["selected_genere"]]

    if df_filtered.empty:
        st.session_state["question"] = None
        return

    # Set de combos ya respondidas correctamente
    answered = set()
    for c in st.session_state.get("session_corrects", []):
        answered.add(
            (c.get("tiempo"), c.get("nombre"), c.get("modo"), c.get("pronombre"), c.get("verb"))
        )

    # ---------- 1) Priorizar preguntas en cola de repetición ----------
    now_q = st.session_state.get("questions", 0)
    repeat_item = None
    queue = list(st.session_state.get("repeat_queue", []))
    for i, it in enumerate(queue):
        if it.get("scheduled_at", 0) > now_q:
            continue
        key = (it.get("tiempo"), it.get("nombre"), it.get("modo"), it.get("pronombre"), it.get("verb"))
        if key in answered:
            # ya se respondió bien, la saco de la cola
            try:
                st.session_state["repeat_queue"].pop(i)
                save_progress()
            except Exception:
                pass
            continue

        mask = (
            (df_filtered["Tiempo"] == it["tiempo"])
            & (df_filtered["Nombre"] == it["nombre"])
            & (df_filtered["Modo"] == it["modo"])
            & (df_filtered["Pronombre"] == it["pronombre"])
            & (df_filtered["Genere"] == it.get("genere", "M"))
        )
        candidates = df_filtered[mask]
        if not candidates.empty:
            repeat_item = it
            try:
                st.session_state["repeat_queue"].pop(i)
                save_progress()
            except Exception:
                pass
            break

    if repeat_item:
        mask = (
            (df_filtered["Tiempo"] == repeat_item["tiempo"])
            & (df_filtered["Nombre"] == repeat_item["nombre"])
            & (df_filtered["Modo"] == repeat_item["modo"])
            & (df_filtered["Pronombre"] == repeat_item["pronombre"])
            & (df_filtered["Genere"] == repeat_item.get("genere", "M"))
        )
        r = df_filtered[mask].sample(1).iloc[0]
        st.session_state["question"] = {
            "tiempo": repeat_item["tiempo"],
            "nombre": repeat_item["nombre"],
            "modo": repeat_item["modo"],
            "pronombre": repeat_item["pronombre"],
            "verb": repeat_item.get(
                "verb",
                random.choice(st.session_state.get("selected_verbs", list(VERB_COLUMNS.keys()))),
            ),
            "correct": repeat_item.get("correct"),
            "genere": repeat_item.get("genere", "M"),
            "is_repeat": True,
        }
        st.session_state["feedback"] = ""
        st.session_state["validated"] = False
        return

    # ---------- 2) Pregunta aleatoria normal ----------
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

    if not chosen:
        st.session_state["question"] = None
        st.session_state["all_done"] = True
        return

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
        "is_repeat": False,
    }

    last = st.session_state.setdefault("last_questions", [])
    last.append(
        (
            st.session_state["question"]["tiempo"],
            st.session_state["question"]["nombre"],
            st.session_state["question"]["modo"],
            st.session_state["question"]["pronombre"],
            st.session_state["question"]["verb"],
        )
    )
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
    st.session_state["selected_verbs"] = random.sample(list(VERB_COLUMNS.keys()), k=len(VERB_COLUMNS))

if "selected_modes" not in st.session_state:
    st.session_state["selected_modes"] = sorted(df["Modo"].unique())

if "selected_tiempos" not in st.session_state:
    st.session_state["selected_tiempos"] = sorted(df["Tiempo"].unique())

if "selected_genere" not in st.session_state:
    st.session_state["selected_genere"] = "Ambos"

if "selected_nombre" not in st.session_state:
    st.session_state["selected_nombre"] = "Tutti"

if "question" not in st.session_state:
    new_question()

if "feedback" not in st.session_state:
    st.session_state["feedback"] = ""
if "validated" not in st.session_state:
    st.session_state["validated"] = False
if "all_done" not in st.session_state:
    st.session_state["all_done"] = False
if "last_questions" not in st.session_state:
    st.session_state["last_questions"] = []
if "session_corrects" not in st.session_state:
    st.session_state["session_corrects"] = []
if "session_errors" not in st.session_state:
    st.session_state["session_errors"] = []
if "repeat_queue" not in st.session_state:
    st.session_state["repeat_queue"] = []
if "progress_loaded" not in st.session_state:
    load_progress()
    st.session_state["progress_loaded"] = True


# ============================================================
#                     HERO PRINCIPAL
# ============================================================
qs = st.session_state.get("questions", 0)
sc = st.session_state.get("score", 0)
pct = (sc / qs * 100) if qs > 0 else 0
num_repeats = len(st.session_state.get("repeat_queue", []))

st.markdown(
    f"""
<div class="hero">
    <div class="hero-main">
        <div class="hero-title">CONIUGAZIONI ITALIANO</div>
        <div class="hero-metrics">
            <div class="metric">
                <div class="metric-label">Sessione</div>
                <div class="metric-value">{qs}</div>
                <div class="metric-badge">Domande risolte</div>
            </div>
            <div class="metric">
                <div class="metric-label">Precisione</div>
                <div class="metric-value">{pct:.1f}%</div>
                <div class="metric-badge">Ultime 50 domande</div>
            </div>
            <div class="metric">
                <div class="metric-label">Ripetizioni</div>
                <div class="metric-value">{num_repeats}</div>
                <div class="metric-badge">Spaced repetition</div>
            </div>
        </div>
    </div>
    <div class="hero-right">
        <div class="hero-badge">
            <div class="hero-badge-dot"></div>
            <span>Allenamento attivo</span>
        </div>
        <div class="hero-tagline">
            <strong>Un verbo alla volta.</strong><br/>
            Il trucco è la costanza, non la perfezione.
        </div>
        <div class="hero-chip-row">
            <div class="hero-chip">🧠 Spaced repetition</div>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# ============================================================
#                     CONTROL DE PÁGINAS
# ============================================================
st.sidebar.markdown("## 📂 Sezioni")
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

    st.sidebar.markdown("### 🏷️ Nome del tempo")
    nombre_options = sorted(df["Nombre"].dropna().unique())
    nombre_choices = ["Tutti"] + list(nombre_options)
    current_nombre = st.session_state["selected_nombre"]
    if current_nombre not in nombre_choices:
        current_nombre = "Tutti"
    st.session_state["selected_nombre"] = st.sidebar.selectbox(
        "Scegli nome:",
        nombre_choices,
        index=nombre_choices.index(current_nombre),
    )

    st.sidebar.markdown("### 👤 Genere")
    current_genere = st.session_state["selected_genere"]
    if current_genere not in ["M", "F", "Ambos"]:
        current_genere = "Ambos"
    st.session_state["selected_genere"] = st.sidebar.radio(
        "Seleziona genere:",
        ["M", "F", "Ambos"],
        index=["M", "F", "Ambos"].index(current_genere),
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Rigenera domanda", use_container_width=True):
        new_question()
        try:
            st.rerun()
        except Exception:
            # fallback: no-op if rerun not available
            pass

    # -------------------- BLOQUE PRINCIPAL --------------------
    st.markdown(
        """
        <div style="display:flex; justify-content:center; margin-bottom:1.5rem;">
            <div class="badge-compact">Modalità Allenamento</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state["question"] is None and not st.session_state["all_done"]:
        new_question()

    q = st.session_state.get("question")

    if q is None:
        if st.session_state["all_done"]:
            st.markdown(
                """
                <div class="mod-card">
                    <div class="mod-card-title">🎉 Complimenti!</div>
                    <div class="mod-card-sub">
                        Hai esaurito tutte le combinazioni disponibili con i filtri attuali.
                    </div>
                    <p class="small-muted">
                        Prova a cambiare filtri (verbi, tempi, pronomi) per continuare ad allenarti.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.error("⚠ Nessuna combinazione disponibile con i filtri attuali.")
    else:
        st.markdown("<div class='grid-2'>", unsafe_allow_html=True)

        # --------- CARD PRINCIPAL: DETALLES DE LA PREGUNTA ---------
        st.markdown("<div class='mod-card main-card'>", unsafe_allow_html=True)
        st.markdown(
            f"""
        <div class="question-meta">
          <div class="question-meta-row">
            <div class="key">Tempo</div>
            <div class="val">
                {q['tiempo']} – <span class="tempo-nome">{q['nombre']}</span>
            </div>
          </div>

          <div class="question-meta-row">
            <div class="key">Modo</div>
            <div class="val">
                {q['modo']} • Genere: {q['genere']}
            </div>
          </div>

          <div class="question-meta-row">
            <div class="key">Pronome &amp; verbo</div>
            <div class="val">
                <span class="pronome">{q['pronombre']}</span>
                <span class="tag-verb" style="margin-left:0.6rem;">{q['verb']}</span>
            </div>
          </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # ---------- FORM: RESPUESTA ----------
        form_key = (
            f"answer_form_{q['tiempo']}_{q['nombre']}_{q['modo']}_"
            f"{q['pronombre']}_{q['verb']}_{st.session_state['questions']}"
        )

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

            # Botones dentro del form: CONTROLLA a la izquierda, PROSSIMA a la derecha
            btn_col, next_col = st.columns([1,1])
            with btn_col:
                submitted = st.form_submit_button("🎯 CONTROLLA LA RISPOSTA", use_container_width=True)
            with next_col:
                next_pressed = st.form_submit_button("➡️ PROSSIMA DOMANDA", use_container_width=True)

            if next_pressed:
                # limpiar input y avanzar inmediatamente
                try:
                    st.session_state[f"input_{form_key}"] = ""
                except Exception:
                    pass
                st.session_state["feedback"] = ""
                st.session_state["validated"] = False
                new_question()
                try:
                    st.rerun()
                except Exception:
                    pass

            if submitted and user_input.strip():
                ans = user_input
                current_question = st.session_state["question"].copy()
                st.session_state["validated"] = True
                st.session_state["questions"] += 1

                if normalize(ans) == normalize(current_question["correct"]):
                    st.session_state["score"] += 1
                    st.session_state["feedback"] = (
                        f"<div class='feedback-correct'>✅ PERFETTO! "
                        f"La risposta corretta è: <strong>{current_question['correct']}</strong></div>"
                    )
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
                    save_progress()
                else:
                    st.session_state["feedback"] = (
                        f"<div class='feedback-incorrect'>❌ Non proprio. "
                        f"La forma corretta è: <strong>{current_question['correct']}</strong></div>"
                    )
                    err = {
                        "verb": current_question.get("verb"),
                        "modo": current_question.get("modo"),
                        "tiempo": current_question.get("tiempo"),
                        "nombre": current_question.get("nombre"),
                        "pronombre": current_question.get("pronombre"),
                        "provided": ans,
                        "correct": current_question.get("correct"),
                        "is_repeat": current_question.get("is_repeat", False),
                    }
                    st.session_state.setdefault("session_errors", []).append(err)

                    interval = 3
                    scheduled_at = st.session_state["questions"] + interval
                    repeat_item = {
                        "modo": current_question.get("modo"),
                        "tiempo": current_question.get("tiempo"),
                        "nombre": current_question.get("nombre"),
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
        # Inline script + CSS: forzar que los dos botones del formulario ocupen
        # el 100% del ancho (cada uno 50%) y no haya espacio entre ellos.
        # Buscamos el input por placeholder para localizar el form correspondiente.
        style_script = '''
        <style>
        .no-gap-btns { display:flex; gap:0; width:100%; }
        .no-gap-btns button { flex:1 1 50%; margin:0; }
        .no-gap-btns button:first-child{ border-top-right-radius:0; border-bottom-right-radius:0; }
        .no-gap-btns button:last-child{ border-top-left-radius:0; border-bottom-left-radius:0; }
        </style>
        <script>
        (function(){
            try{
                const inputs = document.querySelectorAll('input[placeholder="Inserisci la coniugazione corretta..."]');
                if(!inputs || inputs.length===0) return;
                const input = inputs[0];
                const form = input.closest('form');
                if(!form) return;
                // localizar contenedor de botones (Streamlit crea divs); agruparlos
                const buttons = Array.from(form.querySelectorAll('button'))
                    .filter(b => /(CONTROLLA|PROSSIMA)/i.test(b.innerText || b.textContent));
                if(buttons.length < 2) return;
                // crear wrapper
                const wrapper = document.createElement('div');
                wrapper.className = 'no-gap-btns';
                // move buttons into wrapper in correct order
                // ensure CONTROLLA is first
                buttons.sort((a,b)=>{ return (/CONTROLLA/i.test(a.innerText||a.textContent)?-1:1) - (/CONTROLLA/i.test(b.innerText||b.textContent)?-1:1); });
                buttons.forEach(b=>{ wrapper.appendChild(b); });
                // append wrapper to form
                form.appendChild(wrapper);
            }catch(e){console.warn('btn layout script', e)}
        })();
        </script>
        '''
        st.markdown(style_script, unsafe_allow_html=True)
        if st.session_state["feedback"]:
            st.markdown(st.session_state["feedback"], unsafe_allow_html=True)

        # ---------- LADO DERECHO: STATO SESSIONE + STORICO ----------
        st.markdown("<div class='mod-card'>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="mod-card-title">📈 Andamento della sessione</div>
            <div class="mod-card-sub">Vedi come sta andando il tuo allenamento in tempo reale.</div>
            <div style="display:flex; align-items:center; gap:1.25rem; justify-content:space-between;">
                <div style="flex:1;">
                    <div class="key">Sessione</div>
                    <div class="val">Domande: {qs}</div>
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
        st.markdown("<hr style='border-color: rgba(255,255,255,0.08);' />", unsafe_allow_html=True)
        st.markdown("<div class='key'>Storico rapido</div>", unsafe_allow_html=True)

        if st.session_state.get("session_corrects") or st.session_state.get("session_errors"):
            if st.button("🧹 RICOMINCIA SESSIONE", use_container_width=True):
                st.session_state["score"] = 0
                st.session_state["questions"] = 0
                st.session_state["session_corrects"] = []
                st.session_state["session_errors"] = []
                st.session_state["repeat_queue"] = []
                st.session_state["last_questions"] = []
                st.session_state["feedback"] = ""
                st.session_state["validated"] = False
                st.session_state["all_done"] = False
                save_progress()
                new_question()
                try:
                    st.rerun()
                except Exception:
                    pass

            rc, re = st.columns(2)
            with rc:
                st.markdown("<strong>Corrette (sessione)</strong>", unsafe_allow_html=True)
                sc_sess = st.session_state.get("session_corrects", [])
                if sc_sess:
                    df_sc = pd.DataFrame(sc_sess)
                    df_display = df_sc[
                        ["verb", "modo", "tiempo", "nombre", "pronombre", "provided", "correct"]
                    ].rename(
                        columns={
                            "verb": "Verbo",
                            "modo": "Modo",
                            "tiempo": "Tempo",
                            "nombre": "Serie",
                            "pronombre": "Pronome",
                            "provided": "Risposta data",
                            "correct": "Corretta",
                        }
                    )
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
                else:
                    st.markdown(
                        "<span class='small-muted'>Ancora nessuna risposta corretta registrata.</span>",
                        unsafe_allow_html=True,
                    )
            with re:
                st.markdown("<strong>Errori (sessione)</strong>", unsafe_allow_html=True)
                se_sess = st.session_state.get("session_errors", [])
                if se_sess:
                    df_se = pd.DataFrame(se_sess)
                    df_display = df_se[
                        ["verb", "modo", "tiempo", "nombre", "pronombre", "provided", "correct"]
                    ].rename(
                        columns={
                            "verb": "Verbo",
                            "modo": "Modo",
                            "tiempo": "Tempo",
                            "nombre": "Serie",
                            "pronombre": "Pronome",
                            "provided": "Risposta data",
                            "correct": "Corretta",
                        }
                    )
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
                else:
                    st.markdown(
                        "<span class='small-muted'>Per ora nessun errore. Ma non rilassarti 😉</span>",
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown(
                "<span class='small-muted'>Rispondi ad alcune domande per vedere lo storico.</span>",
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)  # cierre card derecha
        st.markdown("</div>", unsafe_allow_html=True)  # cierre grid-2

# ============================================================
#                     PAGINA: RIPASSO
# ============================================================
elif page == "Ripasso":
    st.markdown(
        """
        <div class="badge-compact">Ripasso</div>
        <h2>Storico e ripasso delle coniugazioni</h2>
        """,
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs(["✅ Corrette", "❌ Errori"])

    with tab1:
        sc_sess = st.session_state.get("session_corrects", [])
        if sc_sess:
            df_sc = pd.DataFrame(sc_sess)
            df_display = df_sc[
                ["verb", "modo", "tiempo", "nombre", "pronombre", "provided", "correct", "is_repeat"]
            ].rename(
                columns={
                    "verb": "Verbo",
                    "modo": "Modo",
                    "tiempo": "Tempo",
                    "nombre": "Serie",
                    "pronombre": "Pronome",
                    "provided": "Risposta data",
                    "correct": "Corretta",
                    "is_repeat": "Ripetizione",
                }
            )
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.markdown(
                "<span class='small-muted'>Ancora nessuna risposta corretta registrata in questa sessione.</span>",
                unsafe_allow_html=True,
            )

    with tab2:
        se_sess = st.session_state.get("session_errors", [])
        if se_sess:
            df_se = pd.DataFrame(se_sess)
            df_display = df_se[
                ["verb", "modo", "tiempo", "nombre", "pronombre", "provided", "correct", "is_repeat"]
            ].rename(
                columns={
                    "verb": "Verbo",
                    "modo": "Modo",
                    "tiempo": "Tempo",
                    "nombre": "Serie",
                    "pronombre": "Pronome",
                    "provided": "Risposta data",
                    "correct": "Corretta",
                    "is_repeat": "Ripetizione",
                }
            )
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.markdown(
                "<span class='small-muted'>Per ora nessun errore registrato in questa sessione.</span>",
                unsafe_allow_html=True,
            )

    # -------------------- TABLA DE VERBOS CON FILTROS --------------------
    st.markdown("---")
    st.markdown(
        """
        <div class="badge-compact">Tabella verbi</div>
        <h3>Coniugazioni per verbo</h3>
        <p class="small-muted">
            Filtra per verbo, modo, tempo, pronome e genere per esplorare il dataset.
        </p>
        """,
        unsafe_allow_html=True,
    )

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)

    with col_f1:
        verb_list = list(VERB_COLUMNS.keys())
        selected_verb_tbl = st.selectbox("Verbo", verb_list, index=0)

    with col_f2:
        modos_list = sorted(df["Modo"].unique())
        selected_modos_tbl = st.multiselect("Modo", modos_list, default=modos_list)

    with col_f3:
        tiempos_list = sorted(df["Tiempo"].unique())
        selected_tiempos_tbl = st.multiselect("Tempo", tiempos_list, default=tiempos_list)

    with col_f4:
        pron_available = [p for p in PRON_ORDER if p in df["Pronombre"].unique()]
        selected_pron_tbl = st.multiselect("Pronome", pron_available, default=pron_available)

    genere_filter_tbl = st.radio("Genere", ["Ambos", "M", "F"], horizontal=True, index=0)

    df_v = df.copy()
    col_verb = VERB_COLUMNS[selected_verb_tbl]

    if selected_modos_tbl:
        df_v = df_v[df_v["Modo"].isin(selected_modos_tbl)]
    if selected_tiempos_tbl:
        df_v = df_v[df_v["Tiempo"].isin(selected_tiempos_tbl)]
    if selected_pron_tbl:
        df_v = df_v[df_v["Pronombre"].isin(selected_pron_tbl)]
    if genere_filter_tbl != "Ambos":
        df_v = df_v[df_v["Genere"] == genere_filter_tbl]

    if df_v.empty:
        st.info("Nessuna combinazione trovata con i filtri selezionati.")
    else:
        df_v = df_v.sort_values(["Modo", "Tiempo", "Nombre", "Pronombre"])
        df_show = df_v[["Modo", "Tiempo", "Nombre", "Pronombre", "Genere", col_verb]].rename(
            columns={
                "Modo": "Modo",
                "Tiempo": "Tempo",
                "Nombre": "Serie",
                "Pronombre": "Pronome",
                "Genere": "Genere",
                col_verb: "Coniugazione",
            }
        )
        st.dataframe(df_show, use_container_width=True, hide_index=True)

# ============================================================
#              DASHBOARD: RENDIMENTO ULTIMA SESSIONE
# ============================================================
st.markdown("---")
st.markdown("## 📊 Rendimento ultima sessione per 'Nome del tempo'")
sc = st.session_state.get("session_corrects", [])
se = st.session_state.get("session_errors", [])
if not sc and not se:
    st.info("Nessuna attività registrata in questa sessione. Rispondi ad alcune domande per vedere il rendimento qui.")
else:
    # Construir DataFrame de intentos por 'nombre'
    df_corr = pd.DataFrame(sc) if sc else pd.DataFrame(columns=["nombre"])
    df_err = pd.DataFrame(se) if se else pd.DataFrame(columns=["nombre"])

    # Normalizar columna nombre
    if "nombre" in df_corr.columns:
        df_corr["nombre"] = df_corr["nombre"].astype(str)
    if "nombre" in df_err.columns:
        df_err["nombre"] = df_err["nombre"].astype(str)

    corr_counts = df_corr.groupby("nombre").size().rename("corrects") if not df_corr.empty else pd.Series(dtype=int)
    err_counts = df_err.groupby("nombre").size().rename("errors") if not df_err.empty else pd.Series(dtype=int)

    perf = pd.concat([corr_counts, err_counts], axis=1).fillna(0)
    perf["attempts"] = perf["corrects"] + perf["errors"]
    perf = perf[perf["attempts"] > 0]
    perf["accuracy"] = (perf["corrects"] / perf["attempts"]) * 100
    perf = perf.reset_index().rename(columns={"nombre": "Nome"})

    if perf.empty:
        st.info("Non ci sono tentativi per alcun 'Nome' in questa sessione.")
    else:
        # Ordenar por accuracy ascendente para resaltar los tiempos con peor rendimiento arriba
        perf = perf.sort_values(by="accuracy", ascending=True)

        # Construir el gráfico tipo dashboard dentro de una tarjeta
        st.markdown("<div class='mod-card'>", unsafe_allow_html=True)
        st.markdown("<h4 style='margin-top:0;'>Rendimento per Nome dei verbi</h4>", unsafe_allow_html=True)

        base = alt.Chart(perf).encode(
            y=alt.Y("Nome:N", sort=alt.EncodingSortField(field="accuracy", op="min", order="ascending"), title=None),
        )

        # barras más delgadas (size) para un aspecto menos 'gordo'
        bars = base.mark_bar(size=18).encode(
            x=alt.X("accuracy:Q", title="Precisione (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.condition(alt.datum.accuracy < 60, alt.value("#d62728"), alt.value("#2ca02c")),
            tooltip=[alt.Tooltip("Nome:N"), alt.Tooltip("corrects:Q", title="Corrette"), alt.Tooltip("errors:Q", title="Errori"), alt.Tooltip("accuracy:Q", format=".1f", title="Precisione (%)")],
        )

        # Mostrar el porcentaje dentro de la barra (alineado a la derecha, con color blanco y mayor tamaño)
        text = base.mark_text(align='right', dx=-6, color='white', fontSize=18, fontWeight='bold').encode(
            x=alt.X('accuracy:Q'),
            text=alt.Text('accuracy:Q', format='.1f')
        )

        # Hacer el gráfico más alto para mejorar visibilidad: al menos 420px
        # y usar menos alto por fila para barras más estrechas (36px por fila)
        chart_height = max(420, 36 * len(perf))
        chart = (bars + text).properties(height=chart_height, width='container')

        st.altair_chart(chart, use_container_width=True)

        # Tabla resumen compacta
        perf_display = perf[["Nome", "corrects", "errors", "attempts", "accuracy"]].rename(columns={
            "corrects": "Corrette",
            "errors": "Errori",
            "attempts": "Tentativi",
            "accuracy": "Precisione (%)",
        })
        st.dataframe(perf_display.style.format({"Precisione (%)": "{:.1f}"}), use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)
