# file_generator.py
# Generate DATA (.xls), META (.xls), ZIP output files for SHFEMVD.
# Also updates the master CSV with new daily data (prepended on top).

import os
import shutil
import zipfile
import logging

import xlwt
import pandas as pd

import config

logger = logging.getLogger(__name__)


def _force_int_columns(df):
    """
    Force Placeholder, Level, and Change columns to integer type.
    pandas can promote ints to floats during concat — this reverses that.
    """
    for col in ('Placeholder', 'Level', 'Change'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    return df


class FileGenerator:
    """
    Generates SIMBA-standard output files:
      - DATA file: query output (Placeholder, CMD, Contract, Date, Metric, Level, Change)
      - META file: dataset metadata
      - ZIP file: contains both DATA and META
      - Master CSV: cumulative data with new entries prepended on top
    Output goes to timestamped folder + 'latest' folder.
    """

    def __init__(self):
        self.logger = logger

    # ─────────────────────────────────────────────────────────────────────
    # DATA file
    # ─────────────────────────────────────────────────────────────────────

    def create_data_file(self, df, output_path):
        """
        Create the DATA Excel file from the extracted DataFrame.

        Layout:
            Row 0: Placeholder | CMD | Contract | Date | Metric | Level | Change
            Row 1+: data rows
        """
        self.logger.info('Creating DATA file...')

        workbook = xlwt.Workbook()
        sheet = workbook.add_sheet('DATA')

        # Header row
        for col_idx, col_name in enumerate(config.QUERY_OUTPUT_COLUMNS):
            sheet.write(0, col_idx, col_name)

        # Data rows
        for row_idx, (_, row) in enumerate(df.iterrows()):
            for col_idx, col_name in enumerate(config.QUERY_OUTPUT_COLUMNS):
                value = row[col_name]
                if isinstance(value, (int, float)):
                    sheet.write(row_idx + 1, col_idx, value)
                else:
                    sheet.write(row_idx + 1, col_idx, str(value))

        workbook.save(output_path)

        self.logger.info(f'DATA file saved: {output_path}  |  {len(df)} rows')
        return output_path

    # ─────────────────────────────────────────────────────────────────────
    # META file
    # ─────────────────────────────────────────────────────────────────────

    def create_meta_file(self, output_path):
        """Create the META Excel file with dataset metadata."""
        self.logger.info('Creating META file...')

        workbook = xlwt.Workbook()
        sheet = workbook.add_sheet('META')

        # Header row
        for col_idx, col_name in enumerate(config.METADATA_COLUMNS):
            sheet.write(0, col_idx, col_name)

        # Single metadata row for the dataset
        row_data = {
            'CODE':                 f'{config.DATASET_NAME}.DAILY.D',
            'CODE_MNEMONIC':        f'{config.DATASET_NAME}.DAILY',
            'DESCRIPTION':          'SHFE Member/OSP Volume, Open Interest Rankings',
        }
        # Fill defaults
        for key, value in config.METADATA_DEFAULTS.items():
            if key not in row_data:
                row_data[key] = value

        for col_idx, col_name in enumerate(config.METADATA_COLUMNS):
            value = row_data.get(col_name, '')
            sheet.write(1, col_idx, value)

        workbook.save(output_path)
        self.logger.info(f'META file saved: {output_path}')
        return output_path

    # ─────────────────────────────────────────────────────────────────────
    # ZIP file
    # ─────────────────────────────────────────────────────────────────────

    def create_zip_file(self, data_file, meta_file, zip_path):
        """Bundle DATA and META files into a single ZIP."""
        self.logger.info(f'Creating ZIP: {zip_path}')

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(data_file, os.path.basename(data_file))
            zf.write(meta_file, os.path.basename(meta_file))

        self.logger.info('ZIP created')
        return zip_path

    # ─────────────────────────────────────────────────────────────────────
    # Master CSV update
    # ─────────────────────────────────────────────────────────────────────

    def update_master(self, new_df):
        """
        Prepend new data on top of the existing master CSV.
        This is cumulative data — new records go at the top.
        """
        master_path = config.MASTER_FILE
        self.logger.info(f'Updating master: {master_path}')

        os.makedirs(os.path.dirname(master_path), exist_ok=True)

        if os.path.exists(master_path):
            existing_df = pd.read_csv(master_path)
            # Prepend new data on top
            combined_df = pd.concat([new_df, existing_df], ignore_index=True)
        else:
            combined_df = new_df.copy()

        # Ensure numeric columns stay as integers (no .0 floats)
        combined_df = _force_int_columns(combined_df)

        combined_df.to_csv(master_path, index=False)

        self.logger.info(f'Master updated: {len(new_df)} new rows prepended, '
                         f'{len(combined_df)} total rows')

    # ─────────────────────────────────────────────────────────────────────
    # Output CSV (for timestamped + latest folders)
    # ─────────────────────────────────────────────────────────────────────

    def create_output_csv(self, df, output_dir):
        """Save the extracted DataFrame as CSV in the output directory."""
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, f'{config.DATASET_NAME}_DATA.csv')
        df.to_csv(csv_path, index=False)
        self.logger.info(f'Output CSV saved: {csv_path}')
        return csv_path

    # ─────────────────────────────────────────────────────────────────────
    # Generate all outputs
    # ─────────────────────────────────────────────────────────────────────

    def generate_files(self, df, output_dir):
        """
        Generate DATA, META, ZIP, and output CSV files.
        Copy to 'latest' folder. Update master CSV.

        Args:
            df: Extracted DataFrame (query output format)
            output_dir: timestamped output directory

        Returns:
            dict with paths to all created files
        """
        os.makedirs(output_dir, exist_ok=True)

        # Build the full combined dataset: new data on top of existing master
        master_path = config.MASTER_FILE
        if os.path.exists(master_path):
            existing_df = pd.read_csv(master_path)
            combined_df = pd.concat([df, existing_df], ignore_index=True)
            combined_df = _force_int_columns(combined_df)
            self.logger.info(f'Combined {len(df)} new + {len(existing_df)} '
                             f'existing = {len(combined_df)} total rows')
        else:
            combined_df = df.copy()
            self.logger.info(f'No existing master — using {len(df)} new rows')

        timestamp = config.RUN_TIMESTAMP

        data_filename = config.DATA_FILE_PATTERN.format(timestamp=timestamp)
        meta_filename = config.META_FILE_PATTERN.format(timestamp=timestamp)
        zip_filename  = config.ZIP_FILE_PATTERN.format(timestamp=timestamp)

        data_path = os.path.join(output_dir, data_filename)
        meta_path = os.path.join(output_dir, meta_filename)
        zip_path  = os.path.join(output_dir, zip_filename)

        # DATA .xls: new data only (xls format has 65K row limit)
        self.create_data_file(df, data_path)
        self.create_meta_file(meta_path)
        self.create_zip_file(data_path, meta_path, zip_path)

        # Output CSV: FULL combined data (new + historical)
        csv_path = self.create_output_csv(combined_df, output_dir)

        # Copy to 'latest' folder
        latest_dir = config.LATEST_OUTPUT_DIR
        os.makedirs(latest_dir, exist_ok=True)

        latest_data = os.path.join(latest_dir, f'{config.DATASET_NAME}_DAILY_DATA_latest.xls')
        latest_meta = os.path.join(latest_dir, f'{config.DATASET_NAME}_DAILY_META_latest.xls')
        latest_zip  = os.path.join(latest_dir, f'{config.DATASET_NAME}_DAILY_latest.zip')
        latest_csv  = os.path.join(latest_dir, f'{config.DATASET_NAME}_DATA.csv')

        shutil.copy2(data_path, latest_data)
        shutil.copy2(meta_path, latest_meta)
        shutil.copy2(zip_path, latest_zip)
        shutil.copy2(csv_path, latest_csv)

        self.logger.info(f'Files copied to latest: {latest_dir}')

        # Update master
        self.update_master(df)

        return {
            'data_file':   data_path,
            'meta_file':   meta_path,
            'zip_file':    zip_path,
            'csv_file':    csv_path,
            'latest_data': latest_data,
            'latest_meta': latest_meta,
            'latest_zip':  latest_zip,
            'latest_csv':  latest_csv,
        }
