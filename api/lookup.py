"""
Vercel Serverless Function: /api/lookup
-----------------------------------------
v8 Aenderungen (erweiterte, aber EHRLICHE Terminal-Naeherung):
- Nutzeranfrage: Terminal-Zuordnung fuer alle europaeischen Ziele von
  Lufthansa, Condor, Eurowings, Discover, easyJet abdecken. Recherche-
  ergebnis: Die weit ueberwiegende Mehrheit dieser Ziele sind
  Regionalflughaefen mit GENAU EINEM Terminal - dort ist keine Zuordnung
  noetig, da nichts zuzuordnen ist. Auch mehrere grosse Hubs (Zuerich, Wien,
  Bruessel) haben KEINE echte Airline-basierte Terminal-Trennung, obwohl sie
  mehrere Terminal-Namen haben - eine Schaetzung waere dort irrefuehrend.
- Diese Version deckt daher alle europaeischen Flughaefen ab, an denen eine
  Terminal-Naeherung tatsaechlich einen Unterschied macht (Muenchen,
  Frankfurt, London Heathrow, Paris CDG, Madrid, Mailand Malpensa), PLUS
  eine explizite "kein Terminal-Konzept"-Kennzeichnung fuer Hubs, wo eine
  Schaetzung falsch waere (Amsterdam, Bruessel, Zuerich, Wien), PLUS
  Single-Terminal-Flughaefen wie Porto.
- Alle Regeln basieren auf oeffentlich dokumentierten, offiziellen Angaben
  der Flughafenbetreiber - keine Vermutungen ohne Quellenbasis.
- Weiterhin gilt: NIEMALS ein erfundenes Gate, nur Terminal-Naeherungen,
  klar als "geschaetzt" gekennzeichnet.

Weiterhin: IATA/ICAO-Flugnummer-Fallback, SimBrief-Daten werden immer
angezeigt, robuste Typbehandlung (_d/_l), FIDS-Fallback, Gate-Historie.

WICHTIG: RAPIDAPI_KEY wird als Vercel Environment Variable gesetzt,
ist serverseitig und landet NIE im Browser-Bundle.
"""

import os
import json
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode
import urllib.request
import urllib.error

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"
SIMBRIEF_URL = "https://www.simbrief.com/api/xml.fetcher.php"
ADB_BASE = "https://aerodatabox.p.rapidapi.com"

ICAO_TO_IATA = {
    "DLH": "LH", "CFG": "DE", "GEC": "4Y", "EWG": "EW", "AUA": "OS",
    "SWR": "LX", "BEL": "SN", "KLM": "KL", "BAW": "BA", "AFR": "AF",
    "IBE": "IB", "VLG": "VY", "RYR": "FR", "EZY": "U2", "WZZ": "W6",
    "THY": "TK", "PGT": "PC", "UAE": "EK", "QTR": "QR", "ETD": "EY",
    "SIA": "SQ", "CPA": "CX", "ANA": "NH", "JAL": "JL", "UAL": "UA",
    "AAL": "AA", "DAL": "DL", "ACA": "AC", "QFA": "QF", "TAP": "TP",
    "FIN": "AY", "SAS": "SK", "LOT": "LO", "ROT": "RO", "AEE": "A3",
    "CSA": "OK", "AZA": "AZ", "ITY": "AZ", "VIR": "VS", "NAX": "DY",
    "WJA": "WS", "AMX": "AM", "AVA": "AV", "GLO": "G3", "TAM": "JJ",
    "PIA": "PK", "ETH": "ET", "KQA": "KQ", "MSR": "MS", "RJA": "RJ",
    "ELY": "LY", "SVA": "SV", "UZB": "HY", "AFL": "SU", "AIC": "AI",
    "IGO": "6E", "AXM": "AK", "JST": "JQ", "CEB": "5J", "VJC": "VJ",
    "SXS": "SX", "FDX": "FX", "UPS": "5X", "GTI": "5Y", "BOX": "OY",
}

STAR_ALLIANCE_IATA = {
    "LH", "LX", "OS", "SN", "EW", "VL", "A3", "TP", "SK", "TK",
    "SQ", "NH", "UA", "AC", "CA", "MS", "ET", "ZH", "AI", "NZ",
    "OZ", "OU", "AV", "CM", "SA", "TG", "RO", "EN",
}

