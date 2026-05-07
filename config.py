# config.py
# SHFEMVD -- SHFE Member/OSP Volume, Open Interest Daily Rankings
# All constants, paths, and settings

import os
import json
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR  = os.path.join(BASE_DIR, 'downloads')
OUTPUT_DIR    = os.path.join(BASE_DIR, 'output')
MASTER_DIR    = os.path.join(BASE_DIR, 'Master_data')
MASTER_FILE   = os.path.join(MASTER_DIR, 'MASTER_SHFEMVD_DATA - Sheet73.csv')

# Date tracking file — records which dates have already been scraped
DATE_TRACKER_FILE = os.path.join(BASE_DIR, 'scraped_dates.json')

# ── Timestamped folders ──────────────────────────────────────────────────────
RUN_TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')

DOWNLOAD_RUN_DIR  = os.path.join(DOWNLOAD_DIR, RUN_TIMESTAMP)
OUTPUT_RUN_DIR    = os.path.join(OUTPUT_DIR, RUN_TIMESTAMP)
LATEST_OUTPUT_DIR = os.path.join(OUTPUT_DIR, 'latest')

# ── Source ────────────────────────────────────────────────────────────────────
BASE_URL = 'https://www.shfe.com.cn/eng/reports/StatisticalData/DailyData/'

PROVIDER_NAME = 'SHFE'
DATASET_NAME  = 'SHFEMVD'

# ── Browser ───────────────────────────────────────────────────────────────────
HEADLESS_MODE       = False
WAIT_TIMEOUT        = 60
PAGE_LOAD_DELAY     = 5
DOWNLOAD_WAIT_TIME  = 120
SCROLL_POLL_INTERVAL = 1.0   # seconds between scroll-height checks
SCROLL_STABLE_COUNT  = 5     # consecutive stable checks before considering loaded

# ── Download settings ─────────────────────────────────────────────────────────
MAX_DOWNLOAD_RETRIES = 3
RETRY_DELAY          = 3.0

# ── Date bypass ───────────────────────────────────────────────────────────────
# Set to True to skip the duplicate-date check and force a fresh scrape
BYPASS_DATE_CHECK = False

# ── Target date ───────────────────────────────────────────────────────────────
# Set to a specific date string (e.g. '2026-04-30') to scrape that exact date,
# or None to automatically find the latest unscraped date with data.
TARGET_DATE = None

# ── Output filenames ─────────────────────────────────────────────────────────
RAW_EXCEL_NAME    = 'Daily_Ranking.xlsx'
RAW_CSV_NAME      = 'Daily_Ranking.csv'
DATA_FILE_PATTERN = 'SHFEMVD_DAILY_DATA_{timestamp}.xls'
META_FILE_PATTERN = 'SHFEMVD_DAILY_META_{timestamp}.xls'
ZIP_FILE_PATTERN  = 'SHFEMVD_DAILY_{timestamp}.zip'

# ── Query output columns (matches Power Query output) ────────────────────────
QUERY_OUTPUT_COLUMNS = [
    'Placeholder',
    'CMD',
    'Contract',
    'Date',
    'Metric',
    'Level',
    'Change',
]

# ── Metadata columns ─────────────────────────────────────────────────────────
METADATA_COLUMNS = [
    'CODE',
    'CODE_MNEMONIC',
    'DESCRIPTION',
    'FREQUENCY',
    'MULTIPLIER',
    'AGGREGATION_TYPE',
    'UNIT_TYPE',
    'DATA_TYPE',
    'DATA_UNIT',
    'SEASONALLY_ADJUSTED',
    'ANNUALIZED',
    'PROVIDER_MEASURE_URL',
    'PROVIDER',
    'SOURCE',
    'SOURCE_DESCRIPTION',
    'COUNTRY',
    'DATASET',
]

METADATA_DEFAULTS = {
    'FREQUENCY':            'D',
    'MULTIPLIER':           0.0,
    'AGGREGATION_TYPE':     'END_OF_PERIOD',
    'UNIT_TYPE':            'LEVEL',
    'DATA_TYPE':            'AMOUNT',
    'DATA_UNIT':            'CONTRACTS',
    'SEASONALLY_ADJUSTED':  'N',
    'ANNUALIZED':           'N',
    'PROVIDER_MEASURE_URL': BASE_URL,
    'PROVIDER':             PROVIDER_NAME,
    'SOURCE':               PROVIDER_NAME,
    'SOURCE_DESCRIPTION':   'Shanghai Futures Exchange Member/OSP Volume, Open Interest Rankings',
    'COUNTRY':              'CN',
    'DATASET':              DATASET_NAME,
}


# ── Date tracker helpers ──────────────────────────────────────────────────────

def load_scraped_dates():
    """Load the set of already-scraped date strings from the tracker file."""
    if not os.path.exists(DATE_TRACKER_FILE):
        return set()
    with open(DATE_TRACKER_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return set(data.get('scraped_dates', []))


def save_scraped_date(date_str):
    """Append a date string to the tracker file."""
    dates = load_scraped_dates()
    dates.add(date_str)
    with open(DATE_TRACKER_FILE, 'w', encoding='utf-8') as f:
        json.dump({'scraped_dates': sorted(dates)}, f, indent=2)


def is_date_already_scraped(date_str):
    """Check whether a date has already been scraped."""
    if BYPASS_DATE_CHECK:
        return False
    return date_str in load_scraped_dates()
