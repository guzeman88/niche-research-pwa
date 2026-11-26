"""Bounded, read-only views of integrity-checked customer artifacts."""
from datetime import date, datetime, time
import math
from pathlib import Path
from zipfile import ZipFile, BadZipFile


def customer_files(manifest):
    supplied=manifest.get('render', {}).get('customer_files')
    if supplied is not None:return supplied
    return [item['name'] for item in manifest.get('files', []) if item['name'].startswith('customer.') or item['name'] in ('instructions.txt','font-license.txt')]


def document(engine, job_id, name, fingerprint, page=None):
    from pypdf import PdfReader
    import subprocess
    import sys
    import os
    job=engine.job(job_id);manifest=(job.get('result') or {}).get('manifest') or {}
    if not fingerprint or fingerprint!=manifest.get('artifact_fingerprint'):
        raise ValueError('The product package changed. Reopen its review before viewing files.')
    if name not in customer_files(manifest) or Path(name).suffix.lower()!='.pdf':
        raise ValueError('Choose a customer PDF from this product package.')
    path=engine.file(job_id,name)
    if path.stat().st_size>20*1024*1024:raise ValueError('This PDF exceeds the in-app viewer size limit.')
    with path.open('rb') as stream:count=len(PdfReader(stream).pages)
    if count>500:raise ValueError('This PDF exceeds the in-app viewer page limit.')
    if page is None:
        previews=manifest.get('render',{}).get('previews') or []
        return {'pages':count,'previews':previews if len(previews)==count else [],'artifact_fingerprint':fingerprint}
    if not 0<=page<count:raise ValueError('Choose a page in this PDF.')
    # PDFium is not thread-safe. A separate bounded process keeps viewer reads
    # isolated from each other and the existing production renderer's threads.
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('product_pdf_page.py')),str(path),str(page)],
            capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('This PDF page took too long to render. Retry the page.') from exc
    if result.returncode or not result.stdout.startswith(b'\x89PNG'):
        raise ValueError('This PDF page could not be rendered. Reopen the product review.')
    return result.stdout



def package_entries(path):
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 2048 or sum(x.file_size for x in entries) > 32 * 1024 * 1024:
            raise ValueError('This file exceeds the in-app viewer size limit.')
        return [{'name': x.filename, 'bytes': x.file_size} for x in entries if not x.is_dir()]


def scalar(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)


def read_artifact(path):
    path = Path(path)
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('This file exceeds the in-app viewer size limit.')
    extension = path.suffix.lower()
    if extension == '.txt':
        return {'kind': 'text', 'text': path.read_text(encoding='utf-8-sig')}
    entries = package_entries(path)
    if extension == '.zip':
        return {'kind': 'package', 'files': entries}
    if extension == '.xlsx':
        from openpyxl import load_workbook
        source = load_workbook(path, data_only=False, keep_links=False)
        cached = load_workbook(path, data_only=True, keep_links=False)
        try:
            total = sum(sheet.max_row * sheet.max_column for sheet in source)
            if total > 200000 or any(sheet.max_column > 256 for sheet in source):
                raise ValueError('This workbook exceeds the in-app viewer cell limit.')
            sheets = []
            for sheet in source:
                values = cached[sheet.title]
                rows = []
                for row in sheet.iter_rows():
                    cells = []
                    for cell in row:
                        formula = (cell.value if isinstance(cell.value, str) else getattr(cell.value, 'text', '[Stored formula]')) if cell.data_type == 'f' else None
                        color = cell.fill.fgColor
                        cells.append({'address': cell.coordinate,
                            'value': scalar(values[cell.coordinate].value if formula else cell.value),
                            'formula': formula, 'format': cell.number_format,
                            'bold': bool(cell.font.bold),
                            'fill': color.rgb[-6:] if cell.fill.patternType == 'solid' and color.type == 'rgb' else None})
                    rows.append(cells)
                sheets.append({'name': sheet.title, 'state': sheet.sheet_state,
                    'rows': rows, 'columns': sheet.max_column,
                    'merged': [str(r) for r in sheet.merged_cells.ranges]})
            return {'kind': 'workbook', 'sheets': sheets}
        finally:
            source.close()
            cached.close()
    if extension == '.pptx':
        from pptx import Presentation
        deck = Presentation(path)
        if len(deck.slides) > 300:
            raise ValueError('This presentation exceeds the in-app viewer slide limit.')
        def blocks(shapes):
            result = []
            for shape in shapes:
                if shape.has_text_frame:
                    result.append(shape.text_frame.text)
                if shape.has_table:
                    result.extend('\t'.join(cell.text for cell in row.cells) for row in shape.table.rows)
                if hasattr(shape, 'shapes'):
                    result.extend(blocks(shape.shapes))
            return result
        return {'kind': 'slides', 'slides': [blocks(slide.shapes) for slide in deck.slides]}
    raise ValueError('This file has no structured in-app view.')


def view(engine, job_id, name, fingerprint):
    job = engine.job(job_id)
    manifest = (job.get('result') or {}).get('manifest') or {}
    if not fingerprint or fingerprint != manifest.get('artifact_fingerprint'):
        raise ValueError('The product package changed. Reopen its review before viewing files.')
    if name not in customer_files(manifest):
        raise ValueError('Choose a customer file from this product package.')
    if Path(name).suffix.lower() not in ('.xlsx', '.pptx', '.txt', '.zip'):
        raise ValueError('This file has no structured in-app view.')
    # The existing engine checks membership, safe paths and stored file hashes.
    try:
        result = read_artifact(engine.file(job_id, name))
    except (BadZipFile, UnicodeError) as exc:
        raise ValueError('This customer file could not be read. Reopen the product review or regenerate its revision.') from exc
    return {**result, 'artifact_fingerprint': fingerprint, 'name': name}