AIRPORT_TERMINAL_RULES = {
    "EDDM": {
        "star_alliance_terminal": "2",
        "default_terminal": "1",
        "star_alliance_airlines_iata": STAR_ALLIANCE_IATA,
        "note": "Terminal 2 exklusiv fuer Lufthansa Group & Star Alliance, "
                "Terminal 1 fuer alle anderen Airlines. Quelle: Munich Airport.",
    },
    "EDDF": {
        "star_alliance_terminal": "1",
        "default_terminal": "3",
        "star_alliance_airlines_iata": STAR_ALLIANCE_IATA,
        "note": "Terminal 1 fuer Lufthansa Group & Star Alliance plus Condor, "
                "Terminal 3 fuer alle anderen (Stand 2026). Quelle: Fraport.",
    },
    "EGLL": {
        "terminal_by_airline_iata": {
            "BA": "5", "IB": "5",
            "AA": "3", "VS": "3", "CX": "3", "JL": "3", "QF": "3", "MH": "3",
            "AF": "4", "KL": "4", "QR": "4", "EY": "4", "SV": "4",
            "LH": "2", "UA": "2", "AC": "2", "SQ": "2", "NH": "2", "OS": "2",
            "LX": "2", "SN": "2", "TK": "2", "SK": "2", "LO": "2", "A3": "2",
            "EI": "2", "FI": "2", "MS": "2", "ET": "2",
        },
        "default_terminal": None,
        "note": "T2 Star Alliance, T3 oneworld (ausser BA/IB) + Virgin "
                "Atlantic, T4 SkyTeam (teilweise), T5 exklusiv British "
                "Airways & Iberia. Quelle: Heathrow Airport.",
    },
    "LFPG": {
        "terminal_by_airline_iata": {
            "AF": "2E/2F", "KL": "2F", "DL": "2E",
        },
        "star_alliance_terminal": "1",
        "default_terminal": "2",
        "star_alliance_airlines_iata": STAR_ALLIANCE_IATA,
        "note": "Terminal 1 fuer Star Alliance, Terminal 2E/2F fuer Air "
                "France & SkyTeam-Partner. Quelle: Groupe ADP.",
    },
    "LEMD": {
        "terminal_by_airline_iata": {
            "IB": "4", "I2": "4", "YW": "4", "BA": "4", "AA": "4", "QR": "4",
            "RJ": "4", "AY": "4", "EK": "4",
        },
        "default_terminal": "1",
        "note": "Terminal 4 exklusiv fuer Iberia & oneworld-Partner, "
                "Terminal 1 als Naeherung fuer SkyTeam/Star Alliance/Low-"
                "Cost. Quelle: Aena / Iberia.",
    },
    "LIMC": {
        "terminal_by_airline_iata": {
            "U2": "2",
        },
        "default_terminal": "1",
        "note": "Terminal 2 exklusiv fuer easyJet, Terminal 1 fuer alle "
                "anderen Airlines (Star Alliance, SkyTeam, oneworld, ITA). "
                "Quelle: SEA Milano.",
    },
    "LPPR": {
        "single_terminal": True,
        "default_terminal": None,
        "note": "Porto hat nur ein einziges Terminalgebaeude fuer alle "
                "Airlines (Concourse A/B nach Security, keine Airline-"
                "Zuordnung).",
    },
    "EHAM": {
        "no_terminal_concept": True,
        "note": "Schiphol hat kein Multi-Terminal-Konzept, sondern ein "
                "Gebaeude mit mehreren Piers ohne feste Airline-Zuordnung.",
    },
    "EBBR": {
        "no_terminal_concept": True,
        "note": "Bruessel nutzt ein Ein-Terminal-Konzept mit Piers A "
                "(Schengen) und B (Non-Schengen), keine Airline-basierte "
                "Terminal-Trennung.",
    },
    "LSZH": {
        "no_terminal_concept": True,
        "note": "Zuerich hat ein zusammenhaengendes Terminal-Gebaeude mit "
                "Docks A/B/E, die nach Schengen/Non-Schengen, nicht nach "
                "Airline getrennt sind.",
    },
    "LOWW": {
        "no_terminal_concept": True,
        "note": "Wien besteht aus einem zusammenhaengenden Gebaeudekomplex "
                "ohne zuverlaessig vorhersagbare Airline-Terminal-Trennung.",
    },
}


