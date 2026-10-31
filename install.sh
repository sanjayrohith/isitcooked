#!/bin/sh
#
# phonecheck installer: one command installs the CLI plus the phone tools it needs.
#
#   ./install.sh                                  (from a checkout)
#   curl -fsSL <raw-url-of-this-file> | sh        (from anywhere)
#
# Environment:
#   PHONECHECK_SKIP_SYSTEM=1   skip installing libimobiledevice / adb (just install the CLI)
#   PHONECHECK_SOURCE=<path|pip-spec>   override what gets installed
#
set -eu

REMOTE_SPEC="git+https://github.com/rnihesh/capax.git#subdirectory=phonecheck"
BIN_DIR="${HOME}/.local/bin"
VENV_DIR="${HOME}/.phonecheck/venv"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$1" >&2; }
die()  { printf '\033[1;31mxx\033[0m  %s\n' "$1" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------- phone tools
install_system_tools() {
  need_ios=1; need_adb=1
  have ideviceinfo && have idevicediagnostics && need_ios=0
  have adb && need_adb=0
  [ "$need_ios" = 0 ] && [ "$need_adb" = 0 ] && { say "libimobiledevice and adb already installed"; return; }

  case "$(uname -s)" in
    Darwin)
      have brew || { warn "Homebrew not found. Install it from https://brew.sh, then re-run this script."; return; }
      [ "$need_ios" = 1 ] && { say "Installing libimobiledevice (iPhone support)"; brew install libimobiledevice; }
      [ "$need_adb" = 1 ] && { say "Installing Android platform-tools (Android support)"; brew install --cask android-platform-tools; }
      ;;
    Linux)
      SUDO=""; [ "$(id -u)" -ne 0 ] && have sudo && SUDO="sudo"
      if have apt-get; then
        say "Installing phone tools with apt"
        $SUDO apt-get update -qq
        $SUDO apt-get install -y libimobiledevice-utils usbmuxd adb
      elif have dnf; then
        say "Installing phone tools with dnf"
        $SUDO dnf install -y libimobiledevice-utils usbmuxd android-tools
      elif have pacman; then
        say "Installing phone tools with pacman"
        $SUDO pacman -S --needed --noconfirm libimobiledevice usbmuxd android-tools
      else
        warn "Unknown package manager. Install libimobiledevice and adb manually."
      fi
      ;;
    *)
      warn "Unsupported OS for automatic tool install. Install libimobiledevice and adb manually."
      ;;
  esac
}

# ---------------------------------------------------------------- the CLI itself
pick_source() {
  if [ -n "${PHONECHECK_SOURCE:-}" ]; then printf '%s' "$PHONECHECK_SOURCE"; return; fi
  dir="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
  if [ -n "$dir" ] && [ -f "$dir/pyproject.toml" ]; then printf '%s' "$dir"; else printf '%s' "$REMOTE_SPEC"; fi
}

install_cli() {
  have python3 || die "python3 is required (3.9 or newer)."
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || die "Python 3.9 or newer is required."
  SRC="$(pick_source)"
  case "$SRC" in git+*) have git || die "git is required to install from the repository." ;; esac

  if have pipx; then
    say "Installing phonecheck with pipx"
    pipx install --force "$SRC"
  else
    say "Installing phonecheck into ${VENV_DIR}"
    mkdir -p "$(dirname "$VENV_DIR")" "$BIN_DIR"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
    "$VENV_DIR/bin/python" -m pip install --quiet --upgrade "$SRC"
    ln -sf "$VENV_DIR/bin/phonecheck" "$BIN_DIR/phonecheck"
  fi

  case ":${PATH}:" in
    *":${BIN_DIR}:"*) ;;
    *) warn "${BIN_DIR} is not on your PATH. Add this to your shell profile:  export PATH=\"${BIN_DIR}:\$PATH\"" ;;
  esac
}

[ "${PHONECHECK_SKIP_SYSTEM:-0}" = 1 ] || install_system_tools
install_cli
say "Done. Plug in your phone and run:  phonecheck"
