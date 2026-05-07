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
# Step 2: Find a date with data on the calendar
# ─────────────────────────────────────────────────────────────────────────────

def _find_date_with_data(driver):
    """
    Scan the calendar for dates that have data (indicated by the 'budge' class
    marker inside the calendar day cells). Clicks on the most recent date
    that has data. Returns the date string (YYYY-MM-DD) found.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    logger.info('Scanning calendar for dates with data...')

    # Wait for calendar to be visible
    _wait_for(driver, By.CSS_SELECTOR, '.el-calendar',
              description='Calendar widget')
    _human_delay(2.0, 3.0)

    # Get the current month/year from the calendar title.
    # The title may take a moment to render, so poll until non-empty.
    import datetime as dt

    calendar_title = ''
    for _ in range(10):
        title_el = driver.find_element(By.CSS_SELECTOR, '.el-calendar__title')
        calendar_title = title_el.text.strip()
        if calendar_title:
            break
        # Try getting text via JS as fallback
        calendar_title = (driver.execute_script(
            'return arguments[0].textContent;', title_el
        ) or '').strip()
        if calendar_title:
            break
        time.sleep(0.5)

    # If still empty, derive from today's date as fallback
    if not calendar_title:
        now = dt.datetime.now()
        calendar_title = now.strftime('%B %Y')
        logger.warning(f'Calendar title empty — using current month: {calendar_title}')

    logger.info(f'Calendar showing: {calendar_title}')

    # Parse the month/year from the title right away
    parsed_month = dt.datetime.strptime(calendar_title, '%B %Y')

    # Find all "current" month day cells (not prev/next month)
    day_cells = driver.find_elements(
        By.CSS_SELECTOR, 'td.current .el-calendar-day'
    )

    # Determine today's day number for filtering out future dates
    today = dt.datetime.now()
    today_day = today.day
    # Only filter by day if we're looking at the current month
    is_current_month = (
        parsed_month.month == today.month and parsed_month.year == today.year
    )

    # Collect days that have the "budge" marker (red dot = data available)
    days_with_data = []
    for cell in day_cells:
        budge_markers = cell.find_elements(By.CSS_SELECTOR, '.budge')
        if budge_markers:
            # Extract the day number from the <p> tag
            p_tag = cell.find_element(By.TAG_NAME, 'p')
            day_text = p_tag.text.strip().split('\n')[0].strip()
            try:
                day_num = int(day_text)
            except ValueError:
                continue

            # Skip future dates (budge can appear on scheduled future dates)
            if is_current_month and day_num > today_day:
                logger.debug(f'Skipping future date: day {day_num}')
                continue

            days_with_data.append((day_num, cell))

    if not days_with_data:
        raise RuntimeError('No dates with data found on the calendar')

    # Sort by day number descending and pick the most recent
    days_with_data.sort(key=lambda x: x[0], reverse=True)
    target_day, target_cell = days_with_data[0]

    logger.info(f'Found {len(days_with_data)} dates with data. '
                f'Selecting most recent: day {target_day}')

    # Build the full date from parsed month + selected day
    data_date = parsed_month.replace(day=target_day)
    date_str = data_date.strftime('%Y-%m-%d')
    logger.info(f'Target date: {date_str}')

    # Check if already scraped
    if config.is_date_already_scraped(date_str):
        logger.info(f'Date {date_str} already scraped. Skipping.')
        return None

    # Check if the target day is already selected (e.g. today).
    # If so, clicking "Daily Ranking" already triggered data loading for it —
    # we just need to wait. If NOT selected, click it to trigger loading.
    target_td = target_cell.find_element(By.XPATH, './ancestor::td')
    td_classes = target_td.get_attribute('class') or ''
    already_selected = 'is-selected' in td_classes

    if already_selected:
        logger.info(f'Day {target_day} is already selected — '
                     f'data is loading from the Daily Ranking tab click')
    else:
        # Use JS click which is more reliable than Selenium .click()
        driver.execute_script(
            'arguments[0].scrollIntoView({block:"center"});', target_cell
        )
        _human_delay()
        driver.execute_script('arguments[0].click();', target_cell)
        logger.info(f'Clicked calendar day {target_day}')

    # Wait for data to actually load. The site is heavily dynamic (Vue.js) —
    # after clicking "Daily Ranking", a spinner appears then tables render.
    # The POSITIVE signal is "Contract Code" appearing in the page source,
    # which means at least the first table section has rendered.
    logger.info('Waiting for table data to load...')
    data_loaded = False
    for attempt in range(config.WAIT_TIMEOUT):
        time.sleep(1.0)
        page_source = driver.page_source

        # "Contract Code" appears in every loaded table section
        if 'Contract Code' in page_source:
            data_loaded = True
            logger.info(f'Table data detected on page (after {attempt+1}s)')
            break

        if attempt % 10 == 9:
            logger.info(f'Still waiting for data... ({attempt+1}s)')

    if not data_loaded:
        raise RuntimeError(
            f'Table data did not load within {config.WAIT_TIMEOUT}s'
        )

    return date_str


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
