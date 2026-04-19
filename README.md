# 🚀 Service Deploy Commander

A desktop tool built with Python and CustomTkinter to automate service deployments using shell scripts.

## 📁 Project Structure

```text
deploy-tool/
├── app.py              # Desktop application (CustomTkinter)
├── web.py              # Web application backend (Flask)
├── IDS.exe             # Final executable (after build)
├── scripts/            # Automation scripts
│   ├── build.bat/sh    # Build scripts for Windows/Unix
│   └── run_web.bat/sh  # Launch scripts for the web version
├── templates/
│   └── index.html      # Web frontend
├── app.ico             # Application icon
├── deploy.spec         # PyInstaller configuration
├── .env.example        # Environment variables template
├── requirements.txt    # Python dependencies
└── README.md           # Documentation
```

## 🛠 Features

- **Dual UI**: Use the **Desktop App** (`app.py`) for a native experience or the **Web Dashboard** (`web.py`) for a modern browser interface.
- **Service Scanning**: Automatically detects services in a specified workspace directory.
- **Git Integration**: Detects the current branch of the selected service.
- **Environment Support**: Supports "Development" and "Staging" deployment environments.
- **Deployment Logs**: Automatically saves deployment history to a MySQL database.
- **SSH Tunnel Support**: Securely connect to your MySQL database via SSH using environment variables.
- **Customizable**: Configure your workspace directory and Git Bash path directly from the UI.
- **Secure**: All sensitive credentials (DB & SSH) are managed via environment variables (`.env`).

## 📋 Prerequisites

- Python 3.8+
- MySQL Server
- Git Bash (for Windows users)

## 🚀 Getting Started

1. **Clone the repository**:
   ```bash
   git clone https://github.com/thangtranitwork/internal-deploy-system
   cd internal-deploy-system
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file from `.env.example` and fill in your credentials:
   ```env
   # APP_ENV: 'local' (uses SSH if enabled) or 'server' (direct connect)
   APP_ENV=local

   MYSQL_HOST=localhost
   MYSQL_PORT=3306
   MYSQL_USER=your_user
   MYSQL_PASSWORD=your_password
   MYSQL_DB=deploy_logs

   # Optional SSH Tunnel (Checked if APP_ENV=local)
   USE_SSH=true
   SSH_HOST=your_ssh_ip
   SSH_PORT=22
   SSH_USER=ubuntu
   # IMPORTANT: Use Private Key (no extension or .pem), NOT .pub
   SSH_KEY_PATH=C:\path\to\your\id_rsa
   # SSH_PASSWORD=your_ssh_password (if no key)
   ```

4. **Run the Application**:
   - **📱 Desktop Interface**: Run `python app.py` for a native Windows experience.
   - **🌐 Web Dashboard**: Run `python web.py` (hoặc chạy `./scripts/run_web.sh` / `scripts\run_web.bat`) sau đó truy cập `http://localhost:5000`.

## 🏗 Building Executable

To build a standalone `.exe` for Windows:

1. **Run the build script**:
   - **Windows**: `scripts\build.bat`
   - **Linux/macOS**: `chmod +x scripts/build.sh && ./scripts/build.sh`

2. **Output**:
   The final executable (`IDS.exe`) will be generated at the root directory.

## ⚙️ Configuration Details

- **Workspace Directory**: Set this in **Settings (Ctrl+K O)**. This is the root directory where your microsystems are located.
- **SSH Tunneling**: Managed exclusively via the `.env` file for maximum security. It will not be visible or stored in the UI.

## ⚠️ Troubleshooting

### 1. MySQL Error: Authentication failed / No such file
- Check your `SSH_KEY_PATH`. Ensure it points to your **Private Key**, not the `.pub` file.
- Verify your `SSH_PORT` if your server uses a non-standard port.

### 2. Error: REMOTE HOST IDENTIFICATION HAS CHANGED!
This happens when the server's fingerprint changes. Run the following command in your terminal:
```bash
# If using standard port 22
ssh-keygen -R your_server_ip

# If using a custom port (e.g., 2222)
ssh-keygen -R "[your_server_ip]:2222"
```

### 3. [MySQL] Error: ...
If you see a detailed error in the logs, read it carefully as it usually contains the exact reason for the connection failure (e.g., incorrect database password or host unreachable).

## 📄 License

This project is licensed under the MIT License.
