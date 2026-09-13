const usernameInput = document.getElementById("username");
const lookupBtn = document.getElementById("lookupBtn");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");

function showStatus(message, type) {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
  statusEl.classList.remove("hidden");
}

function hideStatus() {
  statusEl.classList.add("hidden");
}

function setText(id, value, fallback = "-") {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = (value === null || value === undefined || value === "") ? fallback : value;
}

function fillGroundBlock(prefix, block) {
  if (!block) {
    setText(`${prefix}Name`, null, "keine Daten");
    setText(`${prefix}Icao`, null, "-");
    document.getElementById(`${prefix}Terminal`).textContent = "keine Daten";
    document.getElementById(`${prefix}Terminal`).classList.add("missing");
    document.getElementById(`${prefix}Gate`).textContent = "keine Daten";
    document.getElementById(`${prefix}Gate`).classList.add("missing");
    setText(`${prefix}Time`, null, "keine Daten");
    return;
  }
  setText(`${prefix}Name`, block.airport_name || block.airport_icao);
  setText(`${prefix}Icao`, block.airport_icao);

  const terminalEl = document.getElementById(`${prefix}Terminal`);
  const gateEl = document.getElementById(`${prefix}Gate`);

  if (block.terminal) {
    terminalEl.textContent = block.terminal;
    terminalEl.classList.remove("missing");
  } else {
    terminalEl.textContent = "keine Daten";
    terminalEl.classList.add("missing");
  }

  if (block.gate) {
    gateEl.textContent = block.gate;
    gateEl.classList.remove("missing");
  } else {
    gateEl.textContent = "keine Daten";
    gateEl.classList.add("missing");
  }

  setText(`${prefix}Time`, block.scheduled_time_local ? (block.scheduled_time_local.split("T")[1] || block.scheduled_time_local) : null, "keine Daten");
}

function fillPlanExtras(plan) {
  setText("depElev", plan.origin.elevation_ft != null ? `${Math.round(plan.origin.elevation_ft)} ft` : null);
  setText("arrElev", plan.destination.elevation_ft != null ? `${Math.round(plan.destination.elevation_ft)} ft` : null);

  const depMetarBox = document.getElementById("depMetarBox");
  const arrMetarBox = document.getElementById("arrMetarBox");
  if (plan.origin.metar) {
    setText("depMetar", plan.origin.metar);
    depMetarBox.classList.remove("hidden");
  } else {
    depMetarBox.classList.add("hidden");
  }
  if (plan.destination.metar) {
    setText("arrMetar", plan.destination.metar);
    arrMetarBox.classList.remove("hidden");
  } else {
    arrMetarBox.classList.add("hidden");
  }

  const distNm = plan.route_distance_nm || plan.air_distance_nm;
  setText("distanceLabel", distNm ? `${Math.round(distNm)} nm` : null);
  setText("detDistance", distNm ? `${Math.round(distNm)} nm` : null);

  setText("detBlockTime", plan.block_time_hhmm);
  setText("detAltitude", plan.initial_altitude_ft ? `FL${Math.round(plan.initial_altitude_ft / 100)}` : null);
  setText("detMach", plan.cruise_mach ? `M${plan.cruise_mach}` : null);
  setText("detTripFuel", plan.trip_fuel_kg ? `${Math.round(plan.trip_fuel_kg).toLocaleString("de-DE")} kg` : null);
  setText("detReserveFuel", plan.reserve_fuel_kg ? `${Math.round(plan.reserve_fuel_kg).toLocaleString("de-DE")} kg` : null);
  setText("detPax", plan.passengers != null ? plan.passengers : null);
  setText("detCargo", plan.cargo_kg ? `${Math.round(plan.cargo_kg).toLocaleString("de-DE")} kg` : null);

  const altBlock = document.getElementById("alternateBlock");
  if (plan.alternate && plan.alternate.icao) {
    setText("alternateValue", `${plan.alternate.name || ""} (${plan.alternate.icao})`.trim());
    altBlock.classList.remove("hidden");
  } else {
    altBlock.classList.add("hidden");
  }

  const routeBlock = document.getElementById("routeBlock");
  if (plan.route_string) {
    setText("routeValue", plan.route_string);
    routeBlock.classList.remove("hidden");
  } else {
    routeBlock.classList.add("hidden");
  }

  const crewBlock = document.getElementById("crewBlock");
  const crewParts = [];
  if (plan.captain) crewParts.push(`PIC: ${plan.captain}`);
  if (plan.dispatcher) crewParts.push(`Dispatch: ${plan.dispatcher}`);
  if (crewParts.length) {
    setText("crewValue", crewParts.join(" · "));
    crewBlock.classList.remove("hidden");
  } else {
    crewBlock.classList.add("hidden");
  }

  const callsignNote = document.getElementById("callsignNote");
  const candidates = plan.flight_number_candidates || [];
  const candidateNote = candidates.length > 1 ? ` · geprüfte Formate: ${candidates.join(", ")}` : "";
  callsignNote.textContent = (plan.callsign ? `Callsign: ${plan.callsign}` : "") + candidateNote;

  setText("aircraftReg", plan.aircraft_reg);
  const regEl = document.getElementById("aircraftReg");
  if (plan.aircraft_reg) {
    regEl.classList.remove("hidden");
  } else {
    regEl.classList.add("hidden");
  }
}

