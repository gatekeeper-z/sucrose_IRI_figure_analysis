#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT_DIR"

echo
echo "============================================================"
echo " IRI Analyzer - Linux environment setup"
echo "============================================================"
echo

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "This setup needs root privileges to install Python/Node packages."
    echo "Please run it as root or install sudo."
    exit 1
  fi
}

python_ok() {
  command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

node_ok() {
  command -v node >/dev/null 2>&1 && node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)' >/dev/null 2>&1
}

npm_ok() {
  command -v npm >/dev/null 2>&1
}

install_system_packages() {
  echo "Installing system packages for Python, Node.js, npm, and build basics..."
  if command -v apt-get >/dev/null 2>&1; then
    run_as_root apt-get update
    run_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y \
      ca-certificates git python3 python3-venv python3-pip nodejs npm
  elif command -v apk >/dev/null 2>&1; then
    run_as_root apk add --no-cache \
      ca-certificates git python3 py3-pip py3-virtualenv nodejs npm
  elif command -v dnf >/dev/null 2>&1; then
    run_as_root dnf install -y \
      ca-certificates git python3 python3-pip nodejs npm
  elif command -v yum >/dev/null 2>&1; then
    run_as_root yum install -y \
      ca-certificates git python3 python3-pip nodejs npm
  elif command -v zypper >/dev/null 2>&1; then
    run_as_root zypper --non-interactive install \
      ca-certificates git python3 python3-pip nodejs npm
  elif command -v pacman >/dev/null 2>&1; then
    run_as_root pacman -Sy --noconfirm \
      ca-certificates git python python-pip nodejs npm
  else
    echo "Unsupported Linux distribution: no apt-get/apk/dnf/yum/zypper/pacman found."
    exit 1
  fi
}

if ! python_ok || ! node_ok || ! npm_ok; then
  install_system_packages
fi

if ! python_ok; then
  echo "Python 3.10+ is still unavailable after package installation."
  exit 1
fi

if ! node_ok; then
  echo "Node.js 18+ is still unavailable after package installation."
  echo "Please install Node.js 18 or newer, then rerun this script."
  exit 1
fi

if ! npm_ok; then
  echo "npm is still unavailable after package installation."
  exit 1
fi

echo "Python: $(python3 --version)"
echo "Node: $(node --version)"
echo "npm: $(npm --version)"

if [ ! -x ".venv/bin/python" ]; then
  echo
  echo "Creating local Python virtual environment: .venv"
  python3 -m venv .venv
else
  echo "Python virtual environment already exists: .venv"
fi

VENV_PY="$ROOT_DIR/.venv/bin/python"

echo
echo "Checking Python dependencies..."
if ! "$VENV_PY" -c 'import iri_analyzer, fastapi, uvicorn, cv2, numpy, pandas, yaml, matplotlib' >/dev/null 2>&1; then
  echo "Installing Python package and dependencies..."
  "$VENV_PY" -m pip install -e .
  "$VENV_PY" -m pip install pytest httpx
else
  echo "Python dependencies are available."
fi

if [ ! -f "web/package.json" ]; then
  echo "Frontend project was not found: web/package.json"
  exit 1
fi

echo
echo "Checking frontend dependencies..."
cd web
if [ ! -d "node_modules" ]; then
  if [ -f "package-lock.json" ]; then
    echo "Installing frontend dependencies with npm ci..."
    npm ci || {
      echo "npm ci failed; trying npm install..."
      npm install
    }
  else
    echo "Installing frontend dependencies with npm install..."
    npm install
  fi
else
  echo "Frontend dependencies already exist: web/node_modules"
fi

echo
echo "Building frontend..."
npm run build
cd "$ROOT_DIR"

echo
echo "Running quick verification tests..."
"$VENV_PY" -m pip install pytest httpx
"$VENV_PY" -m pytest -q

echo
echo "============================================================"
echo " Setup complete."
echo " Start the Web UI with: python -m iri_analyzer.web"
echo "============================================================"
