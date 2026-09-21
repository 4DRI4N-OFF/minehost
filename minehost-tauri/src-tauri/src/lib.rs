// MineHost backend: gestion de servidor Minecraft local + tuneles.
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tauri::{AppHandle, Emitter, Manager};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin};
use tokio::sync::Mutex;

const UA: &str = "MineHost/1.0";
const PURPUR_API: &str = "https://api.purpurmc.org/v2/purpur";

struct ServerProc {
    stdin: Option<ChildStdin>,
    child: Option<Child>,
}

struct AppState {
    server: Mutex<ServerProc>,
    tunnel: Mutex<Option<Child>>,
}

fn server_dir() -> Result<PathBuf, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let dir = exe
        .parent()
        .ok_or("sin dir del exe")?
        .join("server");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn http() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .user_agent(UA)
        .timeout(std::time::Duration::from_secs(25))
        .build()
        .map_err(|e| e.to_string())
}

// ---- versiones ----
#[tauri::command]
async fn list_versions() -> Result<Vec<String>, String> {
    let v: serde_json::Value = http()?
        .get(PURPUR_API)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .json()
        .await
        .map_err(|e| e.to_string())?;
    v["versions"]
        .as_array()
        .ok_or("respuesta sin versions".to_string())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(|s| s.to_string()))
                .collect()
        })
}

#[tauri::command]
async fn latest_build(version: String) -> Result<String, String> {
    let v: serde_json::Value = http()?
        .get(format!("{PURPUR_API}/{version}"))
        .send()
        .await
        .map_err(|e| e.to_string())?
        .json()
        .await
        .map_err(|e| e.to_string())?;
    v["builds"]["latest"]
        .as_str()
        .map(|s| s.to_string())
        .ok_or("sin latest build".to_string())
}

#[tauri::command]
async fn download_jar(
    app: AppHandle,
    version: String,
    build: String,
    jar: String,
) -> Result<String, String> {
    let url = format!("{PURPUR_API}/{version}/{build}/download");
    let mut resp = http()?
        .get(&url)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    let total = resp.content_length().unwrap_or(0);
    let dest = server_dir()?.join(&jar);
    let mut file = tokio::fs::File::create(&dest)
        .await
        .map_err(|e| e.to_string())?;
    let mut done: u64 = 0;
    use tokio::io::AsyncWriteExt;
    while let Some(chunk) = resp.chunk().await.map_err(|e| e.to_string())? {
        file.write_all(&chunk).await.map_err(|e| e.to_string())?;
        done += chunk.len() as u64;
        let _ = app.emit(
            "dl-progress",
            serde_json::json!({ "done": done, "total": total }),
        );
    }
    let _ = app.emit("dl-done", serde_json::json!({ "jar": jar }));
    Ok(dest.to_string_lossy().to_string())
}

// ---- java ----
#[derive(Serialize)]
struct JavaInfo {
    path: String,
    version: u32,
}

