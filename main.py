import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone

import requests
import yfinance as yf

TOKEN_BOT = os.getenv("TOKEN_BOT") or os.getenv("TOKEN_BOT_LONG")
CHAT_ID = os.getenv("CHAT_ID") or os.getenv("CHAT_ID_LONG")
DEFAULT_NEW_CAPITAL = 30_000
DIVIDER = "────────────────────"


@dataclass(frozen=True)
class PortfolioPosition:
    symbol: str
    display_name: str
    emoji: str
    target_weight: int
    currency_suffix: str


POSITIONS: dict[str, PortfolioPosition] = {
    "KOG": PortfolioPosition(
        symbol="KOG.OL",
        display_name="KOG",
        emoji="🛡️",
        target_weight=30,
        currency_suffix=" kr",
    ),
    "NOVO": PortfolioPosition(
        symbol="NVO",
        display_name="NOVO",
        emoji="💊",
        target_weight=30,
        currency_suffix="",
    ),
    "SOFI": PortfolioPosition(
        symbol="SOFI",
        display_name="SOFI",
        emoji="📱",
        target_weight=20,
        currency_suffix="",
    ),
    "TOMRA": PortfolioPosition(
        symbol="TOM.OL",
        display_name="TOMRA",
        emoji="♻️",
        target_weight=20,
        currency_suffix=" kr",
    ),
}


@dataclass
class StockSnapshot:
    key: str
    symbol: str
    display_name: str
    emoji: str
    target_weight: int
    price: float | None
    one_month_change: float | None
    trend_text: str
    status_score: int
    weight: float
    underweight_score: int
    momentum_score: int
    value_score: int
    buy_score: int
    action: str
    assessment: str


class DataFetchError(RuntimeError):
    pass


def validate_env() -> None:
    if not TOKEN_BOT:
        print("TOKEN_BOT/TOKEN_BOT_LONG mangler")
    if not CHAT_ID:
        print("CHAT_ID/CHAT_ID_LONG mangler")
    if not TOKEN_BOT or not CHAT_ID:
        raise ValueError("Mangler TOKEN_BOT/TOKEN_BOT_LONG eller CHAT_ID/CHAT_ID_LONG")


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
            print("Telegram-melding sendt")
            return True

        print(f"Telegram API-feil med statuskode: {response.status_code}")
        print(response.text)
        return False
    except requests.RequestException as exc:
        print(f"Telegram request-feil: {exc}")
        return False


def determine_message_type(run_date: date) -> str | None:
    quarter_starts = {(1, 1), (4, 1), (7, 1), (10, 1)}
    if (run_date.month, run_date.day) in quarter_starts:
        return "quarterly"
    if run_date.day == 20:
        return "monthly"
    return None


def load_holdings() -> dict[str, float]:
    raw = os.getenv("LONG_PORTFOLIO_HOLDINGS")
    if not raw:
        print("LONG_PORTFOLIO_HOLDINGS mangler, bruker standard 1 aksje per posisjon")
        return {key: 1.0 for key in POSITIONS}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("LONG_PORTFOLIO_HOLDINGS må være gyldig JSON") from exc

    holdings: dict[str, float] = {}
    for key in POSITIONS:
        amount = parsed.get(key, 0)
        holdings[key] = max(float(amount), 0.0)

    return holdings


def fetch_market_data(symbol: str) -> tuple[float | None, float | None]:
    print(f"Henter markedsdata for {symbol}")

    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="3mo", interval="1d", auto_adjust=False)
        closes = history.get("Close")

        if closes is None:
            raise DataFetchError(f"Fant ikke Close-serie for {symbol}")

        closes = closes.dropna()
        if closes.empty:
            raise DataFetchError(f"Ingen kursdata for {symbol}")

        latest_price = round(float(closes.iloc[-1]), 2)
        one_month_index = max(len(closes) - 22, 0)
        month_ago_price = float(closes.iloc[one_month_index])
        if month_ago_price <= 0:
            one_month_change = None
        else:
            one_month_change = round(((latest_price / month_ago_price) - 1) * 100, 1)

        return latest_price, one_month_change
    except Exception as exc:
        print(f"Klarte ikke hente markedsdata for {symbol}: {exc}")
        return None, None


def calculate_weights(prices: dict[str, float | None], holdings: dict[str, float]) -> dict[str, float]:
    market_values: dict[str, float] = {}
    for key, position in POSITIONS.items():
        price = prices.get(key)
        shares = holdings.get(key, 0.0)
        market_values[key] = 0.0 if price is None else price * shares

    total_value = sum(market_values.values())
    if total_value <= 0:
        equal_weight = round(100 / len(POSITIONS), 1)
        return {key: equal_weight for key in POSITIONS}

    return {
        key: round((value / total_value) * 100, 1)
        for key, value in market_values.items()
    }


