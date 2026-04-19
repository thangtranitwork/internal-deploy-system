import os
import subprocess
import threading
import datetime
import json
import pymysql
import sys
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv
import shutil
from pathlib import Path
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog

load_dotenv()

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# ─────────────────────────────────────────────
#  Settings Window
# ─────────────────────────────────────────────
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, settings: dict, on_save):
        super().__init__(parent)
        self.title("⚙️ Settings")
        self.geometry("580x430")
        self.resizable(False, False)
        self.grab_set()

        self.settings = dict(settings)
        self.on_save = on_save

        def lbl(text):
            ctk.CTkLabel(self, text=text, text_color="gray",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=24, pady=(14, 2))

        def row_browse(placeholder, key, folder=False, ftypes=None):
            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.pack(fill="x", padx=24, pady=(0, 4))
            entry = ctk.CTkEntry(frame, placeholder_text=placeholder)
            entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            entry.insert(0, self.settings.get(key, ""))
            ctk.CTkButton(
                frame, text="Browse", width=80,
                command=lambda e=entry, f=folder, ft=ftypes: self._browse(e, f, ft)
            ).pack(side="left")
            return entry

        lbl("WORKSPACE DIRECTORY")
        self.entry_ws = row_browse("Path to projects directory", "workspace_url", folder=True)

        if os.name == "nt":
            lbl("GIT BASH PATH")
            self.entry_git = row_browse(
                r"C:\Program Files\Git\bin\bash.exe", "git_bash_path",
                folder=False, ftypes=[("Executable", "*.exe"), ("All", "*.*")]
            )
        else:
            self.entry_git = None

        lbl("YOUR NAME")
        self.entry_name = ctk.CTkEntry(self, placeholder_text="e.g. John Doe")
        self.entry_name.pack(fill="x", padx=24, pady=(0, 4))
        self.entry_name.insert(0, self.settings.get("user_name", ""))

        lbl("PRE-DEPLOY COMMAND  (runs in service dir before deploy script)")
        self.entry_pre = ctk.CTkEntry(self, placeholder_text="e.g. go mod tidy")
        self.entry_pre.pack(fill="x", padx=24, pady=(0, 4))
        self.entry_pre.insert(0, self.settings.get("pre_deploy_cmd", ""))

        row_btn = ctk.CTkFrame(self, fg_color="transparent")
        row_btn.pack(fill="x", padx=24, pady=(18, 20))
        ctk.CTkButton(row_btn, text="Save", command=self._save).pack(side="right", padx=(8, 0))
        ctk.CTkButton(row_btn, text="Cancel", fg_color="transparent", border_width=1,
                      command=self.destroy).pack(side="right")

    def _browse(self, entry, folder=False, ftypes=None):
        path = (filedialog.askdirectory(title="Select Directory") if folder
                else filedialog.askopenfilename(title="Select File", filetypes=ftypes or []))
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def _save(self):
        self.settings["workspace_url"] = self.entry_ws.get().strip()
        self.settings["user_name"] = self.entry_name.get().strip()
        self.settings["pre_deploy_cmd"] = self.entry_pre.get().strip()
        if self.entry_git:
            self.settings["git_bash_path"] = self.entry_git.get().strip()
        self.on_save(self.settings)
        self.destroy()


