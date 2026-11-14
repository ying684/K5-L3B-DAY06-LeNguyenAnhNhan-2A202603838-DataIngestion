"""Deterministic page-local chunking with offsets into normalized source text."""
import hashlib
import re
from .models import Chunk, DocumentPage


def make_chunk(page: DocumentPage, start: int, end: int, method: str) -> Chunk:
    while start < end and page.text[start].isspace(): start += 1
    while end > start and page.text[end-1].isspace(): end -= 1
    text = page.text[start:end]
    identity = f'{page.document_id}|{page.page}|{method}|{start}|{end}|{text}'
    cid = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return Chunk(cid, page.document_id, page.source, page.page, text,
                 {**page.metadata, 'start_char': start, 'end_char': end, 'chunking': method})


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    if size <= 0 or not 0 <= overlap < size: raise ValueError('Require 0 <= overlap < size')
    result=[]
    for start in range(0, len(page.text), size-overlap):
        end=min(start+size,len(page.text))
        chunk=make_chunk(page,start,end,'fixed')
        if chunk.text: result.append(chunk)
        if end == len(page.text): break
    return result


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    if max_size <= 0: raise ValueError('max_size must be positive')
    units=[]
    for match in re.finditer(r'.+?(?:\n\n|\Z)',page.text,re.S):
        start,end=match.span()
        if end-start <= max_size:
            units.append((start,end)); continue
        previous=start
        boundaries=[start+m.end() for m in re.finditer(r'(?<=[.!?])\s+',page.text[start:end])]+[end]
        for boundary in boundaries:
            while boundary-previous > max_size:
                units.append((previous,previous+max_size)); previous += max_size
            if boundary>previous: units.append((previous,boundary)); previous=boundary
    result=[]; group=None
    for start,end in units:
        if group and end-group[0] > max_size:
            result.append(make_chunk(page,*group,'paragraph')); group=None
        group=(group[0] if group else start,end)
    if group: result.append(make_chunk(page,*group,'paragraph'))
    return [c for c in result if c.text]
