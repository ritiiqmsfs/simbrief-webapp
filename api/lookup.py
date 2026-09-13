"""
Vercel Serverless Function: /api/lookup
-----------------------------------------
v2 Aenderungen:
- Flugnummer wird jetzt explizit aus general.icao_airline + general.flight_number
  gebildet (SimBrief-Flugnummer), NICHT mehr aus atc.callsign. Das Callsign
  (z.B. bei Lufthansa oft "LUFTHANSA 1788" oder abweichend) ist NICHT identisch
  mit der oeffentlichen Flugnummer (z.B. DLH1788 / LH1788) und fuehrte bei
  AeroDataBox zu falschen oder keinen Treffern.
- Historische/datumsspezifische Abfrage: nutzt jetzt den AeroDataBox-Endpoint
  /flights/number/{FLUGNUMMER}/{DATUM}, mit dem geplanten SimBrief-Abflugdatum
  als Datum. Fallback auf den Endpoint ohne Datum (aktuelle/naechste Fluege),
  falls kein Datum ermittelbar ist oder die datumsspezifische Abfrage leer bleibt.
- Erweiterter SimBrief-Datenextrakt: Distanz, Flugzeit, Reiseflughoehe, Treibstoff,
  Passagiere/Fracht, Crew, Wetter (METAR) an Abflug/Ziel, Callsign als Zusatzinfo.

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


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _seconds_to_hhmm(seconds):
    total = _safe_int(seconds)
    if total is None:
        return None
    h = total // 3600
    m = (total % 3600) // 60
    return f"{h:02d}:{m:02d}"


def fetch_simbrief_plan(username):
    """Holt den SimBrief-Flugplan. Extrahiert die ECHTE Flugnummer
    (general.icao_airline + general.flight_number), NICHT das ATC-Callsign,
    da beide bei vielen Airlines (z.B. Lufthansa) voneinander abweichen.
    Zusaetzlich werden zahlreiche weitere Flugplandetails extrahiert
    (Distanz, Flugzeit, Reiseflughoehe, Treibstoff, Crew, Wetter, Route)."""
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

    icao_airline = (general.get("icao_airline") or "").strip()
    flight_num_only = (general.get("flight_number") or "").strip()
    flight_number = f"{icao_airline}{flight_num_only}".strip()
    callsign = (atc.get("callsign") or "").strip()

    if not flight_number:
        raise UpstreamError(
            "Konnte keine Flugnummer aus general.icao_airline/flight_number "
            "extrahieren.", 502
        )

    dep_epoch = origin.get("plan_time_departure")
    dep_date_utc = None
    if dep_epoch:
        try:
            dep_date_utc = datetime.fromtimestamp(int(dep_epoch), tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            dep_date_utc = None

    aircraft = data.get("aircraft", {})
    weights = data.get("weights", {})
    fuel = data.get("fuel", {})
    times = data.get("times", {})
    crew = data.get("crew", {})
    weather_orig = origin.get("metar")
    weather_dest = destination.get("metar")
    alternate = data.get("alternate", {})
    params = data.get("params", {})

    route_navlog = []
    navlog_fixes = data.get("navlog", {}).get("fix", []) if isinstance(data.get("navlog"), dict) else []
    if isinstance(navlog_fixes, dict):
        navlog_fixes = [navlog_fixes]
    for fix in navlog_fixes:
        ident = fix.get("ident")
        fix_type = fix.get("type")
        if ident and fix_type in ("wpt", "apt", "vor", "ndb"):
            route_navlog.append(ident)

    return {
        "flight_number": flight_number,
        "callsign": callsign,
        "airline_name": (general.get("icao_airline") or general.get("airline") or "unbekannt"),
        "aircraft": aircraft.get("name", "unbekannt"),
        "aircraft_icao": aircraft.get("icaocode"),
        "aircraft_reg": data.get("params", {}).get("registration") or aircraft.get("reg"),
        "departure_date_utc": dep_date_utc,
        "route_string": general.get("route"),
        "route_waypoints": route_navlog[:12],
        "initial_altitude_ft": general.get("initial_altitude"),
        "cruise_mach": general.get("cruise_mach"),
        "air_distance_nm": _safe_float(general.get("air_distance")),
        "route_distance_nm": _safe_float(general.get("route_distance")),
        "flight_time_hhmm": _seconds_to_hhmm(general.get("total_burn") and times.get("est_time_enroute")),
        "block_time_hhmm": _seconds_to_hhmm(times.get("est_block")),
        "passengers": _safe_int(weights.get("pax_count")),
        "cargo_kg": _safe_float(weights.get("cargo")),
        "payload_kg": _safe_float(weights.get("payload")),
        "takeoff_fuel_kg": _safe_float(fuel.get("plan_takeoff")),
        "trip_fuel_kg": _safe_float(fuel.get("plan_trip")),
        "reserve_fuel_kg": _safe_float(fuel.get("plan_reserve")),
        "captain": crew.get("pic") or None,
        "dispatcher": crew.get("dxname") or None,
        "origin": {
            "icao": origin.get("icao_code"),
            "iata": origin.get("iata_code"),
            "name": origin.get("name"),
            "elevation_ft": _safe_float(origin.get("elevation")),
            "metar": weather_orig,
        },
        "destination": {
            "icao": destination.get("icao_code"),
            "iata": destination.get("iata_code"),
            "name": destination.get("name"),
            "elevation_ft": _safe_float(destination.get("elevation")),
            "metar": weather_dest,
        },
        "alternate": {
            "icao": alternate.get("icao_code"),
            "name": alternate.get("name"),
        } if alternate.get("icao_code") else None,
    }


def fetch_flight_status(flight_number, departure_date_utc=None):
    """Fragt AeroDataBox nach dem Flugstatus ab.

    Wenn ein Abflugdatum vorliegt (z.B. aus einem SimBrief-Plan mit fixem
    Datum, auch in der Vergangenheit), wird der datumsspezifische Endpoint
    /flights/number/{FLUGNUMMER}/{DATUM} verwendet - das deckt sowohl
    zukuenftige als auch HISTORISCHE Flugdaten ab.

    Ohne Datum wird auf den relativen Endpoint (aktuelle/naechste Tage)
    zurueckgefallen.
    """
    if not RAPIDAPI_KEY:
        raise UpstreamError("Kein RAPIDAPI_KEY in den Vercel Env-Vars konfiguriert.", 500)
    if not flight_number:
        raise UpstreamError("Keine Flugnummer vorhanden.", 400)

    clean_number = flight_number.replace(" ", "").upper()
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    query = "withAircraftImage=false&withLocation=false"

    if departure_date_utc:
        url = f"{ADB_BASE}/flights/number/{clean_number}/{departure_date_utc}?{query}"
        status, data = _get_json(url, headers=headers)

        if status == 429:
            raise UpstreamError(
                "AeroDataBox Rate-Limit erreicht (Free Tier: 1 Request/Sek, 400 Units/Monat).",
                429,
            )
        if status == 200 and data:
            return data

    url = f"{ADB_BASE}/flights/number/{clean_number}?{query}"
    status, data = _get_json(url, headers=headers)

    if status == 429:
        raise UpstreamError(
            "AeroDataBox Rate-Limit erreicht (Free Tier: 1 Request/Sek, 400 Units/Monat).",
            429,
        )
    if status == 404 or not data:
        raise UpstreamError(
            f"Keine Daten fuer Flug {clean_number}"
            + (f" am {departure_date_utc}" if departure_date_utc else "")
            + " gefunden.",
            404,
        )
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
            "scheduled_time_local": (block.get("scheduledTime", {}) or {}).get("local"),
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
            flights = fetch_flight_status(plan["flight_number"], plan.get("departure_date_utc"))
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
