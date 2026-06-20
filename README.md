# 🤖 Bybit Signal Bot

Телеграм-бот для торговых сигналов по крипто-парам на Bybit.  
Работает **автономно** через GitHub Actions — бесплатно, 24/7.

## 📊 Пары и индикаторы

| Параметр | Значение |
|---|---|
| Пары | BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT |
| Таймфрейм | 1H |
| Индикаторы | RSI(14), MACD(12/26/9), EMA(9/21), Bollinger Bands(20) |
| Проверка | каждые 5 минут |
| Биржа | Bybit Perpetual (публичный API) |

## 🚀 Установка (5 минут)

### 1. Создай бота в Telegram
- Напиши @BotFather → `/newbot`
- Сохрани полученный **TOKEN**
- Напиши @userinfobot → сохрани **CHAT_ID**
- Найди своего бота и нажми `/start`

### 2. Создай репозиторий на GitHub
```
New repository → название: bybit-signal-bot → Public → Create
```

### 3. Загрузи файлы
Загрузи в репозиторий:
- `bot.py`
- `requirements.txt`
- `state.json`
- `.github/workflows/signal_bot.yml`

### 4. Добавь секреты
```
Settings → Secrets and variables → Actions → New repository secret
```

Добавь два секрета:
| Имя | Значение |
|---|---|
| `TELEGRAM_TOKEN` | токен от @BotFather |
| `TELEGRAM_CHAT_ID` | твой id от @userinfobot |

### 5. Запусти вручную для проверки
```
Actions → Bybit Signal Bot → Run workflow
```

Через 30 секунд придёт сообщение в Telegram ✅

## 📱 Пример сигнала

```
🟢 SOL/USDT — LONG  [3/4 сигналов]
💰 Цена: 71.4300 USDT

Индикаторы:
  ↑ RSI: RSI=32.4 🔵 перепродан
  ↑ MACD: hist=0.00215 ✅ бычий разворот
  ↑ EMA: EMA9(71.2) > EMA21(70.8)
  → BB: Выше средней BB (70.5)

Торговые уровни:
  📍 Вход:  71.4300
  🛑 Стоп:  68.8900
  🎯 Цель:  74.1000
  ⚖️ R/R:   1 : 1.1

⏰ 1H · Bybit Perpetual · автосигнал
```

## ⚙️ Настройка

В `bot.py` можно изменить пороги:
```python
RSI_OVERSOLD   = 35    # сигнал LONG если RSI ниже
RSI_OVERBOUGHT = 65    # сигнал SHORT если RSI выше
MIN_SIGNALS    = 2     # минимум совпавших индикаторов
```

## 💡 Как работает антиспам

Бот хранит последний сигнал в `state.json`.  
Повторный сигнал по той же паре придёт только при **смене направления** (LONG → SHORT или наоборот).

## ⚠️ Дисклеймер

Бот предоставляет технические сигналы на основе индикаторов.  
Не является финансовым советом. Торгуй на свой страх и риск.
