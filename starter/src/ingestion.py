"""PDF extraction retaining original-page lineage and chapter provenance."""
import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path
from pypdf import PdfReader
import pymupdf
from .models import DocumentPage


def normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFC', text).replace('\r\n', '\n').replace('\r', '\n')
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.splitlines())).strip()


def load_pdf(path: Path, document_id: str, source: str, page_map: Path | None = None) -> list[DocumentPage]:
    reader = PdfReader(path)
    fallback = pymupdf.open(path)
    raw_pages = [p.extract_text(extraction_mode='plain') or '' for p in reader.pages]
    first_lines = Counter(next((line.strip() for line in raw.splitlines() if line.strip()), '') for raw in raw_pages)
    running_titles = {line for line,count in first_lines.items() if line and line.isupper() and count >= max(2,len(raw_pages)//2)}
    mapping = []
    if page_map:
        with page_map.open(encoding='utf-8-sig') as mapping_file:
            mapping = list(csv.DictReader(mapping_file))
    if mapping and (len(mapping) != len(reader.pages) or [int(r['pdf_page']) for r in mapping] != list(range(1, len(reader.pages)+1))):
        raise ValueError('Page map must cover every physical PDF page in order')
    originals = [int(row['original_page']) for row in mapping]
    if mapping and len(set(originals)) != len(originals):
        raise ValueError('Duplicate original page identity')
    result, chapter, provenance, previous = [], None, None, None
    for index, page in enumerate(reader.pages, 1):
        original = int(mapping[index-1]['original_page']) if mapping else index
        if previous is not None and original != previous + 1:
            chapter, provenance = None, None
        raw = raw_pages[index-1]
        parser_warning = []
        if any(ord(c) < 32 and c not in '\n\r\t' for c in raw):
            raw = fallback[index-1].get_text()
            parser_warning.append('PYPDF_CONTROL_CHARACTERS_USED_PYMUPDF_FALLBACK')
        lines = [line for line in raw.splitlines() if not re.fullmatch(r'\s*Trang\s+\d+\s*', line)
                 and line.strip() not in running_titles]
        text = normalize_text('\n'.join(lines))
        spans, start = [], 0
        for match in re.finditer(r'(?m)^(\d{1,2})\.\s+([^\n]+)$', text):
            title = match.group(2).strip()
            if not title.isupper() or not any(c.isalpha() for c in title):
                continue
            if match.start() > start:
                spans.append({'start':start,'end':match.start(),'section':chapter,'provenance':provenance})
            chapter = match.group(1) + '. ' + title
            provenance = {'original_page':original,'heading':match.group(0)}
            start = match.start()
        spans.append({'start':start,'end':len(text),'section':chapter,'provenance':provenance})
        warnings = ['TABLE_READING_ORDER_REQUIRES_REVIEW'] if re.search(r'(?m)^(Mã|Phương|Bảng|TT|Trạng thái)\b',text) else []
        warnings.extend(parser_warning)
        if not text:
            warnings.append('EMPTY_EXTRACTION')
        if '\ufffd' in text:
            warnings.append('REPLACEMENT_CHARACTER')
        result.append(DocumentPage(document_id,source,original,text,{'pdf_page':index,'original_page':original,
            'section_spans':spans,'warnings':warnings,'raw_characters':len(raw)}))
        previous = original
    fallback.close()
    return result
