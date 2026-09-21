"""Minecraft Server Manager - Purpur (local) con GUI Tkinter."""
import json, os, re, shutil, socket, subprocess, sys, threading, urllib.request
from pathlib import Path
from tkinter import (Tk, ttk, StringVar, IntVar, BooleanVar, Text, END,
                     filedialog, messagebox)
from tkinter.scrolledtext import ScrolledText

BASE_DIR = Path(__file__).parent.parent / "server"
BASE_DIR.mkdir(exist_ok=True)
CONFIG_FILE = BASE_DIR / "manager_config.json"
PURPUR_API = "https://api.purpurmc.org/v2/purpur"

DEFAULTS = {"version": "", "ram_min": 1, "ram_max": 4, "port": 25565,
            "eula": False, "server_dir": str(BASE_DIR)}

def load_config():
    cfg = DEFAULTS.copy()
    if CONFIG_FILE.exists():
        try: cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception: pass
    return cfg

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def find_best_java():
    """Busca el java.exe con mayor versión (Adoptium, JAVA_HOME, PATH)."""
    cands = []
    for base in [Path(r"C:\Program Files\Eclipse Adoptium"),
                 Path(r"C:\Program Files\Java"), Path(os.environ.get("JAVA_HOME", ""))]:
        if base and base.exists():
            cands += list(base.glob("*/bin/java.exe")) + list(base.glob("bin/java.exe"))
    found = shutil.which("java")
    if found: cands.append(Path(found))
    best, best_v = None, -1
    for c in dict.fromkeys(cands):
        try:
            out = subprocess.run([str(c), "-version"], capture_output=True,
                                 text=True, timeout=10).stderr
            m = re.search(r'version "(\d+)', out)
            v = int(m.group(1)) if m else 0
            if v > best_v: best, best_v = c, v
        except Exception: pass
    return best, best_v

def api_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MCServerManager/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

