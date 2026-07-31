"""
Module d'analyse — logique métier réutilisée par l'appli Streamlit.
Aucune clé API en dur ici : elles sont lues depuis st.secrets (voir app.py).
"""

import yfinance as yf
import requests
import numpy as np
import pandas as pd
from datetime import date, timedelta
import anthropic

COMMODITY_SEARCH_TERMS = {
    "GC=F": "gold price",
    "SI=F": "silver price",
    "CL=F": "WTI crude oil",
    "BZ=F": "Brent crude oil",
}

FR_TO_EN_SEARCH_TERMS = {
    "or": "gold", "argent": "silver", "pétrole": "crude oil", "petrole": "crude oil",
    "gaz naturel": "natural gas", "cuivre": "copper", "platine": "platinum",
    "blé": "wheat", "ble": "wheat", "maïs": "corn", "mais": "corn",
    "café": "coffee", "cafe": "coffee", "sucre": "sugar", "coton": "cotton",
}

IMPORTANT_RELEASES = [
    "Employment Situation", "Consumer Price Index", "Gross Domestic Product",
    "FOMC Press Release", "FOMC Statement", "Personal Consumption Expenditures",
    "Producer Price Index", "Unemployment Insurance Weekly Claims Report",
]


# ---------- Recherche ----------

def search_symbol(query, max_results=8):
    search_term = FR_TO_EN_SEARCH_TERMS.get(query.lower().strip(), query)
    search = yf.Search(search_term, max_results=max_results)
    return search.quotes


# ---------- Données ----------

def get_price_data(symbol, period="6mo"):
    ticker = yf.Ticker(symbol)
    history = ticker.history(period=period)
    info = ticker.info
    return ticker, history, info


def get_intraday_data(symbol, interval="5m"):
    period_map = {"1m": "5d", "5m": "5d", "15m": "1mo", "30m": "1mo"}
    ticker = yf.Ticker(symbol)
    return ticker.history(period=period_map.get(interval, "5d"), interval=interval)


def get_news(company_name, symbol, news_api_key, page_size=5):
    search_name = COMMODITY_SEARCH_TERMS.get(
        symbol, company_name.split(",")[0].split(".")[0].strip()
    )
    url = "https://newsapi.org/v2/everything"
    params = {"q": search_name, "sortBy": "publishedAt", "pageSize": page_size, "apiKey": news_api_key}
    response = requests.get(url, params=params)
    result = response.json()
    return search_name, result.get("articles", [])


def get_economic_calendar(fred_api_key):
    today = date.today().isoformat()
    url = "https://api.stlouisfed.org/fred/releases/dates"
    params = {
        "api_key": fred_api_key, "file_type": "json",
        "realtime_start": today, "realtime_end": today,
        "include_release_dates_with_no_data": "true", "sort_order": "asc",
    }
    response = requests.get(url, params=params)
    data = response.json()
    all_releases = data.get("release_dates", [])
    return [r for r in all_releases if r.get("date") == today and r.get("release_name") in IMPORTANT_RELEASES]


# ---------- Indicateurs techniques ----------

def calculate_rsi(close_prices, period=14):
    delta = close_prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def rsi_zone_label(rsi_value):
    if rsi_value > 70:
        return "Sur-achetée"
    elif rsi_value < 30:
        return "Sur-vendue"
    return "Zone neutre"


def calculate_macd(close_prices):
    ema12 = close_prices.ewm(span=12, adjust=False).mean()
    ema26 = close_prices.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal, macd - signal


def calculate_bollinger(close_prices, window=20, num_std=2):
    mid = close_prices.rolling(window=window).mean()
    std = close_prices.rolling(window=window).std()
    return mid, mid + num_std * std, mid - num_std * std


def calculate_volatility(close_prices):
    return close_prices.pct_change().std() * np.sqrt(252) * 100


def detect_trend(ma20, ma50):
    slope = ma20.iloc[-1] - ma20.iloc[-10]
    if ma20.iloc[-1] > ma50.iloc[-1] and slope > 0:
        return "Tendance haussière"
    elif ma20.iloc[-1] < ma50.iloc[-1] and slope < 0:
        return "Tendance baissière"
    return "Tendance incertaine / range"


def compute_full_technical_analysis(history):
    history["MA20"] = history["Close"].rolling(window=20).mean()
    history["MA50"] = history["Close"].rolling(window=50).mean()
    history["RSI"] = calculate_rsi(history["Close"])
    history["MACD"], history["MACD_signal"], history["MACD_hist"] = calculate_macd(history["Close"])
    history["BB_mid"], history["BB_upper"], history["BB_lower"] = calculate_bollinger(history["Close"])

    last_price = history["Close"].iloc[-1]
    first_price = history["Close"].iloc[0]
    change_pct = ((last_price - first_price) / first_price) * 100
    last_rsi = history["RSI"].iloc[-1]
    macd_signal_text = "Haussier" if history["MACD"].iloc[-1] > history["MACD_signal"].iloc[-1] else "Baissier"

    if last_price > history["BB_upper"].iloc[-1]:
        bb_position = "Au-dessus de la bande haute — possible sur-extension"
    elif last_price < history["BB_lower"].iloc[-1]:
        bb_position = "En-dessous de la bande basse — possible sur-extension"
    else:
        bb_position = "Dans la bande normale"

    return {
        "last_price": last_price, "change_pct": change_pct,
        "trend": detect_trend(history["MA20"], history["MA50"]),
        "last_rsi": last_rsi, "rsi_zone": rsi_zone_label(last_rsi),
        "macd_signal_text": macd_signal_text, "bb_position": bb_position,
        "volatility": calculate_volatility(history["Close"]), "history": history,
    }


