# SHFEMVD Runbook

Automated daily scraper and data pipeline for the **Shanghai Futures Exchange (SHFE) Member/OSP Volume, Open Interest Daily Rankings**.

## Overview

This pipeline scrapes the SHFE English website, downloads the Daily Ranking Excel file, transforms it to match the SIMBA Power Query output format, and generates standardised DATA/META/ZIP output files.

**Source:** https://www.shfe.com.cn/eng/reports/StatisticalData/DailyData/

**Output per run:**
- `SHFEMVD_DAILY_DATA_<timestamp>.xls` — day's extracted data (76 contracts x 3 metrics = 228 rows)
- `SHFEMVD_DAILY_META_<timestamp>.xls` — dataset metadata
- `SHFEMVD_DAILY_<timestamp>.zip` — bundle of DATA + META
- `SHFEMVD_DATA.csv` — full combined data (new + historical)
- Master CSV updated with new rows prepended on top

## Quick Start

### Prerequisites

- Python 3.11+
- Google Chrome (latest)

### Install Dependencies

```bash
pip install selenium selenium-stealth pandas openpyxl xlwt
```

### Run

```bash
python main.py
```

The pipeline will:
1. Open Chrome (visible by default)
2. Navigate to the SHFE Daily Ranking page
3. Find the latest date with data that hasn't been scraped yet
4. Wait for all tables to load, export the Excel file
5. Transform the data and generate output files
6. Update the master CSV and record the date in `scraped_dates.json`

## Configuration

All settings are in `config.py`:

### Key Settings

| Setting | Default | Description |
|---|---|---|
| `TARGET_DATE` | `None` | Set to `'YYYY-MM-DD'` (e.g. `'2026-04-30'`) to scrape a specific date. `None` = auto-detect latest unscraped. |
| `BYPASS_DATE_CHECK` | `False` | Set `True` to force re-scrape a date already in `scraped_dates.json` |
| `HEADLESS_MODE` | `False` | Set `True` to run Chrome without a visible window |
| `WAIT_TIMEOUT` | `60` | Seconds to wait for table data to load |
| `DOWNLOAD_WAIT_TIME` | `120` | Seconds to wait for Excel file download |

### Examples

**Scrape a specific past date:**
```python
# config.py
TARGET_DATE = '2026-04-30'
```

**Re-scrape an already processed date:**
```python
# config.py
BYPASS_DATE_CHECK = True
TARGET_DATE = '2026-05-06'
```

**Run headless (no browser window):**
```python
# config.py
HEADLESS_MODE = True
```

## Project Structure

```
SHFEMVD-Runbook/
├── main.py              # Entry point
├── orchestrator.py      # Pipeline orchestration (download → extract → generate)
├── config.py            # All settings and constants
├── scraper.py           # Selenium scraper (SHFE website navigation + download)
├── extractor.py         # Raw CSV → standardised DataFrame transformation
├── file_generator.py    # Output file generation (DATA/META/ZIP/CSV/Master)
├── scraped_dates.json   # Date tracker (prevents duplicate scrapes)
├── test_calendar_nav.py # Calendar navigation test script (development tool)
│
├── Master_data/
│   └── MASTER_SHFEMVD_DATA - Sheet73.csv   # Cumulative master data
│
├── downloads/
│   └── YYYYMMDD_HHMMSS/                    # Raw downloads per run
│       ├── Daily_Ranking.xlsx
│       └── Daily_Ranking.csv
│
├── output/
│   ├── YYYYMMDD_HHMMSS/                    # Output files per run
│   │   ├── SHFEMVD_DAILY_DATA_<ts>.xls
│   │   ├── SHFEMVD_DAILY_META_<ts>.xls
│   │   ├── SHFEMVD_DAILY_<ts>.zip
│   │   └── SHFEMVD_DATA.csv
│   └── latest/                              # Always has most recent output
│
└── Project_information/                     # Reference docs, samples, screenshots
```

## Pipeline Steps

