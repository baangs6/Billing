"""Bounded CSV/XLSX product import parsing; no database writes."""
import csv
import io
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from xml.etree.ElementTree import ParseError
from openpyxl.utils.exceptions import InvalidFileException

COLUMNS = ('name','sku','category','description','hsn','unit','purchase_price','mrp','selling_price','gst','min_stock','stock')

def read_products(upload):
    if not upload or not upload.filename:
        raise ValueError('Choose a CSV or Excel (.xlsx) file.')
    upload.stream.seek(0)
    content = upload.stream.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise ValueError('The import file must be under 5 MB.')
    suffix = Path(upload.filename).suffix.lower()
    try:
        if suffix == '.csv':
            rows = csv.reader(io.StringIO(content.decode('utf-8-sig')), strict=True)
            workbook = None
        elif suffix == '.xlsx':
            from openpyxl import load_workbook
            with ZipFile(io.BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 25 * 1024 * 1024:
                    raise ValueError('The Excel file expands beyond the 25 MB limit.')
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
            rows = ([cell.value for cell in row] for row in workbook.active.iter_rows())
        else:
            raise ValueError('Use a UTF-8 CSV or Excel (.xlsx) file.')
        try:
            headers = [str(value or '').strip().lower().replace(' ', '_') for value in next(rows, [])]
            if len(headers) != len(set(headers)) or not {'name','sku','selling_price'}.issubset(headers):
                raise ValueError('Use unique column headers including name, sku and selling_price. Download the template.')
            unknown = set(headers) - set(COLUMNS)
            if unknown:
                raise ValueError('Unknown columns: ' + ', '.join(sorted(unknown)))
            records = []
            for number, row in enumerate(rows, 2):
                if number > 1002:
                    raise ValueError('Import at most 500 products with no more than 1,000 spreadsheet rows.')
                if not any(value is not None and str(value).strip() for value in row):
                    continue
                if len(row) > len(headers) and any(value is not None and str(value).strip() for value in row[len(headers):]):
                    raise ValueError(f'Row {number}: extra values have no column header.')
                record = {key: str(value).strip() if value is not None else '' for key, value in zip(headers, row)}
                for key, value in record.items():
                    if len(value) > (2500 if key == 'description' else 300):
                        raise ValueError(f'Row {number}: {key} is too long.')
                    if value.startswith('='):
                        raise ValueError(f'Row {number}: formulas are not supported; use plain values.')
                records.append((number, record))
                if len(records) > 500:
                    raise ValueError('Import at most 500 products at a time.')
            if not records:
                raise ValueError('The file contains no products.')
            return records
        finally:
            if workbook:
                workbook.close()
    except (UnicodeError, csv.Error, BadZipFile, OSError, KeyError, StopIteration, ParseError, InvalidFileException) as error:
        raise ValueError('Unable to read this file. Use the CSV template or a valid .xlsx workbook.') from error
