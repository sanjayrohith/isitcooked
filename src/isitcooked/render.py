"""Terminal UI built with `rich`."""

from __future__ import annotations

from typing import Any, List, Optional

from rich import box
from rich.columns import Columns
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .models import (
    CONDITION_LABELS,
    EXCELLENT,
    FAIR,
    GOOD,
    OK,
    SERVICE,
    Battery,
    DeviceReport,
    Row,
    ScanResult,
)
from .redact import mask

_CONDITION_STYLE = {
    EXCELLENT: "bold green",
    GOOD: "green",
    FAIR: "yellow",
    SERVICE: "bold red",
}


# --------------------------------------------------------------------------- formatting


def human_bytes(n: float) -> str:
    """Decimal units, matching what iOS and Android show in their storage screens."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000.0
    return f"{n:.1f} TB"


def human_duration(seconds: int) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_value(row: Row, reveal: bool) -> str:
    v: Any = row.value
    if row.sensitive and not reveal:
        return mask(str(v))
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if row.unit == "bytes" and isinstance(v, (int, float)):
        return human_bytes(v)
    if row.unit == "s" and isinstance(v, (int, float)):
        return human_duration(int(v))
    if row.unit and isinstance(v, (int, float)):
        return f"{v:,} {row.unit}"
    return str(v)


def bar(fraction: Optional[float], width: int = 18, style: str = "green") -> Text:
    if fraction is None:
        return Text("░" * width, style="dim")
    f = max(0.0, min(1.0, fraction))
    filled = round(f * width)
    t = Text()
    t.append("█" * filled, style=style)
    t.append("░" * (width - filled), style="grey35")
    return t


def _usage_style(fraction: float) -> str:
    return "green" if fraction < 0.6 else "yellow" if fraction < 0.9 else "red"


# --------------------------------------------------------------------------- battery


def battery_block(b: Battery, reveal: bool) -> RenderableType:
    gauges = Table.grid(padding=(0, 2))
    gauges.add_column(style="bold", no_wrap=True)
    gauges.add_column(no_wrap=True)
    gauges.add_column()

    # Health
    health = b.health_percent
    cond_style = _CONDITION_STYLE.get(b.condition, "dim")
    if health is not None:
        gauges.add_row(
            "Health",
            bar(health / 100, style=cond_style),
            Text.assemble((f"{health:.1f}%", cond_style), "  ", (CONDITION_LABELS[b.condition], cond_style)),
        )
    elif b.os_health:
        gauges.add_row("Health", bar(None), Text(f"{b.os_health} (capacity unavailable)", style="dim"))
    else:
        gauges.add_row("Health", bar(None), Text("unavailable", style="dim"))

    # Charge
    if b.charge_percent is not None:
        state = "⚡" if b.is_charging else "full" if b.fully_charged else ""
        gauges.add_row(
            "Charge",
            bar(b.charge_percent / 100, style=_usage_style(1 - b.charge_percent / 100)),
            Text(f"{b.charge_percent:.0f}% {state}".strip()),
        )

    # Cycles
    if b.cycle_count is not None:
        frac = b.cycle_fraction
        if frac is not None:
            label = Text.assemble(
                (f"{b.cycle_count:,}", "bold"),
                f" / {b.rated_cycles:,} rated",
                (" ⚠" if frac > 1.0 else "", "bold red"),
            )
            gauges.add_row("Cycles", bar(frac, style=_usage_style(frac)), label)
        else:
            gauges.add_row("Cycles", bar(None), Text.assemble((f"{b.cycle_count:,}", "bold")))
    else:
        gauges.add_row("Cycles", bar(None), Text("not exposed by this device", style="dim"))

    # Detail table
    detail = Table.grid(padding=(0, 2))
    detail.add_column(style="dim", no_wrap=True)
    detail.add_column()

    def add(label: str, value: Optional[str]) -> None:
        if value:
            detail.add_row(label, value)

    if b.design_mah:
        add("Design capacity", f"{b.design_mah:,} mAh")
    if b.full_charge_mah:
        add("Max capacity now", f"{b.full_charge_mah:,} mAh")
    if b.current_mah:
        add("Charge held", f"{b.current_mah:,} mAh")
    if b.temperature_c is not None:
        add("Temperature", f"{b.temperature_c:.1f} °C  ({b.temperature_c * 9 / 5 + 32:.1f} °F)")
    if b.voltage_mv:
        add("Voltage", f"{b.voltage_mv / 1000:.2f} V")
    if b.current_ma is not None:
        add("Current", f"{b.current_ma:+,} mA")
    if b.external_connected is not None:
        add("External power", "connected" if b.external_connected else "not connected")
    if b.adapter_watts:
        desc = f"  ({b.adapter_description})" if b.adapter_description else ""
        add("Charger", f"{b.adapter_watts:g} W{desc}")
    if b.time_to_empty_min:
        add("Time to empty", human_duration(b.time_to_empty_min * 60))
    add("Technology", b.technology)
    if b.os_health and b.health_percent is not None:
        add("OS-reported health", b.os_health)
    if b.serial:
        add("Battery serial", b.serial if reveal else mask(b.serial))
    if b.capacity_source:
        add("Capacity source", b.capacity_source)

    return Panel(
        Group(gauges, Text(""), detail),
        title="[bold]Battery[/bold]",
        title_align="left",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )


# --------------------------------------------------------------------------- device


def _section_panel(title: str, rows: List[Row], reveal: bool, storage_bar: Optional[Text] = None) -> Panel:
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", no_wrap=True)
    t.add_column(overflow="fold")
    for r in rows:
        t.add_row(r.label, format_value(r, reveal))
    body: RenderableType = Group(storage_bar, Text(""), t) if storage_bar is not None else t
    return Panel(body, title=f"[bold]{title}[/bold]", title_align="left", border_style="grey50", padding=(0, 2))


def _storage_bar(rows: List[Row]) -> Optional[Text]:
    vals = {r.key: r.value for r in rows}
    total, used = vals.get("data_capacity_bytes"), vals.get("data_used_bytes")
    if isinstance(total, int) and isinstance(used, int) and total > 0:
        frac = used / total
        t = bar(frac, width=28, style=_usage_style(frac))
        t.append(f"  {frac * 100:.0f}% used")
        return t
    return None


def device_view(d: DeviceReport, reveal: bool) -> RenderableType:
    label = "iPhone / iPad" if d.platform == "ios" else "Android"
    ident = d.name or d.model or (d.device_id if reveal else mask(d.device_id))
    title = "  ·  ".join(bit for bit in (ident, d.os) if bit)

    if d.state != OK:
        body = Text.assemble((f"{d.state.upper()}\n", "bold yellow"), d.message or "")
        return Panel(body, title=f"[bold]{title or label}[/bold]", border_style="yellow", padding=(1, 2))

    parts: List[RenderableType] = [battery_block(d.battery, reveal)]
    panels = []
    for s in d.sections:
        if s.rows:
            panels.append(_section_panel(s.title, s.rows, reveal, _storage_bar(s.rows) if s.key == "storage" else None))
    if panels:
        parts.append(Columns(panels, equal=True, expand=True))
    for w in d.warnings:
        parts.append(Text(f"! {w}", style="yellow"))
    return Panel(Group(*parts), title=f"[bold]{title}[/bold]", subtitle=label, border_style="bright_blue", padding=(1, 1))


def render_scan(console: Console, result: ScanResult, reveal: bool = False) -> None:
    console.print()
    console.print(Text.assemble(("IsItCooked", "bold cyan"), f"  v{__version__}", ("   phone health report", "dim")))
    console.print()

    if not result.devices:
        console.print(
            Panel(
                Group(
                    Text("No phone detected.", style="bold yellow"),
                    Text(""),
                    Text("iPhone   : unlock it, use a data-capable cable, tap “Trust” if asked."),
                    Text("Android  : enable Developer options → USB debugging, then tap “Allow”."),
                    Text(""),
                    Text("Run `isitcooked --doctor` to check that the required tools are installed.", style="dim"),
                ),
                border_style="yellow",
                padding=(1, 2),
            )
        )
    for d in result.devices:
        console.print(device_view(d, reveal))

    for note in result.notes:
        console.print(Text(f"• {note}", style="yellow"))
    if result.devices and not reveal:
        console.print(Text("Serials, IMEI, MAC addresses and phone numbers are masked. Use --reveal to show them.", style="dim"))
    console.print()


def render_doctor(console: Console, tools: dict) -> bool:
    table = Table(box=box.SIMPLE_HEAD, header_style="bold")
    table.add_column("Tool")
    table.add_column("Needed for")
    table.add_column("Status")
    table.add_column("Path", overflow="fold", style="dim")
    purposes = {
        "idevice_id": "iPhone: detect",
        "ideviceinfo": "iPhone: device info",
        "idevicediagnostics": "iPhone: battery",
        "idevicepair": "iPhone: trust prompt",
        "adb": "Android: everything",
    }
    ok = True
    for name, path in tools.items():
        if path:
            table.add_row(name, purposes.get(name, ""), "[green]✓ found[/green]", path)
        else:
            ok = False
            table.add_row(name, purposes.get(name, ""), "[red]✗ missing[/red]", "")
    console.print()
    console.print(table)
    if not ok:
        cmds = []
        if not all(tools.get(n) for n in tools if n != "adb"):
            cmds.append("brew install libimobiledevice")
        if not tools.get("adb"):
            cmds.append("brew install --cask android-platform-tools")
        console.print("Install the missing tools with:")
        console.print(f"  [bold]{' && '.join(cmds)}[/bold]", soft_wrap=True)
    else:
        console.print("[green]Everything needed is installed.[/green]")
    console.print()
    return ok