def score_underweight(current_weight: float, target_weight: int) -> int:
    diff = round(target_weight - current_weight, 1)
    if diff >= 10:
        return 5
    if diff >= 6:
        return 4
    if diff >= 2:
        return 3
    if diff >= -2:
        return 2
    return 1


def score_momentum(one_month_change: float | None) -> int:
    if one_month_change is None:
        return 3
    if one_month_change >= 12:
        return 5
    if one_month_change >= 5:
        return 4
    if one_month_change >= -3:
        return 3
    if one_month_change >= -10:
        return 2
    return 1


def score_value(current_weight: float, target_weight: int, one_month_change: float | None) -> int:
    underweight = target_weight - current_weight
    if one_month_change is None:
        return 3 if underweight > 0 else 2

    if one_month_change <= -12 and underweight > 0:
        return 5
    if one_month_change <= -5 and underweight > 0:
        return 4
    if one_month_change <= 5:
        return 3
    if one_month_change <= 12:
        return 2
    return 1


def describe_trend(one_month_change: float | None) -> str:
    if one_month_change is None:
        return "Uavklart"
    if one_month_change >= 10:
        return "Sterk positiv"
    if one_month_change >= 3:
        return "Stabil positiv"
    if one_month_change > -3:
        return "Sideveis"
    if one_month_change > -10:
        return "Svak"
    return "Presset"


def determine_action(status_score: int, current_weight: float, target_weight: int) -> str:
    if current_weight > target_weight + 4:
        return "Avvent"
    if status_score >= 4:
        return "Hold"
    if status_score == 3:
        return "Følg nøye"
    return "Se an"


def build_assessment(weight: float, target_weight: int, buy_score: int, trend_text: str) -> str:
    diff = round(target_weight - weight, 1)
    if diff >= 6 and buy_score >= 11:
        return "Klart under mål og attraktiv nå"
    if diff >= 2:
        return f"Under målvekt med {trend_text.lower()} trend"
    if diff <= -4:
        return "Over målvekt, ny kapital nedprioriteres"
    return f"Nær målvekt, {trend_text.lower()} utvikling"


def build_snapshots() -> list[StockSnapshot]:
    holdings = load_holdings()
    prices: dict[str, float | None] = {}
    changes: dict[str, float | None] = {}

    for key, position in POSITIONS.items():
        price, one_month_change = fetch_market_data(position.symbol)
        prices[key] = price
        changes[key] = one_month_change

    weights = calculate_weights(prices, holdings)
    snapshots: list[StockSnapshot] = []

    for key, position in POSITIONS.items():
        change = changes[key]
        weight = weights[key]
        underweight_score = score_underweight(weight, position.target_weight)
        momentum_score = score_momentum(change)
        value_score = score_value(weight, position.target_weight, change)
        buy_score = underweight_score + momentum_score + value_score
        trend_text = describe_trend(change)
        status_score = score_momentum(change)

        snapshots.append(
            StockSnapshot(
                key=key,
                symbol=position.symbol,
                display_name=position.display_name,
                emoji=position.emoji,
                target_weight=position.target_weight,
                price=prices[key],
                one_month_change=change,
                trend_text=trend_text,
                status_score=status_score,
                weight=weight,
                underweight_score=underweight_score,
                momentum_score=momentum_score,
                value_score=value_score,
                buy_score=buy_score,
                action=determine_action(status_score, weight, position.target_weight),
                assessment=build_assessment(weight, position.target_weight, buy_score, trend_text),
            )
        )

    return snapshots


