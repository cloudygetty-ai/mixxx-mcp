"""
mixxx-mcp — MCP server for Mixxx DJ Software

Integration layers:
  WRITE: MCP tool → MidiBridge → rtmidi CC → Mixxx JS → engine.setValue()
  READ:  Mixxx JS → XHR POST → StateServer (HTTP) → OscStateStore → MCP tool
"""

import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from .midi_bridge import MidiBridge
from .osc_listener import OscStateStore
from .state_server import StateServer
from .controls import CONTROL_MAP, MIDI_CC_MAP, validate_group, resolve_channel

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
log = logging.getLogger("mixxx-mcp")

midi  = MidiBridge()
state = OscStateStore()
srv   = StateServer(state)

mcp = FastMCP(
    name="mixxx-mcp",
    instructions=(
        "Control and monitor Mixxx DJ Software. "
        "Supports deck transport, mixing, EQ, effects, loops, hotcues, and library."
    ),
)


# ══════════════════════════════════════════════════════════════════════════════
# TRANSPORT
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def play(deck: int) -> dict:
    """Start playback on a deck. deck: 1–4."""
    group = resolve_channel(deck)
    midi.send_control(group, "play", 1.0)
    return {"ok": True, "deck": deck, "action": "play"}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def stop(deck: int) -> dict:
    """Stop playback on a deck. deck: 1–4."""
    group = resolve_channel(deck)
    midi.send_control(group, "play", 0.0)
    return {"ok": True, "deck": deck, "action": "stop"}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def cue(deck: int) -> dict:
    """Trigger CUE on a deck. deck: 1–4."""
    group = resolve_channel(deck)
    midi.send_control(group, "cue_default", 1.0)
    return {"ok": True, "deck": deck, "action": "cue"}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def sync(deck: int) -> dict:
    """Toggle BPM sync on a deck. deck: 1–4."""
    group   = resolve_channel(deck)
    current = state.get(group, "sync_enabled") or 0.0
    new_val = 0.0 if current else 1.0
    midi.send_control(group, "sync_enabled", new_val)
    return {"ok": True, "deck": deck, "sync_enabled": bool(new_val)}


# ══════════════════════════════════════════════════════════════════════════════
# MIXING
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def set_volume(deck: int, value: float) -> dict:
    """Set channel fader volume. deck: 1–4, value: 0.0–1.0."""
    if not 0.0 <= value <= 1.0:
        return {"ok": False, "error": "value must be 0.0–1.0"}
    midi.send_control(resolve_channel(deck), "volume", value)
    return {"ok": True, "deck": deck, "volume": value}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def set_crossfader(value: float) -> dict:
    """Set crossfader. value: -1.0 (Deck1) to 1.0 (Deck2), 0.0 = center."""
    if not -1.0 <= value <= 1.0:
        return {"ok": False, "error": "value must be -1.0–1.0"}
    midi.send_control("[Master]", "crossfader", value)
    return {"ok": True, "crossfader": value}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def set_eq(deck: int, low: Optional[float] = None, mid: Optional[float] = None, high: Optional[float] = None) -> dict:
    """Set EQ bands. deck: 1–4. low/mid/high: 0.0–4.0, 1.0 = unity. Pass only bands to change."""
    group  = resolve_channel(deck)
    result = {"ok": True, "deck": deck}
    for band, val in [("filterLow", low), ("filterMid", mid), ("filterHigh", high)]:
        if val is not None:
            if not 0.0 <= val <= 4.0:
                return {"ok": False, "error": f"{band} must be 0.0–4.0"}
            midi.send_control(group, band, val)
            result[band] = val
    return result


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def set_pregain(deck: int, value: float) -> dict:
    """Set pre-gain (trim). deck: 1–4, value: 0.0–4.0, 1.0 = unity."""
    if not 0.0 <= value <= 4.0:
        return {"ok": False, "error": "value must be 0.0–4.0"}
    midi.send_control(resolve_channel(deck), "pregain", value)
    return {"ok": True, "deck": deck, "pregain": value}


# ══════════════════════════════════════════════════════════════════════════════
# RATE / PITCH
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def set_rate(deck: int, value: float) -> dict:
    """Set tempo pitch slider. deck: 1–4, value: -1.0 to 1.0, 0.0 = original tempo."""
    if not -1.0 <= value <= 1.0:
        return {"ok": False, "error": "value must be -1.0–1.0"}
    midi.send_control(resolve_channel(deck), "rate", value)
    return {"ok": True, "deck": deck, "rate": value}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def nudge_tempo(deck: int, direction: str, size: str = "small") -> dict:
    """Nudge tempo. deck: 1–4, direction: 'up'/'down', size: 'small'/'large'."""
    if direction not in ("up", "down"):
        return {"ok": False, "error": "direction must be 'up' or 'down'"}
    if size not in ("small", "large"):
        return {"ok": False, "error": "size must be 'small' or 'large'"}
    key = f"rate_perm_{direction}_small" if size == "small" else f"rate_perm_{direction}"
    midi.send_control(resolve_channel(deck), key, 1.0)
    return {"ok": True, "deck": deck, "nudge": f"{direction}_{size}"}


