const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const $ = (id) => document.getElementById(id);
const JAR = "purpur.jar";

// ---- pestañas ----
document.querySelectorAll(".tab").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("tab-" + b.dataset.tab).classList.add("active");
  })
);

// ---- consola ----
function log(msg) {
  const c = $("console");
  c.textContent += msg + "\n";
  c.scrollTop = c.scrollHeight;
  const m = msg.match(/There are (\d+).*players online:?(.*)/);
  if (m) setPlayers(m[1], m[2]);
}
function setPlayers(count, namesStr) {
  $("playerCount").textContent = `${count} en línea`;
  const ul = $("playerList");
  ul.innerHTML = "";
  namesStr.split(",").map((n) => n.replace(/§./g, "").trim()).filter(Boolean)
    .forEach((n) => {
      const li = document.createElement("li");
      li.textContent = n;
      ul.appendChild(li);
    });
}

// ---- estado ----
function setRunning(on) {
  $("dot").classList.toggle("on", on);
  $("statusText").textContent = on ? "Corriendo" : "Detenido";
}

// ---- versiones ----
async function loadVersions() {
  try {
    const vers = await invoke("list_versions");
    const sel = $("version");
    sel.innerHTML = "";
    vers.forEach((v) => {
      const o = document.createElement("option");
      o.textContent = v;
      sel.appendChild(o);
    });
    sel.value = vers[vers.length - 1];
    log(`✓ ${vers.length} versiones cargadas. Última: ${sel.value}`);
  } catch (e) {
    log("[!] No se pudo listar versiones: " + e);
  }
}

$("serverType").addEventListener("change", (e) => {
  if (e.target.value !== "Purpur") {
    alert("Ese tipo llegará próximamente. Usando Purpur.");
    e.target.value = "Purpur";
  }
});

$("btnDownload").addEventListener("click", async () => {
  const version = $("version").value;
  if (!version || version === "cargando...") return alert("Espera a que carguen las versiones.");
  try {
    const build = await invoke("latest_build", { version });
    log(`Descargando Purpur ${version} build ${build}...`);
    await invoke("download_jar", { version, build, jar: JAR });
  } catch (e) {
    log("[!] Error descarga: " + e);
  }
});

// ---- servidor ----
function cfg() {
  return {
    ram_min: parseInt($("ramMin").value),
    ram_max: parseInt($("ramMax").value),
    port: parseInt($("port").value),
    eula: $("eula").checked,
  };
}

$("btnStart").addEventListener("click", async () => {
  try {
    const java = await invoke("start_server", { cfg: cfg(), jar: JAR });
    log("Usando " + java);
    setRunning(true);
  } catch (e) {
    alert(e);
  }
});

$("btnStop").addEventListener("click", async () => {
  try { await invoke("stop_server"); log("Deteniendo servidor..."); }
  catch (e) { log(e); }
});

$("btnKill").addEventListener("click", async () => {
  try { await invoke("kill_server"); await invoke("clear_server_state"); setRunning(false); }
  catch (e) { log(e); }
});

async function sendCmd() {
  const input = $("cmd");
  const c = input.value.trim();
  if (!c) return;
  log("> " + c);
  try { await invoke("send_command", { cmd: c }); }
  catch (e) { log(e); }
  input.value = "";
}
$("btnSend").addEventListener("click", sendCmd);
$("cmd").addEventListener("keydown", (e) => { if (e.key === "Enter") sendCmd(); });
$("btnPlayers").addEventListener("click", async () => {
  try { await invoke("send_command", { cmd: "list" }); }
  catch { log("Servidor no está corriendo."); }
});

// ---- túneles ----
$("btnNgrok").addEventListener("click", async () => {
  try { await invoke("start_ngrok", { port: parseInt($("port").value) }); }
  catch (e) { alert(e); }
});
$("btnPlayit").addEventListener("click", async () => {
  try { await invoke("start_playit"); }
  catch (e) { alert(e); }
});
$("btnStopTunnel").addEventListener("click", async () => {
  try { await invoke("stop_tunnel"); } catch (e) { alert(e); }
});

// ---- ajustes ----
$("btnSave").addEventListener("click", async () => {
  await invoke("save_config", { cfg: cfg() });
  alert("Configuración guardada.");
});
$("btnIp").addEventListener("click", async () => {
  const ip = await invoke("local_ip");
  alert(`IP local: ${ip}:${$("port").value}\nEn tu PC usa: localhost:${$("port").value}`);
});

// ---- eventos del backend ----
await listen("server-line", (e) => log(e.payload));
await listen("server-exit", async () => {
  await invoke("clear_server_state").catch(() => {});
  setRunning(false);
  log("Servidor detenido.");
});
await listen("players", (e) => setPlayers(e.payload.count, e.payload.names));
await listen("dl-progress", (e) => {
  const { done, total } = e.payload;
  $("dlFill").style.width = total ? `${(done / total) * 100}%` : "0";
});
await listen("dl-done", () => {
  $("dlFill").style.width = "100%";
  log("✓ Descarga completada.");
  alert("Descarga completada.");
});
await listen("tunnel-log", (e) => {
  const t = $("tunnelLog");
  t.textContent += e.payload + "\n";
  t.scrollTop = t.scrollHeight;
});
await listen("tunnel-addr", (e) => {
  $("pubAddr").textContent = e.payload;
  alert("Túnel listo. Comparte con tus amigos:\n" + e.payload);
});
await listen("tunnel-claim", (e) => {
  alert(`1. Abre y reclama tu agente:\n${e.payload}\n\n2. Crea un túnel Minecraft Java → puerto ${$("port").value}`);
});

// ---- init ----
try {
  const saved = await invoke("load_config");
  $("ramMin").value = saved.ram_min ?? 1;
  $("ramMax").value = saved.ram_max ?? 4;
  $("port").value = saved.port ?? 25565;
  $("eula").checked = saved.eula ?? false;
} catch {}
try {
  const j = await invoke("find_java");
  $("javaInfo").textContent = `Java ${j.version}: ${j.path}`;
} catch (e) {
  $("javaInfo").textContent = e;
}
loadVersions();
