# test_calendar_nav.py
# Standalone test script to perfect SHFE calendar navigation.
# Uses the date-picker dropdown (.home_calendar_i) to navigate months,
# since the calendar ‹/› buttons are "element not interactable".
#
# Tests:
#   1. Scan current month for budge markers
#   2. Click day 6 in May and check for data
#   3. Navigate to April via the date-picker month panel
#   4. Scan April for budge markers and click day 30
#   5. Navigate back to May via date-picker
#   6. Click day 7 (today) and confirm no data
#
# Run: python test_calendar_nav.py

import os
import sys
import time
import random
import logging
import datetime as dt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

try:
    from selenium_stealth import stealth
except ImportError:
    stealth = None

BASE_URL = 'https://www.shfe.com.cn/eng/reports/StatisticalData/DailyData/'

# Month abbreviation to number mapping for the date-picker panel
MONTH_MAP = {
    'Jan': 1, 'Feb': 2,  'Mar': 3,  'Apr': 4,
    'May': 5, 'Jun': 6,  'Jul': 7,  'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _human_delay(lo=0.4, hi=1.2):
    time.sleep(random.uniform(lo, hi))


def build_driver():
    """Create a visible (non-headless) Chrome driver for testing."""
    opts = Options()
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
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(120)

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

    driver.execute_cdp_cmd(
        'Page.addScriptToEvaluateOnNewDocument',
        {'source': 'Object.defineProperty(navigator,"webdriver",'
                    '{get:()=>undefined})'},
    )
    logger.info('Chrome driver ready')
    return driver


def click_daily_ranking(driver):
    """Navigate to the SHFE page and click 'Daily Ranking'."""
    logger.info(f'Loading SHFE page: {BASE_URL}')
    driver.get(BASE_URL)
    _human_delay(3.0, 5.0)

    WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, '.sqs_Daily_Link'))
    )

    links = driver.find_elements(By.CSS_SELECTOR, '.sqs_Daily_Link a')
    for link in links:
        if 'Daily Ranking' in link.text.strip():
            driver.execute_script(
                'arguments[0].scrollIntoView({block:"center"});', link
            )
            _human_delay()
            link.click()
            logger.info('Clicked "Daily Ranking" tab')
            break
    else:
        raise RuntimeError('"Daily Ranking" link not found')

    _human_delay(2.0, 4.0)


# ── Calendar reading ─────────────────────────────────────────────────────────

def get_calendar_title(driver):
    """Read current month/year from the calendar header (e.g. 'May 2026')."""
    for _ in range(10):
        title_el = driver.find_element(By.CSS_SELECTOR, '.el-calendar__title')
        text = (title_el.text or driver.execute_script(
            'return arguments[0].textContent;', title_el
        ) or '').strip()
        if text:
            return text
        time.sleep(0.5)
    raise RuntimeError('Could not read calendar title')


def get_dates_with_data(driver, include_prev=False):
    """
    Scan calendar for dates with the 'budge' red-dot marker.
    Returns list of (day_num, cell_element, cell_type).
    cell_type: 'current' or 'prev'.
    """
    results = []

    for cell_type in ['current'] + (['prev'] if include_prev else []):
        cells = driver.find_elements(
            By.CSS_SELECTOR, f'td.{cell_type} .el-calendar-day'
        )
        for cell in cells:
            if cell.find_elements(By.CSS_SELECTOR, '.budge'):
                p_tag = cell.find_element(By.TAG_NAME, 'p')
                day_text = p_tag.text.strip().split('\n')[0].strip()
                try:
                    results.append((int(day_text), cell, cell_type))
                except ValueError:
                    continue

    return results


# ── Date-picker month navigation ─────────────────────────────────────────────

