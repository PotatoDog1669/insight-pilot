#!/usr/bin/env bash
set -euo pipefail

# Bootstrap Insight-Pilot Python environment.
#
# Default behavior:
# - Reuse ~/.insight-pilot-venv if it exists
# - Otherwise create it
# - Ensure insight-pilot + key deps are installed
#
# Usage:
#   bash .claude/skills/insight-pilot/scripts/bootstrap_env.sh
#   bash .claude/skills/insight-pilot/scripts/bootstrap_env.sh --upgrade
#   bash .claude/skills/insight-pilot/scripts/bootstrap_env.sh --check-only
#   bash .claude/skills/insight-pilot/scripts/bootstrap_env.sh --editable /path/to/insight-pilot
#
# Env vars:
#   INSIGHT_PILOT_VENV=~/.insight-pilot-venv
#   INSIGHT_PILOT_PYTHON=python3
#   INSIGHT_PILOT_GIT_URL=git+https://github.com/PotatoDog1669/insight-pilot.git

VENV_DIR="${INSIGHT_PILOT_VENV:-$HOME/.insight-pilot-venv}"
PYTHON_BIN="${INSIGHT_PILOT_PYTHON:-python3}"
GIT_URL="${INSIGHT_PILOT_GIT_URL:-git+https://github.com/PotatoDog1669/insight-pilot.git}"

UPGRADE=0
CHECK_ONLY=0
EDITABLE_PATH=""

usage() {
  cat <<EOF
Usage: bootstrap_env.sh [--upgrade] [--check-only] [--editable PATH]

Options:
  --upgrade        Upgrade insight-pilot to latest (pip -U)
  --check-only     Only check environment; do not install
  --editable PATH  Install insight-pilot from local PATH (pip install -e)
  -h, --help       Show help

Environment:
  INSIGHT_PILOT_VENV      Venv dir (default: ~/.insight-pilot-venv)
  INSIGHT_PILOT_PYTHON    Python executable (default: python3)
  INSIGHT_PILOT_GIT_URL   Git URL (default: git+https://github.com/PotatoDog1669/insight-pilot.git)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --upgrade)
      UPGRADE=1
      shift
      ;;
    --check-only)
      CHECK_ONLY=1
      shift
      ;;
    --editable)
      EDITABLE_PATH="${2:-}"
      if [[ -z "$EDITABLE_PATH" ]]; then
        echo "ERROR: --editable requires a PATH" >&2
        exit 2
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() {
  printf "%s\n" "$*"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"
}

need_cmd "$PYTHON_BIN"

activate_venv() {
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
}

create_venv_if_missing() {
  if [[ ! -d "$VENV_DIR" ]]; then
    if [[ $CHECK_ONLY -eq 1 ]]; then
      fail "venv missing at $VENV_DIR (run without --check-only to create it)"
    fi
    log "[bootstrap] Creating venv: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi
}

check_python_health() {
  python -m pip --version >/dev/null 2>&1 || return 1
  python -m pip show insight-pilot >/dev/null 2>&1 || return 1
  python -c "import insight_pilot" >/dev/null 2>&1 || return 1
  python -c "import pymupdf4llm" >/dev/null 2>&1 || return 1
  return 0
}

install_or_upgrade() {
  if [[ $CHECK_ONLY -eq 1 ]]; then
    fail "Environment not ready (run without --check-only to install)"
  fi

  log "[bootstrap] Ensuring pip is recent"
  python -m pip install -U pip >/dev/null

  if [[ -n "$EDITABLE_PATH" ]]; then
    if [[ ! -e "$EDITABLE_PATH" ]]; then
      fail "Editable path not found: $EDITABLE_PATH"
    fi
    log "[bootstrap] Installing editable: $EDITABLE_PATH"
    python -m pip install -e "$EDITABLE_PATH"
    return 0
  fi

  if [[ $UPGRADE -eq 1 ]]; then
    log "[bootstrap] Upgrading from: $GIT_URL"
    python -m pip install -U "$GIT_URL"
  else
    log "[bootstrap] Installing (if needed) from: $GIT_URL"
    python -m pip install "$GIT_URL"
  fi
}

main() {
  create_venv_if_missing
  log "[bootstrap] Activating venv"
  activate_venv

  if check_python_health; then
    log "[bootstrap] OK: environment ready"
    log "[bootstrap] Next: source $VENV_DIR/bin/activate && insight-pilot --help"
    exit 0
  fi

  log "[bootstrap] Environment not ready; installing/upgrading..."
  install_or_upgrade

  if check_python_health; then
    log "[bootstrap] OK: environment ready"
    log "[bootstrap] Next: source $VENV_DIR/bin/activate && insight-pilot --help"
    exit 0
  fi

  fail "Environment still unhealthy after install; check pip output above"
}

main "$@"