### Step 1: Scrape (`scraper.py`)
- Launches stealth Chrome with anti-detection measures
- Navigates to SHFE Statistical Data → Daily Ranking tab
- Scans the calendar for dates with red-dot indicators (budge markers)
- If `TARGET_DATE` is set: navigates to that specific month/day
- If `TARGET_DATE` is `None`: picks the most recent unscraped date
- Waits for "Contract Code" to appear in page (data loaded signal)
- Scrolls to trigger lazy-loading of all contract tables
- Clicks "Export Excel" and waits for the .xlsx download
- Converts XLSX to CSV

### Step 2: Extract (`extractor.py`)
- Parses the raw CSV looking for `Contract Code：<code>` headers
- Extracts the **Total** row from each contract section
- Produces 3 rows per contract: Volume, Long Position, Short Position
- Skips summary sections (e.g. `cuall`, `alall`)
- Date formatted as `M/D/YYYY` (no zero-padding, matching Power Query)

### Step 3: Generate (`file_generator.py`)
- Creates DATA.xls (new data only, .xls format for SIMBA)
- Creates META.xls (dataset metadata row)
- Bundles into ZIP
- Creates combined CSV (new + all historical data)
- Copies everything to `output/latest/`
- Updates the master CSV (new rows prepended on top)

### Step 4: Record
- Adds the scraped date to `scraped_dates.json`

## Date Tracking

The `scraped_dates.json` file prevents duplicate scrapes:

```json
{
  "scraped_dates": [
    "2026-05-06",
    "2026-05-07"
  ]
}
```

- When `TARGET_DATE = None`, the pipeline skips any date already in this list
- To re-scrape a date: set `BYPASS_DATE_CHECK = True` in config
- To reset: edit or delete `scraped_dates.json`

## Calendar Navigation

The SHFE website uses an Element UI calendar with a Vue.js date-picker. Key technical details:

- **Calendar `‹`/`›` buttons don't work** with Selenium (element not interactable)
- **Solution:** The pipeline uses the **date-picker dropdown** (`.home_calendar_i`) to switch months — click the input, wait for the picker panel, click the month abbreviation (Jan, Feb, Mar, etc.)
- **Red dots (budge markers)** indicate dates with data, but data may not be ready yet (published later in the day)
- **Calendar title is unreliable** — may not update after picker navigation. The pipeline verifies by scanning budge markers instead.

## Troubleshooting

### "Table data did not load within 60s"
- SHFE publishes data by late morning Beijing time. If running early, try again later.
- The pipeline now handles this gracefully — it logs "no data available yet" instead of crashing.

### "No new data available"
- All dates with data in the current month have already been scraped.
- Check `scraped_dates.json` to see what's been processed.
- To scrape a past date: set `TARGET_DATE` in config.

### Chrome errors in console
- `PHONE_REGISTRATION_ERROR`, `DEPRECATED_ENDPOINT` — Chrome internal GCM errors, harmless.
- `TensorFlow Lite XNNPACK` — Chrome internal, harmless.

### "element not interactable"
- Calendar navigation buttons are covered/too small. The pipeline uses the date-picker dropdown instead. If you see this in the test script, it's expected for the `‹`/`›` buttons.

### Download doesn't complete
- Increase `DOWNLOAD_WAIT_TIME` in config (default 120s).
- Check the `downloads/` folder for `.crdownload` partial files.

## Data Format

### Output Columns (matches Power Query)

| Column | Type | Example |
|---|---|---|
| Placeholder | int | `1` |
| CMD | str | `cu` |
| Contract | str | `2605` |
| Date | str | `5/7/2026` |
| Metric | str | `Volume` / `Long Position` / `Short Position` |
| Level | int | `453692` |
| Change | int | `-12345` |

### Contracts Covered
All SHFE-listed futures: cu, al, zn, pb, ni, sn, au, ag, rb, wr, hc, ss, fu, lu, bu, ru, nr, sp, ao, br, ec, bc (76 individual contract months per day, varies).
