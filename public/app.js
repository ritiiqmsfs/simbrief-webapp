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

function fillGroundBlock(prefix, block) {
  document.getElementById(`${prefix}Name`).textContent = block.airport_name || block.airport_icao || "-";
  document.getElementById(`${prefix}Icao`).textContent = block.airport_icao || "-";

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
}

async function runLookup() {
  const username = usernameInput.value.trim();
  if (!username) {
    showStatus("Bitte einen SimBrief-Usernamen eingeben.", "error");
    return;
  }

  lookupBtn.disabled = true;
  resultEl.classList.add("hidden");
  showStatus("Lade SimBrief-Flugplan und Live-Daten ...", "info");

  try {
    const resp = await fetch("/api/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simbrief_username: username }),
    });

    const data = await resp.json();

    if (!resp.ok) {
      showStatus(data.error || "Unbekannter Fehler.", "error");
      return;
    }

    hideStatus();

    const plan = data.simbrief_plan;
    const ground = data.ground_info;

    document.getElementById("flightNumber").textContent = ground.flight_number || plan.flight_number;
    document.getElementById("aircraftType").textContent = ground.aircraft_model || plan.aircraft;

    fillGroundBlock("dep", ground.departure);
    fillGroundBlock("arr", ground.arrival);

    const fetchedDate = new Date(ground.fetched_at);
    document.getElementById("fetchedNote").textContent =
      `Abgerufen: ${fetchedDate.toLocaleString("de-DE")} · Quelle: AeroDataBox`;

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
