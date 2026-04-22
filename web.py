import os
import subprocess
import threading
import datetime
import json
import pymysql
import shutil
from pathlib import Path
import sys
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Persistent DB/SSH globals
_GLOBAL_CONN = None
_GLOBAL_TUNNEL = None

# ─────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_PATH = Path(sys.executable).parent
else:
    BASE_PATH = Path(__file__).resolve().parent

SETTINGS_FILE = BASE_PATH / "settings.json"

def get_settings():
    default_settings = {
        "user_name": "",
        "git_bash_path": r"C:\Program Files\Git\bin\bash.exe",
        "workspace_url": str(BASE_PATH.parent),
        "pre_deploy_cmd": "",
    }
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_settings.update(data)
        except Exception:
            pass
    return default_settings

def save_settings(new_settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(new_settings, f, indent=4)
        return True
    except Exception:
        return False

# ─────────────────────────────────────────────
#  Service Logic
# ─────────────────────────────────────────────
def get_bash_path(settings):
    if os.name == "nt":
        custom = settings.get("git_bash_path", "")
        if custom and os.path.exists(custom):
            return custom
        git_bash = r"C:\Program Files\Git\bin\bash.exe"
        if os.path.exists(git_bash):
            return git_bash
        return "bash"
    return shutil.which("bash") or "bash"

def scan_services(workspace_url):
    services = []
    p = Path(workspace_url)
    if not p.exists() or not p.is_dir():
        return services

    for d in sorted(p.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        dev_path = next((x for x in [d / "deploy-dev.sh", d / "scripts" / "deploy-dev.sh"] if x.exists()), None)
        stg_path = next((x for x in [d / "deploy-stg.sh", d / "scripts" / "deploy-stg.sh"] if x.exists()), None)
        
        if dev_path or stg_path:
            # Get current branch
            branch = "unknown"
            try:
                cf = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == "nt" else {}
                branch = subprocess.check_output(
                    ["git", "-c", "safe.directory=*", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(d), text=True, stderr=subprocess.STDOUT, **cf
                ).strip()
            except Exception:
                pass

            # Get latest commit message
            commit_msg = ""
            try:
                commit_msg = subprocess.check_output(
                    ["git", "-c", "safe.directory=*", "log", "-1", "--pretty=%s"],
                    cwd=str(d), text=True, stderr=subprocess.STDOUT, **cf
                ).strip()
            except Exception:
                pass

            services.append({
                "name": d.name,
                "dir": str(d),
                "branch": branch,
                "last_commit": commit_msg,
                "has_dev": bool(dev_path),
                "has_stg": bool(stg_path),
                "dev_script": str(dev_path) if dev_path else "",
                "stg_script": str(stg_path) if stg_path else ""
            })
    return services

def get_db_conn():
    """Helper for MySQL connection with optional SSH tunnel using ENV vars (Persistent)."""
    global _GLOBAL_CONN, _GLOBAL_TUNNEL
    
    if _GLOBAL_CONN:
        try:
            _GLOBAL_CONN.ping(reconnect=True)
            return _GLOBAL_CONN
        except:
            if _GLOBAL_TUNNEL:
                try: _GLOBAL_TUNNEL.stop()
                except: pass
            _GLOBAL_CONN = None
            _GLOBAL_TUNNEL = None

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
        
        if ssh_host and ssh_user:
            _GLOBAL_TUNNEL = SSHTunnelForwarder(
                (ssh_host, ssh_port),
                ssh_username=ssh_user,
                ssh_password=ssh_pwd if not ssh_key else None,
                ssh_pkey=ssh_key if ssh_key else None,
                remote_bind_address=(db_host, db_port)
            )
            _GLOBAL_TUNNEL.start()
            
            _GLOBAL_CONN = pymysql.connect(
                host='127.0.0.1',
                port=_GLOBAL_TUNNEL.local_bind_port,
                user=db_user,
                password=db_pwd,
                database=db_name,
                cursorclass=pymysql.cursors.DictCursor
            )
            return _GLOBAL_CONN

    _GLOBAL_CONN = pymysql.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_pwd,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )
    return _GLOBAL_CONN

def log_to_mysql(user_name, service_name, env, branch, message):
    conn = None
    try:
        conn = get_db_conn()
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
            ''', (user_name, service_name, env, branch, message, datetime.datetime.now()))
        conn.commit()
        return True, "Saved deployment log \u2713"
    except Exception as e:
        err_msg = str(e)
        ssh_key_path = os.getenv("SSH_KEY_PATH", "")
        if ".pub" in ssh_key_path.lower():
            err_msg += " (Note: Do not use .pub file, use the Private Key file)"
        print(f"MySQL Error: {err_msg}")
        return False, err_msg
    finally:
        pass

# ─────────────────────────────────────────────
#  API Endpoints
# ─────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("favicon.ico")

@app.route("/api/settings", methods=["GET", "POST"])
def settings_api():
    if request.method == "POST":
        data = request.json
        if save_settings(data):
            return jsonify({"status": "ok"})
        return jsonify({"status": "error"}), 500
    
    try:
        settings = get_settings()
        return jsonify(settings)
    except Exception as e:
        print(f"Settings API Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/services")
def services_api():
    settings = get_settings()
    return jsonify(scan_services(settings["workspace_url"]))

@app.route("/api/history/<service_name>")
def history_api(service_name):
    conn = None
    try:
        conn = get_db_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_name, environment, branch, created_at, message 
                FROM deployments 
                WHERE service = %s 
                ORDER BY created_at DESC 
                LIMIT 30
            """, (service_name,))
            rows = cur.fetchall()
            for r in rows:
                r['created_at'] = (r['created_at'] + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
        return jsonify(rows)
    except Exception as e:
        print(f"History API Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        pass

@app.route("/api/deploy", methods=["POST"])
def deploy_api():
    data = request.json
    service_name = data.get("service")
    env = data.get("env")
    user_msg = data.get("message", "Auto deploy")
    
    settings = get_settings()
    services = scan_services(settings["workspace_url"])
    svc = next((s for s in services if s["name"] == service_name), None)
    
    if not svc:
        return jsonify({"status": "error", "message": "Service not found"}), 404
        
    script_path = svc["dev_script"] if env == "Development" else svc["stg_script"]
    if not script_path:
        return jsonify({"status": "error", "message": "Script not found for environment"}), 400

    def generate():
        bash = get_bash_path(settings)
        user_name = settings.get("user_name") or "WebUser"
        branch = svc["branch"]
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_msg = f"[{user_name}] [{branch}] [{now_str}] {user_msg}"
        
        script_name = os.path.basename(script_path)
        script_dir = os.path.dirname(script_path)
        pre_cmd = settings.get("pre_deploy_cmd", "").strip()

        # Step 1: Pre-deploy
        if pre_cmd:
            yield f"data: [Pre-deploy] $ {pre_cmd}\n\n"
            cf = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == "nt" else {}
            if os.name == "nt":
                cmd_parts = ["cmd.exe", "/c", pre_cmd]
            else:
                cmd_parts = ["sh", "-c", pre_cmd]
                
            proc = subprocess.Popen(cmd_parts, cwd=svc["dir"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **cf)
            for line in proc.stdout:
                yield f"data: {line}\n\n"
            proc.wait()
            if proc.returncode != 0:
                yield f"data: \n[Pre-deploy failed — exit {proc.returncode}. Aborting.]\n\n"
                return

        # Step 2: Deploy script
        yield f"data: $ bash {script_name} \"{final_msg}\"\n\n"
        proc = subprocess.Popen([bash, script_name, final_msg], cwd=script_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **cf)
        for line in proc.stdout:
            yield f"data: {line}\n\n"
        proc.wait()
        
        if proc.returncode == 0:
            yield f"data: \n[Deploy finished successfully \u2713]\n\n"
            success, msg = log_to_mysql(user_name, service_name, env, branch, user_msg)
            yield f"data: [MySQL] {msg}\n\n"
        else:
            yield f"data: \n[Deploy error \u2014 exit {proc.returncode}]\n\n"
        
        yield "data: [EOF]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

if __name__ == "__main__":
    # Create templates folder if it doesn't exist
    os.makedirs("templates", exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=True)
