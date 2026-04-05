import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

TOKEN_BOT = os.getenv("TOKEN_BOT") or os.getenv("TOKEN_BOT_LONG")
CHAT_ID = os.getenv("CHAT_ID") or os.getenv("CHAT_ID_LONG")
DEFAULT_NEW_CAPITAL = 30_000
DIVIDER = "────────────────────"
STATE_FILE_PATH = Path(__file__).with_name("longterm_portfolio_state.json")
PERFORMANCE_SNAPSHOT_PATH = Path(__file__).with_name("longterm_performance_snapshot.json")


@dataclass(frozen=True)
class PortfolioPosition:
    symbol: str
    display_name: str
    emoji: str
    target_weight: int
    local_currency: str
    sanity_floor_price: float | None = None


POSITIONS: dict[str, PortfolioPosition] = {
    "KOG": PortfolioPosition(
        symbol="KOG.OL",
        display_name="KOG",
        emoji="🛡️",
        target_weight=30,
        local_currency="NOK",
    ),
    "NOVO": PortfolioPosition(
        symbol="NOVO-B.CO",
        display_name="NOVO",
        emoji="💊",
        target_weight=30,
        local_currency="DKK",
        sanity_floor_price=100.0,
    ),
    "SOFI": PortfolioPosition(
        symbol="SOFI",
        display_name="SOFI",
        emoji="📱",
        target_weight=20,
        local_currency="USD",
    ),
    "TOMRA": PortfolioPosition(
        symbol="TOM.OL",
        display_name="TOMRA",
        emoji="♻️",
        target_weight=20,
        local_currency="NOK",
    ),
}


@dataclass
class StockSnapshot:
    key: str
    symbol: str
    local_currency: str
    display_name: str
    emoji: str
    target_weight: int
    price: float | None
    month_ago_price: float | None
    price_currency: str | None
    one_month_change: float | None
    price_direction: str
    trend_text: str
    status_score: int
    weight: float
    shares: float | None
    underweight_score: int
    momentum_score: int
    value_score: int
    buy_score: int
    action: str
    assessment: str
    avg_price: float | None
    invested_value: float | None
    invested_value_nok: float | None
    current_value: float | None
    current_value_nok: float | None
    previous_value: float | None
    previous_value_nok: float | None
    change_since_last: float | None
    change_since_last_pct: float | None
    change_emoji: str


@dataclass
class PortfolioPerformanceSnapshot:
    last_report_date: str
    tickers: dict[str, dict[str, float]]
    total_value: float


class DataFetchError(RuntimeError):
    pass


def normalize_holding_key(key: str) -> str:
    upper_key = key.upper()
    aliases = {"NVO": "NOVO"}
    return aliases.get(upper_key, upper_key)


def holding_log_label(key: str) -> str:
    return key


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


