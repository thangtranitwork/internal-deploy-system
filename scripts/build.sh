#!/bin/bash

# Navigate to the project root directory
cd "$(dirname "$0")/.."

echo "========================================"
echo " Building Service Deploy Commander"
echo "========================================"

# Remove old build artifacts
echo "[1/3] Cleaning old builds..."
rm -rf build dist

# Install/Update dependencies
echo "[2/3] Checking dependencies..."
pip install pyinstaller customtkinter pymysql python-dotenv Pillow --quiet --upgrade

# Build using the spec file
echo "[3/3] Building executable..."
pyinstaller --clean --distpath . deploy.spec

echo ""
echo "========================================"
echo " SUCCESS: IDS.exe (Located in root)"
echo "========================================"
