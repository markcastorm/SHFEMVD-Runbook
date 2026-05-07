# scraper.py
# Downloads the SHFE Daily Ranking Excel from the Shanghai Futures Exchange
# website using Selenium stealth. The site is heavily dynamic (Vue.js + Element UI)
# so we must: click "Daily Ranking", find a date with data via the calendar,
# wait for all tables to fully load, then click "Export Excel".

import os
import sys
import time
import glob
import logging
import subprocess
import random
import shutil

import config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Chrome version detection (Windows dev + Linux Docker)
# ─────────────────────────────────────────────────────────────────────────────

def get_chrome_version():
    """Detect Chrome major version -- works on Windows (dev) and Linux (Docker)."""
    if sys.platform == 'win32':
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Google\Chrome\BLBeacon',
            )
            return winreg.QueryValueEx(key, 'version')[0].split('.')[0]
        except Exception:
            pass
    for cmd in ['google-chrome', 'google-chrome-stable',
                'chromium', 'chromium-browser']:
        try:
            out = subprocess.check_output(
                [cmd, '--version'], stderr=subprocess.DEVNULL
            ).decode()
            return out.strip().split()[-1].split('.')[0]
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: wait utilities
# ─────────────────────────────────────────────────────────────────────────────

def _human_delay(lo=0.4, hi=1.2):
    """Small random pause to mimic human speed."""
    time.sleep(random.uniform(lo, hi))


def _wait_and_click(driver, by, value, timeout=None, description='element'):
    """Wait for an element to be clickable, scroll into view, then click."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    timeout = timeout or config.WAIT_TIMEOUT
    wait = WebDriverWait(driver, timeout)
    el = wait.until(EC.element_to_be_clickable((by, value)))
    driver.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    _human_delay()
    el.click()
    logger.debug(f'Clicked: {description}')
    return el


def _wait_for(driver, by, value, timeout=None, description='element'):
    """Wait for element presence and return it."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    timeout = timeout or config.WAIT_TIMEOUT
    wait = WebDriverWait(driver, timeout)
    el = wait.until(EC.presence_of_element_located((by, value)))
    logger.debug(f'Found: {description}')
    return el


def _wait_for_all(driver, by, value, timeout=None, description='elements'):
    """Wait for all matching elements to be present and return them."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    timeout = timeout or config.WAIT_TIMEOUT
    wait = WebDriverWait(driver, timeout)
    els = wait.until(EC.presence_of_all_elements_located((by, value)))
    logger.debug(f'Found {len(els)} {description}')
    return els


# ─────────────────────────────────────────────────────────────────────────────
# Build driver
# ─────────────────────────────────────────────────────────────────────────────

def _build_driver(download_dir):
    """Create a Selenium stealth Chrome driver configured for Excel download."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    try:
        from selenium_stealth import stealth
    except ImportError:
        stealth = None

    abs_dl = os.path.abspath(download_dir)
    os.makedirs(abs_dl, exist_ok=True)

    opts = Options()
    if config.HEADLESS_MODE:
        opts.add_argument('--headless=new')
        opts.add_argument('--disable-gpu')

    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument('--lang=en-US')
    opts.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Safari/537.36'
    )

    prefs = {
        'download.default_directory': abs_dl,
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': False,
        'profile.default_content_settings.popups': 0,
    }
    opts.add_experimental_option('prefs', prefs)
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(config.WAIT_TIMEOUT * 2)

    # Apply selenium-stealth if available
    if stealth is not None:
        stealth(
            driver,
            languages=['en-US', 'en'],
            vendor='Google Inc.',
            platform='Win32',
            webgl_vendor='Intel Inc.',
            renderer='Intel Iris OpenGL Engine',
            fix_hairline=True,
        )
        logger.info('Selenium stealth applied')

    # Suppress navigator.webdriver flag
    driver.execute_cdp_cmd(
        'Page.addScriptToEvaluateOnNewDocument',
        {'source': 'Object.defineProperty(navigator,"webdriver",'
                    '{get:()=>undefined})'},
    )

    # Enable downloads in headless mode
    driver.execute_cdp_cmd(
        'Page.setDownloadBehavior',
        {'behavior': 'allow', 'downloadPath': abs_dl},
    )

    logger.info(f'Chrome driver ready -- download dir: {abs_dl}')
    return driver


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Navigate to page and click "Daily Ranking"
# ─────────────────────────────────────────────────────────────────────────────

