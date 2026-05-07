# CLAUDE.md — SHFEMVD Runbook Developer Context

This file gives an AI assistant (or new developer) full context on the SHFEMVD pipeline so you never need to re-read every source file.

## What This Project Does

Scrapes the **SHFE (Shanghai Futures Exchange)** "Daily Ranking" data from their English website, transforms it into a standardised SIMBA pipeline format, and outputs DATA/META/ZIP files plus an updated master CSV.

- **Source URL:** `https://www.shfe.com.cn/eng/reports/StatisticalData/DailyData/`
- **Data:** Member/OSP Volume, Long Position, and Short Position totals per futures contract (cu, al, zn, pb, ni, sn, au, ag, rb, wr, hc, ss, fu, lu, bu, ru, nr, sp, ao, br, ec, bc)
- **Frequency:** Daily (published on trading days, typically by late morning Beijing time)
- **Output format:** Matches the Power Query output from `Query_v3.1 (SHFEMVD).xlsx`

## Project Structure

```
SHFEMVD-Runbook/
├── main.py              # Entry point: sys.exit(orchestrator.main())
├── orchestrator.py      # Wires: download → extract → generate. Handles logging.
├── config.py            # All constants, paths, settings, date tracker helpers
├── scraper.py           # Selenium stealth scraper: navigate SHFE, find date, export Excel
├── extractor.py         # Parse raw CSV → standardised DataFrame (Volume/Long/Short totals)
├── file_generator.py    # Create DATA.xls, META.xls, ZIP, update master CSV
├── scraped_dates.json   # Tracks which dates have been scraped (prevents duplicates)
├── test_calendar_nav.py # Standalone test script for calendar navigation (not part of pipeline)
├── Master_data/         # Master CSV (cumulative, new rows prepended on top)
├── downloads/           # Timestamped raw downloads (XLSX → CSV)
├── output/              # Timestamped output folders + 'latest/' symlink
│   ├── YYYYMMDD_HHMMSS/  # DATA.xls, META.xls, ZIP, combined CSV
│   └── latest/            # Always has the most recent output files
└── Project_information/ # Reference docs, sample files, screenshots, conversation log
```

## Pipeline Flow (orchestrator.py)

```
main.py → orchestrator.main()
  Step 1: scraper.download()        → (csv_path, date_str) or (None, None)
  Step 2: extractor.extract()       → DataFrame [Placeholder, CMD, Contract, Date, Metric, Level, Change]
  Step 3: file_generator.generate() → DATA.xls + META.xls + ZIP + CSV, update master
  Step 4: config.save_scraped_date() → record date in scraped_dates.json
```

If `download()` returns `(None, None)`, the pipeline exits with "No new data available" (exit code 0, not an error).

## Key File Details

### config.py
- All paths are absolute, computed from `BASE_DIR` (project root)
- `RUN_TIMESTAMP` — generated once at import time, used for folder names
- `TARGET_DATE` — set to `'YYYY-MM-DD'` to scrape a specific date, or `None` for auto (latest unscraped)
- `BYPASS_DATE_CHECK` — set `True` to force re-scrape even if date is in `scraped_dates.json`
- `HEADLESS_MODE` — `False` by default (shows browser window for debugging)
- `WAIT_TIMEOUT` — 60s for table data detection
- Date tracker helpers: `load_scraped_dates()`, `save_scraped_date()`, `is_date_already_scraped()`

### scraper.py
The most complex file. The SHFE site is a Vue.js + Element UI SPA. Key challenges:
- **Anti-bot:** Uses selenium-stealth, custom user-agent, suppresses navigator.webdriver
- **Calendar navigation:** The calendar `‹`/`›` buttons are "element not interactable". We use the **date-picker dropdown** (`.home_calendar_i`) instead — click input → picker panel opens with month table (`.el-month-table`) → click month abbreviation (Jan/Feb/Mar/etc.)
- **Calendar title is unreliable:** After navigating via the date-picker, `.el-calendar__title` may still show the old month. Don't rely on it — verify by scanning budge markers instead.
- **Budge markers:** Red dots (`.budge` class inside `.el-calendar-day` cells) indicate dates that have data. But a budge marker does NOT guarantee data will load — data may not be published yet (e.g. early morning runs).
- **Data detection:** Wait for `'Contract Code'` string in `driver.page_source`. Returns `True`/`False` instead of crashing.
- **Auto mode (TARGET_DATE=None):** Scans current month's budge markers, tries most recent first, skips already-scraped dates. If all are scraped or data not ready, returns `None` gracefully.
- **Specific mode (TARGET_DATE='2026-04-30'):** Navigates to that month via date-picker, clicks the day, waits for data. Raises if data doesn't load.

