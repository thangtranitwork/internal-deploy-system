#!/bin/bash

# Navigate to the project root directory
cd "$(dirname "$0")/.."

echo "========================================"
echo " Starting Service Deploy Commander (WEB)"
echo "========================================"

# Install dependencies
echo "[1/2] Checking dependencies..."
pip install Flask flask-cors pymysql python-dotenv --quiet --upgrade

# Start the server
echo "[2/2] Launching server at http://localhost:5000"
echo "Ctrl+C to stop."
python3 web.py || python web.py
