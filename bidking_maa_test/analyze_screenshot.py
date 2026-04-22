#!/usr/bin/env python3
"""BidKing screenshot analyzer v1.

This version focuses on fixed-window screenshot testing:
- fixed ROI analysis
- state detection
- recommended click coordinates
- annotated image export

It is intended as a stable first prototype before OCR or action automation.
"""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageStat


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
CONFIG_PATH = ROOT / "roi_config.json"


STATE_LABELS = {
    "main_screen": "主界面",
    "bid_input_overlay": "出价弹窗",
    "tool_strip_visible": "底部道具栏",
    "reveal_overlay": "情报揭示界面",
    "unknown": "未知状态",
}


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def parse_rect(raw: dict) -> Rect:
    return Rect(
        x=int(raw["x"]),
        y=int(raw["y"]),
        width=int(raw["width"]),
        height=int(raw["height"]),
    )


def scale_x(value: int, image_width: int, ref_width: int) -> int:
    return int(round(value * image_width / ref_width))


def scale_y(value: int, image_height: int, ref_height: int) -> int:
    return int(round(value * image_height / ref_height))


def scale_rect(rect: Rect, image_size: Tuple[int, int], ref_size: Tuple[int, int]) -> Rect:
    image_width, image_height = image_size
    ref_width, ref_height = ref_size
    return Rect(
        x=scale_x(rect.x, image_width, ref_width),
        y=scale_y(rect.y, image_height, ref_height),
        width=scale_x(rect.width, image_width, ref_width),
        height=scale_y(rect.height, image_height, ref_height),
    )


def scale_point(point: dict, image_size: Tuple[int, int], ref_size: Tuple[int, int]) -> Tuple[int, int]:
    image_width, image_height = image_size
    ref_width, ref_height = ref_size
    return (
        scale_x(int(point["x"]), image_width, ref_width),
        scale_y(int(point["y"]), image_height, ref_height),
    )


def build_scaled_rois(config: dict, image_size: Tuple[int, int]) -> Dict[str, object]:
    ref_size = (
        int(config["reference_resolution"]["width"]),
        int(config["reference_resolution"]["height"]),
    )
    scaled: Dict[str, object] = {}
    for name, raw in config["rois"].items():
        if {"x", "y", "width", "height"} <= set(raw):
            scaled[name] = scale_rect(parse_rect(raw), image_size, ref_size)
        else:
            scaled[name] = scale_point(raw, image_size, ref_size)
    return scaled


def crop(image: Image.Image, rect: Rect) -> Image.Image:
    return image.crop((rect.x, rect.y, rect.right, rect.bottom))


def grayscale_mean(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("L")).mean[0])


def grayscale_std(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("L")).stddev[0])


def yellow_strength(image: Image.Image) -> float:
    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    mask = (pixels[..., 0] >= 180) & (pixels[..., 1] >= 180) & (pixels[..., 2] <= 120)
    return float(mask.mean())


def dark_ratio(image: Image.Image, threshold: int = 80) -> float:
    pixels = np.asarray(image.convert("L"), dtype=np.uint8)
    return float((pixels <= threshold).mean())


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def parse_rect_point_center(rect: object) -> Tuple[int, int]:
    if isinstance(rect, Rect):
        return rect.center
    if isinstance(rect, tuple) and len(rect) == 2:
        return rect
    raise TypeError(f"Unsupported ROI center type: {type(rect)!r}")


