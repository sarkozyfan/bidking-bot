#!/usr/bin/env python3
"""Win32 window capture and background input backend.

This module follows the same broad PC-window idea used by mature helpers:
bind a target window, work in window-relative coordinates, capture via Win32,
and send input messages to the target window instead of relying on absolute
desktop mouse positions.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
from PIL import Image, ImageGrab
import numpy as np
import pyautogui


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi
kernel32 = ctypes.windll.kernel32


WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_PASTE = 0x0302
WM_SETTEXT = 0x000C
MK_LBUTTON = 0x0001
VK_CONTROL = 0x11
VK_A = 0x41
PW_RENDERFULLCONTENT = 0x00000002
SRCCOPY = 0x00CC0020
DWMWA_EXTENDED_FRAME_BOUNDS = 9

READY_WINDOW_STATES = {"main_screen", "bid_input_overlay"}
WAITING_WINDOW_STATES = {"tool_strip_visible", "reveal_overlay", "input_locked_modal", "unknown", "lobby_screen"}


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]
    client_rect: tuple[int, int, int, int]
    client_origin: tuple[int, int]
    process_id: int
    process_name: str

    @property
    def width(self) -> int:
        return max(0, self.client_rect[2] - self.client_rect[0])

    @property
    def height(self) -> int:
        return max(0, self.client_rect[3] - self.client_rect[1])


def _get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _rect_tuple(rect: wt.RECT) -> tuple[int, int, int, int]:
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def _client_origin(hwnd: int) -> tuple[int, int]:
    point = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(point))
    return int(point.x), int(point.y)


def _process_name(pid: int) -> str:
    try:
        import psutil

        return psutil.Process(pid).name()
    except Exception:
        return ""


def get_window_info(hwnd: int) -> WindowInfo:
    rect = wt.RECT()
    client_rect = wt.RECT()
    dwm_rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(dwm_rect), ctypes.sizeof(dwm_rect)) == 0:
        rect = dwm_rect
    user32.GetClientRect(hwnd, ctypes.byref(client_rect))
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return WindowInfo(
        hwnd=hwnd,
        title=_get_window_text(hwnd),
        rect=_rect_tuple(rect),
        client_rect=_rect_tuple(client_rect),
        client_origin=_client_origin(hwnd),
        process_id=int(pid.value),
        process_name=_process_name(int(pid.value)),
    )


def list_windows() -> list[WindowInfo]:
    rows: list[WindowInfo] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def callback(hwnd: int, lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _get_window_text(hwnd).strip()
        if not title:
            return True
        try:
            info = get_window_info(hwnd)
        except Exception:
            return True
        if info.width <= 0 or info.height <= 0:
            return True
        rows.append(info)
        return True

    user32.EnumWindows(callback, 0)
    rows.sort(key=lambda item: (item.process_name.lower(), item.title.lower()))
    return rows


def find_window(window_config: dict[str, Any]) -> WindowInfo:
    hwnd_value = int(window_config.get("hwnd") or 0)
    if hwnd_value:
        if not user32.IsWindow(hwnd_value):
            raise RuntimeError(f"Configured hwnd does not exist: {hwnd_value}")
        return get_window_info(hwnd_value)

    title_keyword = str(window_config.get("title_keyword") or "").strip().lower()
    title_regex = str(window_config.get("title_regex") or "").strip()
    process_name = str(window_config.get("process_name") or "").strip().lower()
    candidates = list_windows()
    matched: list[WindowInfo] = []
    for info in candidates:
        if title_keyword and title_keyword not in info.title.lower():
            continue
        if title_regex and not re.search(title_regex, info.title, re.IGNORECASE):
            continue
        if process_name and process_name != info.process_name.lower():
            continue
        matched.append(info)

    if not matched:
        hint = {
            "title_keyword": title_keyword,
            "title_regex": title_regex,
            "process_name": process_name,
        }
        raise RuntimeError(f"No target window matched: {hint}. Run list-windows first.")
    matched.sort(key=lambda item: item.width * item.height, reverse=True)
    return matched[0]


def scale_rect(rect: dict[str, Any], reference: dict[str, Any], actual_width: int, actual_height: int) -> tuple[int, int, int, int]:
    ref_width = max(1, int(reference.get("width") or actual_width))
    ref_height = max(1, int(reference.get("height") or actual_height))
    x = round(float(rect["left"]) * actual_width / ref_width)
    y = round(float(rect["top"]) * actual_height / ref_height)
    width = round(float(rect["width"]) * actual_width / ref_width)
    height = round(float(rect["height"]) * actual_height / ref_height)
    return int(x), int(y), int(width), int(height)


def scale_point(point: dict[str, Any], reference: dict[str, Any], actual_width: int, actual_height: int) -> tuple[int, int]:
    ref_width = max(1, int(reference.get("width") or actual_width))
    ref_height = max(1, int(reference.get("height") or actual_height))
    x = round(float(point["x"]) * actual_width / ref_width)
    y = round(float(point["y"]) * actual_height / ref_height)
    return int(x), int(y)


def capture_window_image(hwnd: int) -> Image.Image:
    info = get_window_info(hwnd)
    width, height = info.width, info.height
    if width <= 0 or height <= 0:
        raise RuntimeError("Target window client area is empty")

    hwnd_dc = user32.GetDC(hwnd)
    src_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
    old_obj = gdi32.SelectObject(src_dc, bitmap)
    try:
        ok = user32.PrintWindow(hwnd, src_dc, PW_RENDERFULLCONTENT)
        if not ok:
            ok = gdi32.BitBlt(src_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY)
        if not ok:
            raise RuntimeError("PrintWindow/BitBlt failed")

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        lines = gdi32.GetDIBits(src_dc, bitmap, 0, height, buffer, ctypes.byref(bmi), 0)
        if lines != height:
            raise RuntimeError("GetDIBits failed")
        return Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        gdi32.SelectObject(src_dc, old_obj)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(src_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)


def capture_window_with_fallback(hwnd: int) -> Image.Image:
    try:
        return capture_window_image(hwnd)
    except Exception:
        info = get_window_info(hwnd)
        left, top = info.client_origin
        return ImageGrab.grab(bbox=(left, top, left + info.width, top + info.height)).convert("RGB")


def capture_window_frame(config: dict[str, Any]) -> tuple[Image.Image, WindowInfo]:
    window_config = config.get("window", {})
    info = find_window(window_config)
    return capture_window_with_fallback(info.hwnd), info


def crop_central_info_from_image(image: Image.Image, config: dict[str, Any]) -> tuple[Image.Image, tuple[int, int, int, int]]:
    window_config = config.get("window", {})
    reference = window_config.get("reference_client_size", {})
    region = config["capture"]["central_info_region"]
    x, y, width, height = scale_rect(region, reference, image.width, image.height)
    right = min(image.width, max(0, x + width))
    bottom = min(image.height, max(0, y + height))
    left = min(max(0, x), right)
    top = min(max(0, y), bottom)
    return image.crop((left, top, right, bottom)), (left, top, right - left, bottom - top)


def _white_modal_score(image: Image.Image) -> float:
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    if gray.size == 0:
        return 0.0
    height, width = gray.shape
    left = max(0, int(width * 0.18))
    right = min(width, int(width * 0.82))
    top = max(0, int(height * 0.18))
    bottom = min(height, int(height * 0.82))
    center = gray[top:bottom, left:right]
    if center.size == 0:
        return 0.0
    mean_gray = float(center.mean())
    bright_ratio = float((center >= 200).mean())
    mean_score = max(0.0, min(1.0, (mean_gray - 110.0) / 55.0))
    bright_score = max(0.0, min(1.0, (bright_ratio - 0.18) / 0.45))
    return min(0.99, mean_score * 0.7 + bright_score * 0.3)


def _lobby_entry_score(image: Image.Image) -> tuple[float, tuple[int, int] | None]:
    arr = np.asarray(image.convert("RGB"), dtype=np.uint8)
    if arr.size == 0:
        return 0.0, None

    roi = arr[120:320, 0:420]
    if roi.size == 0:
        return 0.0, None

    mask = (
        ((roi[..., 0] >= 120) & (roi[..., 1] >= 120) & (roi[..., 2] <= 180))
        | ((roi[..., 0] <= 180) & (roi[..., 1] >= 150) & (roi[..., 2] >= 100))
        | ((roi[..., 0] <= 140) & (roi[..., 1] >= 170) & (roi[..., 2] >= 130))
    ).astype(np.uint8) * 255

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    bars: list[tuple[int, int, int, int, int]] = []
    for index in range(1, num_labels):
        x, y, w, h, area = stats[index]
        if area < 20 or w < 180 or h > 8:
            continue
        bars.append((int(x), int(y), int(w), int(h), int(area)))

    if len(bars) < 2:
        return 0.0, None

    x0 = min(item[0] for item in bars)
    y0 = min(item[1] for item in bars)
    x1 = max(item[0] + item[2] for item in bars)
    y1 = max(item[1] + item[3] for item in bars)
    span_x = x1 - x0
    span_y = y1 - y0

    score = 0.55
    score += min(0.20, 0.05 * len(bars))
    score += min(0.15, max(0.0, (span_x - 250.0) / 500.0))
    score += min(0.10, max(0.0, (span_y - 20.0) / 200.0))
    return min(0.99, score), (207, 216)


def detect_window_state_from_image(image: Image.Image) -> dict[str, Any]:
    try:
        from .analyze_screenshot import build_scaled_rois, detect_state, load_config as load_roi_config
    except ImportError:
        from analyze_screenshot import build_scaled_rois, detect_state, load_config as load_roi_config

    roi_config = load_roi_config()
    rois = build_scaled_rois(roi_config, image.size)
    result = detect_state(image, rois)

    lobby_score, lobby_point = _lobby_entry_score(image)
    if lobby_score >= 0.60 and result.get("state") not in {"bid_input_overlay", "reveal_overlay"}:
        metrics = dict(result.get("metrics", {}))
        metrics["lobby_entry_score"] = round(lobby_score, 4)
        candidates = [
            {"state": "lobby_screen", "label": "拍卖大厅", "score": round(lobby_score, 4)},
        ] + list(result.get("candidates", []))
        return {
            "state": "lobby_screen",
            "state_label": "拍卖大厅",
            "confidence": round(lobby_score, 4),
            "metrics": metrics,
            "candidates": candidates,
            "next_action": {
                "action": "click_lobby_entry",
                "point": list(lobby_point or (207, 216)),
                "reason": "检测到拍卖大厅入口页，先点击进入竞拍大厅。",
            },
        }

    white_score = _white_modal_score(image)
    if white_score >= 0.65 and result.get("state") != "bid_input_overlay":
        metrics = dict(result.get("metrics", {}))
        metrics["white_modal_score"] = round(white_score, 4)
        candidates = [
            {"state": "input_locked_modal", "label": "白色确认层", "score": round(white_score, 4)},
        ] + list(result.get("candidates", []))
        return {
            "state": "input_locked_modal",
            "state_label": "白色确认层",
            "confidence": round(white_score, 4),
            "metrics": metrics,
            "candidates": candidates,
            "next_action": {
                "action": "wait_modal_clear",
                "point": None,
                "reason": "检测到大面积白色确认层，暂缓输入",
            },
        }

    return result


def crop_central_info(config: dict[str, Any]) -> tuple[Image.Image, WindowInfo, tuple[int, int, int, int]]:
    image, info = capture_window_frame(config)
    crop, crop_rect = crop_central_info_from_image(image, config)
    return crop, info, crop_rect


def _lparam(x: int, y: int) -> int:
    return (int(y) << 16) | (int(x) & 0xFFFF)


def background_click(hwnd: int, x: int, y: int, pause: float = 0.05) -> None:
    lp = _lparam(x, y)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    time.sleep(pause)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def background_ctrl_a(hwnd: int, pause: float = 0.03) -> None:
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_CONTROL, 0)
    time.sleep(pause)
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_A, 0)
    time.sleep(pause)
    user32.PostMessageW(hwnd, WM_KEYUP, VK_A, 0)
    time.sleep(pause)
    user32.PostMessageW(hwnd, WM_KEYUP, VK_CONTROL, 0)


def background_type_text(hwnd: int, text: str, interval: float = 0.01) -> None:
    for char in str(text):
        user32.PostMessageW(hwnd, WM_CHAR, ord(char), 0)
        time.sleep(interval)


def perform_window_input(config: dict[str, Any], price: int, *, screen_state: dict[str, Any] | None = None) -> list[str]:
    input_config = config.get("input", {})
    mode = str(input_config.get("control_mode", "window_background")).strip().lower()
    if mode == "window_foreground":
        return perform_window_foreground_input(config, price, screen_state=screen_state)

    window_config = config.get("window", {})
    info = find_window(window_config)
    reference = window_config.get("reference_client_size", {})
    safety = config.get("safety", {})
    pause = float(safety.get("move_pause_seconds", 0.08))
    actions: list[str] = []

    if screen_state:
        state = screen_state.get("state")
        if state not in READY_WINDOW_STATES and state != "lobby_screen":
            actions.append(f"skip input because window_state={state}")
            return actions
        if state == "lobby_screen":
            x, y = 207, 216
            sx, sy = _screen_point(info, x, y)
            actions.append(f"background click lobby entry client={x},{y} screen={sx},{sy} hwnd={info.hwnd}")
            if not bool(safety.get("dry_run", True)):
                background_click(info.hwnd, x, y, pause=pause)
            return actions

    for item in _tool_clicks(input_config):
        x, y = scale_point(item, reference, info.width, info.height)
        name = item.get("name", "tool")
        item_pause = float(item.get("pause_seconds", pause))
        actions.append(f"background tool click {name} {x},{y} hwnd={info.hwnd}")
        background_click(info.hwnd, x, y, pause=pause)
        time.sleep(item_pause)

    _click_target(actions, info, input_config.get("click_bid_button", {}), reference, bool(safety.get("dry_run", True)), pause, "background click click_bid_button")
    _click_target(actions, info, input_config.get("click_input_box", {}), reference, bool(safety.get("dry_run", True)), pause, "background click click_input_box")

    method = input_config.get("type_method", "hotkey_paste")
    actions.append(f"background type price {price} method={method}")
    if method in ("hotkey_paste", "write"):
        background_ctrl_a(info.hwnd, pause=pause)
    background_type_text(info.hwnd, str(price), interval=0.02)
    time.sleep(pause)

    if bool(safety.get("confirm_after_type", False)):
        _click_target(actions, info, input_config.get("confirm_button", {}), reference, bool(safety.get("dry_run", True)), pause, "background click confirm_button")
    else:
        actions.append("skip confirm_button because safety.confirm_after_type=false")
    return actions


def _tool_clicks(input_config: dict[str, Any]) -> list[dict[str, Any]]:
    sequence = input_config.get("tool_sequence", {})
    if not sequence.get("enabled", False) or not sequence.get("run_before_bid", True):
        return []
    return [item for item in sequence.get("clicks", []) if item.get("enabled", True)]


def _center_to_screen(info: WindowInfo, point: tuple[int, int]) -> tuple[int, int]:
    return _screen_point(info, int(point[0]), int(point[1]))


def _click_target(actions: list[str], info: WindowInfo, target: dict[str, Any], reference: dict[str, Any], dry_run: bool, pause: float, label: str) -> bool:
    if not target.get("enabled", True):
        return False
    x, y = scale_point(target, reference, info.width, info.height)
    sx, sy = _screen_point(info, x, y)
    actions.append(f"{label} client={x},{y} screen={sx},{sy} hwnd={info.hwnd}")
    if not dry_run:
        pyautogui.click(sx, sy)
        time.sleep(pause)
    return True


def capture_and_classify_window_state(config: dict[str, Any]) -> dict[str, Any]:
    image, _info = capture_window_frame(config)
    state = detect_window_state_from_image(image)
    state["can_input"] = state.get("state") in READY_WINDOW_STATES
    state["should_wait"] = state.get("state") in WAITING_WINDOW_STATES
    return state


def _screen_point(info: WindowInfo, x: int, y: int) -> tuple[int, int]:
    left, top = info.client_origin
    return left + int(x), top + int(y)


def perform_window_foreground_input(config: dict[str, Any], price: int, *, screen_state: dict[str, Any] | None = None) -> list[str]:
    window_config = config.get("window", {})
    info = find_window(window_config)
    reference = window_config.get("reference_client_size", {})
    input_config = config.get("input", {})
    safety = config.get("safety", {})
    pause = float(safety.get("move_pause_seconds", 0.08))
    dry_run = bool(safety.get("dry_run", True))
    pyautogui.FAILSAFE = bool(safety.get("failsafe", True))
    actions: list[str] = []

    try:
        user32.SetForegroundWindow(info.hwnd)
        time.sleep(pause)
    except Exception:
        pass

    if screen_state:
        state = screen_state.get("state")
        if state not in READY_WINDOW_STATES and state != "lobby_screen":
            actions.append(f"skip input because window_state={state}")
            return actions
        if state == "lobby_screen":
            x, y = 207, 216
            sx, sy = _screen_point(info, x, y)
            actions.append(f"foreground click lobby entry client={x},{y} screen={sx},{sy} hwnd={info.hwnd}")
            if not dry_run:
                pyautogui.click(sx, sy)
                time.sleep(pause)
            return actions

    for item in _tool_clicks(input_config):
        x, y = scale_point(item, reference, info.width, info.height)
        sx, sy = _screen_point(info, x, y)
        name = item.get("name", "tool")
        item_pause = float(item.get("pause_seconds", pause))
        actions.append(f"foreground tool click {name} client={x},{y} screen={sx},{sy} hwnd={info.hwnd}")
        if not dry_run:
            pyautogui.click(sx, sy)
            time.sleep(item_pause)

    for key in ("click_bid_button", "click_input_box"):
        target = input_config.get(key, {})
        if not target.get("enabled", True):
            continue
        x, y = scale_point(target, reference, info.width, info.height)
        sx, sy = _screen_point(info, x, y)
        actions.append(f"foreground click {key} client={x},{y} screen={sx},{sy} hwnd={info.hwnd}")
        if not dry_run:
            pyautogui.click(sx, sy)
            time.sleep(pause)

    method = input_config.get("type_method", "hotkey_paste")
    actions.append(f"foreground type price {price} method={method}")
    if not dry_run:
        if method in ("hotkey_paste", "write"):
            pyautogui.hotkey("ctrl", "a")
            time.sleep(pause)
        pyautogui.write(str(price), interval=0.02)
        time.sleep(pause)

    if bool(safety.get("confirm_after_type", False)):
        target = input_config.get("confirm_button", {})
        if target.get("enabled", True):
            x, y = scale_point(target, reference, info.width, info.height)
            sx, sy = _screen_point(info, x, y)
            actions.append(f"foreground click confirm_button client={x},{y} screen={sx},{sy} hwnd={info.hwnd}")
            if not dry_run:
                pyautogui.click(sx, sy)
    else:
        actions.append("skip confirm_button because safety.confirm_after_type=false")
    return actions


def window_rows_as_dict() -> list[dict[str, Any]]:
    rows = []
    for info in list_windows():
        rows.append(
            {
                "hwnd": info.hwnd,
                "title": info.title,
                "process_id": info.process_id,
                "process_name": info.process_name,
                "rect": info.rect,
                "client_origin": info.client_origin,
                "client_size": [info.width, info.height],
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="BidKing Win32 window backend helper.")
    parser.add_argument("command", choices=["list-windows", "capture"])
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "automation_config.json"))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    if args.command == "list-windows":
        print(json.dumps(window_rows_as_dict(), ensure_ascii=False, indent=2))
        return 0

    config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    image, info, crop_rect = crop_central_info(config)
    output = Path(args.output) if args.output else Path(__file__).resolve().parent / "automation_runs" / "window_capture_test.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    print(json.dumps({"ok": True, "output": str(output), "window": info.__dict__, "crop_rect": crop_rect}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
