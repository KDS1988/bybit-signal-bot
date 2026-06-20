#!/usr/bin/env python3
"""
Bybit Signal Bot — GitHub Actions version
Индикаторы через библиотеку 'ta' (без pandas-ta)
"""

import os
import json
import logging
import requests
import pandas as pd
import ta

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SYMBOLS        = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
INTERVAL       = "60"
CANDLES_LIMIT  = 200
RSI_OVERSOLD   = 35
RSI_OVERBOUGHT = 65
BB_TOUCH_PCT   = 0.002
MIN_SIGNALS    = 2
STATE_FILE     = "state.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════
#  СОСТОЯНИЕ
# ═══════════════════════════════════════════

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {sym: None for sym in SYMBOLS}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ═══════════════════════════════════════════
#  BYBIT API
# ═══════════════════════════════════════════

def fetch_candles(symbol):
    url = "https://api.bybit.com/v5/market/kline"
    params = {"category": "linear", "symbol": symbol, "interval": INTERVAL, "limit": CANDLES_LIMIT}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("retCode") != 0:
        raise ValueError(f"Bybit error: {data.get('retMsg')}")
    raw = data["result"]["list"]
    df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume","turnover"])
    df = df.iloc[::-1].reset_index(drop=True)
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    return df

# ═══════════════════════════════════════════
#  ИНДИКАТОРЫ
# ═══════════════════════════════════════════

def calc_indicators(df):
    c = df["close"]
    h = df["high"]
    l = df["low"]

    # RSI
    rsi = ta.momentum.RSIIndicator(close=c, window=14).rsi()
    rsi_val = float(rsi.iloc[-1])

    # MACD
    macd_obj = ta.trend.MACD(close=c, window_fast=12, window_slow=26, window_sign=9)
    macd_h     = float(macd_obj.macd_diff().iloc[-1])
    macd_h_p   = float(macd_obj.macd_diff().iloc[-2])

    # EMA 9 / 21
    ema9  = ta.trend.EMAIndicator(close=c, window=9).ema_indicator()
    ema21 = ta.trend.EMAIndicator(close=c, window=21).ema_indicator()
    e9    = float(ema9.iloc[-1]);  e9p  = float(ema9.iloc[-2])
    e21   = float(ema21.iloc[-1]); e21p = float(ema21.iloc[-2])

    # Bollinger Bands
    bb    = ta.volatility.BollingerBands(close=c, window=20, window_dev=2)
    bb_u  = float(bb.bollinger_hband().iloc[-1])
    bb_l  = float(bb.bollinger_lband().iloc[-1])
    bb_m  = float(bb.bollinger_mavg().iloc[-1])

    return dict(
        price=float(c.iloc[-1]),
        rsi=rsi_val,
        macd_h=macd_h, macd_h_p=macd_h_p,
        e9=e9, e9p=e9p, e21=e21, e21p=e21p,
        bb_u=bb_u, bb_l=bb_l, bb_m=bb_m,
    )

# ═══════════════════════════════════════════
#  АНАЛИЗ СИГНАЛОВ
# ═══════════════════════════════════════════