def detect_state(image: Image.Image, rois: Dict[str, object]) -> dict:
    bid_overlay = crop(image, rois["bid_overlay_panel"])
    tool_strip = crop(image, rois["tool_strip_panel"])
    reveal_cards = crop(image, rois["reveal_cards_area"])
    reveal_info = crop(image, rois["reveal_right_info"])
    main_bid = crop(image, rois["main_bid_button"])
    confirm_bid = crop(image, rois["confirm_bid_button"])

    metrics = {
        "bid_overlay_dark_ratio": dark_ratio(bid_overlay, threshold=95),
        "tool_strip_dark_ratio": dark_ratio(tool_strip, threshold=95),
        "tool_strip_mean_gray": grayscale_mean(tool_strip),
        "tool_strip_std_gray": grayscale_std(tool_strip),
        "reveal_cards_mean_gray": grayscale_mean(reveal_cards),
        "reveal_cards_std_gray": grayscale_std(reveal_cards),
        "reveal_info_dark_ratio": dark_ratio(reveal_info, threshold=95),
        "reveal_info_mean_gray": grayscale_mean(reveal_info),
        "reveal_info_std_gray": grayscale_std(reveal_info),
        "main_bid_yellow_strength": yellow_strength(main_bid),
        "main_bid_mean_gray": grayscale_mean(main_bid),
        "confirm_bid_yellow_strength": yellow_strength(confirm_bid),
        "confirm_bid_mean_gray": grayscale_mean(confirm_bid),
    }

    state_scores = {
        "bid_input_overlay": (
            clamp01((metrics["confirm_bid_yellow_strength"] - 0.72) / 0.18) * 0.80
            + clamp01((metrics["confirm_bid_mean_gray"] - 150.0) / 60.0) * 0.10
            + clamp01((metrics["bid_overlay_dark_ratio"] - 0.82) / 0.12) * 0.10
        ),
        "main_screen": (
            clamp01((metrics["main_bid_yellow_strength"] - 0.68) / 0.16) * 0.75
            + clamp01((metrics["main_bid_mean_gray"] - 160.0) / 60.0) * 0.15
            + clamp01((100.0 - metrics["tool_strip_mean_gray"]) / 80.0) * 0.10
        ),
        "tool_strip_visible": (
            clamp01((metrics["tool_strip_mean_gray"] - 110.0) / 35.0) * 0.70
            + clamp01((0.55 - metrics["tool_strip_dark_ratio"]) / 0.25) * 0.20
            + clamp01((metrics["tool_strip_std_gray"] - 45.0) / 30.0) * 0.10
        ),
        "reveal_overlay": (
            clamp01((metrics["reveal_cards_mean_gray"] - 56.0) / 10.0) * 0.55
            + clamp01((20.0 - metrics["reveal_cards_std_gray"]) / 12.0) * 0.25
            + clamp01((0.94 - metrics["reveal_info_dark_ratio"]) / 0.08) * 0.20
        ),
    }

    if state_scores["bid_input_overlay"] >= 0.75:
        current_state = "bid_input_overlay"
    elif state_scores["main_screen"] >= 0.75:
        current_state = "main_screen"
    elif state_scores["tool_strip_visible"] >= 0.70:
        current_state = "tool_strip_visible"
    elif state_scores["reveal_overlay"] >= 0.55:
        current_state = "reveal_overlay"
    else:
        best_state, best_score = max(state_scores.items(), key=lambda item: item[1])
        current_state = best_state if best_score >= 0.40 else "unknown"

    candidates = sorted(state_scores.items(), key=lambda item: item[1], reverse=True)
    confidence = 0.0 if current_state == "unknown" else round(state_scores[current_state], 4)

    next_action = {
        "main_screen": {
            "action": "click_main_bid",
            "point": list(rois["main_bid_button_center"]),
            "reason": "检测到主界面的亮黄色出价按钮。",
        },
        "bid_input_overlay": {
            "action": "click_confirm_bid",
            "point": list(rois["confirm_bid_button_center"]),
            "reason": "检测到出价输入弹窗与确认出价按钮。",
        },
        "tool_strip_visible": {
            "action": "review_tool_cards",
            "point": list(parse_rect_point_center(rois["tool_strip_panel"])),
            "reason": "检测到底部道具栏，适合继续读取道具信息。",
        },
        "reveal_overlay": {
            "action": "review_reveal_cards",
            "point": list(parse_rect_point_center(rois["reveal_cards_area"])),
            "reason": "检测到情报揭示界面，应优先读取揭示卡片和右侧说明。",
        },
        "unknown": {
            "action": "manual_review",
            "point": None,
            "reason": "当前截图没有匹配到高置信度状态，需要人工校准。",
        },
    }[current_state]

    return {
        "state": current_state,
        "state_label": STATE_LABELS[current_state],
        "confidence": confidence,
        "metrics": {key: round(value, 4) for key, value in metrics.items()},
        "candidates": [
            {"state": name, "label": STATE_LABELS[name], "score": round(score, 4)}
            for name, score in candidates
        ],
        "next_action": next_action,
    }


