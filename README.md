# longterm-bot

Dette er en Telegram-bot for en strukturert longportefølje med faste målvekter og to faste meldingstyper:

- månedlig statusmelding den 20. hver måned
- kvartalsvis beslutningsmelding 1.1 / 1.4 / 1.7 / 1.10

## Porteføljestruktur

Faste målvekter i systemet:

- KOG: 30 %
- NOVO: 30 %
- SOFI: 20 %
- TOMRA: 20 %

Kvartalsmeldingen bruker en kjøpsscore per aksje:

- undervekt-score (1–5)
- trend/momentum-score (1–5)
- verdi/attraktivitet-score (1–5)

Totalscore brukes til å fordele 30 000 kr dynamisk mellom posisjonene.

## Miljøvariabler

Boten støtter både gamle og nye navn på Telegram-variabler:

- `TOKEN_BOT` eller `TOKEN_BOT_LONG`
- `CHAT_ID` eller `CHAT_ID_LONG`

For å regne ut porteføljevekter leser boten beholdninger i denne rekkefølgen:

1. `longterm_portfolio_state.json` (primærkilde, persistent state)
2. `LONG_PORTFOLIO_HOLDINGS` (fallback)
3. `shares=1` per ticker (siste nødløsning)

### `longterm_portfolio_state.json`

Statefilen ligger i prosjektroten og støtter disse feltene per ticker:

- `shares`
- `avg_price`
- `currency`
- `market_value_nok` (valgfri referanseverdi)

Eksempel:

```json
{
  "KOG": {"shares": 143, "avg_price": 340.42, "currency": "NOK", "market_value_nok": 59896},
  "NVO": {"shares": 66, "avg_price": 339.71, "currency": "DKK", "market_value_nok": 23581},
  "SOFI": {"shares": 94, "avg_price": 26.37, "currency": "USD", "market_value_nok": 14583},
  "TOMRA": {"shares": 139, "avg_price": 136.19, "currency": "NOK", "market_value_nok": 16180}
}
```

Vekter regnes alltid live som:

- verdi per ticker = `shares * siste markedskurs`
- totalverdi = sum av tickere
- vekt = `tickerverdi / totalverdi * 100`

### Fallback med miljøvariabel

Eksempel:

```json
{"KOG": 12, "NOVO": 8, "SOFI": 30, "TOMRA": 15}
```

Hvis både statefil og `LONG_PORTFOLIO_HOLDINGS` mangler, bruker boten `1` som standard per posisjon for å kunne lage en melding uten å krasje.

### Enkel manuell oppdatering av state

Bruk hjelpefunksjonen `update_longterm_holding(...)` når du vil oppdatere beholdning etter kjøp/salg:

```python
from main import update_longterm_holding

update_longterm_holding("KOG", shares=150, avg_price=345.10)
```

## Kjøring

Ved oppstart sjekker boten datoen:

- 20. i måneden: sender månedlig statusmelding
- 1. januar / 1. april / 1. juli / 1. oktober: sender kvartalsmelding
- andre datoer: sender ingen melding

## Data og melding

- Kursdata hentes fra Yahoo Finance via `yfinance`
- Meldinger formatteres for kort, mobilvennlig Telegram-visning
- Kvartalsfordeling rundes til nærmeste 500 kr og summeres til 30 000 kr