def navigate_to_month(driver, target_month_abbr):
    """
    Use the date-picker dropdown (.home_calendar_i) to switch the calendar
    to a different month.

    Steps:
      1. Click the date-picker input to open the panel
      2. The month table (.el-month-table) shows Jan–Dec
      3. Click the cell whose text matches target_month_abbr (e.g. 'Apr')
      4. Wait for the main calendar to refresh

    target_month_abbr: 'Jan','Feb','Mar','Apr','May','Jun',
                       'Jul','Aug','Sep','Oct','Nov','Dec'
    """
    logger.info(f'Navigating to month: {target_month_abbr}')

    # Step 1: Click the date-picker input to open the dropdown panel.
    # Element UI needs a native click (not JS) to trigger the Vue event binding.
    # We try multiple targets: the input itself, then the icon, then the wrapper.
    picker_input = driver.find_element(
        By.CSS_SELECTOR, '.home_calendar_i .el-input__inner'
    )
    driver.execute_script(
        'arguments[0].scrollIntoView({block:"center"});', picker_input
    )
    _human_delay()

    # Try native click first
    try:
        picker_input.click()
        logger.info('Clicked date-picker input (native click)')
    except Exception:
        # Fallback: click the date icon
        try:
            icon = driver.find_element(
                By.CSS_SELECTOR, '.home_calendar_i .el-icon-date'
            )
            icon.click()
            logger.info('Clicked date-picker icon (fallback)')
        except Exception:
            # Last resort: JS click on wrapper
            wrapper = driver.find_element(By.CSS_SELECTOR, '.home_calendar_i')
            driver.execute_script('arguments[0].click();', wrapper)
            logger.info('Clicked date-picker wrapper (JS fallback)')

    _human_delay(1.5, 2.0)

    # Step 2: Wait for the picker panel to become visible.
    # The panel may already exist in DOM but be hidden, so check visibility.
    try:
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, '.el-picker-panel')
            )
        )
        logger.info('Date-picker panel is visible')
    except Exception:
        # Debug: check if panel exists but is hidden
        panels = driver.find_elements(By.CSS_SELECTOR, '.el-picker-panel')
        logger.warning(f'Panel wait timed out. Found {len(panels)} panel elements in DOM.')
        if panels:
            for i, p in enumerate(panels):
                displayed = p.is_displayed()
                style = p.get_attribute('style') or ''
                logger.warning(f'  Panel {i}: displayed={displayed}, style={style[:100]}')
        # Try clicking the input again with JS as last resort
        driver.execute_script('arguments[0].focus(); arguments[0].click();', picker_input)
        _human_delay(1.5, 2.0)

    _human_delay(0.5, 1.0)

    # Step 3: Find the month table and click the target month.
    # The month table has cells with <a class="cell">Apr</a> etc.
    month_cells = driver.find_elements(
        By.CSS_SELECTOR, '.el-month-table .cell'
    )
    logger.info(f'Found {len(month_cells)} month cells')

    clicked = False
    for cell in month_cells:
        cell_text = cell.text.strip()
        if cell_text == target_month_abbr:
            driver.execute_script('arguments[0].click();', cell)
            logger.info(f'Clicked month: {target_month_abbr}')
            clicked = True
            break

    if not clicked:
        found = [c.text.strip() for c in month_cells]
        logger.error(f'Month "{target_month_abbr}" not found. Available: {found}')
        raise RuntimeError(f'Month "{target_month_abbr}" not found in picker')

    _human_delay(1.5, 2.5)

    # Step 4: Verify the calendar title updated
    new_title = get_calendar_title(driver)
    logger.info(f'Calendar now shows: {new_title}')
    return new_title


def navigate_to_year_month(driver, target_year, target_month_abbr):
    """
    Navigate to a specific year + month using the date-picker.

    Steps:
      1. Click date-picker input to open panel (shows month table)
      2. Click the year label (e.g. '2026') to switch to year table
      3. Click target year
      4. Click target month
    """
    logger.info(f'Navigating to: {target_month_abbr} {target_year}')

    # Step 1: Open date-picker (same approach as navigate_to_month)
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
        driver.execute_script('arguments[0].click();', picker_input)
    _human_delay(1.5, 2.0)

    try:
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, '.el-picker-panel')
            )
        )
    except Exception:
        driver.execute_script('arguments[0].focus(); arguments[0].click();', picker_input)
        _human_delay(1.5, 2.0)
    _human_delay(0.5, 1.0)

    # Step 2: Click the year header label to show the year table
    year_label = driver.find_element(
        By.CSS_SELECTOR, '.el-date-picker__header-label'
    )
    driver.execute_script('arguments[0].click();', year_label)
    logger.info('Clicked year label to show year table')
    _human_delay(0.5, 1.0)

    # Step 3: Click the target year
    year_cells = driver.find_elements(
        By.CSS_SELECTOR, '.el-year-table .cell'
    )
    for cell in year_cells:
        if cell.text.strip() == str(target_year):
            driver.execute_script('arguments[0].click();', cell)
            logger.info(f'Selected year: {target_year}')
            break
    else:
        raise RuntimeError(f'Year {target_year} not found in year table')
    _human_delay(0.5, 1.0)

    # Step 4: Now the month table should be visible — click target month
    month_cells = driver.find_elements(
        By.CSS_SELECTOR, '.el-month-table .cell'
    )
    for cell in month_cells:
        if cell.text.strip() == target_month_abbr:
            driver.execute_script('arguments[0].click();', cell)
            logger.info(f'Selected month: {target_month_abbr}')
            break
    else:
        raise RuntimeError(f'Month {target_month_abbr} not found')

    _human_delay(1.5, 2.5)
    new_title = get_calendar_title(driver)
    logger.info(f'Calendar now shows: {new_title}')
    return new_title


