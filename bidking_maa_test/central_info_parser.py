#!/usr/bin/env python3
"""Parse BidKing central-info OCR text into advisor fields."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


COLOR_ALIASES = {
    "蓝": "blue",
    "蓝色": "blue",
    "蓝色品质": "blue",
    "紫": "purple",
    "紫色": "purple",
    "紫色品质": "purple",
    "橙": "gold",
    "橙色": "gold",
    "橙色品质": "gold",
    "金": "gold",
    "金色": "gold",
    "金色品质": "gold",
    "黄": "gold",
    "黄色": "gold",
    "黄色品质": "gold",
    "红": "red",
    "红色": "red",
    "红色品质": "red",
    "绿": "green",
    "绿色": "green",
    "绿色品质": "green",
    "白": "white",
    "白色": "white",
    "白色品质": "white",
}


def color_pattern() -> str:
    return r"(蓝色品质|紫色品质|橙色品质|金色品质|黄色品质|红色品质|绿色品质|白色品质|蓝色|紫色|橙色|金色|黄色|红色|绿色|白色|蓝|紫|橙|金|黄|红|绿|白)"


def empty_constraints() -> dict[str, dict[str, Any]]:
    return {
        "wg": {"avg": None, "count": None, "grid": None, "min_count": None},
        "blue": {"avg": None, "count": None, "grid": None, "min_count": None},
        "purple": {"avg": None, "count": None, "grid": None, "min_count": None},
        "gold": {"avg": None, "count": None, "grid": None, "min_count": None},
        "red": {"avg": None, "count": None, "grid": None, "min_count": None},
    }


def normalize_text(text: str) -> str:
    return (
        text.replace("：", ":")
        .replace("，", ",")
        .replace("。", ".")
        .replace("（", "(")
        .replace("）", ")")
        .replace("约为", "约")
        .replace("本场拍卖", "本次竞拍")
        .replace("道具", "藏品")
    )


def normalize_line(line: str) -> str:
    line = normalize_text(line)
    line = re.sub(r"\s+", "", line)
    line = line.replace("所有藏品总占用的格子数量", "所有藏品总格子数量")
    line = line.replace("总占用的格子数量", "总格子数量")
    line = line.replace("总占用格子数量", "总格子数量")
    line = line.replace("平均格数约", "平均格数约为")
    line = line.replace("平均格子数约", "平均格数约为")
    line = line.replace("平均格数", "平均格数")
    return line


def normalize_number(raw: str) -> float:
    cleaned = raw.replace(",", "").strip()
    return float(cleaned)


def maybe_int(value: float) -> int | float:
    return int(value) if abs(value - int(value)) < 1e-9 else value


def ensure_constraint(result: dict[str, Any], color: str) -> dict[str, Any]:
    result.setdefault("constraints", empty_constraints())
    result["constraints"].setdefault(color, {"avg": None, "count": None, "grid": None, "min_count": None})
    return result["constraints"][color]


def append_fact(result: dict[str, Any], field: str, value: Any, line: str) -> None:
    result["parsed_facts"].append({"field": field, "value": value, "line": line})


def color_name(raw: str) -> str:
    return COLOR_ALIASES[raw]


def has_wg_phrase(line: str) -> bool:
    return any(token in line for token in ("白色和绿色", "绿色和白色", "白绿", "白+绿"))


def parse_total_all(line: str) -> int | None:
    patterns = [
        r"总藏品数量为(\d+)件",
        r"共有(\d+)件",
        r"总数量为(\d+)件",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return int(match.group(1))
    return None


def parse_victor_total_all(line: str) -> int | None:
    patterns = [
        r"本次竞拍共有品质紫色[、,]金色[、,]红色藏品(\d+)件",
        r"本次竞拍共有品质紫色[、,]橙色[、,]红色藏品(\d+)件",
        r"共有品质紫色[、,]金色[、,]红色藏品(\d+)件",
        r"共有品质紫色[、,]橙色[、,]红色藏品(\d+)件",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return int(match.group(1))
    return None


def parse_total_grid(line: str) -> int | None:
    patterns = [
        r"所有藏品总格子数量为(\d+)格",
        r"全部总格子数量为(\d+)格",
        r"总藏品总格子数量为(\d+)格",
        r"本次竞拍(?:的)?总藏品总格子数量为(\d+)格",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return int(match.group(1))
    return None


def parse_avg_grid_all(line: str) -> float | None:
    patterns = [
        r"总平均格子数(?:为|是)?([0-9]+(?:\.[0-9]+)?)",
        r"平均格子数(?:为|是)?([0-9]+(?:\.[0-9]+)?)",
        r"每格平均(?:为|是)?([0-9]+(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return normalize_number(match.group(1))
    return None


def parse_green_white_total(line: str) -> int | None:
    patterns = [
        r"绿白总数量为(\d+)",
        r"绿白合计为(\d+)",
        r"绿白总件数为(\d+)",
        r"绿白总数为(\d+)",
        r"绿色白色总数量为(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return int(match.group(1))
    return None


def parse_green_white_grid(line: str) -> int | None:
    patterns = [
        r"所有白色和绿色品质藏品总占位数为(\d+)格",
        r"所有白色和绿色品质藏品总格数为(\d+)格",
        r"所有白色和绿色品质藏品总格子数量为(\d+)格",
        r"白色和绿色品质藏品总占位数为(\d+)格",
        r"白色和绿色品质藏品总格数为(\d+)格",
        r"白色和绿色品质藏品总格子数量为(\d+)格",
        r"白绿总占位数为(\d+)格",
        r"白绿总格数为(\d+)格",
        r"白\+绿总格数为(\d+)格",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return int(match.group(1))
    return None


def parse_green_white_avg(line: str) -> float | None:
    patterns = [
        r"所有白色和绿色品质藏品平均格(?:子)?数(?:约为|为)?([\d,]+(?:\.\d+)?)(?:格)?",
        r"白色和绿色品质藏品平均格(?:子)?数(?:约为|为)?([\d,]+(?:\.\d+)?)(?:格)?",
        r"白绿平均格(?:子)?数(?:约为|为)?([\d,]+(?:\.\d+)?)(?:格)?",
        r"白\+绿平均格(?:子)?数(?:约为|为)?([\d,]+(?:\.\d+)?)(?:格)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return maybe_int(normalize_number(match.group(1)))
    return None


def parse_green_white_avg_price(line: str) -> float | None:
    patterns = [
        r"所有白色和绿色品质藏品(?:的)?平均价值约(?:为)?([\d,]+(?:\.\d+)?)",
        r"白色和绿色品质藏品(?:的)?平均价值约(?:为)?([\d,]+(?:\.\d+)?)",
        r"白绿(?:的)?平均价值约(?:为)?([\d,]+(?:\.\d+)?)",
        r"白\+绿(?:的)?平均价值约(?:为)?([\d,]+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return normalize_number(match.group(1))
    return None


def parse_green_white_total_price(line: str) -> float | None:
    patterns = [
        r"所有白色和绿色品质藏品(?:的)?总价值约(?:为)?([\d,]+(?:\.\d+)?)",
        r"白色和绿色品质藏品(?:的)?总价值约(?:为)?([\d,]+(?:\.\d+)?)",
        r"白绿(?:的)?总价值约(?:为)?([\d,]+(?:\.\d+)?)",
        r"白\+绿(?:的)?总价值约(?:为)?([\d,]+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return normalize_number(match.group(1))
    return None


def parse_low_price(line: str) -> float | None:
    patterns = [
        r"当前预估最低价格[:：]?([\d,]+(?:\.\d+)?)",
        r"预估最低价格[:：]?([\d,]+(?:\.\d+)?)",
        r"最低价格[:：]?([\d,]+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return normalize_number(match.group(1))
    return None


def parse_round(line: str) -> int | None:
    match = re.search(r"第(\d+)轮", line)
    if match:
        return int(match.group(1))
    return None


def parse_color_count(line: str) -> tuple[str, int] | None:
    if has_wg_phrase(line):
        return None
    match = re.search(
        color_pattern() + r"(?:藏品)?(?:的)?(?:总数量|总件数|件数|数量)为(\d+)(?:件)?",
        line,
    )
    if match:
        return color_name(match.group(1)), int(match.group(2))

    match = re.search(
        r"共有" + color_pattern() + r"(?:藏品)?(\d+)(?:件)?",
        line,
    )
    if match:
        return color_name(match.group(1)), int(match.group(2))
    return None


def parse_color_grid(line: str) -> tuple[str, int] | None:
    if has_wg_phrase(line):
        return None
    match = re.search(
        color_pattern() + r"(?:藏品)?(?:的)?(?:总格子数量|总占用格子数量|占用的格子数量)为(\d+)(?:格)?",
        line,
    )
    if match:
        return color_name(match.group(1)), int(match.group(2))
    return None


def parse_color_avg(line: str) -> tuple[str, int | float] | None:
    if has_wg_phrase(line):
        return None
    match = re.search(
        color_pattern() + r"(?:藏品)?平均格(?:子)?数(?:约为|为)?([\d,]+(?:\.\d+)?)(?:格)?",
        line,
    )
    if match:
        return color_name(match.group(1)), maybe_int(normalize_number(match.group(2)))
    return None


def parse_color_avg_price(line: str) -> tuple[str, float] | None:
    if has_wg_phrase(line):
        return None
    match = re.search(
        r"所有" + color_pattern() + r"(?:藏品|品质藏品)?的?平均价值约(?:为)?([\d,]+(?:\.\d+)?)",
        line,
    )
    if match:
        return color_name(match.group(1)), normalize_number(match.group(2))
    match = re.search(
        color_pattern() + r"(?:藏品|品质藏品)?(?:的)?平均价值约(?:为)?([\d,]+(?:\.\d+)?)",
        line,
    )
    if match:
        return color_name(match.group(1)), normalize_number(match.group(2))
    return None


def parse_color_total_price(line: str) -> tuple[str, float] | None:
    if has_wg_phrase(line):
        return None
    match = re.search(
        r"所有" + color_pattern() + r"(?:藏品|品质藏品)?的?总价值约(?:为)?([\d,]+(?:\.\d+)?)",
        line,
    )
    if match:
        return color_name(match.group(1)), normalize_number(match.group(2))
    match = re.search(
        color_pattern() + r"(?:藏品|品质藏品)?(?:的)?总价值约(?:为)?([\d,]+(?:\.\d+)?)",
        line,
    )
    if match:
        return color_name(match.group(1)), normalize_number(match.group(2))
    return None


def parse_generic_avg(line: str) -> tuple[int, float] | None:
    match = re.search(r"有(\d+)种藏品类型占位每格的均价约([\d,]+(?:\.\d+)?)", line)
    if match:
        return int(match.group(1)), normalize_number(match.group(2))
    return None


def parse_central_info(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "constraints": empty_constraints(),
        "parsed_facts": [],
        "unparsed_lines": [],
    }

    lines = [line.strip() for line in re.split(r"[\r\n]+", text or "") if line.strip()]
    for raw_line in lines:
        line = normalize_line(raw_line)
        parsed_any = False

        round_value = parse_round(line)
        if round_value is not None:
            result["round"] = round_value
            append_fact(result, "round", round_value, raw_line)
            parsed_any = True

        total_all = parse_total_all(line)
        if total_all is not None:
            result["total_all"] = total_all
            append_fact(result, "total_all", total_all, raw_line)
            parsed_any = True

        victor_total_all = parse_victor_total_all(line)
        if victor_total_all is not None:
            result["victor_total_all"] = victor_total_all
            append_fact(result, "victor_total_all", victor_total_all, raw_line)
            parsed_any = True

        total_grid = parse_total_grid(line)
        if total_grid is not None:
            result["total_grid_all"] = total_grid
            append_fact(result, "total_grid_all", total_grid, raw_line)
            parsed_any = True

        avg_grid_all = parse_avg_grid_all(line)
        if avg_grid_all is not None:
            result["avg_grid_all"] = avg_grid_all
            append_fact(result, "avg_grid_all", avg_grid_all, raw_line)
            parsed_any = True

        green_white_total = parse_green_white_total(line)
        if green_white_total is not None:
            result["wg_total"] = green_white_total
            append_fact(result, "wg_total", green_white_total, raw_line)
            parsed_any = True

        green_white_grid = parse_green_white_grid(line)
        if green_white_grid is not None:
            ensure_constraint(result, "wg")["grid"] = green_white_grid
            append_fact(result, "constraints.wg.grid", green_white_grid, raw_line)
            parsed_any = True

        green_white_avg = parse_green_white_avg(line)
        if green_white_avg is not None:
            ensure_constraint(result, "wg")["avg"] = green_white_avg
            append_fact(result, "constraints.wg.avg", green_white_avg, raw_line)
            parsed_any = True

        green_white_avg_price = parse_green_white_avg_price(line)
        if green_white_avg_price is not None:
            result["avg_price_wg"] = green_white_avg_price
            append_fact(result, "avg_price_wg", green_white_avg_price, raw_line)
            parsed_any = True

        green_white_total_price = parse_green_white_total_price(line)
        if green_white_total_price is not None:
            result["total_price_wg"] = green_white_total_price
            append_fact(result, "total_price_wg", green_white_total_price, raw_line)
            parsed_any = True

        low_price = parse_low_price(line)
        if low_price is not None:
            result["observed_low_price"] = low_price
            append_fact(result, "observed_low_price", low_price, raw_line)
            parsed_any = True

        color_count = parse_color_count(line)
        if color_count is not None:
            color, value = color_count
            if color in ("green", "white"):
                result[f"count_{color}"] = value
                field = f"count_{color}"
            else:
                ensure_constraint(result, color)["count"] = value
                field = f"constraints.{color}.count"
            append_fact(result, field, value, raw_line)
            parsed_any = True

        color_grid = parse_color_grid(line)
        if color_grid is not None:
            color, value = color_grid
            if color in ("green", "white"):
                result[f"grid_{color}"] = value
                field = f"grid_{color}"
            else:
                ensure_constraint(result, color)["grid"] = value
                field = f"constraints.{color}.grid"
            append_fact(result, field, value, raw_line)
            parsed_any = True

        color_avg = parse_color_avg(line)
        if color_avg is not None:
            color, value = color_avg
            if color in ("green", "white"):
                result[f"avg_{color}"] = value
                field = f"avg_{color}"
            else:
                ensure_constraint(result, color)["avg"] = value
                field = f"constraints.{color}.avg"
            append_fact(result, field, value, raw_line)
            parsed_any = True

        color_avg_price = parse_color_avg_price(line)
        if color_avg_price is not None:
            color, value = color_avg_price
            result[f"avg_price_{color}"] = value
            append_fact(result, f"avg_price_{color}", value, raw_line)
            parsed_any = True

        color_total_price = parse_color_total_price(line)
        if color_total_price is not None:
            color, value = color_total_price
            result[f"total_price_{color}"] = value
            append_fact(result, f"total_price_{color}", value, raw_line)
            parsed_any = True

        generic_avg = parse_generic_avg(line)
        if generic_avg is not None:
            type_count, avg_price = generic_avg
            result["mixed_type_count"] = type_count
            result["mixed_type_avg_grid_price"] = avg_price
            append_fact(result, "mixed_type_count", type_count, raw_line)
            append_fact(result, "mixed_type_avg_grid_price", avg_price, raw_line)
            parsed_any = True

        if not parsed_any:
            result["unparsed_lines"].append(raw_line)

    return result


def merge_patch(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base, ensure_ascii=False))
    for key, value in patch.items():
        if key in ("parsed_facts", "unparsed_lines"):
            continue
        if key == "constraints":
            merged.setdefault("constraints", empty_constraints())
            for color, fields in value.items():
                merged["constraints"].setdefault(color, {})
                for field, field_value in fields.items():
                    if field_value is not None:
                        merged["constraints"][color][field] = field_value
        else:
            merged[key] = value
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse BidKing central info text.")
    parser.add_argument("--text", help="Central info text.")
    parser.add_argument("--text-file", help="Text file containing central info.")
    parser.add_argument("--base-json", help="Optional advisor input JSON to merge into.")
    args = parser.parse_args()

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8-sig")
    elif args.text:
        text = args.text
    else:
        raise SystemExit("Please provide --text or --text-file")

    parsed = parse_central_info(text)
    if args.base_json:
        base = json.loads(Path(args.base_json).read_text(encoding="utf-8-sig"))
        parsed["merged_advisor_input"] = merge_patch(base, parsed)

    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