def resolve_run_date() -> date:
    force_run_date = os.getenv("FORCE_RUN_DATE")
    if force_run_date:
        try:
            parsed = datetime.strptime(force_run_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("FORCE_RUN_DATE må være på format YYYY-MM-DD") from exc
        print(f"[LONGTERM] FORCE_RUN_DATE aktiv: {parsed.isoformat()}")
        return parsed

    now_oslo = datetime.now(ZoneInfo("Europe/Oslo"))
    return now_oslo.date()


def load_longterm_portfolio_state() -> dict[str, dict[str, float | str]]:
    if STATE_FILE_PATH.exists():
        try:
            raw_state = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("longterm_portfolio_state.json må være gyldig JSON") from exc

        state: dict[str, dict[str, float | str]] = {}
        for raw_key, raw_value in raw_state.items():
            key = normalize_holding_key(raw_key)
            if key not in POSITIONS or not isinstance(raw_value, dict):
                continue
            shares = max(float(raw_value.get("shares", 0.0)), 0.0)
            avg_price = float(raw_value.get("avg_price", 0.0))
            currency = str(raw_value.get("currency", ""))
            entry: dict[str, float | str] = {
                "shares": shares,
                "avg_price": avg_price,
                "currency": currency,
            }
            if "market_value_nok" in raw_value:
                entry["market_value_nok"] = float(raw_value["market_value_nok"])
            state[key] = entry

        loaded_log = ", ".join(
            f"{holding_log_label(key)}={int(state.get(key, {}).get('shares', 0))}"
            for key in POSITIONS
        )
        print(f"[LONGTERM] loaded state: {loaded_log}")
        return state

    raw = os.getenv("LONG_PORTFOLIO_HOLDINGS")
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("LONG_PORTFOLIO_HOLDINGS må være gyldig JSON") from exc

        state: dict[str, dict[str, float | str]] = {}
        for raw_key, raw_value in parsed.items():
            key = normalize_holding_key(raw_key)
            if key not in POSITIONS:
                continue

            if isinstance(raw_value, dict):
                shares = max(float(raw_value.get("shares", 0.0)), 0.0)
                avg_price = float(raw_value.get("avg_price", 0.0))
                currency = str(raw_value.get("currency", ""))
                entry: dict[str, float | str] = {
                    "shares": shares,
                    "avg_price": avg_price,
                    "currency": currency,
                }
                if "market_value_nok" in raw_value:
                    entry["market_value_nok"] = float(raw_value["market_value_nok"])
            else:
                entry = {
                    "shares": max(float(raw_value), 0.0),
                    "avg_price": 0.0,
                    "currency": "",
                }
            state[key] = entry

        loaded_log = ", ".join(
            f"{holding_log_label(key)}={int(state.get(key, {}).get('shares', 0))}"
            for key in POSITIONS
        )
        print(f"[LONGTERM] loaded state from env: {loaded_log}")
        return state

    state = {}
    for key in POSITIONS:
        print(f"[LONGTERM] fallback shares=1 brukt for {holding_log_label(key)}")
        state[key] = {"shares": 1.0, "avg_price": 0.0, "currency": ""}
    return state


def save_longterm_portfolio_state(state: dict[str, dict[str, float | str]]) -> None:
    normalized: dict[str, dict[str, float | str]] = {}
    for raw_key, holding in state.items():
        key = normalize_holding_key(raw_key)
        if key not in POSITIONS:
            continue

        entry: dict[str, float | str] = {
            "shares": max(float(holding.get("shares", 0.0)), 0.0),
            "avg_price": float(holding.get("avg_price", 0.0)),
            "currency": str(holding.get("currency", "")),
        }
        if "market_value_nok" in holding:
            entry["market_value_nok"] = float(holding["market_value_nok"])
        normalized[key] = entry

    default_holding = {"shares": 1.0, "avg_price": 0.0, "currency": ""}
    ordered = {key: normalized.get(key, default_holding) for key in POSITIONS}
    STATE_FILE_PATH.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_longterm_holding(ticker: str) -> dict[str, float | str]:
    state = load_longterm_portfolio_state()
    key = normalize_holding_key(ticker)
    if key in state:
        return state[key]
    print(f"[LONGTERM] fallback shares=1 brukt for {holding_log_label(key)}")
    return {"shares": 1.0, "avg_price": 0.0, "currency": ""}


def update_longterm_holding(
    ticker: str,
    shares: float | None = None,
    avg_price: float | None = None,
    currency: str | None = None,
    market_value_nok: float | None = None,
) -> dict[str, dict[str, float | str]]:
    state = load_longterm_portfolio_state()
    key = normalize_holding_key(ticker)
    current = state.get(key, {"shares": 1.0, "avg_price": 0.0, "currency": ""}).copy()

    if shares is not None:
        current["shares"] = max(float(shares), 0.0)
    if avg_price is not None:
        current["avg_price"] = float(avg_price)
    if currency is not None:
        current["currency"] = currency
    if market_value_nok is not None:
        current["market_value_nok"] = float(market_value_nok)

    state[key] = current
    save_longterm_portfolio_state(state)
    return state


def calculate_longterm_weights(
    state: dict[str, dict[str, float | str]],
    market_data_nok: dict[str, float | None],
) -> tuple[dict[str, float], float]:
    market_values: dict[str, float] = {}
    for key in POSITIONS:
        holding = state.get(key)
        shares = 1.0
        if holding is None:
            print(f"[LONGTERM] fallback shares=1 brukt for {holding_log_label(key)}")
        else:
            shares = max(float(holding.get("shares", 1.0)), 0.0)

        price = market_data_nok.get(key)
        value = 0.0 if price is None else shares * price
        market_values[key] = value

    total_value = sum(market_values.values())
    if total_value <= 0:
        equal_weight = round(100 / len(POSITIONS), 1)
        return {key: equal_weight for key in POSITIONS}, total_value

    weights = {}
    for key, value in market_values.items():
        weight = round((value / total_value) * 100, 1)
        weights[key] = weight
        price = market_data_nok.get(key)
        holding = state.get(key, {})
        shares = max(float(holding.get("shares", 1.0)), 0.0)
        print(
            f"[LONGTERM] weight calc: {holding_log_label(key)} shares={shares:.0f} price={price} value={value:.2f} weight={weight:.1f}"
        )
    print(f"[LONGTERM] weight calc total value={total_value:.2f}")
    return weights, total_value


def fetch_market_data(symbol: str) -> tuple[float | None, float | None, float | None, str | None]:
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
        currency = history.attrs.get("currency")
        one_month_index = max(len(closes) - 22, 0)
        month_ago_price = round(float(closes.iloc[one_month_index]), 2)
        if month_ago_price <= 0:
            one_month_change = None
        else:
            one_month_change = round(((latest_price / month_ago_price) - 1) * 100, 1)

        return latest_price, month_ago_price, one_month_change, currency
    except Exception as exc:
        print(f"Klarte ikke hente markedsdata for {symbol}: {exc}")
        return None, None, None, None




def fetch_fx_rate_to_nok(currency: str) -> float | None:
    if not currency:
        return None
    if currency in {"NOK", "KR"}:
        return 1.0

    symbol = f"{currency}NOK=X"
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="5d", interval="1d", auto_adjust=False)
        closes = history.get("Close")
        if closes is None:
            raise DataFetchError(f"Fant ikke FX Close-serie for {symbol}")

        closes = closes.dropna()
        if closes.empty:
            raise DataFetchError(f"Ingen FX-kursdata for {symbol}")

        return round(float(closes.iloc[-1]), 6)
    except Exception as exc:
        print(f"Klarte ikke hente FX-rate for {currency}->NOK ({symbol}): {exc}")
        return None

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