def format_percentage(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def allocate_capital(snapshots: list[StockSnapshot], total_capital: int = DEFAULT_NEW_CAPITAL) -> dict[str, int]:
    weighted_scores: dict[str, int] = {}
    for snapshot in snapshots:
        score = snapshot.buy_score
        if snapshot.weight > snapshot.target_weight + 6:
            score = max(1, score - 4)
        elif snapshot.weight > snapshot.target_weight + 2:
            score = max(1, score - 2)
        weighted_scores[snapshot.key] = max(score, 1)

    total_score = sum(weighted_scores.values())
    if total_score <= 0:
        equal_amount = total_capital // len(snapshots)
        return {snapshot.key: equal_amount for snapshot in snapshots}

    raw_allocations = {
        key: (score / total_score) * total_capital for key, score in weighted_scores.items()
    }
    rounded_allocations = {
        key: int(round(amount / 500.0) * 500) for key, amount in raw_allocations.items()
    }

    diff = total_capital - sum(rounded_allocations.values())
    if diff != 0:
        ordered_keys = sorted(weighted_scores, key=weighted_scores.get, reverse=diff > 0)
        step = 500 if diff > 0 else -500
        remaining = abs(diff)
        index = 0
        while remaining > 0 and ordered_keys:
            key = ordered_keys[index % len(ordered_keys)]
            candidate = rounded_allocations[key] + step
            if candidate >= 0:
                rounded_allocations[key] = candidate
                remaining -= 500
            index += 1

    return rounded_allocations


def format_monthly_message(run_date: date, snapshots: list[StockSnapshot]) -> str:
    title = "🔥 VISUELT – MÅNEDLIG (20.)"
    closing_line = "👉 Ingen handling – kun observasjon"

    lines = [
        title,
        "",
        f"📊 Longportefølje – {run_date.strftime('%d.%m.%Y')}",
        "(Statusoppdatering)",
        "",
    ]

    for snapshot in snapshots:
        lines.extend(
            [
                f"{snapshot.emoji} {snapshot.display_name}",
                f"Trend: {snapshot.trend_text}",
                f"Endring (1m): {format_percentage(snapshot.one_month_change)}",
                f"Score: {snapshot.status_score}/5",
                f"Vekt: {snapshot.weight:.1f}% (mål {snapshot.target_weight}%)",
                f"Tiltak: {snapshot.action}",
                "",
            ]
        )

    observations = build_monthly_commentary(snapshots)
    lines.extend(
        [
            DIVIDER,
            "🧭 Kort vurdering:",
            *observations,
            "",
            closing_line,
        ]
    )
    return "\n".join(lines)


def format_quarterly_message(run_date: date, snapshots: list[StockSnapshot]) -> str:
    allocations = allocate_capital(snapshots)
    lines = [
        "💰 VISUELT – KVARTAL",
        "",
        f"📊 Longportefølje – {run_date.strftime('%d.%m.%Y')}",
        f"({DEFAULT_NEW_CAPITAL:,.0f} kr til fordeling)".replace(",", " "),
        "",
    ]

    for snapshot in snapshots:
        lines.extend(
            [
                f"{snapshot.emoji} {snapshot.display_name}",
                f"Score: {snapshot.status_score}/5",
                f"Vekt: {snapshot.weight:.1f}% (mål {snapshot.target_weight}%)",
                f"Kjøpsscore: {snapshot.buy_score}/15",
                f"Vurdering: {snapshot.assessment}",
                "",
            ]
        )

    lines.extend([DIVIDER, "💰 Anbefalt fordeling:"])
    for snapshot in snapshots:
        amount = f"{allocations[snapshot.key]:,} kr".replace(",", " ")
        lines.append(f"{snapshot.emoji} {snapshot.display_name:<6} {amount}")

    lines.extend(
        [
            "",
            DIVIDER,
            "🧭 Kommentar:",
            *build_quarterly_commentary(snapshots, allocations),
            "",
            "👉 Strategi: Fyll opp undervekt + kvalitet først",
        ]
    )
    return "\n".join(lines)


def build_monthly_commentary(snapshots: list[StockSnapshot]) -> list[str]:
    strongest = max(snapshots, key=lambda item: item.status_score)
    weakest = min(snapshots, key=lambda item: item.status_score)
    most_underweight = max(snapshots, key=lambda item: item.target_weight - item.weight)
    return [
        f"• Beste kortsiktige trend: {strongest.display_name}.",
        f"• Mest å følge nå: {weakest.display_name}.",
        f"• Størst undervekt mot mål: {most_underweight.display_name}.",
    ]


def build_quarterly_commentary(
    snapshots: list[StockSnapshot], allocations: dict[str, int]
) -> list[str]:
    highest_score = max(snapshots, key=lambda item: item.buy_score)
    lowest_score = min(snapshots, key=lambda item: item.buy_score)
    top_allocation = max(allocations, key=allocations.get)
    return [
        f"• Høyest kjøpsscore: {highest_score.display_name} ({highest_score.buy_score}/15).",
        f"• Mest ny kapital går til {top_allocation}.",
        f"• Lavest prioritet nå: {lowest_score.display_name}.",
    ]


def main() -> None:
    validate_env()

    run_date = datetime.now(timezone.utc).date()
    message_type = determine_message_type(run_date)
    if message_type is None:
        print(f"Ingen planlagt melding for {run_date.strftime('%d.%m.%Y')}")
        return

    snapshots = build_snapshots()

    if message_type == "monthly":
        message = format_monthly_message(run_date, snapshots)
    else:
        message = format_quarterly_message(run_date, snapshots)

    sent = send_telegram(message)
    if sent:
        print("Telegram-melding ble sendt")
    else:
        print("Telegram-melding ble ikke sendt")


if __name__ == "__main__":
    main()
