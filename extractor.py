# extractor.py
# Parses the raw Daily_Ranking CSV downloaded from SHFE and transforms it
# into the standardised SHFEMVD output format, replicating the Power Query
# logic from Query_v3.1 (SHFEMVD).xlsx.
#
# Raw CSV structure (per contract section):
#   "Contract Code：cu2605"   (header row with date)
#   20 ranked member rows     (Ranking, Name, Volume, Change, ... x3 metrics)
#   "Total" row               (Total, , Volume, Change, Total, , Long, Change, Total, , Short, Change)
#
# Output columns: Placeholder, CMD, Contract, Date, Metric, Level, Change
# Grouped: all Volume rows first, then all Long Position, then all Short Position.

import os
import re
import logging
import pandas as pd

import config

logger = logging.getLogger(__name__)


def _parse_contract_code(text):
    """
    Parse a contract code line like 'Contract Code：cu2605' or 'Contract Code：cuall'.
    Returns (commodity, contract_num) e.g. ('cu', '2605') or ('cu', 'all').
    Returns None if the line doesn't match.
    """
    # Handle both full-width and half-width colons
    match = re.search(r'Contract\s+Code[：:]\s*([a-zA-Z]+)(\w+)', text)
    if match:
        commodity = match.group(1).lower()
        contract_num = match.group(2)
        return commodity, contract_num
    return None


def _format_date(date_str):
    """
    Convert YYYY-MM-DD to M/D/YYYY (no zero-padding) to match Power Query output.
    e.g. '2026-05-06' -> '5/6/2026'
    """
    from datetime import datetime
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return f'{dt.month}/{dt.day}/{dt.year}'


def extract(csv_path, date_str):
    """
    Parse the raw Daily_Ranking CSV and transform it into the SHFEMVD
    output format (replicating the Power Query logic).

    Args:
        csv_path: Path to the raw CSV file
        date_str: Date string in YYYY-MM-DD format (extracted from file)

    Returns:
        pd.DataFrame with columns: Placeholder, CMD, Contract, Date, Metric, Level, Change
    """
    logger.info(f'Extracting data from: {csv_path}')

    formatted_date = _format_date(date_str)

    # Read the raw CSV as plain text lines for parsing
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    # Parse each contract section and extract Total rows
    volume_rows = []
    long_rows = []
    short_rows = []

    current_commodity = None
    current_contract = None
    in_contract_section = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check for contract code header
        parsed = _parse_contract_code(stripped)
        if parsed:
            commodity, contract_num = parsed
            # Skip "all" summary sections (e.g. cuall, alall)
            if contract_num.lower() == 'all':
                current_commodity = None
                current_contract = None
                in_contract_section = False
                continue

            current_commodity = commodity
            current_contract = contract_num
            in_contract_section = True
            continue

        # Look for the Total row within a contract section
        if in_contract_section and current_commodity and stripped.startswith('Total'):
            parts = stripped.split(',')

            # The Total row structure (12 columns):
            # Total, , Volume_Total, Volume_Change,
            # Total, , Long_Total, Long_Change,
            # Total, , Short_Total, Short_Change
            try:
                # Volume: columns index 2, 3 (after "Total,,")
                vol_level = _safe_int(parts[2]) if len(parts) > 2 else 0
                vol_change = _safe_int(parts[3]) if len(parts) > 3 else 0

                # Long Position: columns index 6, 7 (after second "Total,,")
                long_level = _safe_int(parts[6]) if len(parts) > 6 else 0
                long_change = _safe_int(parts[7]) if len(parts) > 7 else 0

                # Short Position: columns index 10, 11 (after third "Total,,")
                short_level = _safe_int(parts[10]) if len(parts) > 10 else 0
                short_change = _safe_int(parts[11]) if len(parts) > 11 else 0

                volume_rows.append({
                    'Placeholder': 1,
                    'CMD': current_commodity,
                    'Contract': current_contract,
                    'Date': formatted_date,
                    'Metric': 'Volume',
                    'Level': vol_level,
                    'Change': vol_change,
                })

                long_rows.append({
                    'Placeholder': 1,
                    'CMD': current_commodity,
                    'Contract': current_contract,
                    'Date': formatted_date,
                    'Metric': 'Long Position',
                    'Level': long_level,
                    'Change': long_change,
                })

                short_rows.append({
                    'Placeholder': 1,
                    'CMD': current_commodity,
                    'Contract': current_contract,
                    'Date': formatted_date,
                    'Metric': 'Short Position',
                    'Level': short_level,
                    'Change': short_change,
                })

                logger.debug(f'Parsed {current_commodity}{current_contract}: '
                             f'Vol={vol_level}, Long={long_level}, '
                             f'Short={short_level}')

            except (IndexError, ValueError) as e:
                logger.warning(f'Failed to parse Total row for '
                               f'{current_commodity}{current_contract}: {e}')

            # Reset — we've consumed this contract section
            in_contract_section = False
            current_commodity = None
            current_contract = None

    # Combine: Volume first, then Long Position, then Short Position
    all_rows = volume_rows + long_rows + short_rows

    if not all_rows:
        logger.error('No data extracted from the CSV file')
        return pd.DataFrame(columns=config.QUERY_OUTPUT_COLUMNS)

    df = pd.DataFrame(all_rows, columns=config.QUERY_OUTPUT_COLUMNS)

    logger.info(f'Extracted {len(df)} rows '
                f'({len(volume_rows)} Volume, {len(long_rows)} Long, '
                f'{len(short_rows)} Short) '
                f'from {len(volume_rows)} contracts')
    return df


def _safe_int(value):
    """Convert a string to int, stripping whitespace. Returns 0 if empty/invalid."""
    if value is None:
        return 0
    s = str(value).strip()
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        # Try float -> int for values like "1234.0"
        try:
            return int(float(s))
        except ValueError:
            return 0