def _click_daily_ranking(driver):
    """
    Navigate to the SHFE Statistical Data page and click the
    'Daily Ranking' button/tab.
    """
    from selenium.webdriver.common.by import By

    logger.info(f'Loading SHFE page: {config.BASE_URL}')
    driver.get(config.BASE_URL)
    _human_delay(3.0, 5.0)

    # Wait for the page to fully render (look for the data section)
    _wait_for(driver, By.CSS_SELECTOR, '.sqs_Daily_Link',
              description='Daily link tabs')

    # Find and click "Daily Ranking" link
    # The links are <a> tags inside .sqs_Daily_Link div
    links = driver.find_elements(By.CSS_SELECTOR, '.sqs_Daily_Link a')
    clicked = False
    for link in links:
        text = link.text.strip()
        if 'Daily Ranking' in text:
            driver.execute_script(
                'arguments[0].scrollIntoView({block:"center"});', link
            )
            _human_delay()
            link.click()
            clicked = True
            logger.info('Clicked "Daily Ranking" tab')
            break

    if not clicked:
        raise RuntimeError('"Daily Ranking" link not found on page')

    _human_delay(2.0, 4.0)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Calendar helpers & find a date with data
# ─────────────────────────────────────────────────────────────────────────────

# Month abbreviation ↔ number (matches the date-picker panel labels)
_MONTH_ABBRS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _navigate_to_month(driver, month_abbr):
    """
    Switch the calendar to a different month via the date-picker dropdown
    (.home_calendar_i).  The calendar ‹/› buttons are unreliable ("element
    not interactable"), so we use the month-picker panel instead.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    logger.info(f'Navigating calendar to month: {month_abbr}')

    # Open the date-picker (native click triggers the Vue event binding)
    picker_input = driver.find_element(
        By.CSS_SELECTOR, '.home_calendar_i .el-input__inner'
    )
    driver.execute_script(
        'arguments[0].scrollIntoView({block:"center"});', picker_input
    )
    _human_delay()

    try:
        picker_input.click()
    except Exception:
        try:
            icon = driver.find_element(
                By.CSS_SELECTOR, '.home_calendar_i .el-icon-date'
            )
            icon.click()
        except Exception:
            wrapper = driver.find_element(By.CSS_SELECTOR, '.home_calendar_i')
            driver.execute_script('arguments[0].click();', wrapper)

    _human_delay(1.5, 2.0)

    # Wait for the picker panel to become visible
    try:
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, '.el-picker-panel')
            )
        )
    except Exception:
        # Retry with focus + click
        driver.execute_script(
            'arguments[0].focus(); arguments[0].click();', picker_input
        )
        _human_delay(1.5, 2.0)

    _human_delay(0.5, 1.0)

    # Click the target month cell
    month_cells = driver.find_elements(
        By.CSS_SELECTOR, '.el-month-table .cell'
    )
    for cell in month_cells:
        if cell.text.strip() == month_abbr:
            driver.execute_script('arguments[0].click();', cell)
            logger.info(f'Selected month: {month_abbr}')
            _human_delay(1.5, 2.5)
            return

    found = [c.text.strip() for c in month_cells]
    raise RuntimeError(
        f'Month "{month_abbr}" not found in picker. Available: {found}'
    )


def _scan_calendar_dates(driver):
    """
    Scan the current calendar view for days with the 'budge' red-dot marker.
    Returns a list of (day_num, cell_element) for 'current'-month cells only.
    """
    from selenium.webdriver.common.by import By

    results = []
    cells = driver.find_elements(
        By.CSS_SELECTOR, 'td.current .el-calendar-day'
    )
    for cell in cells:
        if cell.find_elements(By.CSS_SELECTOR, '.budge'):
            p_tag = cell.find_element(By.TAG_NAME, 'p')
            day_text = p_tag.text.strip().split('\n')[0].strip()
            try:
                results.append((int(day_text), cell))
            except ValueError:
                continue
    return results


def _click_day(driver, target_day, day_cells):
    """
    Click a specific day from a pre-scanned list of (day_num, cell) tuples.
    Returns True if clicked, False if the day wasn't in the list.
    """
    for day_num, cell in day_cells:
        if day_num == target_day:
            driver.execute_script(
                'arguments[0].scrollIntoView({block:"center"});', cell
            )
            _human_delay()
            driver.execute_script('arguments[0].click();', cell)
            logger.info(f'Clicked calendar day {target_day}')
            return True
    return False


def _wait_for_table_data(driver, timeout=None):
    """
    Wait for "Contract Code" to appear in the page source (= data loaded).
    Returns True on success, False on timeout (no data for that date).
    Gives the page 2 s to react before the first check.
    """
    timeout = timeout or config.WAIT_TIMEOUT

    logger.info('Waiting for table data to load...')
    time.sleep(2)

    for attempt in range(timeout):
        time.sleep(1.0)
        if 'Contract Code' in driver.page_source:
            logger.info(f'Table data detected (after {attempt + 3}s)')
            return True
        if attempt % 10 == 9:
            logger.info(f'Still waiting for data... ({attempt + 3}s)')

    logger.info(f'No data loaded within {timeout + 2}s')
    return False


def _find_date_with_data(driver):
    """
    Find a date with downloadable data on the calendar.

    Behaviour depends on config.TARGET_DATE:
      • If set (e.g. '2026-04-30') → navigate to that exact month, click that
        day, and wait for data.  Raises if data doesn't load.
      • If None → automatically search for the latest unscraped date.
        Starts from the current month and works backwards (up to 3 months)
        using the date-picker to switch months.  Skips dates that are already
        in scraped_dates.json.  If a clicked date's data doesn't load within
        the timeout, logs it and tries the next candidate.

    Returns the date string 'YYYY-MM-DD' on success, or None when every
    available date has already been scraped.
    """
    from selenium.webdriver.common.by import By
    import datetime as dt

    logger.info('Scanning calendar for dates with data...')

    # Wait for calendar widget
    _wait_for(driver, By.CSS_SELECTOR, '.el-calendar',
              description='Calendar widget')
    _human_delay(2.0, 3.0)

    today = dt.date.today()

    # ── Specific date mode ────────────────────────────────────────────────
    if config.TARGET_DATE is not None:
        target = dt.datetime.strptime(config.TARGET_DATE, '%Y-%m-%d').date()
        target_month_abbr = _MONTH_ABBRS[target.month - 1]

        # Navigate to the target month (always navigate to be safe)
        _navigate_to_month(driver, target_month_abbr)

        # Scan and click the target day
        day_cells = _scan_calendar_dates(driver)
        day_nums = [d for d, _ in day_cells]
        logger.info(f'Dates with data in {target_month_abbr}: {day_nums}')

        if not _click_day(driver, target.day, day_cells):
            # Day exists on calendar but has no budge marker — click anyway
            logger.warning(
                f'Day {target.day} has no budge marker — clicking anyway'
            )
            all_cells = driver.find_elements(
                By.CSS_SELECTOR, 'td.current .el-calendar-day'
            )
            for cell in all_cells:
                p_tag = cell.find_element(By.TAG_NAME, 'p')
                txt = p_tag.text.strip().split('\n')[0].strip()
                try:
                    if int(txt) == target.day:
                        driver.execute_script(
                            'arguments[0].scrollIntoView({block:"center"});',
                            cell,
                        )
                        _human_delay()
                        driver.execute_script('arguments[0].click();', cell)
                        logger.info(f'Clicked day {target.day} (no budge)')
                        break
                except ValueError:
                    continue

        if not _wait_for_table_data(driver):
            raise RuntimeError(
                f'No data loaded for target date {config.TARGET_DATE}'
            )

        return config.TARGET_DATE

    # ── Auto mode: check current month for the latest unscraped date ─────
    day_cells = _scan_calendar_dates(driver)
    day_nums = sorted([d for d, _ in day_cells], reverse=True)
    logger.info(f'Dates with data on calendar: {day_nums}')

    if not day_nums:
        logger.info('No dates with data found on calendar — '
                     'no new data available yet')
        return None

    # Filter out future dates
    day_nums = [d for d in day_nums if d <= today.day]

    # Try each day, most recent first
    for day_num in day_nums:
        date_str = dt.date(today.year, today.month, day_num).isoformat()

        if config.is_date_already_scraped(date_str):
            logger.info(f'{date_str} already scraped — skipping')
            continue

        # Re-scan cells (DOM may refresh after previous attempts)
        day_cells = _scan_calendar_dates(driver)
        if not _click_day(driver, day_num, day_cells):
            logger.warning(f'Could not click day {day_num} — skipping')
            continue

        if _wait_for_table_data(driver):
            logger.info(f'Data loaded for {date_str}')
            return date_str

        # Data didn't load — budge marker present but data not ready yet
        logger.info(
            f'{date_str}: no data loaded (data not available yet) — '
            f'trying next date'
        )

    # All dates with markers are either already scraped or have no data yet
    logger.info('No new data available yet — all dates already scraped '
                'or data not published')
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Wait for all tables to fully load
# ─────────────────────────────────────────────────────────────────────────────

def _wait_for_tables_to_load(driver):
    """
    The SHFE page loads tables dynamically as you scroll. We scroll to the
    bottom of the page and monitor document.body.scrollHeight. When it
    stabilises for several consecutive checks, all tables are loaded.
    """
    from selenium.webdriver.common.by import By

    logger.info('Waiting for all tables to load (scroll-based detection)...')

    # First ensure at least one table/contract section is visible
    _wait_for(driver, By.CSS_SELECTOR, '.el-table',
              timeout=config.WAIT_TIMEOUT,
              description='First data table')

    _human_delay(1.0, 2.0)

    prev_height = 0
    stable_count = 0
    max_iterations = 120  # safety cap

    for i in range(max_iterations):
        # Scroll to the absolute bottom of the page
        driver.execute_script(
            'window.scrollTo(0, document.body.scrollHeight);'
        )
        time.sleep(config.SCROLL_POLL_INTERVAL)

        current_height = driver.execute_script(
            'return document.body.scrollHeight;'
        )

        if current_height == prev_height:
            stable_count += 1
            logger.debug(f'Scroll height stable: {current_height} '
                         f'({stable_count}/{config.SCROLL_STABLE_COUNT})')
        else:
            stable_count = 0
            logger.debug(f'Scroll height changed: {prev_height} -> '
                         f'{current_height}')

        prev_height = current_height

        if stable_count >= config.SCROLL_STABLE_COUNT:
            logger.info(f'All tables loaded (scroll height stabilised at '
                        f'{current_height} after {i+1} iterations)')
            return

    logger.warning(f'Scroll monitoring hit max iterations ({max_iterations}). '
                   f'Proceeding with current content.')


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Click "Export Excel" and wait for download
# ─────────────────────────────────────────────────────────────────────────────

def _click_export_excel(driver, download_dir):
    """
    Click the 'Export Excel' button and wait for the .xlsx file to appear
    in the download directory.
    """
    from selenium.webdriver.common.by import By

    logger.info('Clicking "Export Excel" button...')

    # Scroll back to the top where the Export Excel button is
    driver.execute_script('window.scrollTo(0, 0);')
    _human_delay(1.0, 2.0)

    # Find the Export Excel button
    # Structure: <div class="sqs_Contract_Excel"><img ...> <span>Export Excel</span></div>
    export_btn = None

    # Try CSS selector first
    try:
        export_btn = driver.find_element(
            By.CSS_SELECTOR, '.sqs_Contract_Excel'
        )
    except Exception:
        pass

    # Fallback: find by text content
    if export_btn is None:
        spans = driver.find_elements(By.TAG_NAME, 'span')
        for span in spans:
            if 'Export Excel' in span.text:
                export_btn = span.find_element(By.XPATH, '..')
                break

    if export_btn is None:
        raise RuntimeError('"Export Excel" button not found')

    # Record existing files before clicking
    existing_files = set(os.listdir(download_dir)) if os.path.exists(download_dir) else set()

    driver.execute_script(
        'arguments[0].scrollIntoView({block:"center"});', export_btn
    )
    _human_delay()
    export_btn.click()
    logger.info('Export Excel clicked -- waiting for download...')

    # Wait for a new .xlsx file to appear
    deadline = time.time() + config.DOWNLOAD_WAIT_TIME
    downloaded_file = None

    while time.time() < deadline:
        time.sleep(1.0)
        if not os.path.exists(download_dir):
            continue

        current_files = set(os.listdir(download_dir))
        new_files = current_files - existing_files

        for f in new_files:
            full_path = os.path.join(download_dir, f)
            # Skip partial downloads (.crdownload, .tmp)
            if f.endswith('.crdownload') or f.endswith('.tmp'):
                continue
            if f.endswith('.xlsx') or f.endswith('.xls'):
                # Verify file size is stable (not still downloading)
                size1 = os.path.getsize(full_path)
                time.sleep(1.0)
                size2 = os.path.getsize(full_path)
                if size1 == size2 and size1 > 0:
                    downloaded_file = full_path
                    break

        if downloaded_file:
            break

    if downloaded_file is None:
        raise RuntimeError(
            f'Download did not complete within {config.DOWNLOAD_WAIT_TIME}s'
        )

    file_size = os.path.getsize(downloaded_file)
    logger.info(f'Downloaded: {os.path.basename(downloaded_file)} '
                f'({file_size:,} bytes)')
    return downloaded_file


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Convert XLSX to CSV
# ─────────────────────────────────────────────────────────────────────────────

def _convert_xlsx_to_csv(xlsx_path, download_dir):
    """
    Convert the downloaded .xlsx file to CSV format using openpyxl/pandas.
    Returns the CSV file path.
    """
    import pandas as pd

    logger.info(f'Converting {os.path.basename(xlsx_path)} to CSV...')

    # Read with openpyxl (the file has no proper headers — raw dump)
    df = pd.read_excel(xlsx_path, header=None, engine='openpyxl')

    csv_path = os.path.join(download_dir, config.RAW_CSV_NAME)
    df.to_csv(csv_path, index=False, header=False, encoding='utf-8-sig')

    logger.info(f'CSV saved: {csv_path}')
    return csv_path


# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Extract date from the downloaded file
# ─────────────────────────────────────────────────────────────────────────────

def _extract_date_from_csv(csv_path):
    """
    Scan the CSV file for a date string in the format 'Date: YYYY-MM-DD'.
    Returns the date string (YYYY-MM-DD) or raises if not found.
    """
    import re

    logger.info('Extracting date from downloaded CSV...')

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        for line_num, line in enumerate(f, 1):
            match = re.search(r'Date:\s*(\d{4}-\d{2}-\d{2})', line)
            if match:
                date_str = match.group(1)
                logger.info(f'Found date: {date_str} (line {line_num})')
                return date_str
            if line_num > 20:
                break

    raise RuntimeError('Could not find "Date: YYYY-MM-DD" in the CSV file')


# ─────────────────────────────────────────────────────────────────────────────
# Main download function
# ─────────────────────────────────────────────────────────────────────────────

def download():
    """
    Full scraping pipeline:
    1. Launch stealth Chrome
    2. Navigate to SHFE Statistical Data page
    3. Click "Daily Ranking"
    4. Find and click a date with data on the calendar
    5. Wait for all tables to load (scroll-based)
    6. Click "Export Excel" and wait for download
    7. Convert XLSX to CSV
    8. Extract and validate the date
    Returns (csv_path, date_str) or raises on failure.
    """
    download_dir = config.DOWNLOAD_RUN_DIR
    os.makedirs(download_dir, exist_ok=True)

    driver = None
    try:
        # Step 0: Build driver
        driver = _build_driver(download_dir)

        # Step 1: Navigate and click Daily Ranking
        _click_daily_ranking(driver)

        # Step 2: Find date with data
        date_str = _find_date_with_data(driver)
        if date_str is None:
            logger.info('No new data to scrape (all available dates '
                        'already processed)')
            return None, None

        # Step 3: Wait for all tables to load
        _wait_for_tables_to_load(driver)

        # Step 4: Export Excel
        xlsx_path = _click_export_excel(driver, download_dir)

        # Step 5: Convert to CSV
        csv_path = _convert_xlsx_to_csv(xlsx_path, download_dir)

        # Step 6: Extract and validate date
        file_date = _extract_date_from_csv(csv_path)
        if file_date != date_str:
            logger.warning(f'Calendar date ({date_str}) differs from file '
                           f'date ({file_date}). Using file date.')
            date_str = file_date

        logger.info(f'Scraping complete: {csv_path} (date: {date_str})')
        return csv_path, date_str

    finally:
        if driver:
            try:
                driver.quit()
                logger.info('Browser closed')
            except Exception:
                pass