fn java_version(path: &std::path::Path) -> Option<u32> {
    let out = std::process::Command::new(path)
        .arg("-version")
        .output()
        .ok()?;
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    Regex::new(r#"version "(\d+)"#)
        .ok()?
        .captures(&text)?
        .get(1)?
        .as_str()
        .parse()
        .ok()
}

#[tauri::command]
async fn find_java() -> Result<JavaInfo, String> {
    let mut cands: Vec<PathBuf> = vec![];
    for base in [
        PathBuf::from(r"C:\Program Files\Eclipse Adoptium"),
        PathBuf::from(r"C:\Program Files\Java"),
        std::env::var("JAVA_HOME").map(PathBuf::from).unwrap_or_default(),
    ] {
        if base.as_os_str().is_empty() || !base.exists() {
            continue;
        }
        if base.join("bin").join("java.exe").exists() {
            cands.push(base.join("bin").join("java.exe"));
        }
        if let Ok(rd) = std::fs::read_dir(&base) {
            for e in rd.flatten() {
                let j = e.path().join("bin").join("java.exe");
                if j.exists() {
                    cands.push(j);
                }
            }
        }
    }
    cands.push(PathBuf::from("java"));
    let mut best: Option<(PathBuf, u32)> = None;
    for c in cands {
        if let Some(v) = java_version(&c) {
            if best.as_ref().map(|(_, bv)| v > *bv).unwrap_or(true) {
                best = Some((c, v));
            }
        }
    }
    best.map(|(p, v)| JavaInfo {
        path: p.to_string_lossy().to_string(),
        version: v,
    })
    .ok_or("No se encontró Java instalado".to_string())
}

// ---- config ----
#[derive(Deserialize, Serialize, Clone)]
struct ServerCfg {
    ram_min: u32,
    ram_max: u32,
    port: u16,
    eula: bool,
}

#[tauri::command]
async fn save_config(cfg: ServerCfg) -> Result<(), String> {
    let dir = server_dir()?;
    std::fs::write(
        dir.join("manager_config.json"),
        serde_json::to_string_pretty(&cfg).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    std::fs::write(
        dir.join("eula.txt"),
        if cfg.eula { "eula=true\n" } else { "eula=false\n" },
    )
    .map_err(|e| e.to_string())?;
    let sp = dir.join("server.properties");
    if sp.exists() {
        let re = Regex::new(r"(?m)^server-port=.*$").unwrap();
        let t = std::fs::read_to_string(&sp).map_err(|e| e.to_string())?;
        let out = if re.is_match(&t) {
            re.replace(&t, format!("server-port={}", cfg.port)).to_string()
        } else {
            format!("{t}\nserver-port={}\n", cfg.port)
        };
        std::fs::write(&sp, out).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
async fn load_config() -> Result<serde_json::Value, String> {
    let f = server_dir()?.join("manager_config.json");
    if f.exists() {
        serde_json::from_str(&std::fs::read_to_string(f).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())
    } else {
        Ok(serde_json::json!({ "ram_min": 1, "ram_max": 4, "port": 25565, "eula": false }))
    }
}

// ---- servidor ----
#[tauri::command]
async fn start_server(app: AppHandle, cfg: ServerCfg, jar: String) -> Result<String, String> {
    {
        let state = app.state::<AppState>();
        let s = state.server.lock().await;
        if s.child.is_some() {
            return Err("El servidor ya está corriendo".to_string());
        }
    }
    if !cfg.eula {
        return Err("Debes aceptar el EULA".to_string());
    }
    let dir = server_dir()?;
    let jar_path = dir.join(&jar);
    if !jar_path.exists() {
        return Err("Primero descarga el JAR".to_string());
    }
    save_config(cfg.clone()).await?;
    let java = find_java().await?;
    if java.version < 25 {
        return Err(format!("Java {} encontrado, se exige Java 25+", java.version));
    }
    let mut child = tokio::process::Command::new(&java.path)
        .args([
            format!("-Xms{}G", cfg.ram_min),
            format!("-Xmx{}G", cfg.ram_max),
            "-jar".to_string(),
            jar_path.to_string_lossy().to_string(),
            "nogui".to_string(),
        ])
        .current_dir(&dir)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;

    let stdin = child.stdin.take();
    let stdout = child.stdout.take().ok_or("sin stdout")?;
    let stderr = child.stderr.take();

    // Une stderr al mismo flujo
    let reader = BufReader::new(stdout);
    let app2 = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut lines = reader.lines();
        let re = Regex::new(r"There are (\d+).*players online:?(.*)").unwrap();
        while let Ok(Some(line)) = lines.next_line().await {
            let _ = app2.emit("server-line", &line);
            if let Some(c) = re.captures(&line) {
                let _ = app2.emit(
                    "players",
                    serde_json::json!({ "count": &c[1], "names": &c[2] }),
                );
            }
        }
        let _ = app2.emit("server-exit", ());
    });
    if let Some(err) = stderr {
        let app3 = app.clone();
        tauri::async_runtime::spawn(async move {
            let mut lines = BufReader::new(err).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                let _ = app3.emit("server-line", &line);
            }
        });
    }

    let state = app.state::<AppState>();
    state.server.lock().await.stdin = stdin;
    state.server.lock().await.child = Some(child);
    Ok(format!("Java {}: {}", java.version, java.path))
}

async fn write_stdin(app: &AppHandle, cmd: &str) -> Result<(), String> {
    let state = app.state::<AppState>();
    let mut s = state.server.lock().await;
    if let Some(stdin) = s.stdin.as_mut() {
        stdin
            .write_all(format!("{cmd}\n").as_bytes())
            .await
            .map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err("Servidor no está corriendo".to_string())
    }
}

#[tauri::command]
async fn send_command(app: AppHandle, cmd: String) -> Result<(), String> {
    write_stdin(&app, &cmd).await
}

#[tauri::command]
async fn stop_server(app: AppHandle) -> Result<(), String> {
    write_stdin(&app, "stop").await
}

#[tauri::command]
async fn kill_server(app: AppHandle) -> Result<(), String> {
    let state = app.state::<AppState>();
    let mut s = state.server.lock().await;
    s.stdin = None;
    if let Some(mut c) = s.child.take() {
        c.kill().await.map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err("Servidor no está corriendo".to_string())
    }
}

#[tauri::command]
async fn server_running(app: AppHandle) -> bool {
    app.state::<AppState>().server.lock().await.child.is_some()
}

#[tauri::command]
async fn clear_server_state(app: AppHandle) -> Result<(), String> {
    let state = app.state::<AppState>();
    let mut s = state.server.lock().await;
    s.stdin = None;
    s.child = None;
    Ok(())
}

// ---- red ----
#[tauri::command]
async fn local_ip() -> Result<String, String> {
    let sock = std::net::UdpSocket::bind("0.0.0.0:0").map_err(|e| e.to_string())?;
    sock.connect("8.8.8.8:80").map_err(|e| e.to_string())?;
    sock.local_addr()
        .map(|a| a.ip().to_string())
        .map_err(|e| e.to_string())
}

// ---- tuneles ----
fn find_bin(name: &str, fallback: &str) -> Option<String> {
    for dir in std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()) {
        let p = dir.join(format!("{name}.exe"));
        if p.exists() {
            return Some(p.to_string_lossy().to_string());
        }
    }
    if std::path::Path::new(fallback).exists() {
        return Some(fallback.to_string());
    }
    None
}

