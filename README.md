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
- **Dynamic Refresh**: 
    - **Global Refresh**: Refresh the entire service list from the header.
    - **Contextual Refresh**: Automatically fetches the latest Git information (branch, last commit) when selecting a service.
    - **Manual Service Refresh**: Dedicated button within the service card for targeted updates without reloading the entire list.
- **Persistent DB/SSH Connection**: Optimized connection management with built-in auto-reconnect and SSH tunnel pooling (available in Go and Python).
- **Service-Ready**: Enhanced compatibility for running as a Windows Service (NSSM), including automatic path detection and Git ownership fix (`safe.directory`).
- **Auto Timezone Adjustment**: Automatically displays history in local timezone (GMT+7).
- **Deployment History**: Tracks every deployment action in MySQL with branch info, user names, and commit messages.

## 📋 Prerequisites

- **Go 1.22+** (For Go version)
- **Python 3.8+** (For Python/Desktop version)
- **MySQL Server** (Remote or Local)
- **Git Bash** (Required for Windows users to execute `.sh` scripts)
- **Ubuntu/Linux Support**: Fully supported natively. The tool will automatically use system `bash` and `git` without requiring any extra configuration.

## 🚀 Getting Started

### 1. Configure Environment
Create a `.env` file from `.env.example`. 
> [!TIP]
> Use absolute paths for `SSH_KEY_PATH` to ensure reliability when running as a service.

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

#### Option C: Desktop App (Python)
```powershell
python app.py
```

## ⚙️ Configuration Details

- **Workspace Directory**: Set this in the Web UI **Settings**. This is the root folder containing your services.
- **Pre-deploy Command**: Configure a command (like `go mod tidy` or `npm install`) to run before the main deployment script.
- **Git Ownership**: The tool automatically uses `-c safe.directory=*` for Git commands to prevent environment-related permission issues.

## 🖥️ Running as a Windows Service (NSSM)

To ensure the Tool runs in the background and starts automatically, you can use **NSSM**:

1. **Build the executable**:
   ```powershell
   go build -o IDS.exe main.go
   ```
2. **Install the Service**:
   Open PowerShell as **Administrator**:
   ```powershell
   nssm install IDS-Commander
   ```
3. **Configure correctly**:
   - **Path**: Path to `IDS.exe`.
   - **Startup directory**: Your project root folder.
   - **Log on Tab (IMPORTANT)**: Choose **"This account"** and enter your Windows credentials. This solves 90% of Git/SSH environment issues when running as a service.

## 📄 License

This project is licensed under the MIT License.
