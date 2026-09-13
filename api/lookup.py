"""
Vercel Serverless Function: /api/lookup
-----------------------------------------
Ablauf:
1. SimBrief-Flugplan des Users abrufen (kein Key noetig)
2. Flugnummer bei AeroDataBox (RapidAPI Free Tier) abfragen
3. Passenden Flug (Route-Match) auswaehlen, Terminal/Gate extrahieren

WICHTIG: RAPIDAPI_KEY wird als Vercel Environment Variable gesetzt,
ist serverseitig und landet NIE im Browser-Bundle.
"""

import os
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode
import urllib.request
import urllib.error

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"
SIMBRIEF_URL = "https://www.simbrief.com/api/xml.fetcher.php"
ADB_BASE = "https://aerodatabox.p.rapidapi.com"


class UpstreamError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def _get_json(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {}
        return e.code, parsed
    except urllib.error.URLError as e:
        raise UpstreamError(f"Verbindung fehlgeschlagen: {e.reason}", 502)


def fetch_simbrief_plan(username):
    if not username or not username.strip():
        raise UpstreamError("SimBrief-Username fehlt.", 400)

    url = f"{SIMBRIEF_URL}?{urlencode({'username': username.strip(), 'json': '1'})}"
    status, data = _get_json(url)

    if status != 200:
        raise UpstreamError(
            f"SimBrief antwortete mit Status {status}. Username pruefen.", status
        )

    if isinstance(data, dict) and data.get("fetch", {}).get("status") == "Error":
        raise UpstreamError(
            "Kein aktueller Flugplan fuer diesen SimBrief-User gefunden.", 404
        )

    try:
        origin = data["origin"]
        destination = data["destination"]
        general = data["general"]
        atc = data.get("atc", {})
    except (KeyError, TypeError):
        raise UpstreamError("SimBrief-Antwort konnte nicht geparst werden.", 502)

    flight_number_raw = atc.get("callsign") or (
        general.get("icao_airline", "") + general.get("flight_number", "")
    )

    return {
        "flight_number": flight_number_raw.strip(),
        "aircraft": data.get("aircraft", {}).get("name", "unbekannt"),
        "origin": {
            "icao": origin.get("icao_code"),
            "iata": origin.get("iata_code"),
            "name": origin.get("name"),
        },
        "destination": {
            "icao": destination.get("icao_code"),
            "iata": destination.get("iata_code"),
            "name": destination.get("name"),
        },
    }


def fetch_flight_status(flight_number):
    if not RAPIDAPI_KEY:
        raise UpstreamError("Kein RAPIDAPI_KEY in den Vercel Env-Vars konfiguriert.", 500)
    if not flight_number:
        raise UpstreamError("Keine Flugnummer vorhanden.", 400)

    clean_number = flight_number.replace(" ", "").upper()
    url = f"{ADB_BASE}/flights/number/{clean_number}?withAircraftImage=false&withLocation=false"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }

    status, data = _get_json(url, headers=headers)

    if status == 429:
        raise UpstreamError(
            "AeroDataBox Rate-Limit erreicht (Free Tier: 1 Request/Sek, 400 Units/Monat).",
            429,
        )
    if status == 404 or not data:
        raise UpstreamError(f"Keine Daten fuer Flug {clean_number} gefunden.", 404)
    if status != 200:
        raise UpstreamError(f"AeroDataBox antwortete mit Status {status}.", status)

    return data


def pick_best_match(flights, origin_icao, destination_icao):
    for f in flights:
        dep_icao = f.get("departure", {}).get("airport", {}).get("icao")
        arr_icao = f.get("arrival", {}).get("airport", {}).get("icao")
        if dep_icao == origin_icao and arr_icao == destination_icao:
            return f
    return flights[0]


def extract_ground_info(flight):
    dep = flight.get("departure", {})
    arr = flight.get("arrival", {})

    def gate_block(block):
        return {
            "airport_icao": block.get("airport", {}).get("icao"),
            "airport_iata": block.get("airport", {}).get("iata"),
            "airport_name": block.get("airport", {}).get("name"),
            "terminal": block.get("terminal") or None,
            "gate": block.get("gate") or None,
        }

    return {
        "flight_number": flight.get("number"),
        "status": flight.get("status"),
        "airline": (flight.get("airline") or {}).get("name"),
        "aircraft_model": (flight.get("aircraft") or {}).get("model"),
        "departure": gate_block(dep),
        "arrival": gate_block(arr),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            payload = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            payload = {}

        username = payload.get("simbrief_username", "")

        try:
            plan = fetch_simbrief_plan(username)
            flights = fetch_flight_status(plan["flight_number"])
            best = pick_best_match(flights, plan["origin"]["icao"], plan["destination"]["icao"])
            ground_info = extract_ground_info(best)
            response_body = {"simbrief_plan": plan, "ground_info": ground_info}
            status_code = 200
        except UpstreamError as exc:
            response_body = {"error": str(exc)}
            status_code = exc.status_code
        except Exception as exc:
            response_body = {"error": f"Interner Fehler: {exc}"}
            status_code = 500

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_body).encode("utf-8"))
