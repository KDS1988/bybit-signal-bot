#!/usr/bin/env python3
"""
Bybit Signal Bot — GitHub Actions version
Запускается каждые 5 минут через GitHub Actions.
Состояние (последние сигналы) хранится в state.json в репозитории.
"""

import os
import json
import logging
import requests
import pandas as pd
import pandas_ta as ta

# ═══════════════════════════════════════════
#  НАСТРОЙКИ — берутся из GitHub Secrets
# ═══════════════════════════════════════════

TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SYMBOLS        = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
INTERVAL       = "60"       # 1H свечи
CANDLES_LIMIT  = 200

RSI_OVERSOLD   = 35
RSI_OVERBOUGHT = 65
BB_TOUCH_PCT   = 0.002
MIN_SIGNALS    = 2          # минимум совпавших индикаторов для алерта

STATE_FILE     = "state.json"

# ═══════════════════════════════════════════
#  ЛОГИРОВАНИЕ
# ═══════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════
#  СОСТОЯНИЕ (чтобы не спамить одинаковые сигналы)
# ═══════════════════════════════════════════

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {sym: None for sym in SYMBOLS}

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ═══════════════════════════════════════════
#  BYBIT API
# ═══════════════════════════════════════════

def fetch_candles(symbol: str) -> pd.DataFrame:
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": "linear",
        "symbol":   symbol,
        "interval": INTERVAL,
        "limit":    CANDLES_LIMIT,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("retCode") != 0:
        raise ValueError(f"Bybit API error: {data.get('retMsg')}")

    raw = data["result"]["list"]
    df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume","turnover"])
    df = df.iloc[::-1].reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms")
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    return df

# ═══════════════════════════════════════════
#  ИНДИКАТОРЫ
# ═══════════════════════════════════════════

def calc_indicators(df: pd.DataFrame) -> dict:
    c = df["close"]

    rsi_s = ta.rsi(c, length=14)
    rsi   = float(rsi_s.iloc[-1]) if rsi_s is not None else None

    macd_df   = ta.macd(c, fast=12, slow=26, signal=9)
    macd_h    = float(macd_df["MACDh_12_26_9"].iloc[-1])  if macd_df is not None else None
    macd_h_p  = float(macd_df["MACDh_12_26_9"].iloc[-2])  if macd_df is not None else None

    ema9  = ta.ema(c, length=9)
    ema21 = ta.ema(c, length=21)
    e9    = float(ema9.iloc[-1])  if ema9  is not None else None
    e9p   = float(ema9.iloc[-2])  if ema9  is not None else None
    e21   = float(ema21.iloc[-1]) if ema21 is not None else None
    e21p  = float(ema21.iloc[-2]) if ema21 is not None else None

    bb    = ta.bbands(c, length=20, std=2)
    bb_u  = float(bb["BBU_20_2.0"].iloc[-1]) if bb is not None else None
    bb_l  = float(bb["BBL_20_2.0"].iloc[-1]) if bb is not None else None
    bb_m  = float(bb["BBM_20_2.0"].iloc[-1]) if bb is not None else None

    return dict(
        price=float(c.iloc[-1]),
        rsi=rsi,
        macd_h=macd_h, macd_h_p=macd_h_p,
        e9=e9, e9p=e9p, e21=e21, e21p=e21p,
        bb_u=bb_u, bb_l=bb_l, bb_m=bb_m,
    )

# ═══════════════════════════════════════════
#  АНАЛИЗ
# ═══════════════════════════════════════════

