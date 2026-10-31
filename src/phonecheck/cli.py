"""Command-line entry point: `phonecheck`."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import List, Optional

from rich.console import Console

from . import __version__, jsonout, render, scanner, tools
from .models import OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="phonecheck",
        description="Plug in an iPhone or Android phone and get its battery health and device stats.",
    )
    p.add_argument("--json", action="store_true", help="print machine-readable JSON instead of the UI")
    p.add_argument("--reveal", action="store_true", help="show serials, IMEI, MAC addresses and phone numbers unmasked")
    p.add_argument("--watch", nargs="?", const=5, type=float, metavar="SECONDS", help="refresh continuously (default every 5s)")
    p.add_argument("--no-wait", action="store_true", help="do not wait for the Trust / Allow prompt on the phone")
    p.add_argument("--doctor", action="store_true", help="check that the required tools are installed")
    p.add_argument("--version", action="version", version=f"phonecheck {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()

    if args.doctor:
        return 0 if render.render_doctor(console, tools.status()) else 1

    if args.json:
        result = scanner.scan(wait_for_prompts=not args.no_wait)
        print(json.dumps(jsonout.to_dict(result, args.reveal), indent=2, ensure_ascii=False))
        return 0 if any(d.state == OK for d in result.devices) else 1

    if args.watch is not None:
        return _watch(console, args)

    with console.status("Scanning for phones…", spinner="dots") as status:
        result = scanner.scan(on_status=status.update, wait_for_prompts=not args.no_wait)
    render.render_scan(console, result, args.reveal)
    return 0 if any(d.state == OK for d in result.devices) else 1


def _watch(console: Console, args: argparse.Namespace) -> int:
    interval = max(args.watch, 2.0)
    try:
        while True:
            result = scanner.scan(wait_for_prompts=False)
            console.clear()
            render.render_scan(console, result, args.reveal)
            console.print(f"[dim]Refreshing every {interval:g}s. Press Ctrl-C to stop.[/dim]")
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
