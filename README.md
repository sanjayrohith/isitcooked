# IsItCooked

**Is your phone's battery cooked?** Plug in an iPhone or Android phone, run one command, and get a clean report in your terminal: battery health, cycle count, capacity, charging state, storage, and basic device info.

```sh
isitcooked
```

## Why this exists

Buying a used phone? Wondering if it's time to replace yours? Battery health is the number that matters most, but it's buried in settings, missing on many Android phones, or only shown inside closed apps.

IsItCooked reads the battery data straight from the phone over USB and works out the health itself. It is:

- **Simple**: one command, one readable report.
- **Honest**: health is calculated from raw capacity numbers (`max capacity ÷ design capacity`). It never trusts a health figure reported by the OS. If a phone doesn't expose a value, the report leaves it out instead of guessing.
- **Private**: everything runs on your computer. See [Privacy](#privacy).
- **Cross-platform**: iPhone, iPad and Android, from macOS or Linux.

## Quick start

You need Python 3.9 or newer and a USB cable that carries data (not a charge-only one).

```sh
curl -fsSL https://raw.githubusercontent.com/sanjayrohith/isitcooked/main/install.sh | sh
```

Or clone it and install from the checkout:

```sh
git clone https://github.com/sanjayrohith/isitcooked.git
cd isitcooked
./install.sh
```

Then plug in your phone and run:

```sh
isitcooked
```

The installer does two things:

1. Installs the phone tools if they're missing: `libimobiledevice` for iPhone and `adb` for Android. It uses Homebrew on macOS, and apt, dnf or pacman on Linux.
2. Installs the `isitcooked` command with `pipx` if you have it. Otherwise it uses a private virtual environment at `~/.isitcooked/venv` and links the command into `~/.local/bin`.

Make sure `~/.local/bin` is on your `PATH`. To skip the phone tools and install only the command, run with `ISITCOOKED_SKIP_SYSTEM=1`.

## Connecting your phone

- **iPhone / iPad**: unlock it and tap **Trust This Computer**. IsItCooked triggers the prompt and waits up to 45 seconds for you to accept.
- **Android**: turn on **Settings → Developer options → USB debugging**, then tap **Allow** on the prompt.

Not sure everything is set up? Run `isitcooked --doctor`.

## Usage

| Command                | What it does                                                |
| ---------------------- | ----------------------------------------------------------- |
| `isitcooked`           | Scan every connected phone and show the report              |
| `isitcooked --json`    | Same data as JSON, for scripts and bug reports              |
| `isitcooked --watch`   | Live view that refreshes every 5 seconds (`--watch 2` for 2s) |
| `isitcooked --reveal`  | Show serial, IMEI, MAC addresses and phone number unmasked  |
| `isitcooked --doctor`  | Check which required tools are installed                    |
| `isitcooked --no-wait` | Don't wait for the Trust / Allow prompt on the phone        |

The exit code is `0` if at least one phone was read, and `1` otherwise.

## What it reads

| | iPhone / iPad | Android |
| --- | --- | --- |
| Battery | cycle count, design and max capacity, health %, charge, voltage, current, charger, temperature | cycle count, capacity and health % (when exposed), charge, voltage, temperature, charger, OS-reported health |
| Device | name, model, board, CPU, serial, UDID | name, manufacturer, model, SoC, serial |
| Software | OS version, build, activation, passcode set | Android version, security patch, build |
| Storage | disk size, used, available | data partition, used, available, RAM |
| Network | Wi-Fi/Bluetooth address, IMEI, SIM status | carrier, network type, SIM state |

Many Android phones don't expose cycle count or capacity over `adb`, especially older ones or locked-down vendor builds. When that happens the report says so.

### Reading the result

| Health      | Condition           |
| ----------- | ------------------- |
| 90% or more | Excellent           |
| 80 – 90%    | Good                |
| 60 – 80%    | Fair                |
| Below 60%   | Service recommended |

The cycle bar compares against Apple's rated cycle life: 500 for iPhone 14 and earlier, 1000 for iPhone 15 and later.

## Privacy

Your phone's data is yours. Here is exactly what IsItCooked does and doesn't do:

- **Nothing leaves your computer.** IsItCooked makes no network calls, has no analytics or telemetry, and has no accounts.
- **It only reads.** It doesn't change anything on your phone, and it writes no files of its own.
- **Identifiers are masked by default.** Serial numbers, UDID, IMEI, MAC addresses, ICCID and phone numbers are hidden in both the terminal and the `--json` output (for example `00••••••-•••••••••••••01E`), so you can paste a report into a forum post or bug report safely. Use `--reveal` only when you need the real values.
- **No data is stored.** When you close the terminal, the report is gone.

Two things to know:

- The standard phone tools keep their own pairing data on your computer. Tapping **Trust** on an iPhone creates a pairing record, and Android's **Allow** stores an `adb` key in `~/.android/`. This is how Apple's and Google's tools work, and IsItCooked doesn't add to it. You can revoke them on the phone (see [Uninstall](#uninstall)).
- Only the installer uses the network, to download the phone tools and the package. The `isitcooked` command itself never does.

The code is short and open. Feel free to read it.

## Set up locally

To run or change the code from a checkout:

```sh
git clone https://github.com/sanjayrohith/isitcooked.git
cd isitcooked
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/isitcooked --doctor     # check phone tools
.venv/bin/pytest                  # run tests
```

You still need `libimobiledevice` and/or `adb`. Running `./install.sh` installs them, or install them yourself with your package manager.

Code layout (`src/isitcooked/`):

| File                          | Purpose                                        |
| ----------------------------- | ---------------------------------------------- |
| `ios.py`, `android.py`        | Read each platform and parse the output        |
| `scanner.py`                  | Finds and reads every connected device         |
| `render.py`, `jsonout.py`     | Terminal UI and JSON output                    |
| `redact.py`                   | Masks personal identifiers                     |
| `cli.py`                      | Command-line entry point                       |

## Uninstall

Remove the command:

```sh
pipx uninstall isitcooked                          # if installed with pipx
rm -rf ~/.isitcooked ~/.local/bin/isitcooked       # if installed by install.sh without pipx
```

Remove the local dev setup: delete the `.venv` folder inside your checkout (`rm -rf .venv`).

Optionally, remove the phone tools if nothing else uses them:

```sh
brew uninstall libimobiledevice && brew uninstall --cask android-platform-tools   # macOS
```

To revoke computer access on the phone:

- **iPhone**: Settings → General → Transfer or Reset iPhone → Reset → **Reset Location & Privacy**.
- **Android**: Developer options → **Revoke USB debugging authorizations**, and turn USB debugging off.

## License

MIT
