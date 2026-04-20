# 🚀 Service Deploy Commander (IDS)

A powerful, aesthetic deployment dashboard to automate service deployments using shell scripts. Now available in both **Python** and **Go** versions.

## 📁 Project Structure

```text
deploy-tool/
├── main.go             # High-performance Go Backend (Standard Library)
├── web.py              # Python Backend (Flask)
├── app.py              # Desktop application (CustomTkinter)
├── main.exe            # Built Go executable
├── scripts/            # Automation & Runner scripts
│   ├── run_go.bat/sh   # Launch Go version (Recommended)
│   ├── run_web.bat/sh  # Launch Python web version
│   └── build.bat/sh    # Build scripts for Python version
├── templates/          # Web UI templates
├── static/             # Static assets (favicon, etc.)
├── settings.json       # Tool configuration (workspace, user, etc.)
├── .env                # Environment variables (DB, SSH)
└── README.md           # Documentation
```

## 🛠 Features

- **Multi-Backend Runtime**: 
    - **Go Version** (`main.go`): Native performance, clean standard library implementation, supports Go 1.22+ routing.
    - **Python Version** (`web.py`): Flexible Flask-based implementation.
    - **Desktop Version** (`app.py`): Native Windows UI using CustomTkinter.
- **Premium UI**: Modern dark-mode interface with glassmorphism effects, rhythmic animations, and responsive design.
- **Real-time Logging**: Uses Server-Sent Events (SSE) to stream deployment logs directly to your browser.
- **Service Scanning**: Automatically detects services in your workspace containing `deploy-dev.sh` or `deploy-stg.sh`.
- **SSH Tunnel Support**: Connect to remote MySQL databases securely via SSH tunnels (built into both Go and Python versions).
- **Deployment History**: Tracks every deployment action in MySQL with branch info, user names, and commit messages.

## 📋 Prerequisites

- **Go 1.22+** (For Go version)
- **Python 3.8+** (For Python/Desktop version)
- **MySQL Server** (Remote or Local)
- **Git Bash** (Required for Windows users to execute `.sh` scripts)

## 🚀 Getting Started

### 1. Configure Environment
Create a `.env` file from `.env.example`:
```env
# APP_ENV: 'local' (enables SSH tunnel) or 'server'
APP_ENV=local

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DB=deploy_logs

# SSH Tunnel Configuration
USE_SSH=true
SSH_HOST=your_server_ip
SSH_PORT=22
SSH_USER=ubuntu
SSH_KEY_PATH=C:/Users/YourUser/.ssh/id_rsa
```

### 2. Run the Application

#### Option A: Go Web Version (Recommended)
Fast, lightweight, and requires no external framework dependencies.
```powershell
.\scripts\run_go.bat
```
Visit `http://localhost:5000`

#### Option B: Python Web Version
```powershell
.\scripts\run_web.bat
```
Visit `http://localhost:5000`

#### Option C: Desktop App (Python)
```powershell
python app.py
```

## ⚙️ Configuration Details

- **Workspace Directory**: Set this in the Web UI **Settings**. This is the root folder containing your services.
- **Pre-deploy Command**: Configure a command (like `go mod tidy` or `npm install`) to run before the main deployment script.
- **SSH Protocol**: Built-in support for both SSH Password and Private Key authentication.

## 🖥️ Running as a Windows Service (NSSM)

To ensure the Deployment Tool runs in the background and starts automatically with Windows, you can use **NSSM**:

1. **Build the executable**:
   ```powershell
   go build -o app.exe main.go
   ```
2. **Download NSSM**: Get it from [nssm.cc](https://nssm.cc/download).
3. **Install the Service**:
   Open PowerShell/CMD as **Administrator** and run:
   ```powershell
   path\to\nssm.exe install IDS-Commander
   ```
4. **Configure in GUI**:
   - **Path**: Select your built `app.exe`.
   - **Startup directory**: Your project root folder.
   - **Details Tab**: Set the Display Name (e.g., `IDS Deploy Tool`).
5. **Manage Service**:
   - **Start**: `nssm start IDS-Commander`
   - **Edit**: `nssm edit IDS-Commander`
   - **Remove**: `nssm remove IDS-Commander`

## 📄 License

This project is licensed under the MIT License.
