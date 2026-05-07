# orchestrator.py
# Wires the full SHFEMVD pipeline: download → extract → generate.

import sys
import logging

import config
from scraper import download
from extractor import extract
from file_generator import FileGenerator

logger = logging.getLogger(__name__)


def main():
    """Run the full pipeline. Returns 0 on success, 1 on failure."""
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Silence noisy third-party loggers
    for noisy in ('selenium', 'selenium.webdriver', 'urllib3',
                   'urllib3.connectionpool'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        logger.info('=== SHFEMVD pipeline started ===')
        logger.info(f'Timestamp: {config.RUN_TIMESTAMP}')
        logger.info(f'Source:    {config.BASE_URL}')
        logger.info(f'Master:   {config.MASTER_FILE}')

        # ── Step 1: Download ─────────────────────────────────────────────
        logger.info('Step 1: Scraping SHFE Daily Ranking...')
        csv_path, date_str = download()

        if csv_path is None:
            logger.info('No new data available — pipeline finished (nothing to do)')
            return 0

        logger.info(f'Downloaded: {csv_path} (date: {date_str})')

        # ── Step 2: Extract / Transform ──────────────────────────────────
        logger.info('Step 2: Extracting and transforming data...')
        df = extract(csv_path, date_str)

        if df.empty:
            logger.error('No data extracted — aborting')
            return 1

        logger.info(f'Extracted {len(df)} rows')

        # ── Step 3: Generate output files ────────────────────────────────
        logger.info('Step 3: Generating output files...')
        generator = FileGenerator()
        output_files = generator.generate_files(df, config.OUTPUT_RUN_DIR)

        # ── Step 4: Record scraped date ──────────────────────────────────
        config.save_scraped_date(date_str)
        logger.info(f'Date {date_str} recorded in tracker')

        # ── Summary ──────────────────────────────────────────────────────
        logger.info('=== SHFEMVD pipeline completed successfully ===')
        logger.info(f'Output dir:  {config.OUTPUT_RUN_DIR}')
        logger.info(f'Latest dir:  {config.LATEST_OUTPUT_DIR}')
        logger.info(f'DATA: {output_files["data_file"]}')
        logger.info(f'META: {output_files["meta_file"]}')
        logger.info(f'ZIP:  {output_files["zip_file"]}')
        logger.info(f'CSV:  {output_files["csv_file"]}')

        return 0

    except Exception as e:
        logger.exception(f'Pipeline failed: {e}')
        return 1