# ─────────────────────────────────────────────
#  History Window
# ─────────────────────────────────────────────
class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, parent, service_name):
        super().__init__(parent)
        self.title(f"📜 Deployment History - {service_name}")
        self.geometry("800x500")
        self.grab_set()

        ctk.CTkLabel(self, text=f"Deployment history for {service_name}",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=12)

        self.table_frame = ctk.CTkScrollableFrame(self)
        self.table_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self._load_history(service_name)

    def _load_history(self, service_name):
        conn = None
        try:
            conn = self.master.master.master._get_db_conn() # Access parent's helper if possible, but cleaner to just reimplement or pass it
            # Actually, HistoryWindow is a child of the app.
            # Let's just use a simple connection here for now or fix the access
            parent_app = self.master
            conn = parent_app._get_db_conn()
            
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_name, environment, branch, created_at, message 
                    FROM deployments 
                    WHERE service = %s 
                    ORDER BY created_at DESC 
                    LIMIT 50
                """, (service_name,))
                rows = cur.fetchall()

            if not rows:
                ctk.CTkLabel(self.table_frame, text="No history found.").pack(pady=20)
                return

            for r in rows:
                f = ctk.CTkFrame(self.table_frame, fg_color="#161b22")
                f.pack(fill="x", pady=4, padx=5)
                
                time_str = r['created_at'].strftime("%H:%M %d/%m/%Y")
                title = f"{time_str} | User: {r['user_name']} | Env: {r['environment']} | Branch: {r['branch']}"
                
                ctk.CTkLabel(f, text=title, font=ctk.CTkFont(weight="bold", size=12), text_color="#58a6ff").pack(anchor="w", padx=12, pady=(8, 2))
                ctk.CTkLabel(f, text=f"💬 {r['message']}", text_color="#e6edf3", font=ctk.CTkFont(size=12), wraplength=740).pack(anchor="w", padx=12, pady=(0, 8))

        except Exception as e:
            ctk.CTkLabel(self.table_frame, text=f"Error loading history: {e}", text_color="red").pack(pady=20)
        finally:
            if conn:
                conn.close()
                if hasattr(conn, 'ssh_tunnel'):
                    conn.ssh_tunnel.stop()


# ─────────────────────────────────────────────
#  Main App
# ─────────────────────────────────────────────
class DeployApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Service Deploy Commander")
        self.geometry("1100x760")
        self.minsize(960, 640)

        self.services = []
        self.current_branch = ""
        if getattr(sys, 'frozen', False):
            # Running as bundled exe
            self.base_path = Path(sys.executable).parent
        else:
            # Running as script
            self.base_path = Path(__file__).resolve().parent

        self.settings_file = self.base_path / "settings.json"

        self.settings = {
            "user_name": "",
            "git_bash_path": r"C:\Program Files\Git\bin\bash.exe",
            "workspace_url": str(self.base_path.parent),
            "pre_deploy_cmd": "",
        }

        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    self.settings.update(json.load(f))
            except Exception:
                pass

        self._setup_ui()
        self._bind_shortcuts()

        missing = not self.settings.get("workspace_url") or not self.settings.get("user_name")
        if missing:
            self.after(300, self._open_settings)
        else:
            self.load_services()

    # ── Shortcuts ──────────────────────────────────────────────────────────
    def _bind_shortcuts(self):
        self.bind("<Control-k>", self._on_ctrl_k)

    def _on_ctrl_k(self, event):
        self.bind("<o>", self._ctrl_k_o_handler)
        self.bind("<O>", self._ctrl_k_o_handler)
        self.after(1000, self._unbind_k_combo)

    def _ctrl_k_o_handler(self, event):
        self._unbind_k_combo()
        self._open_settings()

    def _unbind_k_combo(self):
        try:
            self.unbind("<o>")
            self.unbind("<O>")
        except Exception:
            pass

    # ── UI ─────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        # Top bar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(14, 0))
        ctk.CTkLabel(top, text="🚀 Service Deploy Commander",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="⚙️ Settings  (Ctrl+K O)",
                       width=170, command=self._open_settings).pack(side="right")

        # Info bar
        self.lbl_info = ctk.CTkLabel(self, text="", text_color="gray",
                                     font=ctk.CTkFont(family="Consolas", size=11))
        self.lbl_info.pack(anchor="w", padx=22, pady=(4, 0))
        self._refresh_info_bar()

        ctk.CTkFrame(self, height=1, fg_color="#30363d").pack(fill="x", padx=20, pady=(8, 0))

        # Two-column body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)
        body.columnconfigure(0, weight=3, minsize=280)
        body.columnconfigure(1, weight=5)
        body.rowconfigure(0, weight=1)

        # ══ LEFT ══
        left = ctk.CTkFrame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="SERVICES", text_color="gray",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w",
                                                      padx=14, pady=(14, 4))

        list_frame = ctk.CTkFrame(left, fg_color="#010409")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.svc_listbox = tk.Listbox(
            list_frame,
            bg="#010409", fg="#e6edf3",
            selectbackground="#1f6feb", selectforeground="white",
            activestyle="none",
            font=("Consolas", 15),
            bd=0, highlightthickness=0, relief="flat",
        )
        self.svc_listbox.grid(row=0, column=0, sticky="nsew")
        self.svc_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        sb = ctk.CTkScrollbar(list_frame, command=self.svc_listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.svc_listbox.configure(yscrollcommand=sb.set)

        ctk.CTkButton(left, text="↻ Refresh", width=100,
                      command=self.load_services).grid(row=2, column=0, sticky="w",
                                                       padx=14, pady=(0, 14))

        # ══ RIGHT ══
        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        # --- branch label
        self.lbl_branch = ctk.CTkLabel(right, text="Branch: —", text_color="#58a6ff",
                                       font=ctk.CTkFont(family="Consolas", size=13))
        self.lbl_branch.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 0))

        # --- environment
        ctk.CTkLabel(right, text="ENVIRONMENT", text_color="gray",
                     font=ctk.CTkFont(size=11)).grid(row=1, column=0, sticky="w",
                                                     padx=16, pady=(10, 2))
        self.env_var = ctk.StringVar(value="Development")
        ctk.CTkSegmentedButton(right, values=["Development", "Staging"],
                               variable=self.env_var,
                               command=self.validate_form).grid(row=2, column=0,
                                                                sticky="w", padx=16,
                                                                pady=(0, 10))

        # --- deploy message
        ctk.CTkLabel(right, text="DEPLOY MESSAGE", text_color="gray",
                     font=ctk.CTkFont(size=11)).grid(row=3, column=0, sticky="w",
                                                     padx=16, pady=(0, 2))
        self.entry_msg = ctk.CTkEntry(right,
                                      placeholder_text="Latest commit message (auto-filled)")
        self.entry_msg.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))

        # --- action buttons row
        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 10))
        btn_row.columnconfigure(0, weight=1)

        self.btn_deploy = ctk.CTkButton(btn_row, text="🚀 Run Deploy",
                                        command=self.run_deploy, height=38,
                                        font=ctk.CTkFont(weight="bold", size=14))
        self.btn_deploy.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.btn_terminal = ctk.CTkButton(
            btn_row, text="💻 Open Terminal Here",
            command=self._open_terminal_here,
            height=38, width=180,
            fg_color="#21262d", hover_color="#30363d",
            border_width=1, border_color="#30363d",
            font=ctk.CTkFont(size=13),
        )
        self.btn_terminal.grid(row=0, column=1)

        # --- history bar (new)
        self.hist_frame = ctk.CTkFrame(right, fg_color="#161b22", corner_radius=6)
        self.hist_frame.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 10))
        
        self.lbl_last_deploy = ctk.CTkLabel(self.hist_frame, text="Last deploy: —", 
                                            font=ctk.CTkFont(size=11), text_color="#8b949e")
        self.lbl_last_deploy.pack(side="left", padx=12, pady=8)
        
        self.btn_view_more = ctk.CTkButton(self.hist_frame, text="View More", width=80, 
                                           height=24, font=ctk.CTkFont(size=10),
                                           fg_color="transparent", border_width=1,
                                           command=self._view_full_history)
        self.btn_view_more.pack(side="right", padx=12)
        self.btn_view_more.configure(state="disabled")

        # --- logs
        ctk.CTkLabel(right, text="LOGS", text_color="gray",
                     font=ctk.CTkFont(size=11)).grid(row=7, column=0, sticky="w",
                                                      padx=16, pady=(4, 2))
        right.rowconfigure(8, weight=1)
        self.terminal = ctk.CTkTextbox(right,
                                       font=ctk.CTkFont(family="Consolas", size=12),
                                       fg_color="#010409", text_color="#e6edf3")
        self.terminal.grid(row=8, column=0, sticky="nsew", padx=16, pady=(0, 16))

    # ── Open real terminal ──────────────────────────────────────────────────
    def _open_terminal_here(self):
        """Open a real interactive terminal in the selected service directory."""
        svc = self._get_selected_service()
        cwd = svc["dir"] if svc else self.settings.get("workspace_url", os.getcwd())

        if os.name == "nt":
            # Try Windows Terminal first, fall back to Git Bash, then cmd
            wt = shutil.which("wt")
            git_bash = self.settings.get("git_bash_path", "")
            if not git_bash or not os.path.exists(git_bash):
                git_bash = r"C:\Program Files\Git\bin\bash.exe"

            if wt:
                # Windows Terminal opens in the given startingDirectory
                subprocess.Popen(
                    ["wt", "--startingDirectory", cwd],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            elif os.path.exists(git_bash):
                subprocess.Popen(
                    [git_bash, "--login", "-i"],
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                # Last resort: cmd.exe
                subprocess.Popen(
                    ["cmd.exe"],
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
        else:
            # Linux / macOS: try common terminals
            for term in ["gnome-terminal", "xterm", "konsole", "x-terminal-emulator"]:
                if shutil.which(term):
                    subprocess.Popen([term], cwd=cwd)
                    return
            # macOS
            subprocess.Popen(
                ["open", "-a", "Terminal", cwd]
            )

    # ── Settings ───────────────────────────────────────────────────────────
    def _open_settings(self, event=None):
        SettingsWindow(self, self.settings, self._on_settings_saved)

    def _on_settings_saved(self, new_settings: dict):
        self.settings.update(new_settings)
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except Exception:
            pass
        self._refresh_info_bar()
        self.load_services()

    def _refresh_info_bar(self):
        ws   = self.settings.get("workspace_url") or "(not set)"
        name = self.settings.get("user_name")     or "(not set)"
        pre  = self.settings.get("pre_deploy_cmd") or "—"
        self.lbl_info.configure(
            text=f"Workspace: {ws}   |   User: {name}   |   Pre-deploy: {pre}"
        )

    # ── Services ───────────────────────────────────────────────────────────
    def load_services(self):
        ws_dir = self.settings.get("workspace_url", "").strip()
        self.svc_listbox.delete(0, "end")
        self.services = []

        if not ws_dir:
            self.svc_listbox.insert("end", "  ⚠ No workspace set")
            return
        p = Path(ws_dir)
        if not p.exists() or not p.is_dir():
            self.svc_listbox.insert("end", "  ⚠ Invalid path")
            return

        for d in sorted(p.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            dev_path = next(
                (x for x in [d / "deploy-dev.sh", d / "scripts" / "deploy-dev.sh"]
                 if x.exists()), None)
            stg_path = next(
                (x for x in [d / "deploy-stg.sh", d / "scripts" / "deploy-stg.sh"]
                 if x.exists()), None)
            if dev_path or stg_path:
                self.services.append({
                    "name": d.name,
                    "dir": str(d),
                    "dev": str(dev_path) if dev_path else "",
                    "stg": str(stg_path) if stg_path else "",
                })
                self.svc_listbox.insert("end", f"  📦 {d.name}")

        if not self.services:
            self.svc_listbox.insert("end", "  (no services found)")
        else:
            self.svc_listbox.selection_set(0)
            self._on_listbox_select(None)

    def _on_listbox_select(self, event):
        svc = self._get_selected_service()
        if not svc:
            return
        cf = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == "nt" else {}

        # Branch
        try:
            out = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=svc["dir"], text=True, stderr=subprocess.STDOUT, **cf
            )
            self.current_branch = out.strip()
        except Exception:
            self.current_branch = "unknown"
        self.lbl_branch.configure(text=f"Branch: {self.current_branch}")

        # Auto-fill latest commit message
        try:
            commit_msg = subprocess.check_output(
                ["git", "log", "-1", "--pretty=%s"],
                cwd=svc["dir"], text=True, stderr=subprocess.STDOUT, **cf
            ).strip()
            self.entry_msg.delete(0, "end")
            if commit_msg:
                self.entry_msg.insert(0, commit_msg)
        except Exception:
            pass

        self.validate_form()
        self._refresh_last_deploy_info()

    def _get_db_conn(self):
        """Helper to get MySQL connection, optionally via SSH tunnel using ENV vars."""
        db_host = os.getenv("MYSQL_HOST", "localhost")
        db_user = os.getenv("MYSQL_USER", "root")
        db_pwd  = os.getenv("MYSQL_PASSWORD", "")
        db_name = os.getenv("MYSQL_DB", "deploy_logs")
        db_port = int(os.getenv("MYSQL_PORT", "3306"))

        app_env = os.getenv("APP_ENV", "local").lower()
        use_ssh = os.getenv("USE_SSH", "false").lower() == "true" or app_env == "local"

        if use_ssh and app_env == "local":
            ssh_host = os.getenv("SSH_HOST")
            ssh_port = int(os.getenv("SSH_PORT", "22"))
            ssh_user = os.getenv("SSH_USER")
            ssh_key  = os.getenv("SSH_KEY_PATH")
            ssh_pwd  = os.getenv("SSH_PASSWORD")
            
            if not ssh_host or not ssh_user:
                # If SSH is missing in ENV while in local, try direct connect as fallback or log error
                pass 
            else:
                tunnel = SSHTunnelForwarder(
                    (ssh_host, ssh_port),
                    ssh_username=ssh_user,
                    ssh_password=ssh_pwd if not ssh_key else None,
                    ssh_pkey=ssh_key if ssh_key else None,
                    remote_bind_address=(db_host, db_port)
                )
                tunnel.start()
                
                conn = pymysql.connect(
                    host='127.0.0.1',
                    port=tunnel.local_bind_port,
                    user=db_user,
                    password=db_pwd,
                    database=db_name,
                    cursorclass=pymysql.cursors.DictCursor
                )
                conn.ssh_tunnel = tunnel
                return conn

        return pymysql.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_pwd,
            database=db_name,
            cursorclass=pymysql.cursors.DictCursor
        )

    def _refresh_last_deploy_info(self):
        svc = self._get_selected_service()
        if not svc:
            self.lbl_last_deploy.configure(text="Last deploy: —")
            self.btn_view_more.configure(state="disabled")
            return

        def task():
            conn = None
            try:
                conn = self._get_db_conn()
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT user_name, created_at, environment, branch, message 
                        FROM deployments 
                        WHERE service = %s 
                        ORDER BY created_at DESC LIMIT 1
                    """, (svc["name"],))
                    row = cur.fetchone()

                if row:
                    time_str = row['created_at'].strftime("%H:%M %d/%m")
                    msg = row['message']
                    if len(msg) > 40: msg = msg[:37] + "..."
                    info = f"Last: {time_str} by {row['user_name']} | {row['environment']} | {row['branch']} | {msg}"
                    self.after(0, lambda: self.lbl_last_deploy.configure(text=info))
                    self.after(0, lambda: self.btn_view_more.configure(state="normal"))
                else:
                    self.after(0, lambda: self.lbl_last_deploy.configure(text="Last deploy: Never"))
                    self.after(0, lambda: self.btn_view_more.configure(state="disabled"))
            except Exception as e:
                print(f"DB Error: {e}")
                self.after(0, lambda: self.lbl_last_deploy.configure(text="Last deploy: (db error)"))
            finally:
                if conn:
                    conn.close()
                    if hasattr(conn, 'ssh_tunnel'):
                        conn.ssh_tunnel.stop()

        threading.Thread(target=task, daemon=True).start()

    def _view_full_history(self):
        svc = self._get_selected_service()
        if svc:
            HistoryWindow(self, svc["name"])

    def _get_selected_service(self):
        sel = self.svc_listbox.curselection()
        if not sel:
            return None
        idx = sel[0]
        return self.services[idx] if idx < len(self.services) else None

    # ── Validate ───────────────────────────────────────────────────────────
    def validate_form(self, *args):
        svc = self._get_selected_service()
        if not svc:
            self.btn_deploy.configure(state="disabled", text="Select a service")
            return
        env = self.env_var.get()
        has_script = svc["dev"] if env == "Development" else svc["stg"]
        if not has_script:
            self.btn_deploy.configure(state="disabled", text=f"No script for {env}")
        else:
            self.btn_deploy.configure(state="normal", text="🚀 Run Deploy")

    # ── Logs ───────────────────────────────────────────────────────────────
    def append_terminal(self, text):
        self.terminal.insert("end", text)
        self.terminal.see("end")

    def _get_bash(self):
        """Git Bash path - dung de chay .sh scripts."""
        if os.name == "nt":
            custom = self.settings.get("git_bash_path", "")
            if custom and os.path.exists(custom):
                return custom
            git_bash = r"C:\Program Files\Git\bin\bash.exe"
            if os.path.exists(git_bash):
                return git_bash
            # Tranh WSL bash - chi lay bash.exe thuan Windows
            for p in os.environ.get("PATH", "").split(os.pathsep):
                candidate = os.path.join(p, "bash.exe")
                if os.path.exists(candidate) and "System32\\lxss" not in candidate and "wsl" not in candidate.lower():
                    return candidate
            return "bash"
        return shutil.which("bash") or "bash"

    def _stream_proc(self, cmd_parts, cwd):
        """Blocking: stream process stdout into log box. Returns exit code."""
        cf = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == "nt" else {}
        proc = subprocess.Popen(
            cmd_parts, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, **cf,
        )
        for line in proc.stdout:
            self.after(0, self.append_terminal, line)
        proc.wait()
        return proc.returncode

    def _stream_cmd(self, raw_cmd, cwd):
        """Chay lenh Windows thuan (go, docker, npm...) khong qua bash.
        Tren Windows dung cmd /c, tren Unix dung sh -c."""
        if os.name == "nt":
            cmd_parts = ["cmd.exe", "/c", raw_cmd]
        else:
            cmd_parts = [shutil.which("sh") or "sh", "-c", raw_cmd]
        return self._stream_proc(cmd_parts, cwd)

    # ── Deploy ─────────────────────────────────────────────────────────────
    def run_deploy(self):
        svc = self._get_selected_service()
        if not svc:
            return
        env = self.env_var.get()
        script_path = svc["dev"] if env == "Development" else svc["stg"]

        user_name = self.settings.get("user_name") or "Unknown"
        user_msg  = self.entry_msg.get().strip() or "Auto deploy"
        now_str   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_msg = f"[{user_name}] [{self.current_branch}] [{now_str}] {user_msg}"

        script_name = os.path.basename(script_path)
        script_dir  = os.path.dirname(script_path)
        pre_cmd     = self.settings.get("pre_deploy_cmd", "").strip()
        bash        = self._get_bash()

        self.btn_deploy.configure(state="disabled", text="Deploying…")
        self.terminal.delete("1.0", "end")

        def save_to_mysql():
            conn = None
            try:
                conn = self._get_db_conn()
                with conn.cursor() as cur:
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS deployments (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_name VARCHAR(100), service VARCHAR(100),
                            environment VARCHAR(50), branch VARCHAR(100),
                            message TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    cur.execute('''
                        INSERT INTO deployments
                            (user_name, service, environment, branch, message, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    ''', (user_name, svc["name"], env,
                          self.current_branch, user_msg, datetime.datetime.now()))
                conn.commit()
                self.after(0, self.append_terminal, "\n[MySQL] Saved deployment log ✓\n")
            except Exception as e:
                err_msg = str(e)
                if ".pub" in self.settings.get("ssh_key_path", "").lower():
                    err_msg += " (Note: Do not use .pub file, use the Private Key file)"
                self.after(0, self.append_terminal, f"\n[MySQL] Error: {err_msg}\n")
            finally:
                if conn:
                    conn.close()
                    if hasattr(conn, 'ssh_tunnel'):
                        conn.ssh_tunnel.stop()

        def task():
            try:
                # 1. Pre-deploy
                if pre_cmd:
                    self.after(0, self.append_terminal, f"[Pre-deploy] $ {pre_cmd}\n")
                    rc = self._stream_cmd(pre_cmd, cwd=svc["dir"])
                    if rc != 0:
                        self.after(0, self.append_terminal,
                                   f"\n[Pre-deploy failed — exit {rc}. Aborting.]\n")
                        self.after(0, self.validate_form)
                        return
                    self.after(0, self.append_terminal, "[Pre-deploy done ✓]\n\n")

                # 2. Deploy script
                self.after(0, self.append_terminal,
                           f"$ bash {script_name} \"{final_msg}\"\n")
                rc = self._stream_proc([bash, script_name, final_msg], cwd=script_dir)

                result = ("\n[Deploy finished successfully ✓]\n" if rc == 0
                          else f"\n[Deploy error — exit {rc}]\n")
                self.after(0, self.append_terminal, result)
                save_to_mysql()
                self._refresh_last_deploy_info()

            except Exception as e:
                self.after(0, self.append_terminal, f"\nFailed: {e}\n")

            self.after(0, self.validate_form)

        threading.Thread(target=task, daemon=True).start()


if __name__ == "__main__":
    app = DeployApp()
    app.mainloop()