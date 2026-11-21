#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Gl1ch5/rw-agent.git"
CYAN='\033[1;36m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
DIM='\033[2m'
RED='\033[1;31m'
RESET='\033[0m'

step() {
  local pct="$1"
  local msg="$2"
  local filled=$((pct / 5))
  local empty=$((20 - filled))
  local bar
  bar=$(printf "%${filled}s" | tr ' ' '█')$(printf "%${empty}s" | tr ' ' '░')
  printf "\r${CYAN}[%s] %3d%%${RESET} %s\n" "$bar" "$pct" "$msg"
}

echo ""
printf "${CYAN}  >_ rw-agent${RESET} ${DIM}— ultra-minimal read/write AI agent${RESET}\n"
printf "${DIM}  ──────────────────────────────────────────────${RESET}\n"

OS="$(uname -s)"
ARCH="$(uname -m)"
IS_TERMUX=0
if [ -n "${TERMUX_VERSION:-}" ] || [ "$(uname -o 2>/dev/null || true)" = "Android" ] || [ -d "/data/data/com.termux/files/usr" ]; then
  IS_TERMUX=1
fi

if [ "$IS_TERMUX" -eq 1 ]; then
  step 15 "Detected Termux / Android (${ARCH})"
  if ! command -v python3 >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
    step 35 "Installing python & git via pkg..."
    pkg update -y >/dev/null 2>&1 || true
    pkg install -y python git >/dev/null 2>&1
  fi

  step 65 "Installing rw-agent into Termux venv..."
  VENV_DIR="$HOME/.local/share/rw-agent/venv"
  BIN_DIR="${PREFIX:-$HOME/.local}/bin"
  mkdir -p "$BIN_DIR"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --quiet --upgrade pip
  "$VENV_DIR/bin/pip" install --quiet --upgrade "git+${REPO_URL}"
  ln -sf "$VENV_DIR/bin/rw" "$BIN_DIR/rw"
else
  step 15 "Detected ${OS} (${ARCH})"

  # Ensure uv or python3 is available
  if ! command -v uv >/dev/null 2>&1; then
    step 35 "Installing uv package manager..."
    if command -v curl >/dev/null 2>&1; then
      curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
    else
      printf "${RED}✗ curl or wget is required.${RESET}\n"
      exit 1
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  fi

  if command -v uv >/dev/null 2>&1; then
    step 65 "Installing rw-agent via uv..."
    uv tool install --force "git+${REPO_URL}" >/dev/null 2>&1 || uv tool install --force "git+${REPO_URL}"
  elif command -v python3 >/dev/null 2>&1; then
    step 65 "Installing rw-agent into ~/.local/share/rw-agent..."
    VENV_DIR="$HOME/.local/share/rw-agent/venv"
    mkdir -p "$HOME/.local/bin"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet --upgrade "git+${REPO_URL}"
    ln -sf "$VENV_DIR/bin/rw" "$HOME/.local/bin/rw"
  else
    printf "${RED}✗ Neither uv nor python3 found.${RESET}\n"
    exit 1
  fi
fi

step 100 "Installation complete!"
echo ""
printf "${GREEN}✓ rw is ready.${RESET}\n"

if ! command -v rw >/dev/null 2>&1; then
  printf "${YELLOW}Note:${RESET} Add ${CYAN}\$HOME/.local/bin${RESET} to your PATH:\n"
  printf "  ${DIM}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}\n"
fi

printf "\nRun ${CYAN}rw${RESET} to connect your custom provider and start.\n\n"
