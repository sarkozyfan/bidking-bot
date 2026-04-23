#!/usr/bin/env python3
"""BidKing manual advisor."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


CATEGORY_DATA = [
    {"id": "cat1", "name": "家居日用", "purpleItem": 0.76, "orangeItem": 4.60, "redItem": 25.22, "orangeGridMin": 0.78, "orangeGridMax": 0.95, "purpleGrid": 0.23, "redGridMin": 4.13, "redGridMax": 5.47},
    {"id": "cat2", "name": "医疗用品", "purpleItem": 0.78, "orangeItem": 5.59, "redItem": 19.41, "orangeGridMin": 1.06, "orangeGridMax": 1.22, "purpleGrid": 0.25, "redGridMin": 5.44, "redGridMax": 6.75},
    {"id": "cat3", "name": "时尚潮流", "purpleItem": 0.80, "orangeItem": 3.08, "redItem": 21.58, "orangeGridMin": 0.83, "orangeGridMax": 1.13, "purpleGrid": 0.32, "redGridMin": 4.80, "redGridMax": 10.10},
    {"id": "cat4", "name": "武器装备", "purpleItem": 1.22, "orangeItem": 5.10, "redItem": 27.71, "orangeGridMin": 0.78, "orangeGridMax": 0.88, "purpleGrid": 0.21, "redGridMin": 4.82, "redGridMax": 7.16},
    {"id": "cat5", "name": "矿物珠宝", "purpleItem": 1.14, "orangeItem": 3.55, "redItem": 17.97, "orangeGridMin": 1.21, "orangeGridMax": 1.51, "purpleGrid": 0.50, "redGridMin": 7.49, "redGridMax": 10.62},
    {"id": "cat6", "name": "文玩古董", "purpleItem": 0.79, "orangeItem": 4.87, "redItem": 23.77, "orangeGridMin": 0.86, "orangeGridMax": 1.00, "purpleGrid": 0.28, "redGridMin": 4.28, "redGridMax": 5.05},
    {"id": "cat7", "name": "数码电子", "purpleItem": 0.83, "orangeItem": 5.21, "redItem": 20.40, "orangeGridMin": 0.88, "orangeGridMax": 1.00, "purpleGrid": 0.25, "redGridMin": 3.94, "redGridMax": 4.65},
    {"id": "cat8", "name": "能源交通", "purpleItem": 1.08, "orangeItem": 6.59, "redItem": 32.97, "orangeGridMin": 0.86, "orangeGridMax": 0.87, "purpleGrid": 0.26, "redGridMin": 3.14, "redGridMax": 4.44},
    {"id": "cat9", "name": "饮食烹饪", "purpleItem": 0.62, "orangeItem": 3.18, "redItem": 19.03, "orangeGridMin": 1.15, "orangeGridMax": 1.65, "purpleGrid": 0.24, "redGridMin": 5.77, "redGridMax": 8.64},
    {"id": "cat10", "name": "书籍绘画", "purpleItem": 0.89, "orangeItem": 4.84, "redItem": 21.66, "orangeGridMin": 0.94, "orangeGridMax": 1.11, "purpleGrid": 0.30, "redGridMin": 3.86, "redGridMax": 4.93},
]

CONSERVATIVE = {
    "orangeItem": 2.0,
    "redItem": 10.0,
    "orangeGrid": 1.0,
    "purpleGrid": 0.2,
    "redGridMin": 3.6,
    "redGridMax": 6.0,
}

GLOBAL_EXACT = {
    "purpleItem": 0.891,
    "orangeItem": 4.661,
    "redItem": 22.972,
    "orangeGrid": 1.13,
    "purpleGrid": 0.28,
    "redGridMin": 4.77,
    "redGridMax": 6.78,
}

DEFAULT_GRID_PRICES = {
    "green": 0.0,
    "white": 0.0,
    "blue": 0.0,
    "purple": 0.28,
    "gold": 1.13,
    "red": 4.77,
}
LEGACY_GRID_PRICE_MODES = {
    "low": 0.90,
    "normal": 1.00,
    "high": 1.10,
}

COLOR_LABELS = {"blue": "蓝色", "purple": "紫色", "gold": "橙色", "red": "红色"}
FIELD_LABELS = {
    "total_all": "总藏品数",
    "victor_total_all": "维克托紫橙红总件数",
    "total_grid_all": "全部总格子数",
    "count_green": "绿色数量",
    "count_white": "白色数量",
    "min_count_green": "绿色至少件数",
    "min_count_white": "白色至少件数",
    "wg_total": "绿白总数",
    "count_blue": "蓝色总件数",
    "count_purple": "紫色总件数",
    "count_gold": "橙色总件数",
    "count_red": "红色总件数",
    "grid_blue": "蓝色总格数",
    "grid_purple": "紫色总格数",
    "grid_gold": "橙色总格数",
    "grid_red": "红色总格数",
    "avg_blue": "蓝色平均格子",
    "avg_purple": "紫色平均格子",
    "avg_gold": "橙色平均格子",
    "avg_red": "红色平均格子",
}
ROLE_LABELS = {"ahmad": "艾哈迈德", "lavin": "拉文", "victor": "维克托", "none": "未知/通用"}
ROLE_ALIASES = {
    "ahmed": "ahmad",
    "role2": "ahmad",
    "raven": "lavin",
    "role3": "lavin",
    "weiketu": "victor",
}
ROLE_AUTO_FIELDS = {
    "ahmad": {1: ["total_all"], 2: ["avg_gold"], 3: ["avg_purple"], 4: ["avg_blue"], 5: ["wg_total"]},
    "lavin": {5: ["count_blue", "count_purple", "count_gold", "count_red", "wg_total"]},
    "victor": {1: ["total_all"]},
}
ROUND_RULES = {
    1: {"multiplier": 2.0, "pace": 0.42, "label": "两倍出价第二直接获得"},
    2: {"multiplier": 1.6, "pace": 0.56, "label": "1.6 倍出价第二直接获得"},
    3: {"multiplier": 1.4, "pace": 0.70, "label": "1.4 倍出价第二直接获得"},
    4: {"multiplier": 1.2, "pace": 0.84, "label": "1.2 倍出价第二直接获得"},
    5: {"multiplier": 1.0, "pace": 1.00, "label": "价高者得"},
}
FIELD_PRIORITIES = {
    "count_red": 9.0,
    "count_gold": 8.3,
    "avg_gold": 7.8,
    "grid_red": 7.5,
    "count_purple": 7.0,
    "avg_purple": 6.3,
    "grid_gold": 6.0,
    "wg_total": 5.8,
    "count_green": 5.8,
    "count_white": 5.8,
    "min_count_green": 5.4,
    "min_count_white": 5.4,
    "total_all": 5.8,
    "total_grid_all": 5.6,
    "grid_purple": 5.5,
    "avg_blue": 4.6,
    "count_blue": 4.2,
    "grid_blue": 3.8,
    "avg_red": 2.8,
}


@dataclass
class ColorConstraint:
    avg: Optional[float] = None
    count: Optional[int] = None
    grid: Optional[int] = None
    min_count: Optional[int] = None


@dataclass
class PairSolution:
    counts: List[int]
    pair_map: Dict[int, List[int]]
    warns: List[str]


def normalize_role(role: object) -> str:
    raw = str(role or "none").strip().lower()
    raw = ROLE_ALIASES.get(raw, raw)
    return raw if raw in ROLE_LABELS else "none"


def clamp_weight(value: object) -> int:
    if value in (None, ""):
        return 1
    return 2 if float(value) >= 1.5 else 1


def format_w(value: float) -> str:
    return f"{value:.2f}w"


def as_non_neg_int(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("布尔值不能作为整数输入")
    number = int(value)
    if number < 0:
        raise ValueError("数字必须是非负整数")
    return number


def as_non_neg_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("布尔值不能作为数字输入")
    number = float(value)
    if number < 0:
        raise ValueError("数字必须是非负数")
    return number


def resolve_grid_prices(data: dict) -> Dict[str, float]:
    legacy_scalar = as_non_neg_float(data.get("avg_grid_price"))
    if legacy_scalar is None:
        legacy_mode = str(data.get("avg_grid_price_mode") or "").strip().lower()
        legacy_scalar = LEGACY_GRID_PRICE_MODES.get(legacy_mode, 1.0)

    prices: Dict[str, float] = {}
    for color, default_price in DEFAULT_GRID_PRICES.items():
        direct = as_non_neg_float(data.get(f"grid_price_{color}"))
        prices[color] = direct if direct is not None else default_price * legacy_scalar
    return prices


def raw_price_to_w(value: object) -> Optional[float]:
    number = as_non_neg_float(value)
    if number is None:
        return None
    return number / 10000.0


def get_market_price_info(data: dict) -> Dict[str, Dict[str, Optional[float]]]:
    info = dict(data.get("market_prices", {}))
    result: Dict[str, Dict[str, Optional[float]]] = {}
    for color in ("white", "green", "wg", "blue", "purple", "gold", "red"):
        color_info = dict(info.get(color, {}))
        avg = color_info.get("avg", data.get(f"avg_price_{color}"))
        total = color_info.get("total", data.get(f"total_price_{color}"))
        result[color] = {"avg": raw_price_to_w(avg), "total": raw_price_to_w(total)}
    return result


def known_color_price(info: Dict[str, Optional[float]], count: int) -> Optional[float]:
    if info.get("total") is not None:
        return info["total"]
    if info.get("avg") is not None:
        return info["avg"] * count
    return None


def avg_match(grid: int, count: int, avg: Optional[float], tolerance: float) -> bool:
    if avg is None:
        return True
    key = math.floor(avg * 100 + 1e-9)
    if count == 0:
        return grid == 0 and key == 0
    return math.floor((grid * 100) / count + 1e-9) == key


def uniq_sorted(values: Iterable) -> List:
    return sorted(set(values))


def get_color_constraint(data: dict, color: str) -> ColorConstraint:
    color_data = dict(data.get("constraints", {}).get(color, {}))
    return ColorConstraint(
        avg=as_non_neg_float(color_data.get("avg")),
        count=as_non_neg_int(color_data.get("count")),
        grid=as_non_neg_int(color_data.get("grid")),
        min_count=as_non_neg_int(color_data.get("min_count")),
    )


def solve_color(label: str, constraint: ColorConstraint, max_count: int, high_total: int, avg_tolerance: float) -> PairSolution:
    warns: List[str] = []
    count_min = constraint.count if constraint.count is not None else (constraint.min_count if constraint.min_count is not None else 0)
    count_max = constraint.count if constraint.count is not None else min(max_count, high_total)
    pairs: List[Tuple[int, int]] = []

    for count in range(count_min, count_max + 1):
        if constraint.grid is not None:
            grid_min = constraint.grid
            grid_max = constraint.grid
        elif count == 0:
            grid_min = 0
            grid_max = 0
        else:
            grid_min = count
            grid_max = 18 * count

        for grid in range(grid_min, grid_max + 1):
            if count == 0 and grid != 0:
                continue
            if count > 0 and (grid < count or grid > 18 * count):
                continue
            if not avg_match(grid, count, constraint.avg, avg_tolerance):
                continue
            pairs.append((count, grid))

    if constraint.count is not None and constraint.grid is not None and not pairs:
        warns.append(f"{label}的总件数、总格数与平均格子不一致")
    elif not pairs:
        warns.append(f"{label}在当前输入下无可行解")
    if constraint.min_count is not None and constraint.count is not None and constraint.count < constraint.min_count:
        warns.append(f"{label}的总件数小于你设置的最少件数")

    pair_map: Dict[int, List[int]] = {}
    for count, grid in pairs:
        pair_map.setdefault(count, []).append(grid)

    return PairSolution(
        counts=uniq_sorted(count for count, _ in pairs),
        pair_map={count: sorted(grids) for count, grids in pair_map.items()},
        warns=warns,
    )


def weighted_stats(weights: Dict[str, object]) -> Dict[str, float]:
    rows = [(category, float(clamp_weight(weights.get(category["id"], 1)))) for category in CATEGORY_DATA]
    total_weight = sum(weight for _, weight in rows) or float(len(rows))

    def dot(field: str) -> float:
        return sum(weight * category[field] for category, weight in rows) / total_weight

    return {
        "purpleItem": dot("purpleItem"),
        "orangeItem": dot("orangeItem"),
        "redItem": dot("redItem"),
        "orangeGridMin": dot("orangeGridMin"),
        "orangeGridMax": dot("orangeGridMax"),
        "purpleGrid": dot("purpleGrid"),
        "redGridMin": dot("redGridMin"),
        "redGridMax": dot("redGridMax"),
    }


def grid_range(pair_map: Dict[int, List[int]], count: int) -> Optional[Tuple[int, int]]:
    grids = pair_map.get(count)
    if not grids:
        return None
    return min(grids), max(grids)


def build_count_text(values: List[int]) -> str:
    if not values:
        return "--"
    if len(values) <= 16:
        return ", ".join(str(value) for value in values)
    return f"{', '.join(str(value) for value in values[:16])} ... 共 {len(values)} 个"


def green_white_total(data: dict) -> Optional[int]:
    green = as_non_neg_int(data.get("count_green"))
    white = as_non_neg_int(data.get("count_white"))
    direct = as_non_neg_int(data.get("wg_total"))
    if green is not None or white is not None:
        return (green or 0) + (white or 0)
    if direct is not None:
        return direct
    return direct


def derive_total_grid_all(data: dict) -> Optional[int]:
    direct = as_non_neg_int(data.get("total_grid_all"))
    if direct is not None:
        return direct
    role = normalize_role(data.get("my_role", "none"))
    total_all = as_non_neg_int(data.get("victor_total_all")) if role == "victor" else as_non_neg_int(data.get("total_all"))
    avg_grid_all = as_non_neg_float(data.get("avg_grid_all"))
    if total_all is None or avg_grid_all is None:
        return None
    rounding = str(data.get("total_grid_rounding", "round")).strip().lower()
    product = total_all * avg_grid_all
    if rounding == "floor":
        return int(math.floor(product))
    if rounding == "ceil":
        return int(math.ceil(product))
    return int(round(product))


def green_white_min_total(data: dict) -> int:
    green_min = as_non_neg_int(data.get("min_count_green")) or 0
    white_min = as_non_neg_int(data.get("min_count_white")) or 0
    return green_min + white_min


def enumerate_green_white_splits(data: dict, wg_total: int) -> List[Tuple[int, int]]:
    exact_green = as_non_neg_int(data.get("count_green"))
    exact_white = as_non_neg_int(data.get("count_white"))
    min_green = as_non_neg_int(data.get("min_count_green")) or 0
    min_white = as_non_neg_int(data.get("min_count_white")) or 0

    splits: List[Tuple[int, int]] = []
    if exact_green is not None and exact_white is not None:
        if exact_green + exact_white == wg_total and exact_green >= min_green and exact_white >= min_white:
            splits.append((exact_green, exact_white))
        return splits

    if exact_green is not None:
        white = wg_total - exact_green
        if white >= min_white and white >= 0 and exact_green >= min_green:
            splits.append((exact_green, white))
        return splits

    if exact_white is not None:
        green = wg_total - exact_white
        if green >= min_green and green >= 0 and exact_white >= min_white:
            splits.append((green, exact_white))
        return splits

    for green in range(min_green, wg_total - min_white + 1):
        white = wg_total - green
        if white < min_white:
            continue
        splits.append((green, white))
    return splits


def estimate_combo(combo: dict, weighted: Dict[str, float], price_info: Dict[str, Dict[str, Optional[float]]]) -> Dict[str, float]:
    blue_min, blue_max = combo["ranges"].get("blue", (0, 0))
    purple_min, purple_max = combo["ranges"]["purple"]
    gold_min, gold_max = combo["ranges"]["gold"]
    red_min, red_max = combo["ranges"]["red"]

    base = {
        "purpleItemExact": combo["purple"] * GLOBAL_EXACT["purpleItem"],
        "purpleItemScene": combo["purple"] * weighted["purpleItem"],
        "goldItemCons": combo["gold"] * CONSERVATIVE["orangeItem"],
        "goldItemExact": combo["gold"] * GLOBAL_EXACT["orangeItem"],
        "goldItemScene": combo["gold"] * weighted["orangeItem"],
        "redItemCons": combo["red"] * CONSERVATIVE["redItem"],
        "redItemExact": combo["red"] * GLOBAL_EXACT["redItem"],
        "redItemScene": combo["red"] * weighted["redItem"],
        "purpleGridConsMin": purple_min * CONSERVATIVE["purpleGrid"],
        "purpleGridConsMax": purple_max * CONSERVATIVE["purpleGrid"],
        "purpleGridExactMin": purple_min * GLOBAL_EXACT["purpleGrid"],
        "purpleGridExactMax": purple_max * GLOBAL_EXACT["purpleGrid"],
        "purpleGridSceneMin": purple_min * weighted["purpleGrid"],
        "purpleGridSceneMax": purple_max * weighted["purpleGrid"],
        "goldGridConsMin": gold_min * CONSERVATIVE["orangeGrid"],
        "goldGridConsMax": gold_max * CONSERVATIVE["orangeGrid"],
        "goldGridExactMin": gold_min * GLOBAL_EXACT["orangeGrid"],
        "goldGridExactMax": gold_max * GLOBAL_EXACT["orangeGrid"],
        "goldGridSceneMin": gold_min * weighted["orangeGridMin"],
        "goldGridSceneMax": gold_max * weighted["orangeGridMax"],
        "redGridConsMin": red_min * CONSERVATIVE["redGridMin"],
        "redGridConsMax": red_max * CONSERVATIVE.get("redGridMax", CONSERVATIVE["redGridMin"]),
        "redGridExactMin": red_min * GLOBAL_EXACT["redGridMin"],
        "redGridExactMax": red_max * GLOBAL_EXACT["redGridMax"],
        "redGridSceneMin": red_min * weighted["redGridMin"],
        "redGridSceneMax": red_max * weighted["redGridMax"],
    }
    out = {
        "itemCons": base["goldItemCons"] + base["redItemCons"],
        "itemExact": base["purpleItemExact"] + base["goldItemExact"] + base["redItemExact"],
        "itemScene": base["purpleItemScene"] + base["goldItemScene"] + base["redItemScene"],
        "gridConsMin": base["goldGridConsMin"] + base["purpleGridConsMin"] + base["redGridConsMin"],
        "gridConsMax": base["goldGridConsMax"] + base["purpleGridConsMax"] + base["redGridConsMax"],
        "gridExactMin": base["goldGridExactMin"] + base["purpleGridExactMin"] + base["redGridExactMin"],
        "gridExactMax": base["goldGridExactMax"] + base["purpleGridExactMax"] + base["redGridExactMax"],
        "gridSceneMin": base["goldGridSceneMin"] + base["purpleGridSceneMin"] + base["redGridSceneMin"],
        "gridSceneMax": base["goldGridSceneMax"] + base["purpleGridSceneMax"] + base["redGridSceneMax"],
    }

    known = {
        "wg": known_color_price(price_info["wg"], combo.get("wg_total", 0)),
        "blue": known_color_price(price_info["blue"], combo.get("blue", 0)),
        "purple": known_color_price(price_info["purple"], combo.get("purple", 0)),
        "gold": known_color_price(price_info["gold"], combo.get("gold", 0)),
        "red": known_color_price(price_info["red"], combo.get("red", 0)),
    }
    extra_fixed = (known["wg"] or 0.0) + (known["blue"] or 0.0)
    for key in ("itemCons", "itemExact", "itemScene", "gridConsMin", "gridConsMax", "gridExactMin", "gridExactMax", "gridSceneMin", "gridSceneMax"):
        out[key] += extra_fixed
    if known["purple"] is not None:
        out["itemExact"] = out["itemExact"] - base["purpleItemExact"] + known["purple"]
        out["itemScene"] = out["itemScene"] - base["purpleItemScene"] + known["purple"]
        for key in ("gridConsMin", "gridConsMax", "gridExactMin", "gridExactMax", "gridSceneMin", "gridSceneMax"):
            base_key = key.replace("grid", "purpleGrid", 1)
            out[key] = out[key] - base[base_key] + known["purple"]
    if known["gold"] is not None:
        out["itemCons"] = out["itemCons"] - base["goldItemCons"] + known["gold"]
        out["itemExact"] = out["itemExact"] - base["goldItemExact"] + known["gold"]
        out["itemScene"] = out["itemScene"] - base["goldItemScene"] + known["gold"]
        for key in ("gridConsMin", "gridConsMax", "gridExactMin", "gridExactMax", "gridSceneMin", "gridSceneMax"):
            base_key = key.replace("grid", "goldGrid", 1)
            out[key] = out[key] - base[base_key] + known["gold"]
    if known["red"] is not None:
        out["itemCons"] = out["itemCons"] - base["redItemCons"] + known["red"]
        out["itemExact"] = out["itemExact"] - base["redItemExact"] + known["red"]
        out["itemScene"] = out["itemScene"] - base["redItemScene"] + known["red"]
        for key in ("gridConsMin", "gridConsMax", "gridExactMin", "gridExactMax", "gridSceneMin", "gridSceneMax"):
            base_key = key.replace("grid", "redGrid", 1)
            out[key] = out[key] - base[base_key] + known["red"]

    conservative_floor = min(out["itemCons"], out["gridConsMin"])
    exact_floor = min(out["itemExact"], out["gridExactMin"])
    raw_aggressive_ceiling = max(out["itemExact"], out["gridExactMax"], out["itemScene"], out["gridSceneMax"])

    return {
        "conservative_floor": conservative_floor,
        "exact_floor": exact_floor,
        "item_cons": out["itemCons"],
        "item_exact": out["itemExact"],
        "item_scene": out["itemScene"],
        "grid_cons_min": out["gridConsMin"],
        "grid_exact_min": out["gridExactMin"],
        "grid_scene_min": out["gridSceneMin"],
        "raw_aggressive_ceiling": raw_aggressive_ceiling,
        "possible_low_price": min(conservative_floor, exact_floor),
        "possible_high_price": raw_aggressive_ceiling,
    }


def compare_combo_key(combo: dict) -> Tuple[int, int, int, int]:
    return (-combo["blue"], -combo["purple"], combo["gold"], combo["red"])


def percentile(values: List[float], ratio: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, ratio)) * (len(ordered) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    part = position - low
    return ordered[low] * (1 - part) + ordered[high] * part


def enumerate_high_totals(data: dict) -> List[Tuple[int, int]]:
    role = normalize_role(data.get("my_role", "none"))
    total_all = as_non_neg_int(data.get("victor_total_all")) if role == "victor" else as_non_neg_int(data.get("total_all"))
    wg_total = green_white_total(data)
    wg_min_total = green_white_min_total(data)
    if total_all is None:
        return []
    if wg_total is not None:
        high_total = total_all - wg_total
        return [(high_total, wg_total)] if high_total >= 0 and wg_total >= wg_min_total else []

    counts = []
    for color in ("blue", "purple", "gold", "red"):
        count_value = as_non_neg_int(data.get("constraints", {}).get(color, {}).get("count"))
        if count_value is None:
            counts = []
            break
        counts.append(count_value)
    if len(counts) == 4:
        high_total = sum(counts)
        inferred_wg = total_all - high_total
        return [(high_total, inferred_wg)] if inferred_wg >= wg_min_total else []

    return [(total_all - candidate_wg, candidate_wg) for candidate_wg in range(wg_min_total, total_all + 1)]


def get_wg_constraint(data: dict) -> ColorConstraint:
    color_data = dict(data.get("constraints", {}).get("wg", {}))
    direct = green_white_total(data)
    return ColorConstraint(
        avg=as_non_neg_float(color_data.get("avg")),
        count=as_non_neg_int(color_data.get("count")) if color_data.get("count") not in (None, "") else direct,
        grid=as_non_neg_int(color_data.get("grid")),
        min_count=green_white_min_total(data) or as_non_neg_int(color_data.get("min_count")),
    )


def empty_solved() -> Dict[str, dict]:
    return {color: {"counts": [], "pair_map": {}, "warns": []} for color in ("blue", "purple", "gold", "red")}


def normalize_solved(solved: Dict[str, dict]) -> Dict[str, dict]:
    for color in solved:
        solved[color]["counts"] = uniq_sorted(solved[color]["counts"])
        solved[color]["warns"] = sorted(set(solved[color]["warns"]))
        solved[color]["pair_map"] = {count: uniq_sorted(grids) for count, grids in solved[color]["pair_map"].items()}
    return solved


def build_summary(
    data: dict,
    estimates: List[dict],
    combos: List[dict],
    round_rule: dict,
    avg_tolerance: float,
    grid_prices: Dict[str, float],
) -> dict:
    floor_price = min(item["est"]["exact_floor"] for item in estimates)
    conservative_floor = min(item["est"]["conservative_floor"] for item in estimates)
    avg_price = (
        min(item["est"]["item_exact"] for item in estimates)
        + min(item["est"]["grid_exact_min"] for item in estimates)
        + min(item["est"]["item_scene"] for item in estimates)
        + min(item["est"]["grid_scene_min"] for item in estimates)
    ) / 4.0
    possible_low_price = min(item["est"]["possible_low_price"] for item in estimates)
    possible_high_price = max(item["est"]["possible_high_price"] for item in estimates)
    combo_low_values = [item["est"]["exact_floor"] for item in estimates]
    combo_high_values = [item["est"]["raw_aggressive_ceiling"] for item in estimates]
    spread = max(0.0, percentile(combo_high_values, 0.9) - percentile(combo_low_values, 0.1))
    spread_ratio = spread / max(avg_price, 1.0)
    count_term = min(45.0, math.log2(len(combos) + 1) * 6.5)
    uncertainty = min(100.0, count_term + spread_ratio * 35.0)
    wg_candidates = uniq_sorted(combo.get("wg_total", 0) for combo in combos)
    total_grid_candidates = uniq_sorted(
        [combo["total_grid_range"][0] for combo in combos if "total_grid_range" in combo]
        + [combo["total_grid_range"][1] for combo in combos if "total_grid_range" in combo]
    )
    return {
        "combo_count": len(combos),
        "conservative_floor": conservative_floor,
        "floor_price": floor_price,
        "avg_price": avg_price,
        "conservative_bid_price": floor_price,
        "balanced_bid_price": avg_price,
        "aggressive_bid_price": avg_price * 1.25,
        "possible_low_price": possible_low_price,
        "possible_high_price": possible_high_price,
        "uncertainty": uncertainty,
        "round_rule": round_rule["label"],
        "avg_tolerance": avg_tolerance,
        "observed_low_price": as_non_neg_float(data.get("observed_low_price")),
        "wg_candidates": wg_candidates,
        "total_grid_candidates": total_grid_candidates,
        "grid_prices": grid_prices,
    }


def lavin_known_price(price_info: Dict[str, Optional[float]], count: int, default_avg: float) -> float:
    known = known_color_price(price_info, count)
    return known if known is not None else count * default_avg


def evaluate_lavin(data: dict) -> dict:
    round_no = max(1, min(5, as_non_neg_int(data.get("round")) or 1))
    round_rule = ROUND_RULES.get(round_no, ROUND_RULES[5])
    weighted = weighted_stats(dict(data.get("category_weights", {})))
    price_info = get_market_price_info(data)
    grid_prices = resolve_grid_prices(data)

    counts = {
        "white": as_non_neg_int(data.get("count_white")) or 0,
        "green": as_non_neg_int(data.get("count_green")) or 0,
        "blue": get_color_constraint(data, "blue").count or 0,
        "purple": get_color_constraint(data, "purple").count or 0,
        "gold": get_color_constraint(data, "gold").count or 0,
        "red": get_color_constraint(data, "red").count or 0,
    }
    grids = {
        "blue": get_color_constraint(data, "blue").grid,
        "purple": get_color_constraint(data, "purple").grid,
        "gold": get_color_constraint(data, "gold").grid,
        "red": get_color_constraint(data, "red").grid,
    }

    white_known = lavin_known_price(price_info["white"], counts["white"], 0.03)
    green_known = lavin_known_price(price_info["green"], counts["green"], 0.09)
    blue_known = lavin_known_price(price_info["blue"], counts["blue"], 0.31)
    fixed_low = white_known + green_known + blue_known
    purple_known = known_color_price(price_info["purple"], counts["purple"])
    gold_known = known_color_price(price_info["gold"], counts["gold"])
    red_known = known_color_price(price_info["red"], counts["red"])
    purple_fallback = counts["purple"] * 0.95

    item_cons = fixed_low + (purple_known if purple_known is not None else purple_fallback) + (gold_known if gold_known is not None else counts["gold"] * CONSERVATIVE["orangeItem"]) + (red_known if red_known is not None else counts["red"] * CONSERVATIVE["redItem"])
    item_exact = fixed_low + (purple_known if purple_known is not None else purple_fallback) + (gold_known if gold_known is not None else counts["gold"] * GLOBAL_EXACT["orangeItem"]) + (red_known if red_known is not None else counts["red"] * GLOBAL_EXACT["redItem"])
    item_scene = fixed_low + (purple_known if purple_known is not None else purple_fallback) + (gold_known if gold_known is not None else counts["gold"] * weighted["orangeItem"]) + (red_known if red_known is not None else counts["red"] * weighted["redItem"])

    has_grid = any(grids[color] is not None for color in ("purple", "gold", "red"))
    if has_grid:
        purple_grid_cons = purple_known if purple_known is not None else ((grids["purple"] or 0) * CONSERVATIVE["purpleGrid"] if grids["purple"] is not None else purple_fallback)
        purple_grid_exact = purple_known if purple_known is not None else ((grids["purple"] or 0) * GLOBAL_EXACT["purpleGrid"] if grids["purple"] is not None else purple_fallback)
        purple_grid_scene = purple_known if purple_known is not None else ((grids["purple"] or 0) * weighted["purpleGrid"] if grids["purple"] is not None else purple_fallback)
        gold_grid_cons_min = gold_known if gold_known is not None else ((grids["gold"] or 0) * CONSERVATIVE["orangeGrid"] if grids["gold"] is not None else counts["gold"] * CONSERVATIVE["orangeItem"])
        gold_grid_cons_max = gold_grid_cons_min
        gold_grid_exact_min = gold_known if gold_known is not None else ((grids["gold"] or 0) * GLOBAL_EXACT["orangeGrid"] if grids["gold"] is not None else counts["gold"] * GLOBAL_EXACT["orangeItem"])
        gold_grid_exact_max = gold_grid_exact_min
        gold_grid_scene_min = gold_known if gold_known is not None else ((grids["gold"] or 0) * weighted["orangeGridMin"] if grids["gold"] is not None else counts["gold"] * weighted["orangeItem"])
        gold_grid_scene_max = gold_known if gold_known is not None else ((grids["gold"] or 0) * weighted["orangeGridMax"] if grids["gold"] is not None else counts["gold"] * weighted["orangeItem"])
        red_grid_cons_min = red_known if red_known is not None else ((grids["red"] or 0) * CONSERVATIVE["redGridMin"] if grids["red"] is not None else counts["red"] * CONSERVATIVE["redItem"])
        red_grid_cons_max = red_known if red_known is not None else ((grids["red"] or 0) * CONSERVATIVE.get("redGridMax", CONSERVATIVE["redGridMin"]) if grids["red"] is not None else counts["red"] * CONSERVATIVE["redItem"])
        red_grid_exact_min = red_known if red_known is not None else ((grids["red"] or 0) * GLOBAL_EXACT["redGridMin"] if grids["red"] is not None else counts["red"] * GLOBAL_EXACT["redItem"])
        red_grid_exact_max = red_known if red_known is not None else ((grids["red"] or 0) * GLOBAL_EXACT["redGridMax"] if grids["red"] is not None else counts["red"] * GLOBAL_EXACT["redItem"])
        red_grid_scene_min = red_known if red_known is not None else ((grids["red"] or 0) * weighted["redGridMin"] if grids["red"] is not None else counts["red"] * weighted["redItem"])
        red_grid_scene_max = red_known if red_known is not None else ((grids["red"] or 0) * weighted["redGridMax"] if grids["red"] is not None else counts["red"] * weighted["redItem"])
        grid_cons_min = fixed_low + purple_grid_cons + gold_grid_cons_min + red_grid_cons_min
        grid_cons_max = fixed_low + purple_grid_cons + gold_grid_cons_max + red_grid_cons_max
        grid_exact_min = fixed_low + purple_grid_exact + gold_grid_exact_min + red_grid_exact_min
        grid_exact_max = fixed_low + purple_grid_exact + gold_grid_exact_max + red_grid_exact_max
        grid_scene_min = fixed_low + purple_grid_scene + gold_grid_scene_min + red_grid_scene_min
        grid_scene_max = fixed_low + purple_grid_scene + gold_grid_scene_max + red_grid_scene_max
    else:
        grid_cons_min = grid_cons_max = item_cons
        grid_exact_min = grid_exact_max = item_exact
        grid_scene_min = grid_scene_max = item_scene

    est = {
        "conservative_floor": min(item_cons, grid_cons_min),
        "exact_floor": min(item_exact, grid_exact_min),
        "item_exact": item_exact,
        "item_scene": item_scene,
        "grid_exact_min": grid_exact_min,
        "grid_scene_min": grid_scene_min,
        "raw_aggressive_ceiling": max(item_exact, item_scene, grid_exact_max, grid_scene_max),
        "possible_low_price": min(item_cons, item_exact, item_scene, grid_cons_min, grid_exact_min, grid_scene_min),
        "possible_high_price": max(item_cons, item_exact, item_scene, grid_cons_max, grid_exact_max, grid_scene_max),
    }
    combo = {
        "green": counts["green"],
        "white": counts["white"],
        "blue": counts["blue"],
        "purple": counts["purple"],
        "gold": counts["gold"],
        "red": counts["red"],
        "wg_total": counts["green"] + counts["white"],
        "ranges": {
            "blue": (grids["blue"] or 0, grids["blue"] or 0),
            "purple": (grids["purple"] or 0, grids["purple"] or 0),
            "gold": (grids["gold"] or 0, grids["gold"] or 0),
            "red": (grids["red"] or 0, grids["red"] or 0),
        },
        "total_grid_range": (sum(grid or 0 for grid in grids.values()), sum(grid or 0 for grid in grids.values())),
    }
    summary = build_summary(data, [{"combo": combo, "est": est}], [combo], round_rule, as_non_neg_float(data.get("avg_tolerance")) or 0.05, grid_prices)
    solved = {
        "blue": {"counts": [counts["blue"]], "pair_map": {counts["blue"]: [grids["blue"] or 0]}, "warns": []},
        "purple": {"counts": [counts["purple"]], "pair_map": {counts["purple"]: [grids["purple"] or 0]}, "warns": []},
        "gold": {"counts": [counts["gold"]], "pair_map": {counts["gold"]: [grids["gold"] or 0]}, "warns": []},
        "red": {"counts": [counts["red"]], "pair_map": {counts["red"]: [grids["red"] or 0]}, "warns": []},
    }
    return {
        "errors": [],
        "warns": [],
        "summary": summary,
        "solved": solved,
        "combos_preview": [combo],
        "info_suggestions": compute_info_suggestions(data, solved, 1),
        "auto_fields_now": fields_known_by_role("lavin", round_no),
        "role_label": ROLE_LABELS["lavin"],
        "resolved_wg_total": combo["wg_total"],
    }


def rounds_until_auto(role: str, current_round: int, field: str) -> Optional[int]:
    role_map = ROLE_AUTO_FIELDS.get(normalize_role(role), {})
    for reveal_round, fields in sorted(role_map.items()):
        if field in fields and reveal_round >= current_round:
            return reveal_round - current_round
    return None


def fields_known_by_role(role: str, current_round: int) -> List[str]:
    role_map = ROLE_AUTO_FIELDS.get(normalize_role(role), {})
    fields: List[str] = []
    for reveal_round, round_fields in sorted(role_map.items()):
        if reveal_round <= current_round:
            fields.extend(round_fields)
    return uniq_sorted(fields)


def compute_info_suggestions(data: dict, solved: dict, combo_count: int) -> List[dict]:
    current_round = int(data.get("round", 1))
    role = normalize_role(data.get("my_role", "none"))
    suggestions = []
    total_all = as_non_neg_int(data.get("victor_total_all")) if role == "victor" else as_non_neg_int(data.get("total_all"))
    total_grid_all = as_non_neg_int(data.get("total_grid_all"))
    high_candidates = enumerate_high_totals(data)
    high_total = max((high for high, _ in high_candidates), default=None)

    candidate_fields = [
        "count_red", "count_gold", "avg_gold", "grid_red", "count_purple", "avg_purple",
        "grid_gold", "count_green", "count_white", "min_count_green", "min_count_white",
        "total_grid_all", "victor_total_all" if role == "victor" else "total_all", "grid_purple", "avg_blue", "count_blue", "grid_blue",
    ]

    missing = set()
    if total_all is None:
        missing.add("victor_total_all" if role == "victor" else "total_all")
    if total_grid_all is None:
        missing.add("total_grid_all")
    if as_non_neg_int(data.get("count_green")) is None:
        missing.add("count_green")
    if as_non_neg_int(data.get("count_white")) is None:
        missing.add("count_white")
    if as_non_neg_int(data.get("min_count_green")) is None:
        missing.add("min_count_green")
    if as_non_neg_int(data.get("min_count_white")) is None:
        missing.add("min_count_white")
    for color in ("blue", "purple", "gold", "red"):
        color_data = data.get("constraints", {}).get(color, {})
        for field in ("count", "grid", "avg"):
            if color_data.get(field) in (None, ""):
                missing.add(f"{field}_{color}")

    for field in candidate_fields:
        if field not in missing:
            continue
        score = FIELD_PRIORITIES.get(field, 3.0)
        wait = rounds_until_auto(role, current_round, field)
        if wait == 0:
            score = 0.05
        elif wait == 1:
            score *= 0.35
        elif wait == 2:
            score *= 0.60

        if field.startswith("count_") and high_total is not None and field not in ("count_green", "count_white"):
            color = field.split("_", 1)[1]
            counts = solved.get(color, {}).get("counts", [])
            if counts:
                span = max(counts) - min(counts)
                score += min(3.4, span / max(high_total, 1) * 6)

        if field == "total_grid_all":
            score += 1.2

        reasons = []
        if wait == 0:
            reasons.append("当前回合角色会自动提供，不建议浪费道具")
        elif wait == 1:
            reasons.append("下一回合角色就会给出，优先级下调")

        if field in ("count_green", "count_white"):
            reasons.append("能锁定绿白拆分，避免总量枚举过宽")
        elif field in ("min_count_green", "min_count_white"):
            reasons.append("能先压缩绿白总量下界")
        elif field == "total_grid_all":
            reasons.append("能直接压缩整局总格子范围")
        elif field.startswith("count_"):
            reasons.append("能直接压缩件数组合空间")
        elif field.startswith("grid_"):
            reasons.append("能帮助锁定平均格与高价组合")
        elif field.startswith("avg_"):
            reasons.append("会直接提升估值精度，尤其影响激进判断")
        else:
            reasons.append("属于全局信息，能先缩小大范围")

        suggestions.append({"field": field, "label": FIELD_LABELS[field], "score": score, "reason": "；".join(reasons)})

    suggestions.sort(key=lambda item: item["score"], reverse=True)
    return suggestions[:5]


def validate_input(data: dict) -> List[str]:
    warns = []
    role = normalize_role(data.get("my_role", "none"))
    total_all = as_non_neg_int(data.get("victor_total_all")) if role == "victor" else as_non_neg_int(data.get("total_all"))
    total_grid_all = derive_total_grid_all(data)
    wg_total = green_white_total(data)
    green_count = as_non_neg_int(data.get("count_green"))
    white_count = as_non_neg_int(data.get("count_white"))
    green_min = as_non_neg_int(data.get("min_count_green"))
    white_min = as_non_neg_int(data.get("min_count_white"))
    max_count = as_non_neg_int(data.get("max_count"))
    max_show = as_non_neg_int(data.get("max_show"))
    round_no = as_non_neg_int(data.get("round"))
    avg_tolerance = as_non_neg_float(data.get("avg_tolerance"))
    for color in ("green", "white", "blue", "purple", "gold", "red"):
        try:
            as_non_neg_float(data.get(f"grid_price_{color}"))
        except Exception as exc:
            warns.append(f"{color} 单格价格输入非法: {exc}")

    if role == "victor" and total_all is None:
        warns.append("缺少 victor_total_all（维克托紫橙红总件数）")
    elif role != "lavin" and total_all is None:
        warns.append("缺少 total_all（总藏品数）")
    if max_count is None or max_count < 1:
        warns.append("max_count 必须是正整数")
    if max_show is None or max_show < 1:
        warns.append("max_show 必须是正整数")
    if round_no is None or round_no < 1 or round_no > 5:
        warns.append("round 必须是 1 到 5 之间的整数")
    if avg_tolerance is None:
        warns.append("缺少 avg_tolerance（平均格容差）")
    elif avg_tolerance < 0 or avg_tolerance > 0.2:
        warns.append("avg_tolerance 建议在 0 到 0.2 之间")
    if total_all is not None and wg_total is not None and wg_total > total_all:
        warns.append("绿白总数量不能大于总藏品数")
    if green_count is not None and green_min is not None and green_count < green_min:
        warns.append("绿色数量不能小于绿色至少件数")
    if white_count is not None and white_min is not None and white_count < white_min:
        warns.append("白色数量不能小于白色至少件数")
    if total_grid_all is not None and total_all is not None and total_grid_all < total_all:
        warns.append("全部总格子数不能小于总藏品数")

    candidates = enumerate_high_totals(data)
    if role not in ("lavin", "victor") and not candidates:
        warns.append("当前信息不足以确定高品质总数（蓝紫橙红总数）")

    for color in ("blue", "purple", "gold", "red"):
        try:
            get_color_constraint(data, color)
        except Exception as exc:
            warns.append(f"{COLOR_LABELS[color]}输入非法: {exc}")

    return warns


def evaluate(data: dict) -> dict:
    errors = validate_input(data)
    if errors:
        return {"errors": errors, "warns": []}

    role = normalize_role(data.get("my_role", "ahmad"))
    if role == "none":
        role = "ahmad"
    if role == "lavin":
        return evaluate_lavin(data)

    max_count = as_non_neg_int(data.get("max_count")) or 60
    max_show = as_non_neg_int(data.get("max_show")) or 20
    avg_tolerance = as_non_neg_float(data.get("avg_tolerance")) or 0.05
    round_no = max(1, min(5, as_non_neg_int(data.get("round")) or 1))
    round_rule = ROUND_RULES.get(round_no, ROUND_RULES[5])
    total_grid_all = derive_total_grid_all(data)
    grid_prices = resolve_grid_prices(data)
    price_info = get_market_price_info(data)
    constraints = {color: get_color_constraint(data, color) for color in ("blue", "purple", "gold", "red")}
    warns: List[str] = []

    total_all = as_non_neg_int(data.get("victor_total_all")) if role == "victor" else as_non_neg_int(data.get("total_all"))
    if total_all is None:
        if role == "victor":
            return {"errors": ["缺少 victor_total_all（维克托紫橙红总件数）"], "warns": warns}
        return {"errors": ["缺少 total_all（总藏品数）"], "warns": warns}

    solved: Dict[str, dict] = empty_solved()
    combos = []
    seen_combos = set()

    if role == "victor":
        high_cases = [(total_all, 0, None)]
    else:
        wg_solution = solve_color("白+绿", get_wg_constraint(data), max_count, total_all, avg_tolerance)
        warns.extend(wg_solution.warns)
        high_cases = []
        for wg_count in wg_solution.counts:
            high_total = total_all - wg_count
            if high_total >= 0:
                high_cases.append((high_total, wg_count, grid_range(wg_solution.pair_map, wg_count)))

    for high_total, candidate_wg_total, wg_range in high_cases:
        local_solved: Dict[str, dict] = {}
        active_colors = ("purple", "gold", "red") if role == "victor" else ("blue", "purple", "gold", "red")
        for color in active_colors:
            solution = solve_color(COLOR_LABELS[color], constraints[color], max_count, high_total, avg_tolerance)
            local_solved[color] = {"counts": solution.counts, "pair_map": solution.pair_map, "warns": solution.warns}
            warns.extend(solution.warns)
            solved[color]["counts"].extend(solution.counts)
            solved[color]["warns"].extend(solution.warns)
            for count, grids in solution.pair_map.items():
                solved[color]["pair_map"].setdefault(count, []).extend(grids)
        if role == "victor":
            local_solved["blue"] = {"counts": [0], "pair_map": {0: [0]}, "warns": []}
            solved["blue"]["counts"].append(0)
            solved["blue"]["pair_map"].setdefault(0, []).append(0)

        if not local_solved["purple"]["counts"] or not local_solved["gold"]["counts"] or (role != "victor" and not local_solved["blue"]["counts"]):
            continue

        red_count_set = set(local_solved["red"]["counts"])
        red_restricted = bool(local_solved["red"]["counts"])
        for blue_count in local_solved["blue"]["counts"]:
            for purple_count in local_solved["purple"]["counts"]:
                for gold_count in local_solved["gold"]["counts"]:
                    red_count = high_total - blue_count - purple_count - gold_count
                    if red_count < 0:
                        continue
                    if red_restricted and red_count not in red_count_set:
                        continue
                    blue_range = (0, 0) if role == "victor" else grid_range(local_solved["blue"]["pair_map"], blue_count)
                    purple_range = grid_range(local_solved["purple"]["pair_map"], purple_count)
                    gold_range = grid_range(local_solved["gold"]["pair_map"], gold_count)
                    red_range = grid_range(local_solved["red"]["pair_map"], red_count)
                    if red_range is None:
                        red_range = (0, 0) if red_count == 0 else (red_count, 18 * red_count)
                    if not blue_range or not purple_range or not gold_range:
                        continue
                    low_wg_grid = wg_range[0] if wg_range else candidate_wg_total
                    high_wg_grid = wg_range[1] if wg_range else candidate_wg_total
                    total_grid_low = blue_range[0] + purple_range[0] + gold_range[0] + red_range[0] + low_wg_grid
                    total_grid_high = blue_range[1] + purple_range[1] + gold_range[1] + red_range[1] + high_wg_grid
                    if total_grid_all is not None and not (total_grid_low <= total_grid_all <= total_grid_high):
                        continue
                    splits = [(0, 0)] if role == "victor" else enumerate_green_white_splits(data, candidate_wg_total)
                    for green_count, white_count in splits:
                        combo_key = (blue_count, purple_count, gold_count, red_count, green_count, white_count)
                        if combo_key in seen_combos:
                            continue
                        seen_combos.add(combo_key)
                        combos.append(
                            {
                                "blue": blue_count,
                                "purple": purple_count,
                                "gold": gold_count,
                                "red": red_count,
                                "green": green_count,
                                "white": white_count,
                                "wg_total": candidate_wg_total,
                                "ranges": {"blue": blue_range, "purple": purple_range, "gold": gold_range, "red": red_range},
                                "total_grid_range": (total_grid_low, total_grid_high),
                            }
                        )

    solved = normalize_solved(solved)
    warns = sorted(set(warns))
    combos.sort(key=lambda combo: (*compare_combo_key(combo), combo["wg_total"]))
    if not combos:
        return {"errors": ["当前约束拼不出有效组合"], "warns": warns, "solved": solved}

    weighted = weighted_stats(dict(data.get("category_weights", {})))
    estimates = [{"combo": combo, "est": estimate_combo(combo, weighted, price_info)} for combo in combos]
    wg_candidates = uniq_sorted(combo["wg_total"] for combo in combos)
    summary = build_summary(data, estimates, combos, round_rule, avg_tolerance, grid_prices)

    return {
        "errors": [],
        "warns": warns,
        "summary": summary,
        "solved": solved,
        "combos_preview": combos[:max_show],
        "info_suggestions": compute_info_suggestions(data, solved, len(combos)),
        "auto_fields_now": fields_known_by_role(role, round_no),
        "role_label": ROLE_LABELS[role],
        "resolved_wg_total": wg_candidates[0] if len(wg_candidates) == 1 else None,
    }


def render_report(data: dict, result: dict) -> str:
    if result.get("errors"):
        lines = ["输入无效："]
        lines.extend(f"- {item}" for item in result["errors"])
        if result.get("warns"):
            lines.append("")
            lines.append("附加警告：")
            lines.extend(f"- {item}" for item in result["warns"])
        return "\n".join(lines)

    summary = result["summary"]
    solved = result["solved"]

    lines = []
    lines.append("竞拍之王手动判断报告")
    lines.append("=" * 26)
    lines.append(f"回合: {data.get('round')} | 角色: {result['role_label']}")
    lines.append("")
    lines.append("核心估值")
    lines.append(f"- 可能最低: {format_w(summary['possible_low_price'])}")
    lines.append(f"- 可能最高: {format_w(summary['possible_high_price'])}")
    lines.append(f"- 保守保底: {format_w(summary['conservative_floor'])}")
    lines.append(f"- 精确底价: {format_w(summary['floor_price'])}")
    lines.append(f"- 平均价格（各估计方式平均）: {format_w(summary['avg_price'])}")
    lines.append(f"- 保守出价（不低于保底）: {format_w(summary['conservative_bid_price'])}")
    lines.append(f"- 均衡出价: {format_w(summary['balanced_bid_price'])}")
    lines.append(f"- 激进出价（平均 +25%）: {format_w(summary['aggressive_bid_price'])}")
    lines.append(
        "- 单格物价: "
        f"绿{summary['grid_prices']['green']:.2f} "
        f"白{summary['grid_prices']['white']:.2f} "
        f"蓝{summary['grid_prices']['blue']:.2f} "
        f"紫{summary['grid_prices']['purple']:.2f} "
        f"橙{summary['grid_prices']['gold']:.2f} "
        f"红{summary['grid_prices']['red']:.2f}"
    )
    lines.append(f"- 平均格容差: ±{summary['avg_tolerance']:.2f}")
    lines.append(f"- 不确定性: {summary['uncertainty']:.1f}/100")
    lines.append(f"- 回合规则: {summary['round_rule']}")
    lines.append(f"- 绿白候选数: {build_count_text(summary['wg_candidates'])}")
    lines.append(f"- 总格子候选: {build_count_text(summary['total_grid_candidates'])}")
    lines.append("")
    lines.append("组合空间")
    lines.append(f"- 有效组合数: {summary['combo_count']}")
    lines.append(f"- 蓝色件数: {build_count_text(solved['blue']['counts'])}")
    lines.append(f"- 紫色件数: {build_count_text(solved['purple']['counts'])}")
    lines.append(f"- 橙色件数: {build_count_text(solved['gold']['counts'])}")
    red_values = uniq_sorted(combo["red"] for combo in result["combos_preview"])
    lines.append(f"- 红色件数预览: {build_count_text(red_values)}")
    lines.append("")
    lines.append("角色当前已知信息")
    if result["auto_fields_now"]:
        for field in result["auto_fields_now"]:
            lines.append(f"- {FIELD_LABELS.get(field, field)}")
    else:
        lines.append("- 当前回合没有角色自动信息")
    lines.append("")
    lines.append("下一条最值得拿的信息")
    if result["info_suggestions"]:
        top = result["info_suggestions"][0]
        lines.append(f"- 首选: {top['label']} (价值分 {top['score']:.2f})")
        lines.append(f"- 原因: {top['reason']}")
        for extra in result["info_suggestions"][1:3]:
            lines.append(f"- 备选: {extra['label']} (价值分 {extra['score']:.2f})")
    else:
        lines.append("- 当前关键信息已经较齐，优先观察排名变化")
    lines.append("")
    lines.append("组合预览")
    for combo in result["combos_preview"][:10]:
        lines.append(
            f"- 绿{combo['green']} 白{combo['white']} | 蓝{combo['blue']} 紫{combo['purple']} 橙{combo['gold']} 红{combo['red']} | "
            f"总格{combo['total_grid_range'][0]}-{combo['total_grid_range'][1]} | "
            f"蓝格{combo['ranges']['blue'][0]}-{combo['ranges']['blue'][1]} "
            f"紫格{combo['ranges']['purple'][0]}-{combo['ranges']['purple'][1]} "
            f"橙格{combo['ranges']['gold'][0]}-{combo['ranges']['gold'][1]} "
            f"红格{combo['ranges']['red'][0]}-{combo['ranges']['red'][1]}"
        )
    return "\n".join(lines)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description="BidKing 融合升级版手动判断脚本")
    parser.add_argument("--input", required=True, help="输入 JSON 文件路径")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON 结果")
    args = parser.parse_args()

    data = load_json(Path(args.input))
    result = evaluate(data)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_report(data, result))
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
