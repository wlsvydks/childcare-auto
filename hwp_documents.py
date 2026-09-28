"""Read HWP 5 table cells without discarding their row/column boundaries."""
import io
import re
import struct
import zlib
import xml.etree.ElementTree as ET

import olefile


def paragraph_text(data):
    chunks = []
    pos = 0
    extended = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
    while pos + 2 <= len(data):
        code = struct.unpack_from('<H', data, pos)[0]
        if code in extended:
            pos += 16
        else:
            if code in (10, 13):
                chunks.append(b'\n\x00')
            elif code >= 32:
                chunks.append(data[pos:pos + 2])
            pos += 2
    return b''.join(chunks).decode('utf-16le', errors='replace').strip()


def records(data):
    pos = 0
    while pos < len(data):
        if pos + 4 > len(data):
            raise ValueError('한글 문서의 레코드가 잘렸습니다.')
        header = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        size = header >> 20
        if size == 4095:
            if pos + 4 > len(data):
                raise ValueError('한글 문서의 레코드 길이가 잘렸습니다.')
            size = struct.unpack_from('<I', data, pos)[0]
            pos += 4
        if pos + size > len(data):
            raise ValueError('한글 문서의 내용이 잘렸습니다.')
        yield header & 1023, (header >> 10) & 1023, data[pos:pos + size]
        pos += size


def read_tables(file_bytes):
    tables = []
    if not olefile.isOleFile(io.BytesIO(file_bytes)):
        root = ET.fromstring(file_bytes)
        for table in root.iter('TABLE'):
            cells = []
            for row in table.findall('ROW'):
                for cell in row.findall('CELL'):
                    cells.append(dict(row=int(cell.get('RowAddr', 0)), col=int(cell.get('ColAddr', 0)),
                                      rowspan=int(cell.get('RowSpan', 1)), colspan=int(cell.get('ColSpan', 1)),
                                      width=int(cell.get('Width', 0)), text='\n'.join(
                                          ''.join(p.itertext()) for p in cell.iter('P') if p.find('.//TABLE') is None)))
            tables.append(cells)
        return tables
    with olefile.OleFileIO(io.BytesIO(file_bytes)) as ole:
        header = ole.openstream('FileHeader').read()
        if len(header) < 40 or not header.startswith(b'HWP Document File') or header[36] & 6:
            raise ValueError('일반 한글 문서만 읽을 수 있습니다.')
        sections = sorted((p for p in ole.listdir() if len(p) == 2 and p[0] == 'BodyText'
                           and re.fullmatch(r'Section\d+', p[1])), key=lambda p: int(p[1][7:]))
        for section in sections:
            raw = ole.openstream(section).read()
            data = zlib.decompress(raw, -15) if header[36] & 1 else raw
            stack = []
            for tag, level, payload in records(data):
                while stack and level <= stack[-1]['level']:
                    stack.pop()
                if tag == 71 and payload[:4] == b' lbt':
                    cells = []
                    tables.append(cells)
                    stack.append(dict(level=level, cells=cells, cell=None))
                elif stack and tag == 72 and level == stack[-1]['level'] + 1 and len(payload) >= 38:
                    col, row, colspan, rowspan, width = struct.unpack_from('<HHHHI', payload, 8)
                    if colspan and rowspan:
                        cell = dict(col=col, row=row, colspan=colspan, rowspan=rowspan, width=width, text='')
                        stack[-1]['cells'].append(cell)
                        stack[-1]['cell'] = cell
                elif stack and tag == 67 and stack[-1]['cell'] is not None:
                    cell = stack[-1]['cell']
                    text = paragraph_text(payload)
                    if text:
                        cell['text'] += ('\n' if cell['text'] else '') + text
    return tables


def weekly_day_contexts(file_bytes):
    """Map weekly rows by physical cell width (the samples use inconsistent grid splits).

    Only accept complete, unambiguous weekday rows. Unknown layouts retain the
    original text path rather than silently dropping cells.
    """
    for cells in read_tables(file_bytes):
        headers = [c for c in cells if re.fullmatch(r'\s*\d{1,2}일\s*\([월화수목금토일]\)\s*', c['text'])]
        if len(headers) < 5 or len({c['row'] for c in headers}) != 1 or any(c['width'] <= 0 for c in headers):
            continue
        headers.sort(key=lambda c: c['col'])
        first_col = headers[0]['col']
        headers = [c for c in headers if not re.search(r'[토일]\)', c['text'])]
        output = {re.sub(r'\s+', '', c['text']): [] for c in headers}
        previous = {}
        row_ids = sorted({c['row'] for c in cells if c['row'] > headers[0]['row']})
        for row in row_ids:
            labels = [c for c in cells if c['col'] < first_col and c['row'] <= row < c['row'] + c['rowspan']]
            label = ' '.join(re.sub(r'\s+', '', c['text']) for c in sorted(labels, key=lambda c: c['col']))
            label = re.sub(r'[∙ㆍ/]', '·', label)
            if not label or re.search(r'안전교육|지역사회', label):
                continue
            values = sorted([c for c in cells if c['row'] == row and c['col'] >= first_col], key=lambda c: c['col'])
            # A weekday row must have at least five distinct cells of the day width.
            if len(values) < 5 or any(abs(c['width'] - h['width']) > 100 for c, h in zip(values[:5], headers[:5])):
                continue
            for header, cell in zip(headers, values):
                key = re.sub(r'\s+', '', header['text'])
                raw = cell['text'].strip()
                prior = previous.get(label, '')
                marker_only = not re.sub(r'\([ㅇoOxX○×]\)|[→←↔─ㅡ\s-]', '', raw)
                starts_repeat = bool(re.match(r'^\s*(?:\([ㅇoOxX○×]\)|[→←↔])', raw))
                inherited = prior if marker_only or starts_repeat else ''
                if starts_repeat and not marker_only:
                    inherited = re.split(r'\(\+\)|\+', inherited, maxsplit=1)[0].strip()
                output[key].append(dict(area=label, original=raw, inherited=inherited))
                if not marker_only:
                    if starts_repeat:
                        # New additions replace the previous day's additions.
                        base = re.split(r'\(\+\)|\+', prior, maxsplit=1)[0].strip()
                        addition = re.sub(r'^\s*(?:\([ㅇoOxX○×]\)|[→←↔])+\s*', '', raw)
                        previous[label] = base + '\n' + addition
                    else:
                        previous[label] = raw
        if all(len(output[re.sub(r'\s+', '', h['text'])]) >= 8 for h in headers[:5]):
            return output
    return {}
