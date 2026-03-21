# longterm-bot

Dette er en enkel testversjon av longterm-bot for å verifisere Telegram- og Railway-oppsettet.
Ved oppstart henter boten en testkurs for KOG, sender én testmelding til Telegram og holder deretter containeren i live.

## Miljøvariabler

Railway må ha disse miljøvariablene satt:

- `TOKEN_BOT_LONG`
- `CHAT_ID_LONG`

## Status nå

Dette er kun en testversjon for Telegram/Railway-oppsett.
Neste steg blir månedlig statusmelding og kvartalsvis longterm-rapport.

## Test i Railway

1. Commit og push til GitHub.
2. Railway deployer automatisk.
3. Se deploy-logger i Railway.
4. Boten sender én testmelding ved oppstart.
