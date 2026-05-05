# BidKing Fresh Bot（项目已停止更新）

`BidKing Fresh Bot` 是一个面向 Windows 桌面端《竞拍之王 / BidKing》的 OCR 识别与自动化工具。

这个项目的目标很直接：

- 识别游戏中央信息区
- 将 OCR 文本解析成结构化拍卖信息
- 根据可配置的价格模型计算建议出价
- 按照校准后的窗口坐标完成道具、出价、确认、回合切换等操作

项目同时提供了一个图形界面，方便日常使用时直接修改参数，而不是每次手动改 JSON。

## 主要功能

- 整窗 OCR 轮询，识别当前回合与界面状态
- 解析中央信息区文本并提取拍卖条件
- 根据可配置的单格价格自动计算建议出价
- 按设定回合自动使用道具
- 自动选择地图并循环多轮运行
- 处理“对局结束”、“奖励继续”等过渡界面
- 启动时自动把游戏窗口拉到前台并居中，减少识别和输入失败
- GUI 停止按钮支持立即请求停止

## 项目结构

- `bidking_fresh_bot/bidking_gui.py`
  - 图形界面启动器
- `bidking_fresh_bot/fresh_bidking_bot.py`
  - 主自动化循环
- `bidking_fresh_bot/config.json`
  - 自动化运行配置
- `bidking_fresh_bot/price_config.json`
  - 单格价格与价格模型配置
- `manual_bidking_advisor.py`
  - 价格计算与建议逻辑
- `bidking_maa_test/central_info_parser.py`
  - OCR 文本解析器
- `bidking_maa_test/window_backend.py`
  - Win32 窗口截图与窗口工具
- `bidking_maa_test/analyze_screenshot.py`
  - 基于 ROI 的截图分析工具
- `bidking_maa_test/roi_config.json`
  - ROI 区域配置

## 运行环境

- Windows 10 / Windows 11
- Python 3.11 或 3.12
- 桌面端游戏窗口
- 推荐使用 1920x1080 布局，便于复用默认坐标

## 安装依赖

建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
```

## 从源码运行

启动图形界面：

```powershell
cd .\bidking_fresh_bot
python .\bidking_gui.py
```

也可以使用附带脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\bidking_fresh_bot\start.ps1
```

## 打包 EXE

仓库中已经附带 PyInstaller 打包脚本：

```powershell
cd .\bidking_fresh_bot
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

打包成功后，默认输出位置为：

```text
bidking_fresh_bot\dist\BidKingFreshBot_release.exe
```

## 配置说明

主要配置文件：

- `bidking_fresh_bot/config.json`
- `bidking_fresh_bot/price_config.json`

通常需要根据自己的环境调整这些内容：

- 游戏窗口标题匹配规则
- 点击坐标
- 地图入口坐标
- 哪些回合使用道具
- 轮询与等待时间
- 保底出价
- 各品质单格价格

## 基本使用流程

1. 打开游戏并进入桌面端窗口。
2. 确认游戏窗口标题与 `config.json` 中的 `title_keyword` 匹配。
3. 如果你的布局不同，先校准 `config.json` 内坐标。
4. 启动 GUI。
5. 设置单格价格、地图、轮次和激进度。
6. 点击开始运行。

## 适合开源发布的说明


## 注意事项

- 本项目仅用于学习、研究与个人自动化实验。
- 游戏更新可能会导致 OCR、ROI 或点击坐标失效，需要重新校准。
- 请自行确认在你的使用环境中运行自动化工具是否合适。


## 仓库目录示意

```text
bidking_open_source/
  README.md
  LICENSE
  requirements.txt
  manual_bidking_advisor.py
  bidking_fresh_bot/
    bidking_gui.py
    fresh_bidking_bot.py
    config.json
    price_config.json
    start.ps1
    build_exe.ps1
  bidking_maa_test/
    __init__.py
    central_info_parser.py
    window_backend.py
    analyze_screenshot.py
    roi_config.json
```

## 许可证

本项目使用 MIT License 开源，详见 [LICENSE](./LICENSE)。
