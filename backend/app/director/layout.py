"""B1-04: immutable registered layout geometry; no generated scene-specific JSX."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.app.contracts import ContractViolation

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "contracts/registries/layouts.v1.json"


@lru_cache(maxsize=1)
def layouts():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    items = {(p["template_id"], p["variant_id"]): p for p in registry["layouts"]}
    if len(items) != 30 or registry["registry_version"] != "1.1.0":
        raise ContractViolation("REGISTRY_INCOMPLETE", "layouts",
                                "Use the 30 canonical A/B/C layout variants v1.1.0.")
    return items


def selected_layout(plan: dict) -> dict:
    key = (plan["template_id"], plan["variant_id"])
    layout = layouts().get(key)
    if layout is None or plan["layout_control"]["layout_id"].split(".")[:2] != list(key):
        raise ContractViolation("LAYOUT_VARIANT_UNKNOWN", plan["setup_id"],
                                "Select the existing layout variant for the authored template.")
    return layout


def slot_rect(slot: dict, layout: dict) -> dict:
    canvas = layout["canvas"]
    if (canvas["width"], canvas["height"], canvas["fps"]) != (1920, 1080, 30):
        raise ContractViolation("LAYOUT_CANVAS_INVALID", layout["template_id"],
                                "Only the pinned 1920x1080 30fps layout registry is supported.")
    pos = slot["rect_normalized"]
    box = {key: int(round(pos[key] * (canvas["width"] if key in ("x", "w") else canvas["height"])))
           for key in ("x", "y", "w", "h")}
    if (box["w"] < 1 or box["h"] < 1 or box["x"] < 0 or box["y"] < 0
            or box["x"] + box["w"] > 1920 or box["y"] + box["h"] > 1080):
        raise ContractViolation("LAYOUT_BOUNDS_INVALID", slot["slot_id"],
                                "Return the authored slot to the registered video canvas.")
    return box


def pixel_geometry(plan: dict) -> dict:
    layout = selected_layout(plan)
    fields = {slot["slot_id"]: slot_rect(slot, layout) for slot in layout["slots"]}
    if len(fields) != len(layout["slots"]):
        raise ContractViolation("LAYOUT_SLOT_DUPLICATE", plan["setup_id"],
                                "Registered template slots must be uniquely identified.")
    return fields


def role_bounds(layout: dict, layers: list[dict]) -> None:
    counts = {}
    for layer in layers:
        role = layer["layer_kind"]
        counts[role] = counts.get(role, 0) + 1
    for rule in layout["composition_rules"]["required_role_counts"]:
        num = counts.get(rule["role"], 0)
        if not rule["min_count"] <= num <= rule["max_count"]:
            raise ContractViolation("LAYOUT_ROLE_MISMATCH", layout["template_id"],
                                    "Provide the registered number of reviewed layers for each required role.")


def windows_font_measure(path: str, expected_sha256: str, *, family: str = "Arial"):
    """Measure pinned installed Windows font with GDI, not approximate character widths.

    Font file/hash/family are explicit caller inputs. B2 must separately validate
    rendered font parity. No alternate font fallback is selected here.
    """
    import ctypes
    import hashlib
    import sys
    from ctypes import wintypes
    font_file = Path(path)
    if sys.platform != "win32" or not font_file.is_file():
        raise ContractViolation("FONT_METRICS_REQUIRED", str(path),
                                "Install and explicitly pin a Windows font file for GDI glyph measurement.")
    actual_sha = hashlib.sha256(font_file.read_bytes()).hexdigest()
    if actual_sha != expected_sha256:
        raise ContractViolation("FONT_IDENTITY_STALE", str(path),
                                "Expected font SHA differs from the actual font bytes.")
    gdi = ctypes.windll.gdi32
    gdi.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi.CreateFontW.argtypes = [ctypes.c_int]*13 + [ctypes.c_wchar_p]
    gdi.CreateFontW.restype = ctypes.c_void_p
    gdi.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi.SelectObject.restype = ctypes.c_void_p
    gdi.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi.GetTextExtentPoint32W.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                          ctypes.c_int, ctypes.POINTER(wintypes.SIZE)]
    hdc = gdi.CreateCompatibleDC(0)
    if not hdc:
        raise ContractViolation("FONT_METRICS_REQUIRED", str(path), "Cannot create Windows GDI measurement context.")
    cache = {}
    def measure(text, size):
        key = (text, size)
        if key in cache:
            return cache[key]
        handle = gdi.CreateFontW(-size, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, family)
        if not handle:
            raise ContractViolation("FONT_METRICS_REQUIRED", str(path), "Failed to select the pinned measurement face.")
        previous = gdi.SelectObject(hdc, handle)
        bounds = wintypes.SIZE()
        try:
            if not gdi.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(bounds)):
                raise ContractViolation("FONT_METRICS_REQUIRED", str(path), "GDI glyph measurement failed.")
            cache[key] = (bounds.cx, bounds.cy)
            return cache[key]
        finally:
            gdi.SelectObject(hdc, previous)
            gdi.DeleteObject(handle)
    return measure, {"font_sha256": actual_sha, "font_family": family,
                     "font_file": font_file.name, "measurement_engine": "win32_gdi"}
