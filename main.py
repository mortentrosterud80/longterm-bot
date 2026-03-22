import os
import time

import requests
import yfinance as yf

TOKEN_BOT = os.getenv("TOKEN_BOT")
CHAT_ID = os.getenv("CHAT_ID")


def validate_env() -> None:
    if not TOKEN_BOT:
        print("TOKEN_BOT mangler")
    if not CHAT_ID:
        print("CHAT_ID mangler")
    if not TOKEN_BOT or not CHAT_ID:
        raise ValueError("Mangler TOKEN_BOT eller CHAT_ID")


def send_telegram(message: str) -> bool:
    url = f"https://api.telegram.org/bot{TOKEN_BOT}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.ok:
            print("Telegram testmelding sendt")
            return True

        print(f"Telegram API-feil med statuskode: {response.status_code}")
        print(response.text)
        return False
    except requests.RequestException as exc:
        print(f"Telegram request-feil: {exc}")
        return False


def get_price(ticker: str) -> float:
    stock = yf.Ticker(ticker)
    data = stock.history(period="1d")

    if data.empty:
        raise ValueError(f"Ingen kursdata funnet for {ticker}")

    return round(float(data["Close"].iloc[-1]), 2)


def build_message() -> str:
    ticker = "KOG.OL"
    price = get_price(ticker)
    return f"📊 <b>KOG</b>\n\nKurs: <b>{price} kr</b>\n\nLongterm status: Stabil utvikling"


def main() -> None:
    validate_env()
    message = build_message()
    sent = send_telegram(message)

    if not sent:
        print("Telegram testmelding feilet")
    else:
        print("Telegram testmelding lyktes")

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
