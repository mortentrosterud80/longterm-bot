import os

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


def fetch_price(symbol: str) -> float | None:
    # Hent siste tilgjengelige kurs for symbolet.
    print(f"Henter kurs for {symbol}")

    try:
        stock = yf.Ticker(symbol)
        info = stock.fast_info
        last_price = info.get("lastPrice") if info else None

        if last_price is None:
            print(f"Fant ikke lastPrice for {symbol}, prøver close-kurs")
            data = stock.history(period="5d")
            if data.empty:
                print(f"Ingen kursdata funnet for {symbol}")
                return None
            last_price = data["Close"].dropna().iloc[-1]

        price = round(float(last_price), 2)
        print(f"Fant kurs for {symbol}: {price} kr")
        return price
    except Exception as exc:
        print(f"Klarte ikke hente kurs for {symbol}: {exc}")
        return None


def main() -> None:
    validate_env()

    symbol = "KOG.OL"
    price = fetch_price(symbol)

    # Bygg en enkel statusmelding ved oppstart.
    if price is not None:
        message = f"📈 Longterm bot aktiv\n{symbol} siste kurs: {price:.2f} kr"
    else:
        message = f"⚠️ Longterm bot aktiv, men klarte ikke hente kurs for {symbol}"

    sent = send_telegram(message)

    if sent:
        print("Telegram-melding ble sendt")
    else:
        print("Telegram-melding ble ikke sendt")


if __name__ == "__main__":
    main()