# ── Calendar day clicking ─────────────────────────────────────────────────────

def click_calendar_day(driver, target_day, cell_type='current'):
    """
    Click a specific day number on the main calendar.
    cell_type: 'current' for current month, 'prev' for previous month cells.
    Returns True if clicked, False if not found.
    """
    selector = f'td.{cell_type} .el-calendar-day'
    cells = driver.find_elements(By.CSS_SELECTOR, selector)

    for cell in cells:
        p_tag = cell.find_element(By.TAG_NAME, 'p')
        day_text = p_tag.text.strip().split('\n')[0].strip()
        try:
            day_num = int(day_text)
        except ValueError:
            continue

        if day_num == target_day:
            driver.execute_script(
                'arguments[0].scrollIntoView({block:"center"});', cell
            )
            _human_delay()
            driver.execute_script('arguments[0].click();', cell)
            logger.info(f'Clicked day {target_day} (cell_type={cell_type})')
            return True

    logger.warning(f'Day {target_day} not found in {cell_type} cells')
    return False


# ── Data detection ────────────────────────────────────────────────────────────

def wait_for_data(driver, timeout=20):
    """
    After clicking a calendar day, wait for table data to load.
    Returns True if 'Contract Code' appears (data loaded).
    Returns False if timeout or explicit no-data message detected.

    Important: waits 2s before first check to let the page react to the
    day click (avoids reading stale page content).
    """
    logger.info(f'Waiting up to {timeout}s for table data...')

    # Give the page a moment to react to the click before checking
    time.sleep(2)

    for i in range(timeout):
        time.sleep(1.0)
        page_source = driver.page_source

        if 'Contract Code' in page_source:
            logger.info(f'Data loaded after {i + 3}s')
            return True

        if i % 5 == 4:
            logger.info(f'Still waiting... ({i + 3}s)')

    logger.info(f'No data loaded within {timeout + 2}s')
    return False


# ── Test Functions ────────────────────────────────────────────────────────────

def test_1_scan_current_month(driver):
    """TEST 1: Show all budge markers on the current month view."""
    logger.info('=' * 60)
    logger.info('TEST 1: Scan current month for dates with data')
    logger.info('=' * 60)

    title = get_calendar_title(driver)
    logger.info(f'Calendar: {title}')

    dates = get_dates_with_data(driver, include_prev=True)
    if dates:
        logger.info(f'Found {len(dates)} dates with budge markers:')
        for day, _, ctype in dates:
            logger.info(f'  Day {day} ({ctype})')
    else:
        logger.info('No dates with budge markers found')

    logger.info('TEST 1 COMPLETE')
    return dates


def test_2_click_day_6(driver):
    """TEST 2: Click day 6 in the current month and check data."""
    logger.info('=' * 60)
    logger.info('TEST 2: Click day 6 in current month')
    logger.info('=' * 60)

    success = click_calendar_day(driver, 6, 'current')
    if success:
        data_loaded = wait_for_data(driver, timeout=20)
        if data_loaded:
            logger.info('TEST 2 RESULT: Day 6 — DATA LOADED')
        else:
            logger.info('TEST 2 RESULT: Day 6 — NO DATA')
    else:
        logger.info('TEST 2 RESULT: Day 6 not found')
    return success


