import os
import requests
import yfinance as yf

TOKEN = os.getenv("TOKEN_BOT_LONG")
CHAT_ID = os.getenv("CHAT_ID_LONG")


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, json=payload)


def get_price(ticker):
    stock = yf.Ticker(ticker)
    data = stock.history(period="1d")
    return round(data["Close"].iloc[-1], 2)


def main():
    if not TOKEN or not CHAT_ID:
        raise ValueError("Mangler TOKEN_BOT_LONG eller CHAT_ID_LONG")

    ticker = "KOG.OL"
    price = get_price(ticker)

    message = f"""📊 <b>KOG</b>

Kurs: <b>{price} kr</b>

Longterm status: Stabil utvikling"""

    send_telegram(message)
if __name__ == "__main__":
    main()