def build_price_direction_emoji(price: float | None, month_ago_price: float | None) -> str:
    if price is None or month_ago_price is None:
        return "➡️"
    tolerance = max(abs(month_ago_price) * 0.002, 0.01)
    diff = price - month_ago_price
    if abs(diff) <= tolerance:
        return "➡️"
    if diff > 0:
        return "↗️"
    return "↘️"


def format_number_no_decimals(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def determine_change_emoji(change_value: float | None) -> str:
    if change_value is None:
        return "➖"
    if abs(change_value) < 0.5:
        return "➖"
    if change_value > 0:
        return "📈"
    return "📉"


def load_performance_snapshot() -> PortfolioPerformanceSnapshot | None:
    if not PERFORMANCE_SNAPSHOT_PATH.exists():
        print("[LONGTERM] performance snapshot mangler, bruker fallback")
        return None

    try:
        parsed = json.loads(PERFORMANCE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("[LONGTERM] performance snapshot er ugyldig JSON, bruker fallback")
        return None

    raw_tickers = parsed.get("tickers", {})
    tickers: dict[str, dict[str, float]] = {}
    if isinstance(raw_tickers, dict):
        for raw_key, value_data in raw_tickers.items():
            key = normalize_holding_key(raw_key)
            if key not in POSITIONS or not isinstance(value_data, dict):
                continue
            ticker_data: dict[str, float] = {}
            local_value = value_data.get("local_value")
            if local_value is not None:
                ticker_data["local_value"] = float(local_value)
            legacy_value = value_data.get("value")
            if legacy_value is not None:
                ticker_data["value"] = float(legacy_value)
            value_nok = value_data.get("value_nok")
            if value_nok is not None:
                ticker_data["value_nok"] = float(value_nok)
            if ticker_data:
                tickers[key] = ticker_data

    last_report_date = str(parsed.get("last_report_date", ""))
    total_value = float(parsed.get("total_value", 0.0))
    print(
        f"[LONGTERM] performance snapshot loaded last_report_date={last_report_date} total_value={total_value:.2f}"
    )
    return PortfolioPerformanceSnapshot(
        last_report_date=last_report_date,
        tickers=tickers,
        total_value=total_value,
    )


def save_performance_snapshot(run_date: date, snapshots: list[StockSnapshot]) -> None:
    total_value = sum(snapshot.current_value_nok or 0.0 for snapshot in snapshots)
    payload = {
        "last_report_date": run_date.isoformat(),
        "tickers": {
            snapshot.key: {
                "local_value": round(snapshot.current_value or 0.0, 2),
                "value_nok": round(snapshot.current_value_nok or 0.0, 2),
            }
            for snapshot in snapshots
        },
        "total_value": round(total_value, 2),
    }
    PERFORMANCE_SNAPSHOT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[LONGTERM] performance snapshot saved date={payload['last_report_date']} total_value={payload['total_value']:.2f}"
    )


def build_snapshots() -> list[StockSnapshot]:
    state = load_longterm_portfolio_state()
    previous_snapshot = load_performance_snapshot()
    prices_local: dict[str, float | None] = {}
    prices_nok: dict[str, float | None] = {}
    month_ago_prices: dict[str, float | None] = {}
    changes: dict[str, float | None] = {}
    currencies: dict[str, str | None] = {}
    fx_to_nok: dict[str, float | None] = {}
    shares_by_ticker: dict[str, float | None] = {}

    for key, position in POSITIONS.items():
        price, month_ago_price, one_month_change, yahoo_currency = fetch_market_data(position.symbol)
        resolved_currency = position.local_currency
        if yahoo_currency and yahoo_currency != position.local_currency:
            print(
                f"[LONGTERM] {position.display_name} currency override: yahoo={yahoo_currency} configured={position.local_currency}"
            )

        fx_rate = fetch_fx_rate_to_nok(resolved_currency)
        price_nok = None if price is None or fx_rate is None else price * fx_rate

        if (
            key == "NOVO"
            and price is not None
            and position.sanity_floor_price is not None
            and price < position.sanity_floor_price
        ):
            print(
                f"[LONGTERM][WARN] NOVO price sanity check triggered: {price:.2f} {resolved_currency} "
                f"(symbol={position.symbol}, expected > {position.sanity_floor_price:.2f})"
            )

        print(
            f"[LONGTERM] ticker mapping: {key} -> {position.symbol} currency={resolved_currency} "
            f"fx_to_nok={fx_rate} price_local={price} price_nok={price_nok}"
        )

        prices_local[key] = price
        prices_nok[key] = price_nok
        month_ago_prices[key] = month_ago_price
        changes[key] = one_month_change
        currencies[key] = resolved_currency
        fx_to_nok[key] = fx_rate
        if key in state:
            shares_by_ticker[key] = max(float(state[key].get("shares", 0.0)), 0.0)
        else:
            shares_by_ticker[key] = None

    weights, _ = calculate_longterm_weights(state, prices_nok)
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
        month_ago_price = month_ago_prices[key]
        direction = build_price_direction_emoji(prices_local[key], month_ago_price)

        # Regelbasert longterm-vurdering: undervekt mot målvekt + trend/momentum + verdi/attraktivitet.
        # Nyhetsanalyse brukes ikke i denne poengmodellen.
        print(
            f"[LONGTERM] {position.display_name} underweight_score={underweight_score} "
            f"(weight={weight:.1f}% target={position.target_weight}%)"
        )
        print(
            f"[LONGTERM] {position.display_name} trend_score={momentum_score} "
            f"(one_month_change={change})"
        )
        print(
            f"[LONGTERM] {position.display_name} value_score={value_score} "
            f"(underweight={position.target_weight - weight:.1f} change={change})"
        )
        print(
            f"[LONGTERM] {position.display_name} total_buy_score={buy_score} "
            f"(underweight+trend+value)"
        )

        holding = state.get(key, {})
        avg_price_raw = holding.get("avg_price")
        avg_price = None
        if avg_price_raw is not None:
            avg_price = float(avg_price_raw)
        shares = shares_by_ticker[key]
        invested_value = None
        if shares is not None and avg_price is not None and avg_price > 0:
            invested_value = shares * avg_price
        invested_value_nok = None
        if invested_value is not None and fx_to_nok[key] is not None:
            invested_value_nok = invested_value * float(fx_to_nok[key])
        current_value = None
        if shares is not None and prices_local[key] is not None:
            current_value = shares * float(prices_local[key])
        current_value_nok = None
        if current_value is not None and fx_to_nok[key] is not None:
            current_value_nok = current_value * float(fx_to_nok[key])

        previous_value = None
        previous_value_nok = None
        if previous_snapshot is not None:
            previous_entry = previous_snapshot.tickers.get(key, {})
            previous_value = previous_entry.get("local_value")
            if previous_value is None:
                previous_value = previous_entry.get("value")
            previous_value_nok = previous_entry.get("value_nok")

        change_since_last = None
        change_since_last_pct = None
        if current_value is not None and previous_value is not None:
            change_since_last = current_value - previous_value
            if previous_value > 0:
                change_since_last_pct = (change_since_last / previous_value) * 100
        change_emoji = determine_change_emoji(change_since_last)

        print(
            f"[LONGTERM] {position.display_name} values: local_currency={currencies[key]} "
            f"invested_local={invested_value} invested_nok={invested_value_nok} "
            f"current_local={current_value} current_nok={current_value_nok}"
        )
        print(f"[LONGTERM] {position.display_name} previous_value={previous_value}")
        print(f"[LONGTERM] {position.display_name} previous_value_nok={previous_value_nok}")
        print(
            f"[LONGTERM] {position.display_name} change_since_last={change_since_last} pct={change_since_last_pct}"
        )
        print(f"[LONGTERM] {position.display_name} change_emoji={change_emoji}")

        snapshots.append(
            StockSnapshot(
                key=key,
                symbol=position.symbol,
                local_currency=currencies[key] or position.local_currency,
                display_name=position.display_name,
                emoji=position.emoji,
                target_weight=position.target_weight,
                price=prices_local[key],
                month_ago_price=month_ago_price,
                price_currency=currencies[key],
                one_month_change=change,
                price_direction=direction,
                trend_text=trend_text,
                status_score=status_score,
                weight=weight,
                shares=shares_by_ticker[key],
                underweight_score=underweight_score,
                momentum_score=momentum_score,
                value_score=value_score,
                buy_score=buy_score,
                action=determine_action(status_score, weight, position.target_weight),
                assessment=build_assessment(weight, position.target_weight, buy_score, trend_text),
                avg_price=avg_price,
                invested_value=invested_value,
                invested_value_nok=invested_value_nok,
                current_value=current_value,
                current_value_nok=current_value_nok,
                previous_value=previous_value,
                previous_value_nok=previous_value_nok,
                change_since_last=change_since_last,
                change_since_last_pct=change_since_last_pct,
                change_emoji=change_emoji,
            )
        )

    return snapshots


def format_percentage(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def resolve_price_currency(snapshot: StockSnapshot) -> str:
    if snapshot.local_currency == "NOK":
        return "kr"
    return snapshot.local_currency


def format_price(snapshot: StockSnapshot) -> str:
    if snapshot.price is None:
        if snapshot.month_ago_price is None:
            return "Kurs: ikke tilgjengelig (sist mnd: ikke tilgjengelig)"
        month_text = format_money(snapshot.month_ago_price)
        currency = resolve_price_currency(snapshot)
        if currency:
            return f"Kurs: ikke tilgjengelig (sist mnd: {month_text} {currency})"
        return f"Kurs: ikke tilgjengelig (sist mnd: {month_text})"

    value = format_money(snapshot.price)
    currency = resolve_price_currency(snapshot)
    if snapshot.month_ago_price is None:
        return f"Kurs: {value} {currency} {snapshot.price_direction} (sist mnd: ikke tilgjengelig)".strip()
    month_value = format_money(snapshot.month_ago_price)
    if currency:
        return f"Kurs: {value} {currency} {snapshot.price_direction} (sist mnd: {month_value} {currency})"
    return f"Kurs: {value} {snapshot.price_direction} (sist mnd: {month_value})"


def format_money(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def format_shares(snapshot: StockSnapshot) -> str:
    if snapshot.shares is None:
        return "Antall: ikke tilgjengelig"
    return f"Antall: {int(snapshot.shares)}"


def format_invested(snapshot: StockSnapshot) -> str:
    if snapshot.invested_value is None:
        return "Investert: ikke tilgjengelig"
    return f"Investert: {format_number_no_decimals(snapshot.invested_value)} {resolve_price_currency(snapshot)}"


def format_current_value(snapshot: StockSnapshot) -> str:
    if snapshot.current_value is None:
        return "Verdi nå: ikke tilgjengelig"
    return f"Verdi nå: {format_number_no_decimals(snapshot.current_value)} {resolve_price_currency(snapshot)}"


def format_since_last(snapshot: StockSnapshot) -> str:
    if snapshot.change_since_last is None or snapshot.change_since_last_pct is None:
        return "➖ Siden sist: ikke tilgjengelig"
    normalized_change = 0.0 if abs(snapshot.change_since_last) < 0.5 else snapshot.change_since_last
    normalized_pct = 0.0 if abs(snapshot.change_since_last_pct) < 0.05 else snapshot.change_since_last_pct
    sign = "+" if normalized_change > 0 else ""
    change_text = f"{sign}{format_number_no_decimals(normalized_change)}"
    pct_text = f"{normalized_pct:+.1f}%".replace(".", ",")
    return f"{snapshot.change_emoji} Siden sist: {change_text} {resolve_price_currency(snapshot)} ({pct_text})"


def format_portfolio_summary(snapshots: list[StockSnapshot], include_post_buy_value: bool = False) -> list[str]:
    invested_total = sum(snapshot.invested_value_nok or 0.0 for snapshot in snapshots)
    current_total = sum(snapshot.current_value_nok or 0.0 for snapshot in snapshots)
    previous_total_values = [
        snapshot.previous_value_nok for snapshot in snapshots if snapshot.previous_value_nok is not None
    ]
    previous_total = sum(previous_total_values) if previous_total_values else None
    since_last_value = None
    since_last_pct = None
    if previous_total is not None:
        since_last_value = current_total - previous_total
        if previous_total > 0:
            since_last_pct = (since_last_value / previous_total) * 100

    pnl_total = current_total - invested_total
    pnl_pct = (pnl_total / invested_total * 100) if invested_total > 0 else None
    change_emoji = determine_change_emoji(since_last_value)

    print(f"[LONGTERM] portfolio invested_total={invested_total}")
    print(f"[LONGTERM] portfolio current_total={current_total}")
    print(f"[LONGTERM] portfolio previous_total={previous_total}")
    print(f"[LONGTERM] portfolio change_emoji={change_emoji}")
    print(f"[LONGTERM] portfolio pnl_total={pnl_total}")

    lines = [
        DIVIDER,
        "",
        "📊 Porteføljeoppsummering",
        "",
        f"Totalt investert: {format_number_no_decimals(invested_total)} kr",
        f"Total verdi nå: {format_number_no_decimals(current_total)} kr",
    ]
    if since_last_value is None or since_last_pct is None:
        lines.append("➖ Siden sist: ikke tilgjengelig")
    else:
        normalized_since_last = 0.0 if abs(since_last_value) < 0.5 else since_last_value
        normalized_since_last_pct = 0.0 if abs(since_last_pct) < 0.05 else since_last_pct
        sign = "+" if normalized_since_last > 0 else ""
        since_last_kr = f"{sign}{format_number_no_decimals(normalized_since_last)}"
        since_last_pct_text = f"{normalized_since_last_pct:+.1f}%".replace(".", ",")
        lines.append(f"{change_emoji} Siden sist: {since_last_kr} kr ({since_last_pct_text})")

    if pnl_pct is None:
        lines.append("Total gevinst/tap: ikke tilgjengelig")
    else:
        sign = "+" if pnl_total > 0 else ""
        pnl_kr = f"{sign}{format_number_no_decimals(pnl_total)}"
        pnl_pct_text = f"{pnl_pct:+.1f}%".replace(".", ",")
        lines.append(f"Total gevinst/tap: {pnl_kr} kr ({pnl_pct_text})")

    if include_post_buy_value:
        lines.append(
            f"Verdi etter nytt kjøp: {format_number_no_decimals(current_total + DEFAULT_NEW_CAPITAL)} kr"
        )
    return lines


def allocate_capital(snapshots: list[StockSnapshot], total_capital: int = DEFAULT_NEW_CAPITAL) -> dict[str, int]:
    weighted_scores: dict[str, int] = {}
    for snapshot in snapshots:
        score = snapshot.buy_score
        if snapshot.weight > snapshot.target_weight + 6:
            score = max(1, score - 4)
        elif snapshot.weight > snapshot.target_weight + 2:
            score = max(1, score - 2)
        weighted_scores[snapshot.key] = max(score, 1)

    def log_allocations(stage: str, allocations: dict[str, int]) -> None:
        ordered = ", ".join(f"{snapshot.key}={allocations[snapshot.key]}" for snapshot in snapshots)
        print(f"[LONGTERM] {stage}: {ordered}")

    snapshots_by_key = {snapshot.key: snapshot for snapshot in snapshots}

    def add_priority(key: str) -> tuple[float, float, float]:
        snapshot = snapshots_by_key[key]
        under_target = snapshot.target_weight - snapshot.weight
        current_vs_target = snapshot.weight / snapshot.target_weight if snapshot.target_weight else float("inf")
        return (snapshot.buy_score, under_target, -current_vs_target)

    def reduce_priority(key: str) -> tuple[float, float, float]:
        snapshot = snapshots_by_key[key]
        over_target = snapshot.weight - snapshot.target_weight
        current_vs_target = snapshot.weight / snapshot.target_weight if snapshot.target_weight else float("inf")
        return (snapshot.buy_score, -over_target, -current_vs_target)

    total_score = sum(weighted_scores.values())
    if total_score <= 0:
        equal_amount = total_capital // len(snapshots)
        fallback_allocations = {snapshot.key: equal_amount for snapshot in snapshots}
        log_allocations("raw allocation", fallback_allocations)
        log_allocations("rounded allocation", fallback_allocations)
        log_allocations("final allocation", fallback_allocations)
        return fallback_allocations

    raw_allocations = {
        key: (score / total_score) * total_capital for key, score in weighted_scores.items()
    }
    log_allocations("raw allocation", {key: int(round(raw_allocations[key])) for key in raw_allocations})

    rounded_allocations = {
        key: int(round(amount / 1000.0) * 1000) for key, amount in raw_allocations.items()
    }
    rounded_allocations = {
        key: amount if amount == 0 or amount >= 2000 else 0 for key, amount in rounded_allocations.items()
    }
    log_allocations("rounded allocation", rounded_allocations)

    max_iterations = 10_000
    iterations = 0
    while sum(rounded_allocations.values()) != total_capital and iterations < max_iterations:
        iterations += 1
        current_total = sum(rounded_allocations.values())

        if current_total < total_capital:
            remaining = total_capital - current_total
            non_zero_keys = [key for key, amount in rounded_allocations.items() if amount >= 2000]
            addable_keys = (
                sorted(non_zero_keys, key=add_priority, reverse=True)
                if non_zero_keys
                else sorted(rounded_allocations, key=add_priority, reverse=True)
            )
            applied = False
            for key in addable_keys:
                if rounded_allocations[key] == 0:
                    if remaining >= 2000:
                        rounded_allocations[key] = 2000
                        applied = True
                        break
                    continue

                rounded_allocations[key] += 1000
                applied = True
                break
            if not applied:
                break
        else:
            reducible_keys = [key for key, amount in rounded_allocations.items() if amount >= 2000]
            reducible_keys = sorted(reducible_keys, key=reduce_priority)
            applied = False
            for key in reducible_keys:
                amount = rounded_allocations[key]
                if amount >= 3000:
                    rounded_allocations[key] -= 1000
                    applied = True
                    break
                if amount == 2000:
                    rounded_allocations[key] = 0
                    applied = True
                    break
            if not applied:
                break

    if sum(rounded_allocations.values()) != total_capital:
        raise ValueError(
            f"Klarte ikke å justere anbefalt fordeling til {total_capital} kr "
            f"(nåværende sum: {sum(rounded_allocations.values())} kr)"
        )

    log_allocations("final allocation", rounded_allocations)

    return rounded_allocations


def format_monthly_message(run_date: date, snapshots: list[StockSnapshot]) -> str:
    lines = [
        f"💼 Longportefølje – {run_date.strftime('%d.%m.%Y')}",
        "",
    ]

    for snapshot in snapshots:
        render_currency = resolve_price_currency(snapshot) if snapshot.price is not None else "n/a"
        print(
            f"[LONGTERM] Render {snapshot.display_name} price={snapshot.price} currency={render_currency}"
        )
        lines.extend(
            [
                f"{snapshot.emoji} {snapshot.display_name}",
                format_price(snapshot),
                format_shares(snapshot),
                format_invested(snapshot),
                format_current_value(snapshot),
                format_since_last(snapshot),
                f"Vekt: {snapshot.weight:.1f}% (mål {snapshot.target_weight}%)",
                f"Vurdering: {snapshot.assessment}",
                "",
            ]
        )
    lines.extend(format_portfolio_summary(snapshots))
    return "\n".join(lines)


def format_quarterly_message(run_date: date, snapshots: list[StockSnapshot]) -> str:
    allocations = allocate_capital(snapshots)
    lines = [
        f"💼 Longportefølje – {run_date.strftime('%d.%m.%Y')}",
        f"({DEFAULT_NEW_CAPITAL:,.0f} kr til fordeling)".replace(",", " "),
        "",
    ]

    for snapshot in snapshots:
        render_currency = resolve_price_currency(snapshot) if snapshot.price is not None else "n/a"
        print(
            f"[LONGTERM] Render {snapshot.display_name} price={snapshot.price} currency={render_currency}"
        )
        lines.extend(
            [
                f"{snapshot.emoji} {snapshot.display_name}",
                format_price(snapshot),
                format_shares(snapshot),
                format_invested(snapshot),
                format_current_value(snapshot),
                format_since_last(snapshot),
                f"Vekt: {snapshot.weight:.1f}% (mål {snapshot.target_weight}%)",
                f"Kjøpsscore: {snapshot.buy_score}/15",
                f"Vurdering: {snapshot.assessment}",
                "",
            ]
        )

    lines.extend([DIVIDER, "", f"💰 Anbefalt fordeling ({DEFAULT_NEW_CAPITAL:,.0f} kr)".replace(",", " "), ""])
    for snapshot in snapshots:
        amount = f"{allocations[snapshot.key]:,} kr".replace(",", " ")
        lines.append(f"{snapshot.display_name}: {amount}")
    lines.extend(format_portfolio_summary(snapshots, include_post_buy_value=True))
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

    now_oslo = datetime.now(ZoneInfo("Europe/Oslo"))
    run_date = resolve_run_date()

    message_type = determine_message_type(run_date)
    print(f"[LONGTERM] now_oslo={now_oslo.isoformat()}")
    print(f"[LONGTERM] run_date={run_date.isoformat()}")
    print(
        f"[LONGTERM] month={run_date.month} day={run_date.day} message_type={message_type}"
    )
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
        save_performance_snapshot(run_date, snapshots)
        print("Telegram-melding ble sendt")
    else:
        print("Telegram-melding ble ikke sendt")


if __name__ == "__main__":
    main()
