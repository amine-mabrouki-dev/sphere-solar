import os
import pathlib
import re
import zipfile
from html import escape
from markdown import markdown
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image as RLImage

INPUT = pathlib.Path(__file__).resolve().parent.parent / 'rapport_pfe_sphere_solar.md'
PDF_OUTPUT = pathlib.Path(__file__).resolve().parent.parent / 'rapport_pfe_sphere_solar.pdf'
DOCX_OUTPUT = pathlib.Path(__file__).resolve().parent.parent / 'rapport_pfe_sphere_solar.docx'


def md_to_pdf(input_path: pathlib.Path, output_path: pathlib.Path) -> None:
    with input_path.open('r', encoding='utf-8') as f:
        text = f.read()

    html = markdown(text)
    stylesheet = getSampleStyleSheet()
    normal = stylesheet['Normal']
    heading1 = ParagraphStyle('Heading1', parent=stylesheet['Heading1'], spaceAfter=12)
    heading2 = ParagraphStyle('Heading2', parent=stylesheet['Heading2'], spaceAfter=10)
    heading3 = ParagraphStyle('Heading3', parent=stylesheet['Heading3'], spaceAfter=8)
    bullet = ParagraphStyle('Bullet', parent=stylesheet['Bullet'], leftIndent=18, spaceAfter=4)

    elements = []
    img_pattern = re.compile(r'<img[^>]+src="([^"]+)"[^>]*>')

    for line in html.splitlines():
        line = line.strip()
        if not line:
            elements.append(Spacer(1, 6))
            continue
        if line.startswith('<hr'):
            elements.append(PageBreak())
            continue
        match = img_pattern.search(line)
        if match:
            img_src = match.group(1)
            img_path = pathlib.Path(img_src)
            if img_path.exists():
                elements.append(RLImage(str(img_path), width=450, height=200))
            continue
        if line.startswith('<h1>') and line.endswith('</h1>'):
            elements.append(Paragraph(line[4:-5], heading1))
        elif line.startswith('<h2>') and line.endswith('</h2>'):
            elements.append(Paragraph(line[4:-5], heading2))
        elif line.startswith('<h3>') and line.endswith('</h3>'):
            elements.append(Paragraph(line[4:-5], heading3))
        elif line.startswith('<li>') and line.endswith('</li>'):
            elements.append(Paragraph(line[4:-5], bullet))
        else:
            clean = line.replace('<strong>', '').replace('</strong>', '').replace('<em>', '').replace('</em>', '')
            clean = clean.replace('<code>', '').replace('</code>', '')
            clean = clean.replace('<pre>', '').replace('</pre>', '')
            clean = clean.replace('<ul>', '').replace('</ul>', '').replace('<ol>', '').replace('</ol>', '')
            clean = clean.replace('</p>', '').replace('<p>', '')
            elements.append(Paragraph(clean, normal))

    def add_page_number(canvas, doc):
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.saveState()
        canvas.setFont('Helvetica', 9)
        canvas.drawCentredString(A4[0] / 2.0, 15, text)
        canvas.restoreState()

    doc = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=40)
    doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)


def _docx_paragraph(text: str, style: str) -> str:
    return (
        """  <w:p>
    <w:pPr>
      <w:pStyle w:val=\"{style}\"/>
    </w:pPr>
    <w:r>
      <w:t>{text}</w:t>
    </w:r>
  </w:p>"""
    ).replace('{style}', style).replace('{text}', escape(text))


def _docx_text(text: str) -> str:
    return escape(text)


def _docx_document_xml(paragraphs: list[tuple[str, str]]) -> str:
    body = ''.join(_docx_paragraph(text, style) for text, style in paragraphs)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
{body}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
  </w:body>
</w:document>'''


def _docx_content_types_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/_rels/document.xml.rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
</Types>'''


def _docx_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''


def _docx_document_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'''


def md_to_docx(input_path: pathlib.Path, output_path: pathlib.Path) -> None:
    with input_path.open('r', encoding='utf-8') as f:
        text = f.read()

    paragraphs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            paragraphs.append(('', 'Normal'))
            continue
        if line.startswith('# '):
            paragraphs.append((line[2:].strip(), 'Heading1'))
        elif line.startswith('## '):
            paragraphs.append((line[3:].strip(), 'Heading2'))
        elif line.startswith('### '):
            paragraphs.append((line[4:].strip(), 'Heading3'))
        elif line.startswith('- '):
            paragraphs.append((line[2:].strip(), 'ListParagraph'))
        else:
            paragraphs.append((line, 'Normal'))

    with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr('[Content_Types].xml', _docx_content_types_xml())
        docx.writestr('_rels/.rels', _docx_rels_xml())
        docx.writestr('word/document.xml', _docx_document_xml(paragraphs))
        docx.writestr('word/_rels/document.xml.rels', _docx_document_rels_xml())


if __name__ == '__main__':
    print('Reading input:', INPUT)
    os.makedirs(INPUT.parent, exist_ok=True)
    md_to_pdf(INPUT, PDF_OUTPUT)
    print('Generated PDF:', PDF_OUTPUT)
    md_to_docx(INPUT, DOCX_OUTPUT)
    print('Generated DOCX:', DOCX_OUTPUT)