def compute_intraday_signals(data):
    data["EMA9"] = data["Close"].ewm(span=9, adjust=False).mean()
    data["EMA21"] = data["Close"].ewm(span=21, adjust=False).mean()
    data["RSI7"] = calculate_rsi(data["Close"], period=7)

    data["date_only"] = data.index.date
    data["TP"] = (data["High"] + data["Low"] + data["Close"]) / 3
    data["TPV"] = data["TP"] * data["Volume"]
    data["cum_TPV"] = data.groupby("date_only")["TPV"].cumsum()
    data["cum_Vol"] = data.groupby("date_only")["Volume"].cumsum()
    data["VWAP"] = data["cum_TPV"] / data["cum_Vol"]

    data["Vol_avg20"] = data["Volume"].rolling(window=20).mean()
    volume_spike = data["Volume"].iloc[-1] > 1.5 * data["Vol_avg20"].iloc[-1]

    last = data.iloc[-1]
    signals = [
        ("EMA9/EMA21", "haussier" if last["EMA9"] > last["EMA21"] else "baissier"),
        ("RSI7", "haussier" if last["RSI7"] > 50 else "baissier"),
        ("Prix vs VWAP", "haussier" if last["Close"] > last["VWAP"] else "baissier"),
    ]
    bullish = sum(1 for _, s in signals if s == "haussier")
    bearish = sum(1 for _, s in signals if s == "baissier")

    return {"last": last, "data": data, "signals": signals, "bullish_count": bullish,
            "bearish_count": bearish, "volume_spike": volume_spike}


# ---------- IA ----------

def _client(anthropic_api_key):
    return anthropic.Anthropic(api_key=anthropic_api_key)


def ai_technical_synthesis(symbol, search_name, analysis, articles, anthropic_api_key):
    news_summary = "\n".join([f"- {a['title']} ({a['source']['name']})" for a in articles]) or "Aucune actualité trouvée."
    prompt = f"""Voici les données techniques et l'actualité pour l'actif {symbol} ({search_name}) :

DONNÉES DE PRIX
- Dernier prix : {analysis['last_price']:.2f}
- Variation sur 6 mois : {analysis['change_pct']:+.2f}%
- Tendance générale (MA20/MA50) : {analysis['trend']}

INDICATEURS TECHNIQUES
- RSI (14j) : {analysis['last_rsi']:.1f} → {analysis['rsi_zone']}
- MACD : {analysis['macd_signal_text']}
- Position Bollinger Bands : {analysis['bb_position']}
- Volatilité annualisée : {analysis['volatility']:.1f}%

ACTUALITÉS RÉCENTES
{news_summary}

Rédige une synthèse en français (7-8 phrases) qui résume la tendance, croise les signaux techniques,
relie (ou non) les actualités au mouvement du prix, et souligne 2-3 points de vigilance.
Ne donne jamais de conseil d'investissement direct, ni de prix cible."""
    message = _client(anthropic_api_key).messages.create(
        model="claude-sonnet-4-6", max_tokens=700, messages=[{"role": "user", "content": prompt}])
    return message.content[0].text


def ai_scalping_read(symbol, interval, intraday, anthropic_api_key):
    signals_summary = "\n".join([f"- {name} : {s}" for name, s in intraday["signals"]])
    prompt = f"""Voici une lecture technique intraday pour {symbol}, en unité de temps {interval} :

Heure de la dernière bougie : {intraday['last'].name}
Dernier prix : {intraday['last']['Close']:.2f}

SIGNAUX TECHNIQUES COURT TERME
{signals_summary}

Volume anormalement élevé : {"Oui" if intraday['volume_spike'] else "Non"}
Biais global : {intraday['bullish_count']} haussier(s) / {intraday['bearish_count']} baissier(s)

Rédige un commentaire court (4-5 phrases) en français : ce que suggèrent les signaux, s'ils sont cohérents,
un rappel que cette lecture peut changer d'une bougie à l'autre, et un principe de gestion du risque.
Ne donne jamais d'ordre d'achat/vente, ni de prix cible, ni d'horaire d'entrée/sortie."""
    message = _client(anthropic_api_key).messages.create(
        model="claude-sonnet-4-6", max_tokens=400, messages=[{"role": "user", "content": prompt}])
    return message.content[0].text


def ai_morning_briefing(symbol, analysis, todays_events, anthropic_api_key):
    events_summary = "\n".join([f"- {e.get('release_name')}" for e in todays_events]) or "Aucun événement majeur prévu aujourd'hui."
    prompt = f"""Voici le contexte pour préparer une séance de trading sur {symbol} aujourd'hui, {date.today().isoformat()}.

CONTEXTE TECHNIQUE ACTUEL
- Dernier prix : {analysis['last_price']:.2f}
- Tendance (MA20/MA50) : {analysis['trend']}
- RSI (14j) : {analysis['last_rsi']:.1f} → {analysis['rsi_zone']}
- MACD : {analysis['macd_signal_text']}
- Bollinger Bands : {analysis['bb_position']}
- Volatilité annualisée : {analysis['volatility']:.1f}%

PUBLICATIONS ÉCONOMIQUES US PROGRAMMÉES AUJOURD'HUI
{events_summary}

Rédige un briefing du matin en français (8-10 phrases) : contexte technique, pourquoi chaque publication
compte pour cet actif, niveau de vigilance attendu pour la journée, et un rappel de prudence.
Ne donne jamais d'heure précise de mouvement, ni de prix cible, ni de conseil d'achat/vente direct."""
    message = _client(anthropic_api_key).messages.create(
        model="claude-sonnet-4-6", max_tokens=800, messages=[{"role": "user", "content": prompt}])
    return message.content[0].text