def analyze(ind):
    signals = {}
    details = {}
    p = ind["price"]

    # RSI
    r = ind["rsi"]
    if r < RSI_OVERSOLD:
        signals["RSI"] = "LONG";    details["RSI"] = f"RSI={r:.1f} перепродан"
    elif r > RSI_OVERBOUGHT:
        signals["RSI"] = "SHORT";   details["RSI"] = f"RSI={r:.1f} перекуплен"
    else:
        signals["RSI"] = "NEUTRAL"; details["RSI"] = f"RSI={r:.1f} нейтрально"

    # MACD
    h, hp = ind["macd_h"], ind["macd_h_p"]
    if h > 0 and hp <= 0:
        signals["MACD"] = "LONG";  details["MACD"] = f"hist={h:.5f} бычий разворот ✅"
    elif h < 0 and hp >= 0:
        signals["MACD"] = "SHORT"; details["MACD"] = f"hist={h:.5f} медвежий разворот ⚠️"
    elif h > 0:
        signals["MACD"] = "LONG";  details["MACD"] = f"hist={h:.5f} выше нуля"
    else:
        signals["MACD"] = "SHORT"; details["MACD"] = f"hist={h:.5f} ниже нуля"

    # EMA
    e9, e9p, e21, e21p = ind["e9"], ind["e9p"], ind["e21"], ind["e21p"]
    if e9 > e21 and e9p <= e21p:
        signals["EMA"] = "LONG";  details["EMA"] = "Золотой крест EMA9/EMA21 🌟"
    elif e9 < e21 and e9p >= e21p:
        signals["EMA"] = "SHORT"; details["EMA"] = "Мёртвый крест EMA9/EMA21 💀"
    elif e9 > e21:
        signals["EMA"] = "LONG";  details["EMA"] = f"EMA9({e9:.2f}) > EMA21({e21:.2f})"
    else:
        signals["EMA"] = "SHORT"; details["EMA"] = f"EMA9({e9:.2f}) < EMA21({e21:.2f})"

    # BB
    bu, bl, bm = ind["bb_u"], ind["bb_l"], ind["bb_m"]
    if p <= bl * (1 + BB_TOUCH_PCT):
        signals["BB"] = "LONG";  details["BB"] = f"Касание нижней BB ({bl:.2f})"
    elif p >= bu * (1 - BB_TOUCH_PCT):
        signals["BB"] = "SHORT"; details["BB"] = f"Касание верхней BB ({bu:.2f})"
    elif p > bm:
        signals["BB"] = "LONG";  details["BB"] = f"Выше средней BB ({bm:.2f})"
    else:
        signals["BB"] = "SHORT"; details["BB"] = f"Ниже средней BB ({bm:.2f})"

    longs  = sum(1 for v in signals.values() if v == "LONG")
    shorts = sum(1 for v in signals.values() if v == "SHORT")
    total  = len(signals)

    if longs > shorts and longs >= MIN_SIGNALS:
        direction, strength = "LONG",    f"{longs}/{total}"
    elif shorts > longs and shorts >= MIN_SIGNALS:
        direction, strength = "SHORT",   f"{shorts}/{total}"
    else:
        direction, strength = "NEUTRAL", f"{longs}L/{shorts}S"

    return dict(direction=direction, strength=strength, signals=signals, details=details)

# ═══════════════════════════════════════════
#  TELEGRAM
# ═══════════════════════════════════════════

DIR_EMOJI = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}
IND_ARROW = {"LONG": "↑", "SHORT": "↓", "NEUTRAL": "→"}

def escape_md(text):
    """Экранируем спецсимволы для MarkdownV2"""
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text

def format_msg(symbol, ind, analysis):
    p   = ind["price"]
    bu  = ind["bb_u"]
    bl  = ind["bb_l"]
    d   = analysis["direction"]
    pair = symbol.replace("USDT", "/USDT")

    if d == "LONG":
        entry  = p
        stop   = round(bl * 0.999, 4)
        target = round(bu, 4)
        rr = round((target - entry) / (entry - stop), 1) if entry > stop else 0
    elif d == "SHORT":
        entry  = p
        stop   = round(bu * 1.001, 4)
        target = round(bl, 4)
        rr = round((entry - target) / (stop - entry), 1) if stop > entry else 0
    else:
        entry = stop = target = rr = None

    lines = [
        f"{DIR_EMOJI[d]} *{pair}* — *{d}*  [{analysis['strength']} сигналов]",
        f"Цена: {p:,.4f} USDT",
        "",
        "Индикаторы:",
    ]
    for name, detail in analysis["details"].items():
        sig = analysis["signals"][name]
        lines.append(f"  {IND_ARROW[sig]} {name}: {escape_md(detail)}")

    if d in ("LONG", "SHORT") and entry:
        lines += [
            "",
            "Торговые уровни:",
            f"  Вход:  {entry:,.4f}",
            f"  Стоп:  {stop:,.4f}",
            f"  Цель:  {target:,.4f}",
            f"  R/R:   1 : {rr}",
        ]

    lines.append("\n_1H · Bybit Perpetual · автосигнал_")
    return "\n".join(lines)

def tg_send(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }, timeout=10)
    if not r.ok:
        log.error(f"Telegram error {r.status_code}: {r.text}")

# ═══════════════════════════════════════════
#  ГЛАВНЫЙ ЦИКЛ
# ═══════════════════════════════════════════

def main():
    state   = load_state()
    changed = False

    for symbol in SYMBOLS:
        try:
            df  = fetch_candles(symbol)
            ind = calc_indicators(df)
            res = analyze(ind)
            d   = res["direction"]

            log.info(f"{symbol}: {d} [{res['strength']}] price={ind['price']:.4f} RSI={ind['rsi']:.1f}")

            if d != "NEUTRAL" and d != state.get(symbol):
                msg = format_msg(symbol, ind, res)
                tg_send(msg)
                log.info(f"✅ Отправлен: {symbol} {d}")
                state[symbol] = d
                changed = True

        except Exception as e:
            log.error(f"{symbol}: ошибка — {e}")

    if changed:
        save_state(state)

if __name__ == "__main__":
    main()
