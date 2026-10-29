"""Bounded text extraction for common local coursework documents."""
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from io import BytesIO

LIMIT=8*1024*1024


def document_text(path: Path):
    if path.stat().st_size>LIMIT:
        raise ValueError('文档超过 8 MiB，请分拆后读取。')
    if path.suffix.lower()=='.pdf':
        from pypdf import PdfReader
        import pypdf.filters
        pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH=4*1024*1024
        reader=PdfReader(BytesIO(path.read_bytes()))
        if reader.is_encrypted:
            raise ValueError('此 PDF 已加密，请提供可读取的副本。')
        if len(reader.pages)>150:
            raise ValueError('PDF 超过 150 页，请先拆分。')
        chunks=[]
        total=0
        for index,page in enumerate(reader.pages,1):
            content=page.get_contents()
            if content and len(content.get_data())>4*1024*1024:
                raise ValueError('PDF 页面内容过大，请先压缩或拆分。')
            text=page.extract_text() or ''
            chunks.append(f'[第 {index} 页]\n'+text)
            total+=len(text)
            if total>1_000_000:
                raise ValueError('文档文本过长，请拆分后读取。')
        if not any(chunk.split('\n',1)[-1].strip() for chunk in chunks):
            raise ValueError('此 PDF 没有可提取的文字，扫描件需先进行 OCR。')
        return '\n\n'.join(chunks),len(reader.pages)
    if path.suffix.lower()=='.docx':
        with ZipFile(path) as archive:
            item=archive.getinfo('word/document.xml')
            if item.file_size>LIMIT:
                raise ValueError('Word 文档解压后文本过大。')
            root=ET.fromstring(archive.read(item))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        paragraphs=[''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in root.findall('.//w:p',ns)]
        return '\n'.join(paragraphs),None
    raise ValueError('不支持的文档格式。')


def read_document(path, name, offset, limit, max_output):
    text,pages=document_text(path)
    lines=text.splitlines();selected=[];used=0;truncated=False
    for number,line in enumerate(lines[offset-1:offset-1+limit],offset):
        value=f'{number:>5}  {line}'
        available=max_output-used-(1 if selected else 0)
        if available<=0:break
        if len(value)>available:
            if selected:break
            value=value[:max(0,available-12)]+' [该行已截断]';truncated=True
        selected.append(value);used+=len(value)+1
    end=min(len(lines),offset-1+len(selected))
    return {'ok':True,'path':name,'format':path.suffix.lower()[1:],'pages':pages,'text':'\n'.join(selected),'total_lines':len(lines),'remaining_lines':max(0,len(lines)-end),'next_offset':end+1 if end<len(lines) else None,'truncated':truncated}
