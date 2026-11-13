"""Page/chapter bounded windows and paragraph/line packing with stable identities."""
import re
from .models import Chunk, DocumentPage
from .io_utils import digest


def _segments(page):
    return page.metadata.get('section_spans') or [{'start':0,'end':len(page.text),'section':None,'provenance':None}]


def _chunk(page,start,end,strategy,section):
    while start < end and page.text[start].isspace():
        start += 1
    while end > start and page.text[end-1].isspace():
        end -= 1
    identity = f'{page.document_id}|{page.page}|{strategy}|{start}|{end}|{page.text[start:end]}|{section}'
    return Chunk(digest(identity),page.document_id,page.source,page.page,page.text[start:end],{
        'pdf_page':page.metadata['pdf_page'],'original_page':page.page,'start':start,'end':end,
        'section':section['section'],'section_provenance':section['provenance']})


def fixed_size(page: DocumentPage,size: int,overlap: int) -> list[Chunk]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError('Require size > overlap >= 0')
    result = []
    for section in _segments(page):
        start = section['start']
        while start < section['end']:
            end = min(start+size,section['end'])
            item = _chunk(page,start,end,f'A:{size}:{overlap}',section)
            if item.text:
                result.append(item)
            if end == section['end']:
                break
            start = end-overlap
    return result


def by_paragraph(page: DocumentPage,max_size: int) -> list[Chunk]:
    if max_size <= 0:
        raise ValueError('max_size must be positive')
    result = []
    for section in _segments(page):
        start,limit = section['start'],section['end']
        while start < limit:
            end = min(start+max_size,limit)
            if end < limit:
                # PDF paragraphs are often represented by single line breaks.
                matches = list(re.finditer(r'\n|(?<=[.!?;])\s+',page.text[start+max_size//2:end]))
                if matches:
                    end = start+max_size//2+matches[-1].end()
                else:
                    space = page.text.rfind(' ',start+max_size//2,end)
                    if space > start:
                        end = space+1
            item = _chunk(page,start,end,f'B:{max_size}',section)
            if item.text:
                result.append(item)
            start = end
    return result
