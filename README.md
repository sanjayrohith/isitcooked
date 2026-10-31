# IsItCooked

**Is your phone's battery cooked?** Plug in an iPhone or an Android phone, run one command, and
get a clean terminal report: battery health, cycle count, capacity, charging state, storage,
software and hardware details.

```
isitcooked
```

## Install (one command)

From this folder:

```sh
./install.sh
```

Once the repository is published, anyone can use (replace `YOUR_USERNAME` with the GitHub account
that hosts it):

```sh
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/isitcooked/main/install.sh | sh
```

The installer also needs `REMOTE_SPEC` in `install.sh` pointed at the same repository for the
curl route to work.

The installer:

1. Installs the phone tools if they are missing: `libimobiledevice` (iPhone) and Android
   `platform-tools` / `adb` (Android). It uses Homebrew on macOS, and apt, dnf or pacman on Linux.
2. Installs the `isitcooked` command with `pipx` if you have it, otherwise into a private venv at
   `~/.isitcooked/venv` with a symlink in `~/.local/bin`.

Needs Python 3.9 or newer. Make sure `~/.local/bin` is on your `PATH`.

Uninstall: `pipx uninstall isitcooked`, or `rm -rf ~/.isitcooked ~/.local/bin/isitcooked`.

## Use

| Command                  | What it does                                                   |
| ------------------------ | -------------------------------------------------------------- |
| `isitcooked`             | Scan every connected phone and show the report                 |
| `isitcooked --json`      | Same data as JSON (for scripts, bug reports, spreadsheets)     |
| `isitcooked --watch`     | Live view, refreshes every 5 seconds (`--watch 2` for 2s)      |
| `isitcooked --reveal`    | Show serial, IMEI, MAC addresses and phone number unmasked     |
| `isitcooked --doctor`    | Check which required tools are installed                       |
| `isitcooked --no-wait`   | Do not wait for the Trust / Allow prompt on the phone          |

Exit code is `0` when at least one phone was read, `1` otherwise.

### First connection

- **iPhone**: unlock it and tap **Trust This Computer**. IsItCooked triggers the prompt itself and
  waits up to 45 seconds for you to accept.
- **Android**: enable **Settings → Developer options → USB debugging**, then tap **Allow** on the
  prompt. Use a data-capable USB cable, not a charge-only one.

## What it reads

| | iPhone / iPad | Android |
| --- | --- | --- |
| Battery | cycle count, design and current max capacity, health %, charge, voltage, current, charger, temperature (when exposed) | cycle count, capacity and health % (when exposed), charge, voltage, temperature, charger, OS-reported health |
| Device | name, model, identifier, board, CPU, serial, UDID | name, manufacturer, model, codename, SoC, ABI, serial |
| Software | OS version, build, activation, passcode set, time zone | Android version, API level, security patch, build, baseband |
| Storage | disk size, user data capacity, used, available | data partition, used, available, RAM |
| Network | Wi-Fi/Bluetooth address, IMEI, phone number, SIM status, baseband | carrier, network type, SIM state |
| Other | | display resolution and density, uptime, verified boot, bootloader lock, encryption |

Fields a phone does not expose are left out rather than guessed.

## How battery health is computed

Health is `max capacity ÷ design capacity`, calculated from raw mAh values. IsItCooked never trusts
a health figure reported by the OS.

- **iPhone**: reads the battery IORegistry through the diagnostics service. Current iOS versions
  publish the maximum capacity as `NominalChargeCapacity` (the number Settings is based on). Older
  versions use `AppleRawMaxCapacity`. If neither exists, health shows as unavailable.
- **Android**: reads `dumpsys battery` plus `/sys/class/power_supply/*/` (`cycle_count`,
  `charge_full`, `charge_full_design`) and `dumpsys batterystats`. Many Android phones do not
  expose cycle count or capacity to `adb`, especially on older Android versions or locked-down
  vendor builds. In that case the report says so.

Condition bands: 90% and above Excellent, 80 to 90 Good, 60 to 80 Fair, below 60 Service
recommended. The cycle bar compares against Apple's rated cycle life (500 for iPhone 14 and
earlier, 1000 for iPhone 15 and later).

## Privacy

Everything stays on your computer. IsItCooked makes no network calls and writes no files. Serial
numbers, UDID, IMEI, MAC addresses, ICCID and phone numbers are masked in both the UI and the JSON
output unless you pass `--reveal`.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Layout: `src/isitcooked/ios.py` and `android.py` (readers and pure parsers), `render.py` (rich UI),
`jsonout.py`, `scanner.py` (finds and reads every device), `cli.py`.
