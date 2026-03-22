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

For å regne ut porteføljevekter bør du også sette beholdningene som JSON i:

- `LONG_PORTFOLIO_HOLDINGS`

Eksempel:

```json
{"KOG": 12, "NOVO": 8, "SOFI": 30, "TOMRA": 15}
```

Hvis beholdninger ikke er satt, bruker boten `1` som standard per posisjon for å kunne lage en melding uten å krasje.

## Kjøring

Ved oppstart sjekker boten datoen:

- 20. i måneden: sender månedlig statusmelding
- 1. januar / 1. april / 1. juli / 1. oktober: sender kvartalsmelding
- andre datoer: sender ingen melding

## Data og melding

- Kursdata hentes fra Yahoo Finance via `yfinance`
- Meldinger formatteres for kort, mobilvennlig Telegram-visning
- Kvartalsfordeling rundes til nærmeste 500 kr og summeres til 30 000 kr