Important functions:
- `_navigate_to_month(driver, 'Apr')` — date-picker based month switching
- `_scan_calendar_dates(driver)` — returns `[(day_num, cell_element), ...]` for current-month cells with budge markers
- `_click_day(driver, day_num, day_cells)` — JS-click a specific day
- `_wait_for_table_data(driver, timeout)` — polls for 'Contract Code', returns bool
- `_find_date_with_data(driver)` — main orchestrator for date selection (auto or specific)
- `_wait_for_tables_to_load(driver)` — scroll-based detection: scrolls to bottom, monitors `scrollHeight` stabilisation
- `_click_export_excel(driver, download_dir)` — clicks Export Excel button, waits for .xlsx file

### extractor.py
Parses the raw CSV (converted from XLSX). Structure per contract:
```
Contract Code：cu2605
Date: 2026-05-07
Ranking, Name, Volume, Change, Ranking, Name, Long, Change, Ranking, Name, Short, Change
1, MemberA, 1234, +56, ...
...
20, MemberT, ...
Total, , 50000, +200, Total, , 40000, -100, Total, , 45000, +150
```
Extracts only the **Total** rows. Skips `*all` sections (e.g. `cuall`).
Output: 3 rows per contract (Volume, Long Position, Short Position) × N contracts.
Date format: `M/D/YYYY` (no zero-padding, matching Power Query output).

### file_generator.py
- **DATA.xls** — new day's rows only (using xlwt, .xls format for SIMBA compatibility)
- **META.xls** — single metadata row with dataset info (CODE, FREQUENCY, PROVIDER, etc.)
- **ZIP** — bundles DATA + META
- **Output CSV** — full combined data (new + historical master)
- **Master CSV update** — new rows prepended on top of existing master
- Files go to `output/YYYYMMDD_HHMMSS/` AND copied to `output/latest/`

## SHFE Website Specifics

- **URL:** `https://www.shfe.com.cn/eng/reports/StatisticalData/DailyData/`
- **Framework:** Vue.js + Element UI
- **Calendar widget:** `.el-calendar` with `.el-calendar__title`, `.el-calendar-day` cells
- **Date picker:** `.home_calendar_i` (class `el-date-editor--month`)
  - Opens picker panel: `.el-picker-panel`
  - Month table: `.el-month-table .cell` (text: Jan, Feb, Mar, ...)
  - Year table: `.el-year-table .cell` (text: 2020, 2021, ...)
- **Data available indicator:** `<div class="budge"></div>` inside day cells (red dot)
- **Current month cells:** `td.current .el-calendar-day`
- **Previous month cells:** `td.prev .el-calendar-day`
- **Selected/today:** `td.is-selected`, `td.is-today`
- **Daily Ranking tab:** `.sqs_Daily_Link a` containing text "Daily Ranking"
- **Export button:** `.sqs_Contract_Excel` or `<span>Export Excel</span>`
- **Data loaded signal:** `'Contract Code'` appears in page source
- **Data publishing time:** Typically available by late morning Beijing time. Early morning runs may find budge markers but no actual data.

## Common Operations

### Run the pipeline (auto mode)
```bash
python main.py
```

### Scrape a specific past date
Edit `config.py`:
```python
TARGET_DATE = '2026-04-30'
```
Then `python main.py`. Reset to `None` after.

### Force re-scrape an already-scraped date
Edit `config.py`:
```python
BYPASS_DATE_CHECK = True
TARGET_DATE = '2026-05-06'  # or None for latest
```

### Check what's been scraped
```bash
cat scraped_dates.json
```

### Test calendar navigation without running the full pipeline
```bash
python test_calendar_nav.py
```

## Dependencies
- Python 3.11+
- selenium, selenium-stealth
- pandas, openpyxl, xlwt
- Chrome browser + ChromeDriver (auto-managed by selenium)

## Known Issues / Gotchas
1. **Calendar title doesn't update** after date-picker navigation — the `.el-calendar__title` still shows the old month. The pipeline works around this by checking budge markers instead.
2. **Budge marker ≠ data ready** — a date can have a red dot but `'Contract Code'` never appears in the page. The pipeline handles this gracefully (logs and skips).
3. **Chrome GCM errors** — `PHONE_REGISTRATION_ERROR` and `DEPRECATED_ENDPOINT` errors in the console are Chrome internals and harmless.
4. **TensorFlow Lite XNNPACK** — Chrome loads this for internal features. Harmless.
5. **Early morning runs** — SHFE typically publishes daily ranking data by late morning Beijing time. Running too early will find no new data.
