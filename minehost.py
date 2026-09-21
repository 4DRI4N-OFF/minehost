"""MineHost - gestor local de servidores Minecraft con GUI oscura por pestanas."""
import json, os, re, shutil, socket, subprocess, threading, urllib.request
from pathlib import Path
from tkinter import Tk, ttk, StringVar, IntVar, BooleanVar, END, messagebox
from tkinter.scrolledtext import ScrolledText

BASE_DIR = Path(__file__).parent / "server"
BASE_DIR.mkdir(exist_ok=True)
CONFIG_FILE = BASE_DIR / "manager_config.json"

BG = "#1e1e2e"
PANEL = "#252538"
FG = "#e0e0e0"
ACCENT = "#4caf50"
MUTED = "#8888aa"

SERVER_TYPES = {
    "Purpur": {"api": "https://api.purpurmc.org/v2/purpur", "jar": "purpur.jar", "ready": True},
    "Paper": {"api": "", "jar": "paper.jar", "ready": False},
    "Vanilla": {"api": "", "jar": "server.jar", "ready": False},
    "Forge": {"api": "", "jar": "forge.jar", "ready": False},
    "Fabric": {"api": "", "jar": "fabric.jar", "ready": False},
}

DEFAULTS = {"server_type": "Purpur", "version": "", "ram_min": 1, "ram_max": 4,
            "port": 25565, "eula": False}

UA = {"User-Agent": "MineHost/1.0"}


def load_config():
    cfg = DEFAULTS.copy()
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def api_get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def find_best_java():
    """Busca el java.exe con mayor version (Adoptium, JAVA_HOME, PATH)."""
    cands = []
    for base in [Path(r"C:\Program Files\Eclipse Adoptium"),
                 Path(r"C:\Program Files\Java"),
                 Path(os.environ.get("JAVA_HOME", ""))]:
        if base and str(base) and base.exists():
            cands += list(base.glob("*/bin/java.exe")) + list(base.glob("bin/java.exe"))
    found = shutil.which("java")
    if found:
        cands.append(Path(found))
    best, best_v = None, -1
    for c in dict.fromkeys(cands):
        try:
            out = subprocess.run([str(c), "-version"], capture_output=True,
                                 text=True, timeout=10).stderr
            m = re.search(r'version "(\d+)', out)
            v = int(m.group(1)) if m else 0
            if v > best_v:
                best, best_v = c, v
        except Exception:
            pass
    return best, best_v