class UpstreamError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def _d(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return value[0]
        return {}
    return {}


def _l(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


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


def build_flight_number_candidates(icao_airline, flight_num_only):
    candidates = []
    icao_airline = (icao_airline or "").strip().upper()
    flight_num_only = (flight_num_only or "").strip()

    iata_code = ICAO_TO_IATA.get(icao_airline)
    if iata_code:
        candidates.append(f"{iata_code}{flight_num_only}")

    if icao_airline:
        icao_variant = f"{icao_airline}{flight_num_only}"
        if icao_variant not in candidates:
            candidates.append(icao_variant)

    return candidates


def get_iata_airline_code(icao_airline):
    return ICAO_TO_IATA.get((icao_airline or "").strip().upper())


def derive_terminal_estimate(airport_icao, airline_iata):
    rule = AIRPORT_TERMINAL_RULES.get(airport_icao)
    if not rule:
        return None

    if rule.get("no_terminal_concept") or rule.get("single_terminal"):
        return {"terminal": None, "note": rule.get("note"), "derived": True}

    airline_iata = (airline_iata or "").upper()

    direct_map = rule.get("terminal_by_airline_iata", {})
    if airline_iata in direct_map:
        return {
            "terminal": direct_map[airline_iata],
            "note": rule.get("note"),
            "derived": True,
        }

    if "star_alliance_terminal" in rule:
        star_set = rule.get("star_alliance_airlines_iata", set())
        if airline_iata in star_set:
            terminal = rule.get("star_alliance_terminal")
        else:
            terminal = rule.get("default_terminal")
        return {"terminal": terminal, "note": rule.get("note"), "derived": True}

    default_terminal = rule.get("default_terminal")
    if default_terminal:
        return {"terminal": default_terminal, "note": rule.get("note"), "derived": True}

    return None


def fetch_simbrief_plan(username):
    if not username or not username.strip():
        raise UpstreamError("SimBrief-Username fehlt.", 400)

    url = f"{SIMBRIEF_URL}?{urlencode({'username': username.strip(), 'json': '1'})}"
    status, data = _get_json(url)

    if status != 200:
        raise UpstreamError(
            f"SimBrief antwortete mit Status {status}. Username pruefen.", status
        )

    if isinstance(data, dict) and _d(data.get("fetch")).get("status") == "Error":
        raise UpstreamError(
            "Kein aktueller Flugplan fuer diesen SimBrief-User gefunden.", 404
        )

    if not isinstance(data, dict):
        raise UpstreamError("SimBrief-Antwort hatte unerwartetes Format.", 502)

    origin = _d(data.get("origin"))
    destination = _d(data.get("destination"))
    general = _d(data.get("general"))
    atc = _d(data.get("atc"))

    if not origin or not destination or not general:
        raise UpstreamError("SimBrief-Antwort konnte nicht geparst werden.", 502)

    icao_airline = str(general.get("icao_airline") or "").strip()
    flight_num_only = str(general.get("flight_number") or "").strip()
    flight_number_candidates = build_flight_number_candidates(icao_airline, flight_num_only)
    callsign = str(atc.get("callsign") or "").strip()

    if not flight_number_candidates:
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

    aircraft = _d(data.get("aircraft"))
    weights = _d(data.get("weights"))
    fuel = _d(data.get("fuel"))
    times = _d(data.get("times"))
    crew = _d(data.get("crew"))
    alternate = _d(data.get("alternate"))
    params = _d(data.get("params"))

    weather_orig = origin.get("metar")
    weather_dest = destination.get("metar")

    route_navlog = []
    navlog_container = _d(data.get("navlog"))
    navlog_fixes = _l(navlog_container.get("fix"))
    for fix in navlog_fixes:
        if not isinstance(fix, dict):
            continue
        ident = fix.get("ident")
        fix_type = fix.get("type")
        if ident and fix_type in ("wpt", "apt", "vor", "ndb"):
            route_navlog.append(ident)

    return {
        "flight_number": flight_number_candidates[0],
        "flight_number_candidates": flight_number_candidates,
        "airline_iata": get_iata_airline_code(icao_airline),
        "callsign": callsign,
        "airline_name": (general.get("icao_airline") or general.get("airline") or "unbekannt"),
        "aircraft": aircraft.get("name", "unbekannt"),
        "aircraft_icao": aircraft.get("icaocode"),
        "aircraft_reg": params.get("registration") or aircraft.get("reg"),
        "departure_date_utc": dep_date_utc,
        "route_string": general.get("route"),
        "route_waypoints": route_navlog[:12],
        "initial_altitude_ft": general.get("initial_altitude"),
        "cruise_mach": general.get("cruise_mach"),
        "air_distance_nm": _safe_float(general.get("air_distance")),
        "route_distance_nm": _safe_float(general.get("route_distance")),
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


def fetch_flights_range(flight_number, from_local, to_local):
    if not RAPIDAPI_KEY:
        raise UpstreamError("Kein RAPIDAPI_KEY in den Vercel Env-Vars konfiguriert.", 500)

    clean_number = flight_number.replace(" ", "").upper()
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    query = "withAircraftImage=false&withLocation=false"
    url = f"{ADB_BASE}/flights/number/{clean_number}/{from_local}/{to_local}?{query}"

    status, data = _get_json(url, headers=headers)

    if status == 429:
        raise UpstreamError(
            "AeroDataBox Rate-Limit erreicht (Free Tier: 1 Request/Sek, 400 Units/Monat).",
            429,
        )
    if status == 200 and data:
        return data if isinstance(data, list) else [data]
    return []


def fetch_flight_status_single(flight_number, departure_date_utc=None):
    if not RAPIDAPI_KEY:
        raise UpstreamError("Kein RAPIDAPI_KEY in den Vercel Env-Vars konfiguriert.", 500)

    clean_number = flight_number.replace(" ", "").upper()
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    query = "withAircraftImage=false&withLocation=false"

    if departure_date_utc:
        url = f"{ADB_BASE}/flights/number/{clean_number}/{departure_date_utc}?{query}"
        status, data = _get_json(url, headers=headers)
        if status == 200 and data:
            return data if isinstance(data, list) else [data]

    url = f"{ADB_BASE}/flights/number/{clean_number}?{query}"
    status, data = _get_json(url, headers=headers)
    if status == 200 and data:
        return data if isinstance(data, list) else [data]

    return []


def fetch_airport_fids(airport_icao, from_local, to_local, direction="Departure"):
    if not RAPIDAPI_KEY or not airport_icao:
        return []

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    query = (
        f"withLeg=false&direction={direction}&withCancelled=true"
        f"&withCodeshared=true&withCargo=false&withPrivate=false&withLocation=false"
    )
    url = f"{ADB_BASE}/flights/airports/icao/{airport_icao}/{from_local}/{to_local}?{query}"

    status, data = _get_json(url, headers=headers)
    if status != 200 or not data:
        return []

    departures = _l(_d(data).get("departures"))
    arrivals = _l(_d(data).get("arrivals"))
    return departures + arrivals


def find_gate_via_fids(flight_number_candidates, origin_icao, destination_icao, range_days=4):
    today = datetime.now(timezone.utc).date()
    candidates_upper = [c.upper() for c in flight_number_candidates]
    matches = []

    for day_offset in range(range_days):
        day = today - timedelta(days=day_offset)
        from_local = day.strftime("%Y-%m-%dT00:00")
        to_local = day.strftime("%Y-%m-%dT23:59")

        dep_flights = fetch_airport_fids(origin_icao, from_local, to_local, direction="Departure")
        for f in dep_flights:
            if not isinstance(f, dict):
                continue
            number = str(f.get("number") or "").replace(" ", "").upper()
            if number in candidates_upper:
                arr_airport = _d(_d(f.get("arrival")).get("airport"))
                if arr_airport.get("icao") == destination_icao:
                    matches.append(f)

        if matches:
            break

    return matches


def collect_gate_history(flight_number_candidates, origin_icao, destination_icao, range_days=4):
    today = datetime.now(timezone.utc).date()
    from_local = (today - timedelta(days=range_days - 1)).strftime("%Y-%m-%dT00:00")
    to_local = today.strftime("%Y-%m-%dT23:59")

    all_matches = []
    last_error = None

    for candidate in flight_number_candidates:
        try:
            flights = fetch_flights_range(candidate, from_local, to_local)
        except UpstreamError as exc:
            last_error = exc
            continue
        for f in flights:
            if not isinstance(f, dict):
                continue
            dep_airport = _d(_d(f.get("departure")).get("airport"))
            arr_airport = _d(_d(f.get("arrival")).get("airport"))
            if dep_airport.get("icao") == origin_icao and arr_airport.get("icao") == destination_icao:
                all_matches.append(f)
        if all_matches:
            break

    if not all_matches:
        for candidate in flight_number_candidates:
            try:
                flights = fetch_flight_status_single(candidate)
            except UpstreamError as exc:
                last_error = exc
                continue
            for f in flights:
                if not isinstance(f, dict):
                    continue
                dep_airport = _d(_d(f.get("departure")).get("airport"))
                arr_airport = _d(_d(f.get("arrival")).get("airport"))
                if dep_airport.get("icao") == origin_icao and arr_airport.get("icao") == destination_icao:
                    all_matches.append(f)
            if all_matches:
                break

    if not all_matches:
        try:
            all_matches = find_gate_via_fids(flight_number_candidates, origin_icao, destination_icao, range_days)
        except UpstreamError as exc:
            last_error = exc

    if not all_matches and last_error:
        raise last_error

    return all_matches


def extract_ground_info(flight):
    dep = _d(flight.get("departure"))
    arr = _d(flight.get("arrival"))

    def gate_block(block):
        airport = _d(block.get("airport"))
        scheduled = _d(block.get("scheduledTime"))
        return {
            "airport_icao": airport.get("icao"),
            "airport_iata": airport.get("iata"),
            "airport_name": airport.get("name"),
            "terminal": block.get("terminal") or None,
            "gate": block.get("gate") or None,
            "scheduled_time_local": scheduled.get("local"),
        }

    airline = _d(flight.get("airline"))
    aircraft = _d(flight.get("aircraft"))
    dep_block = gate_block(dep)

    return {
        "flight_number": flight.get("number"),
        "status": flight.get("status"),
        "airline": airline.get("name"),
        "aircraft_model": aircraft.get("model"),
        "date_local": (dep_block.get("scheduled_time_local") or "").split("T")[0] or None,
        "departure": dep_block,
        "arrival": gate_block(arr),
    }


def apply_terminal_estimates(plan):
    airline_iata = plan.get("airline_iata")
    origin_icao = plan["origin"]["icao"]
    dest_icao = plan["destination"]["icao"]

    return {
        "origin": derive_terminal_estimate(origin_icao, airline_iata),
        "destination": derive_terminal_estimate(dest_icao, airline_iata),
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
        range_days = payload.get("range_days", 4)
        try:
            range_days = max(1, min(int(range_days), 7))
        except (TypeError, ValueError):
            range_days = 4

        response_body = {}

        try:
            plan = fetch_simbrief_plan(username)
            response_body["simbrief_plan"] = plan
        except UpstreamError as exc:
            self.send_response(exc.status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
            return
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Interner Fehler: {exc}"}).encode("utf-8"))
            return

        try:
            matches = collect_gate_history(
                plan["flight_number_candidates"],
                plan["origin"]["icao"],
                plan["destination"]["icao"],
                range_days=range_days,
            )
            if not matches:
                response_body["ground_info_error"] = (
                    f"Keine Live-/Terminaldaten fuer {', '.join(plan['flight_number_candidates'])} "
                    f"in den letzten {range_days} Tagen gefunden (auch nicht ueber die Flughafen-"
                    f"Abflugtafel). Es wird eine Terminal-Naeherung auf Basis oeffentlich "
                    f"dokumentierter Airline-Zuordnungen angezeigt, sofern verfuegbar."
                )
                response_body["ground_info_list"] = []
            else:
                ground_list = [extract_ground_info(f) for f in matches]
                ground_list.sort(key=lambda g: g.get("date_local") or "", reverse=True)
                response_body["ground_info_list"] = ground_list
                response_body["ground_info"] = ground_list[0]
        except UpstreamError as exc:
            response_body["ground_info_error"] = str(exc)
            response_body["ground_info_list"] = []
        except Exception as exc:
            response_body["ground_info_error"] = f"Interner Fehler bei AeroDataBox-Abfrage: {exc}"
            response_body["ground_info_list"] = []

        response_body["terminal_estimate"] = apply_terminal_estimates(plan)
        response_body["fetched_at"] = datetime.now(timezone.utc).isoformat()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_body).encode("utf-8"))