function renderGateHistory(groundList) {
  const container = document.getElementById("gateHistoryList");
  container.innerHTML = "";

  if (!groundList || groundList.length === 0) {
    return;
  }

  groundList.forEach((g, idx) => {
    const row = document.createElement("div");
    row.className = "history-row" + (idx === 0 ? " history-row-latest" : "");

    const dateSpan = document.createElement("span");
    dateSpan.className = "history-date";
    dateSpan.textContent = g.date_local || "Datum unbekannt";

    const depSpan = document.createElement("span");
    depSpan.className = "history-gate";
    const depTerm = g.departure && g.departure.terminal ? `T${g.departure.terminal}` : "–";
    const depGate = g.departure && g.departure.gate ? g.departure.gate : "kein Gate";
    depSpan.textContent = `Abflug: ${depTerm} / ${depGate}`;

    const arrSpan = document.createElement("span");
    arrSpan.className = "history-gate";
    const arrTerm = g.arrival && g.arrival.terminal ? `T${g.arrival.terminal}` : "–";
    const arrGate = g.arrival && g.arrival.gate ? g.arrival.gate : "kein Gate";
    arrSpan.textContent = `Ankunft: ${arrTerm} / ${arrGate}`;

    const statusSpan = document.createElement("span");
    statusSpan.className = "history-status";
    statusSpan.textContent = g.status || "";

    row.appendChild(dateSpan);
    row.appendChild(depSpan);
    row.appendChild(arrSpan);
    row.appendChild(statusSpan);
    container.appendChild(row);
  });
}

async function runLookup() {
  const username = usernameInput.value.trim();
  if (!username) {
    showStatus("Bitte einen SimBrief-Usernamen eingeben.", "error");
    return;
  }

  lookupBtn.disabled = true;
  resultEl.classList.add("hidden");
  showStatus("Lade SimBrief-Flugplan und Live-Daten der letzten Tage ...", "info");

  try {
    const resp = await fetch("/api/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simbrief_username: username, range_days: 4 }),
    });

    const data = await resp.json();

    if (!resp.ok) {
      showStatus(data.error || "Unbekannter Fehler.", "error");
      return;
    }

    const plan = data.simbrief_plan;
    if (!plan) {
      showStatus("SimBrief-Flugplan konnte nicht geladen werden.", "error");
      return;
    }

    hideStatus();

    const groundList = data.ground_info_list || [];
    const latest = groundList[0] || null;

    setText("flightNumber", (latest && latest.flight_number) || plan.flight_number);
    setText("airlineName", (latest && latest.airline) || plan.airline_name);
    setText("aircraftType", (latest && latest.aircraft_model) || plan.aircraft);
    setText("statusBadge", (latest && latest.status) || "geplant");

    fillGroundBlock("dep", latest ? latest.departure : null);
    fillGroundBlock("arr", latest ? latest.arrival : null);
    fillPlanExtras(plan);
    renderGateHistory(groundList);

    const gateNoteEl = document.getElementById("gateInfoNote");
    if (data.ground_info_error) {
      gateNoteEl.textContent = data.ground_info_error;
      gateNoteEl.classList.remove("hidden");
    } else {
      gateNoteEl.classList.add("hidden");
    }

    const historySection = document.getElementById("gateHistorySection");
    if (groundList.length > 0) {
      historySection.classList.remove("hidden");
    } else {
      historySection.classList.add("hidden");
    }

    const fetchedDate = new Date(data.fetched_at);
    setText("fetchedNote", `Abgerufen: ${fetchedDate.toLocaleString("de-DE")} · Quelle: SimBrief & AeroDataBox`);

    resultEl.classList.remove("hidden");
  } catch (err) {
    showStatus("Netzwerkfehler: " + err.message, "error");
  } finally {
    lookupBtn.disabled = false;
  }
}

lookupBtn.addEventListener("click", runLookup);
usernameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") runLookup();
});
