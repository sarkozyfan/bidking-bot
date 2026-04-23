#!/usr/bin/env python3
"""Fresh BidKing automation loop.

This script intentionally ignores the old auto-loop logic.  It follows the
user-provided flow exactly:
- Wait until central OCR sees a round number.
- Wait a fixed delay, use the leftmost tool, wait for animation.
- OCR central info, calculate a bid, input it, confirm.
- If OCR sees "对局结束", run the fixed post-round transition clicks.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyautogui
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from bidking_maa_test.central_info_parser import merge_patch, parse_central_info  # noqa: E402
from bidking_maa_test.window_backend import capture_window_frame, find_window, scale_point  # noqa: E402
from manual_bidking_advisor import evaluate  # noqa: E402

try:
    import ctypes
    import ctypes.wintypes as wt

    USER32 = ctypes.windll.user32
except Exception:  # pragma: no cover - only used on Windows desktops.
    USER32 = None
    wt = None

_FAST_OCR = None
_STOP_EVENT = threading.Event()

HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040
MONITOR_DEFAULTTONEAREST = 2
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class StopRequested(RuntimeError):
    pass


def request_stop() -> None:
    _STOP_EVENT.set()


def reset_stop() -> None:
    _STOP_EVENT.clear()


def stop_requested() -> bool:
    return _STOP_EVENT.is_set()


def ensure_not_stopped() -> None:
    if stop_requested():
        raise StopRequested()


def sleep_interruptible(seconds: float, step: float = 0.05) -> None:
    end = time.monotonic() + max(0.0, float(seconds))
    while True:
        ensure_not_stopped()
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(float(step), remaining))


CHINESE_ROUND_NUMBERS = {
    "一": 1,
    "壹": 1,
    "二": 2,
    "两": 2,
    "贰": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "I": 1,
    "Ⅰ": 1,
    "l": 1,
    "丨": 1,
    "II": 2,
    "Ⅱ": 2,
    "III": 3,
    "Ⅲ": 3,
    "IV": 4,
    "Ⅳ": 4,
    "V": 5,
    "Ⅴ": 5,
}


@dataclass
class CaptureResult:
    text: str
    image_path: Path | None
    parsed: dict[str, Any]


@dataclass
class Observation:
    capture: CaptureResult
    end_text: str
    round_no: int | None
    end_prompt: bool
    reward_continue: bool
    auction_lobby: bool
    home_bid_button: bool
    has_any_signal: bool


class EndPromptDetected(RuntimeError):
    def __init__(self, source: str):
        super().__init__(source)
        self.source = source


def now_text() -> str:
    return time.strftime("%H:%M:%S")


def log(message: str) -> None:
    print(f"[{now_text()}] {message}", flush=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_path(config_path: Path, raw_path: str | None, default_name: str) -> Path:
    if not raw_path:
        return config_path.parent / default_name
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return config_path.parent / path


def default_advisor_input() -> dict[str, Any]:
    return {
        "round": 1,
        "my_role": "ahmad",
        "total_all": 30,
        "avg_grid_all": None,
        "count_green": None,
        "count_white": None,
        "min_count_green": 0,
        "min_count_white": 0,
        "max_count": 60,
        "max_show": 20,
        "avg_tolerance": 0.05,
        "grid_price_green": 0.0,
        "grid_price_white": 0.0,
        "grid_price_blue": 0.0,
        "grid_price_purple": 0.28,
        "grid_price_gold": 1.13,
        "grid_price_red": 4.77,
        "total_grid_rounding": "round",
        "constraints": {
            "blue": {"avg": None, "count": None, "grid": None, "min_count": None},
            "purple": {"avg": None, "count": None, "grid": None, "min_count": None},
            "gold": {"avg": None, "count": None, "grid": None, "min_count": None},
            "red": {"avg": None, "count": None, "grid": None, "min_count": None},
        },
        "category_weights": {f"cat{index}": 1 for index in range(1, 11)},
        "rank_signal": {
            "my_rank": 2,
            "players": 4,
            "pressure": 0.55,
            "suspected_bluff": 0.35,
        },
        "style": {
            "risk_bias": "balanced",
            "need_comeback": False,
        },
    }


def apply_price_config(data: dict[str, Any], price_config: dict[str, Any]) -> dict[str, Any]:
    grid_prices = price_config.get("grid_prices", {})
    for color in ("green", "white", "blue", "purple", "gold", "red"):
        if color in grid_prices:
            data[f"grid_price_{color}"] = float(grid_prices[color])
    if "avg_tolerance" in price_config:
        data["avg_tolerance"] = float(price_config["avg_tolerance"])
    if "category_weights" in price_config:
        data["category_weights"] = dict(price_config["category_weights"])
    if "burst_limit" in price_config:
        data["burst_limit"] = float(price_config["burst_limit"])
    if "round_rules" in price_config:
        data["round_rules"] = dict(price_config["round_rules"])
    return data


def build_advisor_input(config: dict[str, Any], text: str, round_no: int, price_config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    advisor = config.get("advisor", {})
    parsed = parse_central_info(text)
    data = default_advisor_input()
    data = apply_price_config(data, price_config)
    data["round"] = int(round_no)
    data["my_role"] = advisor.get("role", "ahmad")
    data["avg_grid_all"] = advisor.get("avg_grid_all")
    data["total_grid_rounding"] = advisor.get("total_grid_rounding", "round")
    green_count = advisor.get("green_count")
    white_count = advisor.get("white_count")
    data["count_green"] = None if green_count in (None, "") else int(green_count)
    data["count_white"] = None if white_count in (None, "") else int(white_count)
    merged = merge_patch(data, parsed)
    merged["round"] = int(round_no)
    return merged, parsed


def merge_parsed_memory(current: dict[str, Any] | None, new_patch: dict[str, Any]) -> dict[str, Any]:
    if not current:
        return json.loads(json.dumps(new_patch, ensure_ascii=False))

    merged = json.loads(json.dumps(current, ensure_ascii=False))
    for key, value in new_patch.items():
        if key in ("parsed_facts", "unparsed_lines"):
            continue
        if key == "constraints":
            merged.setdefault("constraints", {})
            for color, fields in value.items():
                merged["constraints"].setdefault(color, {})
                for field, field_value in fields.items():
                    if field_value is not None:
                        merged["constraints"][color][field] = field_value
        else:
            if value is not None:
                merged[key] = value

    merged_facts = list(current.get("parsed_facts") or [])
    merged_facts.extend(new_patch.get("parsed_facts") or [])
    merged["parsed_facts"] = merged_facts

    merged_unparsed = list(current.get("unparsed_lines") or [])
    merged_unparsed.extend(new_patch.get("unparsed_lines") or [])
    merged["unparsed_lines"] = merged_unparsed
    return merged


def build_advisor_input_from_patch(config: dict[str, Any], parsed_patch: dict[str, Any], round_no: int, price_config: dict[str, Any]) -> dict[str, Any]:
    advisor = config.get("advisor", {})
    data = default_advisor_input()
    data = apply_price_config(data, price_config)
    data["round"] = int(round_no)
    data["my_role"] = advisor.get("role", "ahmad")
    data["avg_grid_all"] = advisor.get("avg_grid_all")
    data["total_grid_rounding"] = advisor.get("total_grid_rounding", "round")
    green_count = advisor.get("green_count")
    white_count = advisor.get("white_count")
    data["count_green"] = None if green_count in (None, "") else int(green_count)
    data["count_white"] = None if white_count in (None, "") else int(white_count)
    merged = merge_patch(data, parsed_patch)
    merged["round"] = int(round_no)
    return merged


def normalize_text(text: str) -> str:
    table = str.maketrans(
        {
            "０": "0",
            "１": "1",
            "２": "2",
            "３": "3",
            "４": "4",
            "５": "5",
            "６": "6",
            "７": "7",
            "８": "8",
            "９": "9",
            "Ⅰ": "I",
            "Ⅱ": "II",
            "Ⅲ": "III",
            "Ⅳ": "IV",
            "Ⅴ": "V",
        }
    )
    return (text or "").translate(table)


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", normalize_text(text))


def round_token_to_int(token: str) -> int | None:
    token = normalize_text(token).strip()
    if token.isdigit():
        value = int(token)
        return value if 1 <= value <= 5 else None
    value = CHINESE_ROUND_NUMBERS.get(token)
    if value is not None and 1 <= value <= 5:
        return value
    return None


def parse_round_number(text: str) -> int | None:
    raw = normalize_text(text)
    patterns = [
        r"第\s*([1-5一二两三四五壹贰叁肆伍IⅤVⅡⅢⅣ]+)\s*(?:轮|回合)",
        r"(?:当前|现在)?(?:轮次|回合)\s*[:：]?\s*第?\s*([1-5一二两三四五壹贰叁肆伍IⅤVⅡⅢⅣ]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, raw, flags=re.IGNORECASE):
            value = round_token_to_int(match.group(1).upper())
            if value is not None:
                return value

    tight = compact_text(raw)
    for pattern in (
        r"第([1-5一二两三四五壹贰叁肆伍IⅤVⅡⅢⅣ]+)(?:轮|回合)",
        r"(?:轮次|回合)[:：]?第?([1-5一二两三四五壹贰叁肆伍IⅤVⅡⅢⅣ]+)",
    ):
        match = re.search(pattern, tight, flags=re.IGNORECASE)
        if match:
            value = round_token_to_int(match.group(1).upper())
            if value is not None:
                return value
    return None


def has_end_prompt(text: str) -> bool:
    tight = compact_text(text)
    if "对局结束" in tight:
        return True
    return "对局" in tight and "结束" in tight


def has_auction_lobby(text: str) -> bool:
    tight = compact_text(text)
    if "竞拍大厅" in tight:
        return True
    return "竞拍" in tight and "大厅" in tight


def has_home_bid_button(text: str) -> bool:
    tight = compact_text(text)
    return "竞拍" in tight


def has_reward_continue(text: str) -> bool:
    tight = compact_text(text)
    return "EXP" in tight.upper() and "\u7ee7\u7eed" in tight


def ensure_output_dir(config: dict[str, Any], config_path: Path) -> Path:
    debug = config.get("debug", {})
    raw = debug.get("runs_dir", "runs")
    path = Path(raw)
    if not path.is_absolute():
        path = config_path.parent / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def rapidocr_once(image: Image.Image) -> str:
    global _FAST_OCR
    if _FAST_OCR is None:
        from rapidocr_onnxruntime import RapidOCR

        _FAST_OCR = RapidOCR()
    result, _ = _FAST_OCR(image)
    if not result:
        return ""
    rows = sorted(result, key=lambda item: (min(point[1] for point in item[0]), min(point[0] for point in item[0])))
    return "\n".join(str(item[1]) for item in rows)


def scaled_region_box(region: dict[str, Any], config: dict[str, Any], image_width: int, image_height: int) -> tuple[int, int, int, int]:
    reference = config.get("window", {}).get("reference_client_size", {})
    ref_width = max(1, int(reference.get("width") or image_width))
    ref_height = max(1, int(reference.get("height") or image_height))
    left = round(float(region["left"]) * image_width / ref_width)
    top = round(float(region["top"]) * image_height / ref_height)
    width = round(float(region["width"]) * image_width / ref_width)
    height = round(float(region["height"]) * image_height / ref_height)
    right = min(image_width, max(0, left + width))
    bottom = min(image_height, max(0, top + height))
    left = min(max(0, left), right)
    top = min(max(0, top), bottom)
    return int(left), int(top), int(right), int(bottom)


def observe_state_fast(config: dict[str, Any], config_path: Path, label: str) -> Observation:
    bring_window_to_front(config)
    frame, _info = capture_window_frame(config)
    runs_dir = ensure_output_dir(config, config_path)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    image_path: Path | None = None
    if bool(config.get("debug", {}).get("save_crops", True)):
        image_path = runs_dir / f"{timestamp}_{label}_full_window.png"
        frame.save(image_path)
    ocr_image = ImageOps.grayscale(frame).convert("RGB")
    text = rapidocr_once(ocr_image)
    if bool(config.get("debug", {}).get("save_ocr_text", True)):
        (runs_dir / f"{timestamp}_{label}_full_window.txt").write_text(text, encoding="utf-8")

    home_bid_text = ""
    home_region = config.get("capture", {}).get("home_bid_button_region")
    if home_region:
        box = scaled_region_box(home_region, config, frame.width, frame.height)
        home_crop = frame.crop(box)
        home_bid_text = rapidocr_once(ImageOps.grayscale(home_crop).convert("RGB"))

    capture = CaptureResult(text=text, image_path=image_path, parsed=parse_central_info(text))
    parsed_facts = capture.parsed.get("parsed_facts") or []
    any_signal = bool(
        parsed_facts
        or parse_round_number(text) is not None
        or has_end_prompt(text)
        or has_reward_continue(text)
        or has_auction_lobby(text)
        or has_home_bid_button(home_bid_text)
    )
    return Observation(
        capture=capture,
        end_text=text,
        round_no=parse_round_number(text),
        end_prompt=has_end_prompt(text),
        reward_continue=has_reward_continue(text),
        auction_lobby=has_auction_lobby(text),
        home_bid_button=has_home_bid_button(home_bid_text),
        has_any_signal=any_signal,
    )


def observe_state(config: dict[str, Any], config_path: Path, label: str) -> Observation:
    return observe_state_fast(config, config_path, label)


def apply_observation_memory(observation: Observation, knowledge_patch: dict[str, Any] | None) -> dict[str, Any] | None:
    parsed = observation.capture.parsed or {}
    facts = parsed.get("parsed_facts") or []
    if not facts:
        return knowledge_patch
    return merge_parsed_memory(knowledge_patch, parsed)


def save_round_debug_bundle(
    config: dict[str, Any],
    config_path: Path,
    *,
    round_no: int,
    raw_text: str,
    knowledge_patch: dict[str, Any] | None,
    advisor_input: dict[str, Any],
    details: dict[str, Any],
    final_price: int,
) -> None:
    debug = config.get("debug", {})
    if not bool(debug.get("save_round_debug", True)):
        return
    runs_dir = ensure_output_dir(config, config_path)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    prefix = runs_dir / f"{stamp}_round{round_no}"
    (prefix.with_suffix(".ocr.txt")).write_text(raw_text or "", encoding="utf-8")
    (prefix.with_suffix(".knowledge.json")).write_text(
        json.dumps(knowledge_patch or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (prefix.with_suffix(".advisor_input.json")).write_text(
        json.dumps(advisor_input, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    payload = {
        "final_price": final_price,
        "details": details,
    }
    (prefix.with_suffix(".result.json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def virtual_screen_rect() -> tuple[int, int, int, int]:
    if USER32 is None:
        return 0, 0, 1920, 1080
    left = int(USER32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    top = int(USER32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width = int(USER32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    height = int(USER32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    return left, top, left + max(1, width), top + max(1, height)


def get_window_outer_rect(hwnd: int) -> tuple[int, int, int, int]:
    if USER32 is None or wt is None:
        return 0, 0, 1920, 1080
    rect = wt.RECT()
    if not USER32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return 0, 0, 1920, 1080
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def screen_center_position(width: int, height: int) -> tuple[int, int]:
    left, top, right, bottom = virtual_screen_rect()
    screen_width = max(1, right - left)
    screen_height = max(1, bottom - top)
    x = left + max(0, (screen_width - width) // 2)
    y = top + max(0, (screen_height - height) // 2)
    return int(x), int(y)


def prepare_target_window(config: dict[str, Any], *, center: bool) -> None:
    ensure_not_stopped()
    if USER32 is None:
        return
    window_options = config.get("window", {})
    if not bool(config.get("safety", {}).get("bring_window_to_front", True)):
        return
    try:
        info = find_window(window_options)
        hwnd = int(info.hwnd)
        USER32.ShowWindow(hwnd, SW_RESTORE)
        sleep_interruptible(0.05)

        left, top, right, bottom = get_window_outer_rect(hwnd)
        width = max(1, right - left)
        height = max(1, bottom - top)
        if center and bool(window_options.get("center_on_start", True)):
            x, y = screen_center_position(width, height)
            USER32.SetWindowPos(hwnd, HWND_TOP, int(x), int(y), width, height, SWP_SHOWWINDOW)
            sleep_interruptible(0.08)
            log(f"window centered: hwnd={hwnd} pos={x},{y} size={width}x{height}")

        if bool(window_options.get("force_topmost_bump", True)):
            USER32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            sleep_interruptible(0.03)
            USER32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            sleep_interruptible(0.03)

        USER32.SetForegroundWindow(hwnd)
        sleep_interruptible(float(config.get("timing", {}).get("click_pause_seconds", 0.12)))
    except Exception as exc:
        log(f"warn: failed to prepare target window: {exc}")


def bring_window_to_front(config: dict[str, Any]) -> None:
    prepare_target_window(config, center=False)


def client_to_screen(config: dict[str, Any], point: dict[str, Any]) -> tuple[int, int]:
    info = find_window(config.get("window", {}))
    reference = config.get("window", {}).get("reference_client_size", {})
    raw_point = dict(point)
    if str(raw_point.get("origin", "left_top")).strip().lower() in {"left_bottom", "bottom_left"}:
        ref_height = int(reference.get("height") or info.height or 1080)
        raw_point["y"] = ref_height - int(raw_point["y"])
    x, y = scale_point(raw_point, reference, info.width, info.height)
    origin_x, origin_y = info.client_origin
    return origin_x + x, origin_y + y


def click_point(config: dict[str, Any], name: str, repeat: int = 1, pause: float | None = None) -> None:
    bring_window_to_front(config)
    point = config["clicks"][name]
    timing = config.get("timing", {})
    pause_value = float(timing.get("click_pause_seconds", 0.12) if pause is None else pause)
    dry_run = bool(config.get("safety", {}).get("dry_run", False))
    x, y = client_to_screen(config, point)
    for index in range(repeat):
        ensure_not_stopped()
        log(f"click {name} #{index + 1}: screen={x},{y}")
        if not dry_run:
            pyautogui.click(x, y)
        sleep_interruptible(pause_value)


def press_escape(config: dict[str, Any]) -> None:
    ensure_not_stopped()
    bring_window_to_front(config)
    dry_run = bool(config.get("safety", {}).get("dry_run", False))
    log("press key: esc")
    if not dry_run:
        pyautogui.press("esc")
    sleep_interruptible(float(config.get("timing", {}).get("click_pause_seconds", 0.12)))


def type_price(config: dict[str, Any], price: int) -> None:
    ensure_not_stopped()
    bring_window_to_front(config)
    timing = config.get("timing", {})
    pause = float(timing.get("click_pause_seconds", 0.12))
    dry_run = bool(config.get("safety", {}).get("dry_run", False))
    log(f"type price: {price}")
    if dry_run:
        return
    pyautogui.hotkey("ctrl", "a")
    sleep_interruptible(pause)
    ensure_not_stopped()
    pyautogui.write(str(price), interval=0.02)
    sleep_interruptible(pause)


def run_tool_sequence(config: dict[str, Any]) -> None:
    log("tool sequence: open/select/confirm")
    click_point(config, "tool_button")
    click_point(config, "leftmost_tool")
    click_point(config, "tool_confirm")


def input_bid(config: dict[str, Any], price: int) -> None:
    log("bid sequence: open/input/confirm")
    click_point(config, "bid_button")
    click_point(config, "bid_input_box")
    type_price(config, price)
    if bool(config.get("safety", {}).get("confirm_after_type", True)):
        click_point(config, "bid_confirm")
        click_point(config, "tool_confirm")
    sleep_interruptible(float(config.get("timing", {}).get("after_bid_confirm_wait_seconds", 1.0)))


def run_post_round_transition(config: dict[str, Any]) -> float:
    log("post-round transition: fixed click chain")
    click_point(config, "end_reward_click", repeat=2)
    sleep_interruptible(1.0)
    click_point(config, "end_close_click", repeat=2)
    sleep_interruptible(1.0)
    click_point(config, "continue_button", repeat=3)
    log("post-round transition complete; waiting for auction lobby OCR")


def run_auction_lobby_transition(config: dict[str, Any]) -> None:
    log("auction lobby detected: enter selected room")
    sleep_interruptible(1.0)
    click_point(config, "post_continue_action")
    sleep_interruptible(2.0)
    click_point(config, "post_continue_confirm")
    confirm_at = time.monotonic()
    log("auction lobby transition complete; waiting for round OCR")
    return confirm_at


def run_home_bid_button_transition(config: dict[str, Any]) -> None:
    log("home bid button detected: click auction entry")
    click_point(config, "home_bid_button")
    log("home bid button transition complete; waiting for next OCR")


def run_reward_continue_transition(config: dict[str, Any]) -> None:
    log("reward continue detected: click continue")
    click_point(config, "reward_continue_button")
    log("reward continue click complete; waiting for next OCR")


def current_map_point(config: dict[str, Any], selected_map: str) -> dict[str, Any] | None:
    maps = config.get("automation", {}).get("maps", {})
    item = maps.get(str(selected_map), {})
    point = item.get("point")
    return point if isinstance(point, dict) else None


def run_map_selection_transition(config: dict[str, Any], selected_map: str) -> float | None:
    maps = config.get("automation", {}).get("maps", {})
    item = maps.get(str(selected_map), {})
    name = str(item.get("name") or selected_map)
    point = current_map_point(config, selected_map)
    if not point:
        log(f"map selection skipped: no point configured for {selected_map}.{name}")
        return None
    log(f"auction lobby detected: select map {selected_map}.{name}")
    bring_window_to_front(config)
    sleep_interruptible(1.0)
    sx, sy = client_to_screen(config, point)
    log(f"click map point: screen={sx},{sy}")
    if not bool(config.get("safety", {}).get("dry_run", False)):
        pyautogui.click(sx, sy)
    sleep_interruptible(float(config.get("timing", {}).get("click_pause_seconds", 0.12)))
    sleep_interruptible(2.0)
    click_point(config, "post_continue_confirm")
    confirm_at = time.monotonic()
    log("map selection transition complete; waiting for round OCR")
    return confirm_at


def choose_rounding(value: float, rounding: str) -> int:
    if rounding == "ceil_int":
        return int(math.ceil(value))
    if rounding == "round_int":
        return int(round(value))
    return int(math.floor(value))


def apply_observed_low_price_floor(result: dict[str, Any], price: int, rounding: str) -> tuple[int, str | None]:
    summary = (result or {}).get("summary") or {}
    observed_low_price = summary.get("observed_low_price")
    if observed_low_price is None:
        return int(price), None
    try:
        observed_low_price = float(observed_low_price)
    except Exception:
        return int(price), None
    if observed_low_price <= 0:
        return int(price), None
    if observed_low_price > float(price):
        raised = choose_rounding(observed_low_price * 1.25, rounding)
        return int(max(price, raised)), f"observed_low_price={observed_low_price:.0f} -> raised={raised}"
    return int(price), None


def choose_bid_value_by_mode(config: dict[str, Any], result: dict[str, Any]) -> tuple[float | None, str]:
    selected_risk = str(config.get("automation", {}).get("selected_risk", "均衡")).strip()
    summary = (result or {}).get("summary") or {}
    if selected_risk in ("保守", "conservative", "floor_price"):
        return summary.get("floor_price"), "保守=floor_price"
    if selected_risk in ("激进", "aggressive", "avg_price_plus_25"):
        avg_price = summary.get("avg_price")
        return (float(avg_price) * 1.25 if avg_price is not None else None), "激进=avg_price*1.25"
    return summary.get("avg_price"), "均衡=avg_price"


def compute_bid_price(
    config: dict[str, Any],
    parsed_patch: dict[str, Any],
    round_no: int,
    price_config: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    pricing = config.get("pricing", {})
    fallback = int(pricing.get("fallback_bid_price", 22223))
    min_facts = int(pricing.get("min_useful_facts", 1))
    multiplier = int(pricing.get("computed_price_multiplier", 10000))
    rounding = str(pricing.get("rounding", "floor_int"))

    parsed = parsed_patch
    advisor_input = build_advisor_input_from_patch(config, parsed_patch, round_no, price_config)
    facts = parsed.get("parsed_facts") or []
    payload: dict[str, Any] = {
        "fallback": False,
        "reason": "",
        "facts": len(facts),
        "parsed": parsed,
        "advisor_input": advisor_input,
        "result": {},
        "source_value": None,
    }
    if len(facts) < min_facts:
        payload["fallback"] = True
        payload["reason"] = f"not enough parsed facts: {len(facts)}"
        return fallback, payload

    result = evaluate(advisor_input)
    payload["result"] = result
    errors = result.get("errors") or []
    if errors:
        payload["fallback"] = True
        payload["reason"] = "; ".join(str(item) for item in errors)
        return fallback, payload

    value, source_reason = choose_bid_value_by_mode(config, result)
    if value is None:
        payload["fallback"] = True
        payload["reason"] = f"missing bid value: {source_reason}"
        return fallback, payload

    value = float(value)
    payload["source_value"] = value
    if value <= 0:
        payload["fallback"] = True
        payload["reason"] = f"non-positive source value: {value}"
        return fallback, payload

    price = choose_rounding(value * multiplier, rounding)
    if price <= 0:
        payload["fallback"] = True
        payload["reason"] = f"non-positive final price: {price}"
        return fallback, payload
    final_price, low_price_reason = apply_observed_low_price_floor(result, price, rounding)
    if low_price_reason:
        payload["reason"] = f"{source_reason}: {value:.4f}w * {multiplier} -> input={price}; {low_price_reason}; final={final_price}"
    else:
        payload["reason"] = f"{source_reason}: {value:.4f}w * {multiplier} -> input={final_price}"
    return int(final_price), payload


def wait_with_observation(config: dict[str, Any], config_path: Path, seconds: float, message: str) -> None:
    ensure_not_stopped()
    seconds = max(0.0, float(seconds))
    if seconds <= 0:
        return
    log(f"{message}: wait {seconds:g}s")
    end = time.monotonic() + seconds
    poll_seconds = max(0.2, float(config.get("timing", {}).get("poll_seconds", 2.0)))
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        sleep_interruptible(min(poll_seconds, remaining))
        observation = observe_state(config, config_path, f"{message.replace(' ', '_')}_wait")
        if observation.end_prompt:
            raise EndPromptDetected(message)


def handle_round(
    config: dict[str, Any],
    config_path: Path,
    price_config: dict[str, Any],
    round_no: int,
    knowledge_patch: dict[str, Any] | None,
) -> dict[str, Any] | None:
    ensure_not_stopped()
    round_wait = float(config.get("timing", {}).get("round_detect_wait_seconds", 15.0))
    if int(round_no) == 1:
        round_wait += float(config.get("timing", {}).get("round1_extra_wait_seconds", 0.0))
    wait_with_observation(
        config,
        config_path,
        round_wait,
        f"round {round_no} detected",
    )
    tool_rounds = {int(item) for item in config.get("automation", {}).get("tool_rounds", [1, 2])}
    if int(round_no) in tool_rounds:
        run_tool_sequence(config)
        wait_with_observation(
            config,
            config_path,
            float(config.get("timing", {}).get("tool_after_wait_seconds", 5.0)),
            "after tool",
        )
    else:
        log(f"round {round_no}: tool skipped by config")
    observation = observe_state(config, config_path, f"round{round_no}_after_tool")
    knowledge_patch = apply_observation_memory(observation, knowledge_patch)
    if observation.end_prompt:
        raise EndPromptDetected(f"round {round_no} after tool")
    effective_patch = knowledge_patch or observation.capture.parsed
    price, details = compute_bid_price(config, effective_patch, round_no, price_config)
    summary = (details.get("result") or {}).get("summary") or {}
    advisor_input = details.get("advisor_input") or build_advisor_input_from_patch(config, effective_patch, round_no, price_config)
    if details.get("fallback"):
        log(f"price fallback: {price}; reason={details.get('reason')}")
    else:
        log(
            "price computed: "
            f"{price}; {details.get('reason')}; "
            f"facts={details.get('facts')} combo={summary.get('combo_count')}"
        )
    if bool(config.get("debug", {}).get("print_ocr_snippet", False)):
        log("ocr snippet: " + compact_text(observation.capture.text)[:160])
    if bool(config.get("debug", {}).get("print_round_debug", True)):
        log(f"debug raw ocr: {repr(observation.capture.text[:300])}")
        log(f"debug advisor input keys: {sorted(advisor_input.keys())}")
        log(f"debug parsed facts: {len((effective_patch or {}).get('parsed_facts') or [])}")
    save_round_debug_bundle(
        config,
        config_path,
        round_no=round_no,
        raw_text=observation.capture.text,
        knowledge_patch=effective_patch,
        advisor_input=advisor_input,
        details=details,
        final_price=price,
    )
    input_bid(config, price)
    return knowledge_patch


def load_price_config(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    price_path = resolve_path(config_path, config.get("advisor", {}).get("price_config_path"), "price_config.json")
    if not price_path.exists():
        log(f"warn: price config not found, using defaults: {price_path}")
        return {}
    return load_json(price_path)


def handle_end_transition(
    config: dict[str, Any],
    handled_rounds: set[int],
    last_end_at: float,
    transition_debounce: float,
    source: str,
) -> tuple[float, float]:
    if time.monotonic() - last_end_at < transition_debounce:
        log(f"{source}: end prompt ignored by debounce")
        return last_end_at, 0.0
    log(f"{source}: end prompt detected")
    confirm_at = run_post_round_transition(config)
    handled_rounds.clear()
    return time.monotonic(), confirm_at


def run_loop(config_path: Path) -> None:
    config = load_json(config_path)
    price_config = load_price_config(config, config_path)
    selected_map = str(config.get("automation", {}).get("selected_map") or config.get("automation", {}).get("default_map", "4"))
    max_runs = int(config.get("automation", {}).get("selected_runs") or config.get("automation", {}).get("default_runs", 1))
    pyautogui.FAILSAFE = bool(config.get("safety", {}).get("failsafe", True))
    pyautogui.PAUSE = float(config.get("safety", {}).get("move_pause_seconds", 0.08))
    prepare_target_window(config, center=True)

    log("fresh bot started")
    log("mode: full-window OCR -> lobby/end/round handling")

    handled_rounds: set[int] = set()
    knowledge_patch: dict[str, Any] | None = None
    completed_runs = 0
    last_end_at = 0.0
    last_lobby_at = 0.0
    last_home_bid_at = 0.0
    last_reward_continue_at = 0.0
    last_unknown_escape_at = 0.0
    last_post_continue_confirm_at = 0.0
    poll_seconds = float(config.get("timing", {}).get("poll_seconds", 1.0))
    transition_debounce = float(config.get("timing", {}).get("transition_debounce_seconds", 8.0))
    reward_continue_debounce = float(config.get("timing", {}).get("reward_continue_debounce_seconds", 1.0))
    unknown_escape_cooldown = float(config.get("automation", {}).get("unknown_escape_cooldown_seconds", 2.0))
    post_confirm_escape_block_seconds = float(config.get("automation", {}).get("post_confirm_escape_block_seconds", 30.0))
    loop_index = 0

    while True:
        loop_index += 1
        try:
            ensure_not_stopped()
            observation = observe_state(config, config_path, "poll")
            knowledge_patch = apply_observation_memory(observation, knowledge_patch)
            round_no = observation.round_no
            log(
                f"loop {loop_index}: observed round={round_no} "
                f"end={observation.end_prompt} lobby={observation.auction_lobby} "
                f"reward_continue={observation.reward_continue} "
                f"home_bid={observation.home_bid_button} any={observation.has_any_signal}"
            )

            if not observation.has_any_signal:
                since_post_confirm = time.monotonic() - last_post_continue_confirm_at
                if since_post_confirm < post_confirm_escape_block_seconds:
                    log(
                        f"loop {loop_index}: no signal, esc blocked after post_continue_confirm "
                        f"({since_post_confirm:.1f}/{post_confirm_escape_block_seconds:.1f}s)"
                    )
                elif time.monotonic() - last_unknown_escape_at >= unknown_escape_cooldown:
                    press_escape(config)
                    last_unknown_escape_at = time.monotonic()
                else:
                    log(f"loop {loop_index}: no signal, esc on cooldown")
                sleep_interruptible(poll_seconds)
                continue

            if observation.end_prompt:
                last_end_at, confirm_at = handle_end_transition(
                    config,
                    handled_rounds,
                    last_end_at,
                    transition_debounce,
                    f"loop {loop_index}",
                )
                if confirm_at:
                    last_post_continue_confirm_at = confirm_at
                completed_runs += 1
                knowledge_patch = None
                log(f"completed runs: {completed_runs}/{max_runs}")
                if completed_runs >= max_runs:
                    log("target runs reached; exit")
                    return
                sleep_interruptible(poll_seconds)
                continue

            if observation.reward_continue:
                if time.monotonic() - last_reward_continue_at >= reward_continue_debounce:
                    run_reward_continue_transition(config)
                    knowledge_patch = None
                    last_reward_continue_at = time.monotonic()
                else:
                    log(f"loop {loop_index}: reward continue ignored by debounce")
                sleep_interruptible(poll_seconds)
                continue

            if observation.auction_lobby:
                if time.monotonic() - last_lobby_at >= transition_debounce:
                    confirm_at = run_map_selection_transition(config, selected_map)
                    if confirm_at:
                        last_post_continue_confirm_at = confirm_at
                    handled_rounds.clear()
                    knowledge_patch = None
                    last_lobby_at = time.monotonic()
                else:
                    log(f"loop {loop_index}: auction lobby ignored by debounce")
                sleep_interruptible(poll_seconds)
                continue

            if observation.home_bid_button:
                if time.monotonic() - last_home_bid_at >= transition_debounce:
                    run_home_bid_button_transition(config)
                    knowledge_patch = None
                    last_home_bid_at = time.monotonic()
                else:
                    log(f"loop {loop_index}: home bid button ignored by debounce")
                sleep_interruptible(poll_seconds)
                continue

            if round_no is None:
                log(f"loop {loop_index}: no round detected; waiting")
                sleep_interruptible(poll_seconds)
                continue

            if round_no == 1 and any(value > 1 for value in handled_rounds):
                log("new auction inferred from round 1; reset handled rounds")
                handled_rounds.clear()
                knowledge_patch = apply_observation_memory(observation, None)

            if round_no in handled_rounds:
                log(f"loop {loop_index}: round {round_no} already handled; waiting")
                sleep_interruptible(poll_seconds)
                continue

            log(f"loop {loop_index}: round {round_no} detected")
            knowledge_patch = handle_round(config, config_path, price_config, round_no, knowledge_patch)
            handled_rounds.add(round_no)

            if round_no >= 5:
                log("round 5 handled; waiting for end prompt or a new OCR state")

            sleep_interruptible(poll_seconds)
        except KeyboardInterrupt:
            log("stopped by Ctrl+C")
            return
        except StopRequested:
            log("stopped by GUI")
            return
        except EndPromptDetected as exc:
            last_end_at, confirm_at = handle_end_transition(
                config,
                handled_rounds,
                last_end_at,
                transition_debounce,
                f"active handling ({exc.source})",
            )
            if confirm_at:
                last_post_continue_confirm_at = confirm_at
            completed_runs += 1
            knowledge_patch = None
            log(f"completed runs: {completed_runs}/{max_runs}")
            if completed_runs >= max_runs:
                log("target runs reached; exit")
                return
            sleep_interruptible(poll_seconds)
        except Exception as exc:
            log(f"error: {type(exc).__name__}: {exc}")
            sleep_interruptible(max(1.0, poll_seconds))


def print_click_positions(config_path: Path) -> None:
    config = load_json(config_path)
    info = find_window(config.get("window", {}))
    log(f"window hwnd={info.hwnd} client_origin={info.client_origin} client_size={info.width}x{info.height}")
    for name in (
        "tool_button",
        "leftmost_tool",
        "tool_confirm",
        "bid_button",
        "bid_input_box",
        "bid_confirm",
        "end_reward_click",
        "end_close_click",
        "continue_button",
        "post_continue_action",
        "post_continue_confirm",
        "reward_continue_button",
    ):
        point = config.get("clicks", {}).get(name)
        if not point:
            continue
        sx, sy = client_to_screen(config, point)
        origin = point.get("origin", "left_top")
        log(f"{name}: config=({point['x']},{point['y']}) origin={origin} -> screen=({sx},{sy})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fresh BidKing bot loop.")
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--print-clicks", action="store_true", help="Print converted screen click positions and exit.")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    if args.print_clicks:
        print_click_positions(config_path)
    else:
        config = load_json(config_path)
        maps = config.get("automation", {}).get("maps", {})
        default_map = str(config.get("automation", {}).get("default_map", "4"))
        default_runs = int(config.get("automation", {}).get("default_runs", 1))
        print("请选择地图：")
        for key in ("1", "2", "3", "4", "5", "6", "7"):
            item = maps.get(key, {})
            print(f"{key}. {item.get('name', key)}")
        map_input = input(f"地图编号 [默认 {default_map}]: ").strip() or default_map
        runs_input = input(f"刷取次数 [默认 {default_runs}]: ").strip() or str(default_runs)
        selected_runs = int(runs_input) if runs_input.isdigit() and int(runs_input) > 0 else default_runs
        config.setdefault("automation", {})
        config["automation"]["selected_map"] = map_input
        config["automation"]["selected_runs"] = selected_runs
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        reset_stop()
        run_loop(config_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