class MineHost:
    def __init__(self, root):
        self.root = root
        root.title("MineHost")
        root.geometry("820x640")
        root.configure(bg=BG)
        self.cfg = load_config()
        self.proc = None
        self.players = []
        self._style()
        self._build()
        threading.Thread(target=self.refresh_versions, daemon=True).start()

    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("TButton", background=PANEL, foreground=FG, padding=6)
        s.map("TButton", background=[("active", "#33334d")])
        s.configure("Accent.TButton", background=ACCENT, foreground="white")
        s.map("Accent.TButton", background=[("active", "#43a047")])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(14, 8))
        s.map("TNotebook.Tab", background=[("selected", BG)],
              foreground=[("selected", ACCENT)])
        s.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                    foreground=FG, arrowcolor=ACCENT)
        s.configure("TEntry", fieldbackground=PANEL, foreground=FG)
        s.configure("TSpinbox", fieldbackground=PANEL, foreground=FG)
        s.configure("TCheckbutton", background=BG, foreground=FG)

    def _build(self):
        top = ttk.Frame(self.root, padding=(12, 10, 12, 0))
        top.pack(fill="x")
        ttk.Label(top, text="⛏ MineHost", font=("Segoe UI", 16, "bold"),
                  foreground=ACCENT).pack(side="left")
        self.dot = ttk.Label(top, text="●", font=("Segoe UI", 14), foreground="#f44336")
        self.dot.pack(side="right", padx=(0, 4))
        self.status = StringVar(value="Detenido")
        ttk.Label(top, textvariable=self.status).pack(side="right")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=10)
        self._tab_server(nb)
        self._tab_console(nb)
        self._tab_tunnels(nb)
        self._tab_settings(nb)

    # ---- pestana Servidor ----
    def _tab_server(self, nb):
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="  Servidor  ")

        ttk.Label(f, text="Tipo de servidor").grid(row=0, column=0, sticky="w")
        self.type_var = StringVar(value=self.cfg.get("server_type", "Purpur"))
        self.type_box = ttk.Combobox(f, textvariable=self.type_var, width=14,
                                     state="readonly",
                                     values=list(SERVER_TYPES))
        self.type_box.grid(row=0, column=1, sticky="w", pady=4)
        self.type_box.bind("<<ComboboxSelected>>", self._on_type)
        self.type_note = StringVar(value="")
        ttk.Label(f, textvariable=self.type_note, foreground=ACCENT).grid(
            row=0, column=2, sticky="w", padx=8)

        ttk.Label(f, text="Versión").grid(row=1, column=0, sticky="w")
        self.ver_var = StringVar(value=self.cfg.get("version") or "cargando...")
        self.ver_box = ttk.Combobox(f, textvariable=self.ver_var, width=14,
                                    state="readonly")
        self.ver_box.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Button(f, text="Descargar", command=self.download).grid(
            row=1, column=2, sticky="w", padx=8)

        ttk.Label(f, text="RAM mín (GB)").grid(row=2, column=0, sticky="w")
        self.ram_min = IntVar(value=self.cfg["ram_min"])
        ttk.Spinbox(f, from_=1, to=16, textvariable=self.ram_min, width=6).grid(
            row=2, column=1, sticky="w", pady=4)
        ttk.Label(f, text="RAM máx (GB)").grid(row=3, column=0, sticky="w")
        self.ram_max = IntVar(value=self.cfg["ram_max"])
        ttk.Spinbox(f, from_=1, to=32, textvariable=self.ram_max, width=6).grid(
            row=3, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Puerto").grid(row=4, column=0, sticky="w")
        self.port = IntVar(value=self.cfg["port"])
        ttk.Spinbox(f, from_=1024, to=65535, textvariable=self.port, width=8).grid(
            row=4, column=1, sticky="w", pady=4)

        self.eula = BooleanVar(value=self.cfg["eula"])
        ttk.Checkbutton(f, text="Acepto el EULA de Mojang (eula=true)",
                        variable=self.eula).grid(row=5, column=0, columnspan=3,
                                                 sticky="w", pady=6)

        row = ttk.Frame(f)
        row.grid(row=6, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Button(row, text="▶  Iniciar", style="Accent.TButton",
                   command=self.start).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="■  Detener", command=self.stop).pack(side="left")

        ttk.Label(f, text="Jugadores conectados", font=("Segoe UI", 10, "bold"),
                  foreground=ACCENT).grid(row=7, column=0, columnspan=2,
                                           sticky="w", pady=(10, 2))
        ttk.Button(f, text="↻ Actualizar", command=self.refresh_players).grid(
            row=7, column=2, sticky="e")
        self.player_count = StringVar(value="0 en línea")
        ttk.Label(f, textvariable=self.player_count, foreground=MUTED).grid(
            row=8, column=0, columnspan=3, sticky="w")
        from tkinter import Listbox
        self.player_list = Listbox(f, bg=PANEL, fg=FG, height=6, width=50,
                                   highlightthickness=0, relief="flat")
        self.player_list.grid(row=9, column=0, columnspan=3, sticky="ew", pady=4)

    # ---- pestana Consola ----
    def _tab_console(self, nb):
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="  Consola  ")
        self.console = ScrolledText(f, height=22, bg="#11111b", fg="#4caf50",
                                    insertbackground="white", relief="flat")
        self.console.pack(fill="both", expand=True)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(8, 0))
        self.cmd = StringVar()
        entry = ttk.Entry(bar, textvariable=self.cmd)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        entry.bind("<Return>", lambda e: self.send_cmd())
        ttk.Button(bar, text="Enviar", command=self.send_cmd).pack(side="right")

    # ---- pestana Tuneles ----
    def _tab_tunnels(self, nb):
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="  Túneles  ")
        ttk.Label(f, text="Exponer el servidor a internet",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(f, text="El servidor debe estar iniciado antes de abrir un túnel.",
                  foreground=MUTED).pack(anchor="w", pady=(0, 10))
        ttk.Button(f, text="🚀  Abrir túnel Playit (recomendado)",
                   style="Accent.TButton", command=self.start_playit).pack(
                       anchor="w", pady=4)
        ttk.Button(f, text="🌐  Abrir túnel ngrok",
                   command=self.start_ngrok).pack(anchor="w", pady=4)
        ttk.Label(f, text="Tu dirección pública (Playit)",
                  font=("Segoe UI", 10, "bold"), foreground=ACCENT).pack(
                      anchor="w", pady=(14, 2))
        self.pub_addr = StringVar(value="aún sin configurar")
        ttk.Label(f, textvariable=self.pub_addr, font=("Segoe UI", 11)).pack(anchor="w")
        ttk.Label(f, text="IP local para jugar en tu red",
                  font=("Segoe UI", 10, "bold"), foreground=ACCENT).pack(
                      anchor="w", pady=(14, 2))
        ttk.Button(f, text="📡  Ver mi IP local", command=self.show_ip).pack(anchor="w")

    # ---- pestana Ajustes ----
    def _tab_settings(self, nb):
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="  Ajustes  ")
        java, ver = find_best_java()
        ttk.Label(f, text="Java detectado",
                  font=("Segoe UI", 10, "bold"), foreground=ACCENT).pack(anchor="w")
        ttk.Label(f, text=f"Java {ver}: {java}" if java else "No encontrado",
                  foreground=MUTED, wraplength=600).pack(anchor="w", pady=(0, 12))
        ttk.Button(f, text="💾  Guardar configuración", command=self.save).pack(
            anchor="w", pady=4)
        ttk.Button(f, text="📂  Abrir carpeta del servidor",
                   command=self.open_folder).pack(anchor="w", pady=4)
        ttk.Label(f, text="MineHost · MIT",
                  foreground=MUTED).pack(anchor="w", pady=(16, 0))

    # ---- logica ----
    def log(self, msg):
        self.console.insert(END, msg + "\n")
        self.console.see(END)
        m = re.search(r"There are (\d+).*players online:?(.*)", msg)
        if m:
            self._set_players(m.group(1), m.group(2))

    def _set_players(self, count, names):
        self.player_count.set(f"{count} en línea")
        self.player_list.delete(0, END)
        for n in names.split(","):
            n = re.sub(r"§.", "", n).strip()
            if n:
                self.player_list.insert(END, n)

    def current_type(self):
        return SERVER_TYPES.get(self.type_var.get(), SERVER_TYPES["Purpur"])

    def _on_type(self, _e=None):
        t = self.current_type()
        if t["ready"]:
            self.type_note.set("✓ disponible")
            threading.Thread(target=self.refresh_versions, daemon=True).start()
        else:
            self.type_note.set("🔜 próximamente — usando Purpur")
            self.type_var.set("Purpur")

    def refresh_versions(self):
        try:
            data = api_get(self.current_type()["api"])
            vers = data["versions"]

            def apply():
                self.ver_box["values"] = vers
                if not self.ver_var.get() or self.ver_var.get() == "cargando...":
                    self.ver_var.set(self.cfg.get("version") or vers[-1])
                self.log(f"✓ {len(vers)} versiones cargadas. Última: {vers[-1]}")
            self.root.after(0, apply)
        except Exception as e:
            self.root.after(0, lambda: self.log(f"[!] No se pudo listar versiones: {e}"))

    def download(self):
        t = self.current_type()
        if not t["ready"]:
            return messagebox.showinfo("MineHost", "Ese tipo aún no está disponible.")
        v = self.ver_var.get()
        if not v or v == "cargando...":
            return messagebox.showwarning("Aviso", "Espera a que carguen las versiones.")

        def work():
            try:
                d = api_get(f"{t['api']}/{v}")
                b = d["builds"]["latest"]
                url = f"{t['api']}/{v}/{b}/download"
                dest = BASE_DIR / t["jar"]
                self.log(f"Descargando {self.type_var.get()} {v} build {b}...")
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as fh:
                    shutil.copyfileobj(r, fh)
                self.log(f"✓ Guardado ({dest.stat().st_size / 1e6:.1f} MB)")
                self.root.after(0, lambda: messagebox.showinfo(
                    "Listo", f"{self.type_var.get()} {v} (build {b}) descargado."))
            except Exception as e:
                self.log(f"[!] Error descarga: {e}")
        threading.Thread(target=work, daemon=True).start()

    def _persist(self):
        self.cfg.update(server_type=self.type_var.get(), version=self.ver_var.get(),
                        ram_min=self.ram_min.get(), ram_max=self.ram_max.get(),
                        port=self.port.get(), eula=self.eula.get())
        save_config(self.cfg)
        (BASE_DIR / "eula.txt").write_text(
            "eula=true\n" if self.eula.get() else "eula=false\n")

    def save(self):
        self._persist()
        sp = BASE_DIR / "server.properties"
        if sp.exists():
            t = sp.read_text()
            t = re.sub(r"^server-port=.*", f"server-port={self.port.get()}", t, flags=re.M)
            sp.write_text(t)
        messagebox.showinfo("MineHost", "Configuración guardada.")

    def open_folder(self):
        os.startfile(BASE_DIR)

    def show_ip(self):
        ip = socket.gethostbyname(socket.gethostname())
        messagebox.showinfo("Red local",
                            f"IP local: {ip}:{self.port.get()}\n"
                            f"En tu PC usa: localhost:{self.port.get()}")

    def _set_running(self, running):
        self.status.set("Corriendo" if running else "Detenido")
        self.dot.configure(foreground="#4caf50" if running else "#f44336")

    def start(self):
        t = self.current_type()
        jar = BASE_DIR / t["jar"]
        if not jar.exists():
            return messagebox.showerror("Falta JAR", "Primero pulsa 'Descargar'.")
        if not self.eula.get():
            return messagebox.showerror("EULA", "Debes aceptar el EULA.")
        if self.proc and self.proc.poll() is None:
            return messagebox.showwarning("Aviso", "El servidor ya está corriendo.")
        self._persist()
        java, ver = find_best_java()
        if not java:
            return messagebox.showerror("Sin Java", "No se encontró Java instalado.")
        if ver < 25:
            return messagebox.showerror(
                "Java viejo", f"Encontrado Java {ver}, pero se exige Java 25+.")
        self.log(f"Usando Java {ver}: {java}")
        cmd = [str(java), f"-Xms{self.ram_min.get()}G", f"-Xmx{self.ram_max.get()}G",
               "-jar", str(jar), "nogui"]
        self.log(" ".join(cmd))
        self.proc = subprocess.Popen(cmd, cwd=BASE_DIR, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
        self._set_running(True)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.proc.stdout:
            self.console.insert(END, line)
            self.console.see(END)
            m = re.search(r"There are (\d+).*players online:?(.*)", line)
            if m:
                names, count = m.group(2), m.group(1)
                self.root.after(0, lambda: self._set_players(count, names))
        self.root.after(0, lambda: self._set_running(False))

    def send_cmd(self):
        c = self.cmd.get().strip()
        if not c:
            return
        self.log(f"> {c}")
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.write(c + "\n")
            self.proc.stdin.flush()
        self.cmd.set("")

    def refresh_players(self):
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.write("list\n")
            self.proc.stdin.flush()
        else:
            self.log("Servidor no está corriendo.")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write("stop\n")
                self.proc.stdin.flush()
            except Exception:
                self.proc.terminate()
            self.log("Deteniendo servidor...")
        else:
            self.log("Servidor no está corriendo.")

    def start_ngrok(self):
        port = self.port.get()
        ngrok = shutil.which("ngrok")
        if not ngrok:
            self.log("[!] ngrok no instalado: https://ngrok.com/download")
            return messagebox.showinfo(
                "ngrok",
                "1. Descarga ngrok: https://ngrok.com/download\n"
                "2. Crea cuenta gratis y copia tu authtoken\n"
                "3. Ejecuta: ngrok config add-authtoken <TOKEN>\n"
                "4. Vuelve y pulsa este botón de nuevo.")

        def work():
            self.log(f"Abriendo túnel público al puerto {port}...")
            p = subprocess.Popen([ngrok, "tcp", str(port)],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True)
            for line in p.stdout:
                self.log("[ngrok] " + line.strip())
                m = re.search(r"tcp://([^\s]+)", line)
                if m:
                    addr = m.group(1)
                    self.root.after(0, lambda: self.pub_addr.set(addr))
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Túnel listo", f"Comparte con tus amigos:\n{addr}"))
        threading.Thread(target=work, daemon=True).start()

    def start_playit(self):
        playit = shutil.which("playit") or r"C:\Program Files\playit_gg\bin\playit.exe"
        if not os.path.exists(playit):
            return messagebox.showerror(
                "Playit", "No se encontró playit.exe. Descárgalo en https://playit.gg")

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
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Playit",
                        f"1. Abre y reclama tu agente:\n{url}\n\n"
                        "2. En playit.gg crea un túnel:\n"
                        "   Tipo: Minecraft Java | Puerto local: "
                        f"{self.port.get()}\n"
                        "3. Pega la dirección en la pestaña Túneles."))
        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    root = Tk()
    MineHost(root)
    root.mainloop()