#[tauri::command]
async fn start_ngrok(app: AppHandle, port: u16) -> Result<(), String> {
    let bin = find_bin("ngrok", r"C:\Program Files\ngrok\ngrok.exe")
        .ok_or("ngrok no instalado: https://ngrok.com/download")?;
    let mut child = tokio::process::Command::new(bin)
        .args(["tcp", &port.to_string()])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    let out = child.stdout.take().ok_or("sin stdout")?;
    let re = Regex::new(r"tcp://([^\s]+)").unwrap();
    let appc = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut lines = BufReader::new(out).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            let _ = app.emit("tunnel-log", format!("[ngrok] {line}"));
            if let Some(c) = re.captures(&line) {
                let _ = app.emit("tunnel-addr", c[1].to_string());
            }
        }
    });
    *appc.state::<AppState>().tunnel.lock().await = Some(child);
    Ok(())
}

#[tauri::command]
async fn start_playit(app: AppHandle) -> Result<(), String> {
    let bin = find_bin("playit", r"C:\Program Files\playit_gg\bin\playit.exe")
        .ok_or("playit no instalado: https://playit.gg")?;
    let mut child = tokio::process::Command::new(bin)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    let out = child.stdout.take().ok_or("sin stdout")?;
    let re = Regex::new(r"https://playit\.gg/claim/\S+").unwrap();
    let appc = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut lines = BufReader::new(out).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            let l = line.trim().to_string();
            let _ = app.emit("tunnel-log", format!("[playit] {l}"));
            if let Some(c) = re.captures(&l) {
                let _ = app.emit("tunnel-claim", c[0].to_string());
            }
        }
    });
    *appc.state::<AppState>().tunnel.lock().await = Some(child);
    Ok(())
}

#[tauri::command]
async fn stop_tunnel(app: AppHandle) -> Result<(), String> {
    let state = app.state::<AppState>();
    let mut t = state.tunnel.lock().await;
    if let Some(mut c) = t.take() {
        c.kill().await.map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err("No hay túnel activo".to_string())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(AppState {
            server: Mutex::new(ServerProc { stdin: None, child: None }),
            tunnel: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            list_versions,
            latest_build,
            download_jar,
            find_java,
            save_config,
            load_config,
            start_server,
            send_command,
            stop_server,
            kill_server,
            server_running,
            clear_server_state,
            local_ip,
            start_ngrok,
            start_playit,
            stop_tunnel
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