def test_3_navigate_to_april(driver):
    """TEST 3: Navigate to April using the date-picker dropdown."""
    logger.info('=' * 60)
    logger.info('TEST 3: Navigate to April via date-picker')
    logger.info('=' * 60)

    before = get_calendar_title(driver)
    navigate_to_month(driver, 'Apr')
    after = get_calendar_title(driver)

    if 'April' in after or 'Apr' in after:
        logger.info(f'TEST 3 RESULT: SUCCESS — {before} -> {after}')
        return True
    else:
        logger.info(f'TEST 3 RESULT: UNEXPECTED — calendar shows: {after}')
        return False


def test_4_scan_april_and_click_30(driver):
    """TEST 4: Scan April for budge markers and click day 30."""
    logger.info('=' * 60)
    logger.info('TEST 4: Scan April and click day 30')
    logger.info('=' * 60)

    title = get_calendar_title(driver)
    logger.info(f'Calendar: {title}')

    dates = get_dates_with_data(driver, include_prev=False)
    if dates:
        logger.info(f'April dates with budge markers:')
        for day, _, ctype in dates:
            logger.info(f'  Day {day} ({ctype})')
    else:
        logger.info('No budge markers in April')

    success = click_calendar_day(driver, 30, 'current')
    if success:
        data_loaded = wait_for_data(driver, timeout=25)
        if data_loaded:
            logger.info('TEST 4 RESULT: April 30 — DATA LOADED')
        else:
            logger.info('TEST 4 RESULT: April 30 — NO DATA')
    else:
        logger.info('TEST 4 RESULT: Day 30 not found in April')
    return success


def test_5_navigate_back_to_may(driver):
    """TEST 5: Navigate back to May via date-picker."""
    logger.info('=' * 60)
    logger.info('TEST 5: Navigate back to May via date-picker')
    logger.info('=' * 60)

    navigate_to_month(driver, 'May')
    after = get_calendar_title(driver)

    if 'May' in after:
        logger.info(f'TEST 5 RESULT: SUCCESS — back to {after}')
        return True
    else:
        logger.info(f'TEST 5 RESULT: UNEXPECTED — {after}')
        return False


def test_6_detect_no_data_day_7(driver):
    """TEST 6: Click day 7 (today) and confirm no data loads."""
    logger.info('=' * 60)
    logger.info('TEST 6: Click day 7 (today) — expect no data')
    logger.info('=' * 60)

    success = click_calendar_day(driver, 7, 'current')
    if success:
        data_loaded = wait_for_data(driver, timeout=15)
        if data_loaded:
            logger.info('TEST 6 RESULT: Day 7 HAS data (unexpected)')
        else:
            logger.info('TEST 6 RESULT: Day 7 NO DATA (expected)')
    return success


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    logger.info('=== SHFE Calendar Navigation Test ===')
    driver = None
    results = {}

    try:
        driver = build_driver()
        click_daily_ranking(driver)

        # Wait for calendar
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.el-calendar'))
        )
        _human_delay(2.0, 3.0)

        # Run all tests
        results['test_1'] = test_1_scan_current_month(driver)
        _human_delay(2.0, 3.0)

        results['test_2'] = test_2_click_day_6(driver)
        _human_delay(2.0, 3.0)

        results['test_3'] = test_3_navigate_to_april(driver)
        _human_delay(2.0, 3.0)

        results['test_4'] = test_4_scan_april_and_click_30(driver)
        _human_delay(2.0, 3.0)

        results['test_5'] = test_5_navigate_back_to_may(driver)
        _human_delay(2.0, 3.0)

        results['test_6'] = test_6_detect_no_data_day_7(driver)

        logger.info('=' * 60)
        logger.info('ALL TESTS COMPLETE — Summary:')
        for name, result in results.items():
            status = 'PASS' if result else 'FAIL/NONE'
            logger.info(f'  {name}: {status}')
        logger.info('=' * 60)

        # Keep browser open for inspection
        logger.info('Browser stays open 30s for inspection...')
        time.sleep(30)

    except Exception as e:
        logger.error(f'Test failed: {e}', exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
                logger.info('Browser closed')
            except Exception:
                pass


if __name__ == '__main__':
    main()