# ══════════════════════════════════════════════════════════════════════════════
# LOOPS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def set_loop(deck: int, beats: float) -> dict:
    """Activate a beat loop. deck: 1–4, beats: 0.125/0.25/0.5/1/2/4/8/16/32."""
    group = resolve_channel(deck)
    midi.send_control(group, "beatloop_size", beats)
    midi.send_control(group, "beatloop_activate", 1.0)
    return {"ok": True, "deck": deck, "loop_beats": beats}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def exit_loop(deck: int) -> dict:
    """Deactivate loop on a deck. deck: 1–4."""
    midi.send_control(resolve_channel(deck), "reloop_toggle", 0.0)
    return {"ok": True, "deck": deck, "action": "exit_loop"}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def halve_loop(deck: int) -> dict:
    """Halve the current loop length. deck: 1–4."""
    midi.send_control(resolve_channel(deck), "loop_halve", 1.0)
    return {"ok": True, "deck": deck, "action": "loop_halve"}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def double_loop(deck: int) -> dict:
    """Double the current loop length. deck: 1–4."""
    midi.send_control(resolve_channel(deck), "loop_double", 1.0)
    return {"ok": True, "deck": deck, "action": "loop_double"}


# ══════════════════════════════════════════════════════════════════════════════
# HOTCUES
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def set_hotcue(deck: int, slot: int) -> dict:
    """Set hotcue at current position. deck: 1–4, slot: 1–8."""
    if not 1 <= slot <= 8:
        return {"ok": False, "error": "slot must be 1–8"}
    midi.send_control(resolve_channel(deck), f"hotcue_{slot}_set", 1.0)
    return {"ok": True, "deck": deck, "hotcue": slot, "action": "set"}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def goto_hotcue(deck: int, slot: int) -> dict:
    """Jump to a hotcue. deck: 1–4, slot: 1–8."""
    if not 1 <= slot <= 8:
        return {"ok": False, "error": "slot must be 1–8"}
    midi.send_control(resolve_channel(deck), f"hotcue_{slot}_goto", 1.0)
    return {"ok": True, "deck": deck, "hotcue": slot, "action": "goto"}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True})
def clear_hotcue(deck: int, slot: int) -> dict:
    """Clear a hotcue slot. deck: 1–4, slot: 1–8."""
    if not 1 <= slot <= 8:
        return {"ok": False, "error": "slot must be 1–8"}
    midi.send_control(resolve_channel(deck), f"hotcue_{slot}_clear", 1.0)
    return {"ok": True, "deck": deck, "hotcue": slot, "action": "clear"}


# ══════════════════════════════════════════════════════════════════════════════
# BEATJUMP
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def beatjump(deck: int, beats: float) -> dict:
    """Jump forward/backward by N beats. deck: 1–4, beats: positive=forward, negative=backward."""
    group = resolve_channel(deck)
    midi.send_control(group, "beatjump_size", abs(beats))
    midi.send_control(group, "beatjump_forward" if beats > 0 else "beatjump_backward", 1.0)
    return {"ok": True, "deck": deck, "beatjump": beats}


# ══════════════════════════════════════════════════════════════════════════════
# STATE / READ
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def get_deck_state(deck: int) -> dict:
    """Read all live state for a deck. Returns BPM, position, volume, loop, sync, track info."""
    group = resolve_channel(deck)
    keys  = [
        "play","bpm","playposition","volume","pregain",
        "filterLow","filterMid","filterHigh","rate",
        "sync_enabled","loop_enabled","beatloop_size",
        "track_artist","track_title","duration","track_samplerate",
    ]
    result = {"deck": deck, "group": group, "state": {}}
    for k in keys:
        v = state.get(group, k)
        if v is not None:
            result["state"][k] = v
    result["_source"] = "live" if result["state"] else "no_data_connect_mixxx"
    return result


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def get_mixer_state() -> dict:
    """Read master mixer state: crossfader, volume, headphone."""
    keys   = ["crossfader","volume","headVolume","headMix","balance"]
    result = {k: state.get("[Master]", k) for k in keys if state.get("[Master]", k) is not None}
    return {"ok": True, "master": result}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def get_all_state() -> dict:
    """Dump entire cached state for all groups."""
    return {"ok": True, "state": state.snapshot()}


# ══════════════════════════════════════════════════════════════════════════════
# RAW ESCAPE HATCH
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def send_control(group: str, key: str, value: float) -> dict:
    """
    Send any Mixxx control object value directly.
    Reference: https://manual.mixxx.org/latest/en/chapters/appendix/mixxx_controls.html
    group: e.g. '[Channel1]', '[Master]', '[EffectRack1_EffectUnit1]'
    key:   e.g. 'play', 'volume', 'crossfader'
    value: float
    """
    try:
        validate_group(group)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    midi.send_control(group, key, value)
    return {"ok": True, "group": group, "key": key, "value": value}


# ══════════════════════════════════════════════════════════════════════════════
# EFFECTS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def toggle_effect(unit: int, effect: int, enabled: bool) -> dict:
    """Enable/disable an effect. unit: 1–4, effect: 1–3."""
    if not 1 <= unit <= 4:
        return {"ok": False, "error": "unit must be 1–4"}
    if not 1 <= effect <= 3:
        return {"ok": False, "error": "effect must be 1–3"}
    midi.send_control(f"[EffectRack1_EffectUnit{unit}_Effect{effect}]", "enabled", 1.0 if enabled else 0.0)
    return {"ok": True, "unit": unit, "effect": effect, "enabled": enabled}


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def set_effect_mix(unit: int, value: float) -> dict:
    """Set wet/dry mix for an effect unit. unit: 1–4, value: 0.0–1.0."""
    if not 0.0 <= value <= 1.0:
        return {"ok": False, "error": "value must be 0.0–1.0"}
    midi.send_control(f"[EffectRack1_EffectUnit{unit}]", "mix", value)
    return {"ok": True, "unit": unit, "mix": value}


# ══════════════════════════════════════════════════════════════════════════════
# Boot
# ══════════════════════════════════════════════════════════════════════════════

def startup():
    midi.connect()
    srv.start()
    log.info(
        "mixxx-mcp ready | MIDI port: %s | State server: http://127.0.0.1:%d/state",
        midi.port_name, srv.port
    )