def analyze(ind: dict) -> dict:
    signals = {}
    details = {}
    p = ind["price"]

    # RSI
    if ind["rsi"] is not None:
        r = ind["rsi"]
        if r < RSI_OVERSOLD:
            signals["RSI"] = "LONG";  details["RSI"] = f"RSI={r:.1f} 🔵 перепродан"
        elif r > RSI_OVERBOUGHT:
            signals["RSI"] = "SHORT"; details["RSI"] = f"RSI={r:.1f} 🔴 перекуплен"
        else:
            signals["RSI"] = "NEUTRAL"; details["RSI"] = f"RSI={r:.1f} нейтрально"

    # MACD
    if ind["macd_h"] is not None:
        h, hp = ind["macd_h"], ind["macd_h_p"]
        if h > 0 and hp <= 0:
            signals["MACD"] = "LONG";  details["MACD"] = f"hist={h:.5f} ✅ бычий разворот"
        elif h < 0 and hp >= 0:
            signals["MACD"] = "SHORT"; details["MACD"] = f"hist={h:.5f} ⚠️ медвежий разворот"
        elif h > 0:
            signals["MACD"] = "LONG";  details["MACD"] = f"hist={h:.5f} выше нуля"
        else:
            signals["MACD"] = "SHORT"; details["MACD"] = f"hist={h:.5f} ниже нуля"

    # EMA Crossover
    if all(v is not None for v in [ind["e9"], ind["e9p"], ind["e21"], ind["e21p"]]):
        e9, e9p, e21, e21p = ind["e9"], ind["e9p"], ind["e21"], ind["e21p"]
        if e9 > e21 and e9p <= e21p:
            signals["EMA"] = "LONG";  details["EMA"] = f"🌟 Золотой крест EMA9/EMA21"
        elif e9 < e21 and e9p >= e21p:
            signals["EMA"] = "SHORT"; details["EMA"] = f"💀 Мёртвый крест EMA9/EMA21"
        elif e9 > e21:
            signals["EMA"] = "LONG";  details["EMA"] = f"EMA9({e9:.2f}) > EMA21({e21:.2f})"
        else:
            signals["EMA"] = "SHORT"; details["EMA"] = f"EMA9({e9:.2f}) < EMA21({e21:.2f})"

    # Bollinger Bands
    if ind["bb_u"] is not None:
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
        direction, strength = "LONG",  f"{longs}/{total}"
    elif shorts > longs and shorts >= MIN_SIGNALS:
        direction, strength = "SHORT", f"{shorts}/{total}"
    else:
        direction, strength = "NEUTRAL", f"{longs}L/{shorts}S"

    return dict(direction=direction, strength=strength, signals=signals, details=details)

# ═══════════════════════════════════════════
#  ФОРМАТИРОВАНИЕ СООБЩЕНИЯ
# ═══════════════════════════════════════════

DIR_EMOJI = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}
IND_EMOJI = {"LONG": "↑", "SHORT": "↓", "NEUTRAL": "→"}

def format_msg(symbol: str, ind: dict, analysis: dict) -> str:
    p   = ind["price"]
    bu  = ind["bb_u"]
    bl  = ind["bb_l"]
    d   = analysis["direction"]
    pair = symbol.replace("USDT", "/USDT")

    if d == "LONG":
        entry  = p
        stop   = bl * 0.999 if bl else p * 0.98
        target = bu if bu else p * 1.03
        rr = (target - entry) / (entry - stop) if entry > stop else 0
    elif d == "SHORT":
        entry  = p
        stop   = bu * 1.001 if bu else p * 1.02
        target = bl if bl else p * 0.97
        rr = (entry - target) / (stop - entry) if stop > entry else 0
    else:
        entry = stop = target = rr = None

    lines = [
        f"{DIR_EMOJI[d]} *{pair}* — *{d}*  \\[{analysis['strength']} сигналов\\]",
        f"💰 Цена: `{p:,.4f} USDT`",
        "",
        "*Индикаторы:*",
    ]
    for name, detail in analysis["details"].items():
        sig = analysis["signals"][name]
        lines.append(f"  {IND_EMOJI[sig]} {name}: {detail}")

    if d in ("LONG", "SHORT") and entry:
        lines += [
            "",
            "*Торговые уровни:*",
            f"  📍 Вход:  `{entry:,.4f}`",
            f"  🛑 Стоп:  `{stop:,.4f}`",
            f"  🎯 Цель:  `{target:,.4f}`",
            f"  ⚖️ R/R:   1 : {rr:.1f}",
        ]

    lines.append("\n_⏰ 1H · Bybit Perpetual · автосигнал_")
    return "\n".join(lines)

# ═══════════════════════════════════════════
#  TELEGRAM
# ═══════════════════════════════════════════

def tg_send(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "MarkdownV2",
    }
    r = requests.post(url, json=payload, timeout=10)
    if not r.ok:
        log.error(f"Telegram error {r.status_code}: {r.text}")

# ═══════════════════════════════════════════
#  ГЛАВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════

def main():
    state = load_state()
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
                log.info(f"✅ Отправлен сигнал: {symbol} {d}")
                state[symbol] = d
                changed = True

        except Exception as e:
            log.error(f"{symbol}: ошибка — {e}")

    if changed:
        save_state(state)
        log.info("Состояние сохранено")
    else:
        log.info("Новых сигналов нет")

if __name__ == "__main__":
    main()
