import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import analysis as an

# ==========================================================
# CONFIGURATION DE LA PAGE + THÈME "CARNET DE BOURSE"
# ==========================================================

st.set_page_config(page_title="Carnet de bourse", page_icon="📖", layout="wide")

INK = "#efead7"
BRASS = "#A67C3D"
SAGE = "#4C6B4F"
BRICK = "#A44A3F"
PAPER = "#0B0528"
PAPER_DARK = "#1B1268"
LINE = "#E4DFD2"

st.markdown(f"""
<style>
    .stApp {{ background-color: {PAPER}; }}
    h1, h2, h3 {{ font-family: Georgia, 'Times New Roman', serif; color: {INK}; }}
    .eyebrow {{
        font-size: 0.7rem; letter-spacing: 0.18em; text-transform: uppercase;
        color: {BRASS}; font-weight: 600; margin-bottom: -0.6rem;
    }}
    .ledger-row {{
        display: flex; justify-content: space-between; padding: 0.5rem 0;
        border-bottom: 1px solid {LINE}; font-size: 0.92rem;
    }}
    .ledger-label {{ color: #5A6785; }}
    .ledger-value {{ font-family: 'Courier New', monospace; font-weight: 600; color: {INK}; }}
    .stTabs [data-baseweb="tab"] {{ font-family: Georgia, serif; font-size: 1rem; }}
    div[data-testid="stMetricValue"] {{ font-family: 'Courier New', monospace; }}
    .stButton button {{
        background-color: {INK}; color: {PAPER}; border-radius: 2px; border: none;
        font-weight: 600; letter-spacing: 0.02em;
    }}
    .stButton button:hover {{ background-color: {BRASS}; color: {PAPER}; }}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="eyebrow">Outil personnel d\'analyse</div>', unsafe_allow_html=True)
st.title("📖 Carnet de bourse")
st.caption("Analyse technique, actualités et contexte macro — assemblés pour t'aider à lire le marché, pas à le prédire.")

# ==========================================================
# CLÉS API — lues depuis les secrets Streamlit
# ==========================================================

try:
    NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    ANTHROPIC_API_KEY = st.secrets["ANTHROPIC_API_KEY"]
    keys_ok = True
except Exception:
    keys_ok = False
    st.error(
        "Clés API manquantes. Ajoute-les dans les **Secrets** de ton appli Streamlit "
        "(NEWS_API_KEY, FRED_API_KEY, ANTHROPIC_API_KEY) — voir le guide de déploiement."
    )

# Symbole actif, mémorisé pendant la session
if "symbol" not in st.session_state:
    st.session_state.symbol = "GC=F"

# ==========================================================
# ONGLETS
# ==========================================================

tab_search, tab_full, tab_scalp, tab_morning = st.tabs(
    ["🔍 Recherche", "📊 Analyse complète", "⚡ Scalping intraday", "🌅 Briefing du matin"]
)

# ---------- Onglet Recherche ----------
with tab_search:
    st.subheader("Trouver un actif")
    query = st.text_input("Nom de l'actif (français ou anglais)", placeholder="ex: or, tesla, pétrole, lvmh")

    if query:
        results = an.search_symbol(query)
        if not results:
            st.warning("Aucun résultat. Essaie un terme plus général, ou en anglais.")
        else:
            for r in results:
                symbol = r.get("symbol", "?")
                name = r.get("shortname") or r.get("longname") or "Nom inconnu"
                asset_type = r.get("typeDisp", "?")
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{symbol}** — {name} · _{asset_type}_")
                with col2:
                    if st.button("Sélectionner", key=f"select_{symbol}"):
                        st.session_state.symbol = symbol
                        st.success(f"Actif actif : {symbol}")

    st.divider()
    st.markdown(f"**Actif actuellement sélectionné :** `{st.session_state.symbol}`")


# ---------- Onglet Analyse complète ----------
with tab_full:
    symbol = st.session_state.symbol
    st.subheader(f"Analyse 6 mois — {symbol}")

    if st.button("Lancer l'analyse complète", disabled=not keys_ok):
        with st.spinner("Récupération des données et calcul des indicateurs…"):
            ticker, history, info = an.get_price_data(symbol, period="6mo")
            company_name = info.get("longName", symbol)
            result = an.compute_full_technical_analysis(history)
            search_name, articles = an.get_news(company_name, symbol, NEWS_API_KEY)

        # --- Métriques clés ---
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Dernier prix", f"{result['last_price']:.2f}")
        c2.metric("Variation 6 mois", f"{result['change_pct']:+.2f}%")
        c3.metric("RSI (14j)", f"{result['last_rsi']:.1f}", result["rsi_zone"])
        c4.metric("Volatilité annualisée", f"{result['volatility']:.1f}%")

        st.markdown(f"**{result['trend']}** · MACD {result['macd_signal_text']} · {result['bb_position']}")

        # --- Graphique interactif ---
        h = result["history"]
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True, row_heights=[0.55, 0.22, 0.23],
            vertical_spacing=0.03, subplot_titles=("Prix & bandes de Bollinger", "RSI", "MACD"),
        )
        fig.add_trace(go.Scatter(x=h.index, y=h["BB_upper"], line=dict(width=0), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=h.index, y=h["BB_lower"], line=dict(width=0), fill="tonexty",
                                  fillcolor="rgba(166,124,61,0.12)", name="Bollinger"), row=1, col=1)
        fig.add_trace(go.Scatter(x=h.index, y=h["Close"], line=dict(color=INK, width=2), name="Clôture"), row=1, col=1)
        fig.add_trace(go.Scatter(x=h.index, y=h["MA20"], line=dict(color=BRASS, width=1.3, dash="dash"), name="MA20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=h.index, y=h["MA50"], line=dict(color=BRICK, width=1.3, dash="dot"), name="MA50"), row=1, col=1)

        fig.add_trace(go.Scatter(x=h.index, y=h["RSI"], line=dict(color=BRASS, width=1.5), name="RSI"), row=2, col=1)
        fig.add_hline(y=70, line=dict(color=BRICK, dash="dash", width=1), row=2, col=1)
        fig.add_hline(y=30, line=dict(color=SAGE, dash="dash", width=1), row=2, col=1)

        fig.add_trace(go.Scatter(x=h.index, y=h["MACD"], line=dict(color=INK, width=1.5), name="MACD"), row=3, col=1)
        fig.add_trace(go.Scatter(x=h.index, y=h["MACD_signal"], line=dict(color=BRICK, width=1.5), name="Signal"), row=3, col=1)
        fig.add_trace(go.Bar(x=h.index, y=h["MACD_hist"], marker_color=LINE, name="Histogramme"), row=3, col=1)

        fig.update_layout(height=700, plot_bgcolor=PAPER, paper_bgcolor=PAPER,
                           font=dict(family="Georgia, serif", color=INK), margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

        # --- Synthèse IA ---
        st.subheader("🧠 Synthèse IA")
        with st.spinner("Claude analyse le contexte…"):
            synthesis = an.ai_technical_synthesis(symbol, search_name, result, articles, ANTHROPIC_API_KEY)
        st.markdown(synthesis)

        # --- Actualités ---
        with st.expander(f"📰 Actualités récentes ({len(articles)})"):
            for a in articles:
                st.markdown(f"**[{a['title']}]({a['url']})**  \n_{a['source']['name']} · {a['publishedAt'][:10]}_")


# ---------- Onglet Scalping ----------
with tab_scalp:
    symbol = st.session_state.symbol
    st.subheader(f"Lecture intraday — {symbol}")
    interval = st.select_slider("Unité de temps", options=["1m", "5m", "15m", "30m"], value="5m")

    if st.button("Analyser les signaux", disabled=not keys_ok):
        with st.spinner("Récupération des données intraday…"):
            data = an.get_intraday_data(symbol, interval)

        if data.empty:
            st.warning("Aucune donnée disponible pour cet intervalle/symbole.")
        else:
            intraday = an.compute_intraday_signals(data)

            c1, c2, c3 = st.columns(3)
            c1.metric("Dernier prix", f"{intraday['last']['Close']:.2f}")
            c2.metric("Biais", f"{intraday['bullish_count']} haussier / {intraday['bearish_count']} baissier")
            c3.metric("Volume anormal", "Oui ⚠️" if intraday["volume_spike"] else "Non")

            for name, s in intraday["signals"]:
                color = SAGE if s == "haussier" else BRICK
                st.markdown(f"<div class='ledger-row'><span class='ledger-label'>{name}</span>"
                            f"<span class='ledger-value' style='color:{color}'>{s}</span></div>",
                            unsafe_allow_html=True)

            d = intraday["data"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=d.index, y=d["Close"], line=dict(color=INK, width=2), name="Prix"))
            fig.add_trace(go.Scatter(x=d.index, y=d["EMA9"], line=dict(color=BRASS, width=1.3), name="EMA9"))
            fig.add_trace(go.Scatter(x=d.index, y=d["EMA21"], line=dict(color=BRICK, width=1.3), name="EMA21"))
            fig.add_trace(go.Scatter(x=d.index, y=d["VWAP"], line=dict(color=SAGE, width=1.3, dash="dot"), name="VWAP"))
            fig.update_layout(height=400, plot_bgcolor=PAPER, paper_bgcolor=PAPER,
                               font=dict(family="Georgia, serif", color=INK), margin=dict(t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("🧠 Commentaire IA")
            with st.spinner("Claude commente les signaux…"):
                comment = an.ai_scalping_read(symbol, interval, intraday, ANTHROPIC_API_KEY)
            st.markdown(comment)
            st.caption("⚠️ Lecture instantanée, pas une prédiction — peut changer d'une bougie à l'autre.")


# ---------- Onglet Briefing du matin ----------
with tab_morning:
    symbol = st.session_state.symbol
    st.subheader(f"Briefing du jour — {symbol}")

    if st.button("Générer le briefing", disabled=not keys_ok):
        with st.spinner("Préparation du briefing…"):
            ticker, history, info = an.get_price_data(symbol, period="6mo")
            result = an.compute_full_technical_analysis(history)
            todays_events = an.get_economic_calendar(FRED_API_KEY)

        if todays_events:
            st.markdown("**📅 Publications économiques US majeures aujourd'hui**")
            for e in todays_events:
                st.markdown(f"- {e.get('release_name')}")
        else:
            st.markdown("**📅 Aucune publication majeure identifiée aujourd'hui.**")

        st.divider()
        with st.spinner("Claude prépare le briefing…"):
            briefing = an.ai_morning_briefing(symbol, result, todays_events, ANTHROPIC_API_KEY)
        st.markdown(briefing)
