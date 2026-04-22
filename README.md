# BidKing Fresh Bot

A Windows desktop automation toolkit for the PC game **BidKing / 竞拍之王**.

This project focuses on a practical desktop workflow:

- OCR the central information area
- parse auction facts into structured inputs
- compute a recommended bid
- interact with the game window using calibrated coordinates

It also includes a small GUI for day-to-day use, so the bot can be configured without manually editing JSON every round.

## What It Can Do

- Full-window OCR polling for round detection and state transitions
- Central-info parsing into structured auction facts
- Automatic bid calculation from configurable per-grid prices
- Automatic tool usage on configured rounds
- Automatic map entry and round-loop automation
- End-of-round transition handling
- Reward / continue screen handling
- Foreground recovery and startup centering of the game window
- Stop button with immediate stop request behavior

## Included Components

- `bidking_fresh_bot/bidking_gui.py`
  - Tkinter GUI launcher
- `bidking_fresh_bot/fresh_bidking_bot.py`
  - main OCR + automation loop
- `bidking_fresh_bot/config.json`
  - runtime automation configuration
- `bidking_fresh_bot/price_config.json`
  - price model configuration
- `manual_bidking_advisor.py`
  - pricing / recommendation engine
- `bidking_maa_test/central_info_parser.py`
  - OCR text parser
- `bidking_maa_test/window_backend.py`
  - Win32 capture and window utilities
- `bidking_maa_test/analyze_screenshot.py`
  - ROI-based screenshot analysis helper
- `bidking_maa_test/roi_config.json`
  - ROI definitions

## System Requirements

- Windows 10 or Windows 11
- Python 3.11 or 3.12 recommended
- Desktop game client workflow
- 1920x1080 layout recommended for easiest calibration reuse

## Install

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
```

## Run From Source

Launch the GUI:

```powershell
cd .\bidking_fresh_bot
python .\bidking_gui.py
```

Or use the helper script:

```powershell
powershell -ExecutionPolicy Bypass -File .\bidking_fresh_bot\start.ps1
```

## Build EXE

The repository includes a PyInstaller build script:

```powershell
cd .\bidking_fresh_bot
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

If successful, the packaged executable will be generated under:

```text
bidking_fresh_bot\dist\BidKingFreshBot_release.exe
```

## Configuration

Main configuration files:

- `bidking_fresh_bot/config.json`
- `bidking_fresh_bot/price_config.json`

Typical values you may want to edit:

- game window title match rules
- round timings
- click coordinates
- tool usage rounds
- map selection points
- fallback bid price
- per-quality grid prices

## Typical Workflow

1. Open the game and enter the normal desktop client.
2. Make sure the game window title matches the `title_keyword` in `config.json`.
3. Adjust coordinates in `config.json` if your layout differs.
4. Launch the GUI.
5. Set prices, map, run count, and risk mode.
6. Start the bot.

## Open-Source Release Notes

This repository is prepared as a source release:

- local build outputs are excluded
- runtime caches are excluded
- machine-specific package paths were removed from the release version of the build script

## Warnings

- This project is for educational and personal automation research.
- Game updates may break OCR assumptions, ROI layout, or click coordinates.
- You are responsible for checking whether using automation is acceptable in your own environment.

## Development Notes

The current implementation is intentionally practical rather than abstract:

- OCR and parsing are optimized around a specific desktop workflow
- much of the automation logic is coordinate-driven
- configuration is designed for quick iteration instead of large framework complexity

## Repository Structure

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

## License

This project is released under the MIT License. See [LICENSE](./LICENSE).