class Manager:
    def __init__(self, root):
        self.root = root
        root.title("Purpur Server Manager (Local)")
        root.geometry("780x620")
        self.cfg = load_config()
        self.proc = None
        self.build_ui()
        threading.Thread(target=self.refresh_versions, daemon=True).start()

    def build_ui(self):
        f = ttk.Frame(self.root, padding=10); f.pack(fill="both", expand=True)
        # Fila 1: versión + dir
        ttk.Label(f, text="Versión:").grid(row=0, column=0, sticky="w")
        self.ver_var = StringVar(value=self.cfg.get("version") or "cargando...")
        self.ver_box = ttk.Combobox(f, textvariable=self.ver_var, width=15, state="readonly")
        self.ver_box.grid(row=0, column=1, sticky="w")
        ttk.Button(f, text="Actualizar Purpur", command=self.download_purpur).grid(row=0, column=2, padx=5)
        ttk.Label(f, text="Estado:").grid(row=0, column=3)
        self.status = StringVar(value="Detenido")
        ttk.Label(f, textvariable=self.status, foreground="red").grid(row=0, column=4)
        # Fila 2: RAM, puerto
        ttk.Label(f, text="RAM mín (GB):").grid(row=1, column=0, sticky="w")
        self.ram_min = IntVar(value=self.cfg["ram_min"])
        ttk.Spinbox(f, from_=1, to=16, textvariable=self.ram_min, width=5).grid(row=1, column=1, sticky="w")
        ttk.Label(f, text="RAM máx (GB):").grid(row=1, column=2)
        self.ram_max = IntVar(value=self.cfg["ram_max"])
        ttk.Spinbox(f, from_=1, to=32, textvariable=self.ram_max, width=5).grid(row=1, column=3, sticky="w")
        ttk.Label(f, text="Puerto:").grid(row=1, column=4)
        self.port = IntVar(value=self.cfg["port"])
        ttk.Spinbox(f, from_=1024, to=65535, textvariable=self.port, width=7).grid(row=1, column=5, sticky="w")
        # Fila 3: EULA + botones
        self.eula = BooleanVar(value=self.cfg["eula"])
        ttk.Checkbutton(f, text="Acepto EULA de Mojang (eula=true)", variable=self.eula).grid(row=2, column=0, columnspan=3, sticky="w")
        btns = ttk.Frame(f); btns.grid(row=3, column=0, columnspan=6, pady=8, sticky="w")
        ttk.Button(btns, text="▶ Iniciar", command=self.start).pack(side="left", padx=3)
        ttk.Button(btns, text="■ Detener", command=self.stop).pack(side="left", padx=3)
        ttk.Button(btns, text="💾 Guardar config", command=self.save).pack(side="left", padx=3)
        ttk.Button(btns, text="📂 Abrir carpeta", command=self.open_folder).pack(side="left", padx=3)
        ttk.Button(btns, text="🌐 Túnel público (ngrok)", command=self.start_ngrok).pack(side="left", padx=3)
        ttk.Button(btns, text="🚀 Playit (recomendado)", command=self.start_playit).pack(side="left", padx=3)
        ttk.Button(btns, text="🌐 Mi IP local", command=self.show_ip).pack(side="left", padx=3)
        # Consola
        ttk.Label(f, text="Consola del servidor (escribe comandos abajo):").grid(row=4, column=0, columnspan=6, sticky="w")
        self.console = ScrolledText(f, height=20, bg="black", fg="#00ff00", insertbackground="white")
        self.console.grid(row=5, column=0, columnspan=6, sticky="nsew")
        self.cmd = StringVar()
        entry = ttk.Entry(f, textvariable=self.cmd)
        entry.grid(row=6, column=0, columnspan=5, sticky="ew", pady=5)
        entry.bind("<Return>", lambda e: self.send_cmd())
        ttk.Button(f, text="Enviar", command=self.send_cmd).grid(row=6, column=5)
        f.rowconfigure(5, weight=1); f.columnconfigure(0, weight=1)

    def log(self, msg):
        self.console.insert(END, msg + "\n"); self.console.see(END)

    def refresh_versions(self):
        try:
            data = api_get(PURPUR_API)
            vers = data["versions"]
            def apply():
                self.ver_box["values"] = vers
                if not self.ver_var.get() or self.ver_var.get() == "cargando...":
                    self.ver_var.set(self.cfg.get("version") or vers[-1])
                self.log(f"✓ {len(vers)} versiones cargadas. Última: {vers[-1]}")
            self.root.after(0, apply)
        except Exception as e:
            self.root.after(0, lambda: self.log(f"[!] No se pudo listar versiones: {e}"))

    def latest_build(self, version):
        d = api_get(f"{PURPUR_API}/{version}")
        return d["builds"]["latest"]

    def download_purpur(self):
        v = self.ver_var.get()
        if not v or v == "cargando...":
            return messagebox.showwarning("Aviso", "Espera a que carguen las versiones.")
        def work():
            try:
                b = self.latest_build(v)
                url = f"{PURPUR_API}/{v}/{b}/download"
                dest = BASE_DIR / "purpur.jar"
                self.log(f"Descargando Purpur {v} build {b}...")
                req = urllib.request.Request(url, headers={"User-Agent": "MCServerManager/1.0"})
                with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                    shutil.copyfileobj(r, f)
                self.log(f"✓ Guardado en {dest} ({dest.stat().st_size/1e6:.1f} MB)")
                messagebox.showinfo("Listo", f"Purpur {v} (build {b}) descargado.")
            except Exception as e:
                self.log(f"[!] Error descarga: {e}")
        threading.Thread(target=work, daemon=True).start()

    def save(self):
        self.cfg.update(version=self.ver_var.get(), ram_min=self.ram_min.get(),
                        ram_max=self.ram_max.get(), port=self.port.get(), eula=self.eula.get())
        save_config(self.cfg)
        # server.properties puerto
        sp = BASE_DIR / "server.properties"
        if sp.exists():
            t = sp.read_text()
            t = re.sub(r"^server-port=.*", f"server-port={self.port.get()}", t, flags=re.M)
            sp.write_text(t)
        (BASE_DIR / "eula.txt").write_text(f"eula={'true' if self.eula.get() else 'false'}\n")
        messagebox.showinfo("Guardado", "Configuración guardada.")

    def open_folder(self):
        os.startfile(BASE_DIR)

    def show_ip(self):
        ip = socket.gethostbyname(socket.gethostname())
        messagebox.showinfo("Conexión local", f"IP local: {ip}:{self.port.get()}\nEn tu PC usa: localhost:{self.port.get()}")

    def start(self):
        jar = BASE_DIR / "purpur.jar"
        if not jar.exists():
            return messagebox.showerror("Falta JAR", "Primero pulsa 'Actualizar Purpur'.")
        if not self.eula.get():
            return messagebox.showerror("EULA", "Debes aceptar el EULA (marca la casilla).")
        if self.proc and self.proc.poll() is None:
            return messagebox.showwarning("Aviso", "El servidor ya está corriendo.")
        self.save_silent()
        java, ver = find_best_java()
        if not java:
            return messagebox.showerror("Sin Java", "No se encontró Java instalado.")
        if ver < 25:
            return messagebox.showerror("Java viejo", f"Encontrado Java {ver}, pero Purpur 26.x exige Java 25+.")
        self.log(f"Usando Java {ver}: {java}")
        cmd = [str(java), f"-Xms{self.ram_min.get()}G", f"-Xmx{self.ram_max.get()}G",
               "-jar", str(jar), "nogui"]
        self.log(" ".join(cmd))
        self.proc = subprocess.Popen(cmd, cwd=BASE_DIR, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
        self.status.set("Corriendo"); threading.Thread(target=self.reader, daemon=True).start()

    def save_silent(self):
        self.cfg.update(version=self.ver_var.get(), ram_min=self.ram_min.get(),
                        ram_max=self.ram_max.get(), port=self.port.get(), eula=self.eula.get())
        save_config(self.cfg)
        (BASE_DIR / "eula.txt").write_text("eula=true\n" if self.eula.get() else "eula=false\n")

    def reader(self):
        for line in self.proc.stdout:
            self.console.insert(END, line); self.console.see(END)
        self.status.set("Detenido")

    def send_cmd(self):
        c = self.cmd.get().strip()
        if not c: return
        self.log(f"> {c}")
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.write(c + "\n"); self.proc.stdin.flush()
        self.cmd.set("")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try: self.proc.stdin.write("stop\n"); self.proc.stdin.flush()
            except Exception: self.proc.terminate()
            self.log("Deteniendo servidor...")
        else:
            self.log("Servidor no está corriendo.")

    def start_ngrok(self):
        """Expone el puerto con ngrok TCP (requiere ngrok + authtoken una vez)."""
        port = self.port.get()
        ngrok = shutil.which("ngrok")
        if not ngrok:
            self.log("[!] ngrok no instalado. Descárgalo: https://ngrok.com/download")
            messagebox.showinfo("ngrok",
                "1. Descarga ngrok: https://ngrok.com/download\n"
                "2. Crea cuenta gratis y copia tu authtoken\n"
                "3. Ejecuta una vez: ngrok config add-authtoken <TOKEN>\n"
                "4. Vuelve y pulsa este botón de nuevo.")
            return
        def work():
            self.log(f"Abriendo túnel público al puerto {port}...")
            p = subprocess.Popen([ngrok, "tcp", str(port)],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                self.log("[ngrok] " + line.strip())
                m = re.search(r"tcp://([^\s]+)", line)
                if m:
                    self.root.after(0, lambda a=m.group(1): messagebox.showinfo(
                        "Túnel listo", f"Comparte con tus amigos:\n{a}\n\nEn Minecraft: Multijugador > Agregar servidor > esa dirección."))
        threading.Thread(target=work, daemon=True).start()

    def start_playit(self):
        """Lanza el agente Playit (ya instalado) y muestra la URL de claim."""
        playit = shutil.which("playit") or r"C:\Program Files\playit_gg\bin\playit.exe"
        if not os.path.exists(playit):
            return messagebox.showerror("Playit", "No se encontró playit.exe.")
        def work():
            self.log("Iniciando agente Playit... busca el link Claim en la consola.")
            p = subprocess.Popen([playit], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                line = line.strip()
                self.log("[playit] " + line)
                m = re.search(r"https://playit\.gg/claim/\S+", line)
                if m:
                    url = m.group(0)
                    self.root.after(0, lambda: messagebox.showinfo("Playit",
                        f"1. Abre este link y reclama tu agente:\n{url}\n\n"
                        "2. En playit.gg crea un túnel:\n"
                        "   Tipo: Minecraft Java | Puerto local: "
                        f"{self.port.get()}\n3. Comparte la dirección (ej. xxx.mc.ply.gg)"))
        threading.Thread(target=work, daemon=True).start()

if __name__ == "__main__":
    root = Tk()
    Manager(root)
    root.mainloop()