def annotate_image(image: Image.Image, rois: Dict[str, object], result: dict, output_path: Path) -> None:
    annotated = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", annotated.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    palette = {
        "round_banner": (97, 218, 251, 110),
        "center_info_panel": (255, 255, 255, 55),
        "loot_panel": (240, 170, 0, 70),
        "loot_price_text": (160, 150, 255, 95),
        "main_bid_button": (173, 255, 47, 110),
        "tool_button": (255, 255, 0, 95),
        "tool_strip_panel": (255, 120, 120, 70),
        "bid_overlay_panel": (255, 120, 120, 55),
        "bid_overlay_keypad": (255, 120, 120, 95),
        "bid_input_box": (255, 180, 120, 90),
        "confirm_bid_button": (255, 255, 0, 120),
        "bid_overlay_close_button": (255, 0, 0, 120),
        "reveal_overlay_panel": (160, 200, 255, 55),
        "reveal_title": (160, 220, 255, 95),
        "reveal_cards_area": (160, 220, 255, 95),
        "reveal_right_info": (160, 220, 255, 95),
    }

    for name, roi in rois.items():
        if not isinstance(roi, Rect):
            continue
        color = palette.get(name, (255, 255, 255, 70))
        draw.rectangle((roi.x, roi.y, roi.right, roi.bottom), outline=color[:3], width=3, fill=color)
        draw.text((roi.x + 6, max(0, roi.y - 18)), name, fill=color[:3])

    action_point = result.get("next_action", {}).get("point")
    if action_point:
        x, y = action_point
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), outline=(255, 0, 0), width=4, fill=(255, 0, 0, 80))
        draw.line((x - 22, y, x + 22, y), fill=(255, 0, 0), width=3)
        draw.line((x, y - 22, x, y + 22), fill=(255, 0, 0), width=3)

    annotated = Image.alpha_composite(annotated, overlay).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    annotated.save(output_path)


def analyze_loaded_image(image: Image.Image, label: str) -> dict:
    config = load_config()
    image = image.convert("RGB")
    rois = build_scaled_rois(config, image.size)
    result = detect_state(image, rois)

    serializable_rois = {}
    for name, roi in rois.items():
        if isinstance(roi, Rect):
            serializable_rois[name] = {
                "x": roi.x,
                "y": roi.y,
                "width": roi.width,
                "height": roi.height,
                "center": list(roi.center),
            }
        else:
            serializable_rois[name] = list(roi)

    output_base = OUTPUT_DIR / Path(label).stem
    annotated_path = output_base.with_suffix(".annotated.png")
    analysis_path = output_base.with_suffix(".analysis.json")
    annotate_image(image, rois, result, annotated_path)

    analysis = {
        "image": label,
        "image_size": {"width": image.size[0], "height": image.size[1]},
        "result": result,
        "rois": serializable_rois,
        "files": {
            "annotated_image": str(annotated_path),
            "analysis_json": str(analysis_path),
        },
    }
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return analysis


def analyze_image(image_path: Path) -> dict:
    return analyze_loaded_image(Image.open(image_path), str(image_path))


def analyze_base64_image(filename: str, content_base64: str) -> dict:
    payload = content_base64.split(",", 1)[-1]
    image = Image.open(BytesIO(base64.b64decode(payload)))
    return analyze_loaded_image(image, filename)


def annotated_image_as_data_url(image_path: str) -> str:
    data = Path(image_path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze BidKing screenshots using fixed ROIs.")
    parser.add_argument("--image", action="append", required=True, help="Absolute path to a screenshot.")
    args = parser.parse_args()

    results = [analyze_image(Path(item)) for item in args.image]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
