#!/usr/bin/env python3
from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import fresh_bidking_bot as bot


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
PRICE_CONFIG_PATH = ROOT / "price_config.json"

MAP_KEYS = ("1", "2", "3", "4", "5", "6", "7")
RISK_OPTIONS = {
    "保守": 1.20,
    "均衡": 1.40,
    "激进": 1.60,
}


class GuiLogger:
    def __init__(self, write_line):
        self.write_line = write_line

    def __call__(self, message: str) -> None:
        self.write_line(message)


class BidKingApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("竞拍之王助手")
        self.root.geometry("840x760")

        self.worker: threading.Thread | None = None
        self.stop_requested = False
        self.original_log = bot.log
        bot.log = GuiLogger(self.append_log)

        self.config = self.load_json(CONFIG_PATH)
        self.price_config = self.load_json(PRICE_CONFIG_PATH)

        self.price_vars: dict[str, tk.StringVar] = {}
        self.map_var = tk.StringVar()
        self.runs_var = tk.StringVar()
        self.risk_var = tk.StringVar()
        self.tool_slot_hint = tk.StringVar(value="道具一号位良品存量，二号位普品存量")

        self.build_ui()
        self.load_into_form()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def save_json(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        top = ttk.Frame(main)
        top.pack(fill="x")

        prices_box = ttk.LabelFrame(top, text="1. 单格价格设置", padding=10)
        prices_box.pack(side="left", fill="both", expand=True, padx=(0, 8))

        fields = [
            ("green", "绿色"),
            ("white", "白色"),
            ("blue", "蓝色"),
            ("purple", "紫色"),
            ("gold", "橙色"),
            ("red", "红色"),
        ]
        for idx, (key, label) in enumerate(fields):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(prices_box, text=f"{label}单格价").grid(row=row, column=col, sticky="w", padx=(0, 6), pady=4)
            var = tk.StringVar()
            self.price_vars[key] = var
            ttk.Entry(prices_box, textvariable=var, width=12).grid(row=row, column=col + 1, sticky="w", pady=4)

        settings_box = ttk.LabelFrame(top, text="2. 选图与重复轮数", padding=10)
        settings_box.pack(side="left", fill="both", expand=True)

        ttk.Label(settings_box, text="地图").grid(row=0, column=0, sticky="w", pady=4)
        self.map_combo = ttk.Combobox(settings_box, textvariable=self.map_var, state="readonly", width=20)
        self.map_combo["values"] = [f"{k}. {self.config['automation']['maps'][k]['name']}" for k in MAP_KEYS]
        self.map_combo.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(settings_box, text="重复次数").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(settings_box, textvariable=self.runs_var, width=10).grid(row=1, column=1, sticky="w", pady=4)

        risk_box = ttk.LabelFrame(main, text="6. 拍卖激进度", padding=10)
        risk_box.pack(fill="x", pady=(10, 0))
        ttk.Label(risk_box, text="模式").pack(side="left")
        risk_combo = ttk.Combobox(risk_box, textvariable=self.risk_var, state="readonly", width=12)
        risk_combo["values"] = list(RISK_OPTIONS.keys())
        risk_combo.pack(side="left", padx=(8, 12))
        ttk.Label(risk_box, text="保守最高价=平均价上浮20%，均衡40%，激进60%").pack(side="left")

        hint_box = ttk.LabelFrame(main, text="5. 提示", padding=10)
        hint_box.pack(fill="x", pady=(10, 0))
        ttk.Label(hint_box, textvariable=self.tool_slot_hint).pack(anchor="w")

        button_box = ttk.LabelFrame(main, text="3 / 4. 控制", padding=10)
        button_box.pack(fill="x", pady=(10, 0))
        self.start_btn = ttk.Button(button_box, text="开启", command=self.start_bot)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(button_box, text="停止", command=self.stop_bot)
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.stop_btn.state(["disabled"])

        log_box = ttk.LabelFrame(main, text="运行日志 / Debug", padding=10)
        log_box.pack(fill="both", expand=True, pady=(10, 0))
        self.log_text = tk.Text(log_box, height=20, wrap="word")
        self.log_text.pack(fill="both", expand=True)

    def load_into_form(self) -> None:
        grid_prices = self.price_config.get("grid_prices", {})
        for key, var in self.price_vars.items():
            var.set(str(grid_prices.get(key, 0.0)))

        default_map = str(self.config.get("automation", {}).get("default_map", "4"))
        self.map_var.set(f"{default_map}. {self.config['automation']['maps'][default_map]['name']}")
        self.runs_var.set(str(self.config.get("automation", {}).get("default_runs", 1)))
        self.risk_var.set("均衡")

    def append_log(self, message: str) -> None:
        def _write():
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
        self.root.after(0, _write)

    def selected_map_key(self) -> str:
        text = self.map_var.get().strip()
        return text.split(".", 1)[0].strip() if "." in text else text

    def apply_form_to_config(self) -> None:
        runs_value = int(self.runs_var.get()) if self.runs_var.get().isdigit() and int(self.runs_var.get()) > 0 else 1
        selected_map = self.selected_map_key() or "4"
        selected_risk = self.risk_var.get().strip() or "均衡"

        for key, var in self.price_vars.items():
            try:
                self.price_config.setdefault("grid_prices", {})[key] = float(var.get())
            except ValueError:
                raise ValueError(f"{key} 单格价格不是有效数字")

        self.config.setdefault("automation", {})
        self.config["automation"]["selected_map"] = selected_map
        self.config["automation"]["selected_runs"] = runs_value
        self.config["automation"]["selected_risk"] = selected_risk

        self.save_json(CONFIG_PATH, self.config)
        self.save_json(PRICE_CONFIG_PATH, self.price_config)

    def start_bot(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("提示", "脚本已经在运行中")
            return
        try:
            self.apply_form_to_config()
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return

        self.stop_requested = False
        bot.reset_stop()
        self.start_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self.append_log("GUI start: bot thread launching")

        def runner():
            try:
                bot.run_loop(CONFIG_PATH)
            except bot.StopRequested:
                self.append_log("GUI stop: stopped")
            except Exception:
                self.append_log(traceback.format_exc())
            finally:
                self.root.after(0, self.on_worker_done)

        self.worker = threading.Thread(target=runner, daemon=True)
        self.worker.start()

    def stop_bot(self) -> None:
        bot.request_stop()
        self.stop_btn.state(["disabled"])
        self.append_log("GUI stop: requested")

    def on_worker_done(self) -> None:
        self.start_btn.state(["!disabled"])
        self.stop_btn.state(["disabled"])

    def on_close(self) -> None:
        bot.request_stop()
        bot.log = self.original_log
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    app = BidKingApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
