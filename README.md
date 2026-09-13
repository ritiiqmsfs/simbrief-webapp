# SimBrief -> Parkposition Finder

## Setup in 5 Schritten

1. AeroDataBox-Key holen: auf rapidapi.com registrieren, "AeroDataBox" suchen,
   kostenlosen Plan abonnieren, Key kopieren.
2. Auf vercel.com mit GitHub einloggen, dieses Repo importieren.
3. Environment Variable setzen: RAPIDAPI_KEY = dein Key.
4. Deploy klicken. Fertig.

## Struktur
- vercel.json      -> Routing-Konfiguration
- api/lookup.py    -> Backend (SimBrief + AeroDataBox), Key bleibt serverseitig
- public/index.html, app.js, style.css -> die Webseite selbst

## Nutzung
SimBrief-Username eingeben, Abfragen klicken. Die Flugnummer wird automatisch
aus deinem letzten SimBrief-Flugplan gezogen. Fehlt Gate/Terminal (haeufig bei
kleineren Flughaefen wie Porto), zeigt die Seite "keine Daten" statt Fehler.
