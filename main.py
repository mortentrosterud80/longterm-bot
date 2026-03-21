import os
import time
import requests
import yfinance as yf


# Linje 7-8: henter Railway-variabler
TOKEN = os.getenv("TOKEN_BOT_LONG")
CHAT_ID = os.getenv("CHAT_ID_LONG")


# Linje 12-16: stopper tidlig hvis variabler mangler
def validate_env() -> None:
    if not TOKEN or not CHAT_ID:
        raise ValueError("Mangler TOKEN_BOT_LONG eller CHAT_ID_LONG")


# Linje 20-32: sender Telegram-melding
def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()


# Linje 36-43: henter siste close/pris
def get_price(ticker: str) -> float:
    stock = yf.Ticker(ticker)
    data = stock.history(period="1d")

    if data.empty:
        raise ValueError(f"Ingen kursdata funnet for {ticker}")

    return round(float(data["Close"].iloc[-1]), 2)


# Linje 47-56: bygger testmelding
def build_message() -> str:
    ticker = "KOG.OL"
    price = get_price(ticker)

    return f"""📊 <b>KOG</b>

Kurs: <b>{price} kr</b>

Longterm status: Stabil utvikling"""


# Linje 60-74: kjører én testmelding ved oppstart, holder så containeren levende
def main() -> None:
    validate_env()

    message = build_message()
    send_telegram(message)

    # Holder Railway-servicen oppe uten å spamme Telegram
    while True:
        time.sleep(3600)


# Linje 78-79: startpunkt
if __name__ == "__main__":
    main()
