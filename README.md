# 🚀 Service Deploy Commander

A desktop tool built with Python and CustomTkinter to automate service deployments using shell scripts.

## 📁 Project Structure

```text
deploy-tool/
├── app.py              # Main application logic
├── app.ico             # Application icon
├── deploy.spec         # PyInstaller configuration
├── build.bat           # Build script for Windows
├── .env.example        # Environment variables template
├── requirements.txt    # Python dependencies
└── README.md           # Documentation
```

## 🛠 Features

- **Service Scanning**: Automatically detects services in a specified workspace directory.
- **Git Integration**: Detects the current branch of the selected service.
- **Environment Support**: Supports "Development" and "Staging" deployment environments.
- **Deployment Logs**: Automatically saves deployment history to a MySQL database.
- **Customizable**: Configure your workspace directory and Git Bash path directly from the UI.
- **Secure**: Credentials are managed via environment variables (`.env`).

## 📋 Prerequisites

- Python 3.8+
- MySQL Server
- Git Bash (for Windows users)

## 🚀 Getting Started

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd deploy-tool
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file from `.env.example` and fill in your MySQL credentials:
   ```env
   MYSQL_HOST=localhost
   MYSQL_USER=your_user
   MYSQL_PASSWORD=your_password
   MYSQL_DB=deploy_logs
   ```

4. **Run the Application**:
   ```bash
   python app.py
   ```

## 🏗 Building Executable

To build a standalone `.exe` for Windows, we use `PyInstaller`.

1. **Prerequisites for building**:
   - Install build dependencies: `pip install pyinstaller Pillow`
   - Ensure `app.ico` is in the root directory.

2. **Run the build script**:
   ```batch
   build.bat
   ```
   *This script cleans old builds, updates dependencies, and runs PyInstaller with the `deploy.spec` configuration.*

3. **Output**:
   The final executable will be generated at `dist\DeployCommander.exe`.

---

## 📦 Distribution (Sharing with others)

If you want to send this tool to another developer, you only need to send them the `.exe` file. However, they will need to set up a few things on their machine for it to work:

### 1. Requirements for Use
- **Git Bash**: Must be installed on their Windows machine (standard for developers).
- **MySQL Access**: They must have access to the database where logs are recorded.

### 2. Setup on their machine
Since the `.exe` is standalone, they should:
1. Place `DeployCommander.exe` in a dedicated folder.
2. Create a `.env` file in that **same folder** with the following content:
   ```env
   MYSQL_HOST=your_db_host
   MYSQL_USER=your_user
   MYSQL_PASSWORD=your_password
   MYSQL_DB=deploy_logs
   ```
3. Run the `.exe`.
4. On first run, click **Settings (Ctrl+K O)** to configure:
   - **Workspace Directory**: Where their microservices are located.
   - **Your Name**: Their identifier for logs.
   - **Git Bash Path**: Usually `C:\Program Files\Git\bin\bash.exe`.

## ⚙️ Configuration Details

- **Workspace Directory**: The root directory where your services are located. The app scans subdirectories for `deploy-dev.sh` (or `scripts/deploy-dev.sh`).
- **Pre-deploy Command**: A command that runs automatically *before* the shell script (e.g., `go mod tidy` or `npm install`).
- **Settings Storage**: The app saves your preferences in a `settings.json` file created in the same directory as the app.

## 📄 License

This project is licensed under the MIT License.
