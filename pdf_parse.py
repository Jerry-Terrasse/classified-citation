import PyPDF2
from PyPDF2.generic import AnnotationBuilder
import numpy as np
# from PIL import Image, ImageDraw, ImageFont
from py_pdf_parser import loaders
from shapely import geometry

fname = "pdf/2201.02915.pdf"
pdf = PyPDF2.PdfReader(fname)

writer = PyPDF2.PdfWriter()

mark_links = True
mark_all_texts = True
mark_link_texts = False

# {'/Type': '/Annot', '/Subtype': '/Link', '/A': {'/Type': '/Action', '/S': '/URI', '/URI': 'https://www.aminer.cn/'}, '/Border': [0, 0, 0], '/C': [0, 1, 1], '/H': '/I', '/Rect': [58.27, 98.089, 128.09, 108.493]}
# {'/Type': '/Annot', '/Subtype': '/Link', '/A': {'/D': 'cite.Hirsch2005H-index', '/S': '/GoTo'}, '/Border': [0, 0, 0], '/C': [0, 1, 0], '/H': '/I', '/Rect': [459.051, 392.88, 469.383, 400.508]}

# def get_text_width(text, fontSize):
#     # get text size using pillow
#     img = Image.new('RGB', (100, 100), color = (255, 255, 255))
#     d = ImageDraw.Draw(img)
#     x, y = d.textsize(text)
#     # print(x, y, ">>>")
#     x = x / y * fontSize
#     return x

def contains(big_rect, small_rect, threshold=1.0):
    # big_rect = [x0, y0, x1, y1]
    # small_rect = [x0, y0, x1, y1]
    overlap = geometry.box(*big_rect).intersection(geometry.box(*small_rect)).area
    ratio = overlap / geometry.box(*small_rect).area
    return ratio >= threshold

class Annotation:
    def __init__(self, obj, page, rect, to, text=None):
        self.obj = obj
        self.page = page
        self.rect = rect
        self.to = to
        self.text = text
    def bind(self, text: str):
        self.text = text

pdf_parser = loaders.load_file(fname)

links = []
for idx, page in enumerate(pdf.pages):
    writer.add_page(page)
    page_links = []
    assert page.annotations
    for annot in page.annotations:
        obj = annot.get_object()
        if obj['/Subtype'] == '/Link' and obj['/A']['/S'] == '/GoTo':
            page_links.append(Annotation(obj, idx, obj['/Rect'], obj['/A']['/D']))
            if mark_links:
                mark = AnnotationBuilder.rectangle(
                    rect=obj['/Rect'],
                )
                writer.add_annotation(page_number=idx, annotation=mark)
    links.extend(page_links)

    page_parser = pdf_parser.get_page(idx + 1)
    for element in page_parser.elements:
        bbox = element.bounding_box
        rect = (bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        if mark_all_texts:
            mark = AnnotationBuilder.rectangle(
                rect=rect,
            )
            writer.add_annotation(page_number=idx, annotation=mark)

        for link in page_links:
            if contains(rect, link.rect, 0.7):
                link.bind(element.text())
                context = element.text()[: 200].replace('\n', ' ').strip()
                print("Found link:", link.to, "on page", link.page, "with context:", f"`{context}`")
    # def visitor(text, cm, tm, fontDict, fontSize):
    #     pos = np.array([0., 0., 1.])
    #     cmat = np.array([
    #         [cm[0], cm[1], 0.],
    #         [cm[2], cm[3], 0.],
    #         [cm[4], cm[5], 1.]
    #     ])
    #     tmat = np.array([
    #         [tm[0], tm[1], 0.],
    #         [tm[2], tm[3], 0.],
    #         [tm[4], tm[5], 1.]
    #     ])
    #     pos = pos @ cmat @ tmat
    #     x, y, _ = pos
    #     # print(pos)
    #     for link in page_links:
    #         if link.rect[0] < x < link.rect[2] and link.rect[1] < y < link.rect[3]:
    #             link.bind(text)
    #             print("Found link:", link.to, "on page", link.page, "with text:", link.text)
    #             if mark_link_texts:
    #                 mark = AnnotationBuilder.rectangle(
    #                     rect=link.rect,
    #                 )
    #                 writer.add_annotation(page_number=link.page, annotation=mark)
    #     if mark_all_texts:
    #         if fontDict is None:
    #             return
    #         width = fontDict['/Widths'][-1] - fontDict['/Widths'][0]
    #         # lines = text.split('\n')
    #         # width = max(map(lambda x: get_text_width(x, fontSize), lines))
    #         # mark = AnnotationBuilder.rectangle(
    #         #     rect=[x, y, x + width, y + fontSize],
    #         # )
    #         # writer.add_annotation(page_number=idx, annotation=mark)
    #         # writer.write(open("out.pdf", "wb"))
    #         # input('>')
    
    # page.extract_text(visitor_text=visitor)
print()

from pdfminer.high_level import extract_pages
for page_layout in extract_pages(fname):
    for element in page_layout:
        print(element)



writer.write(open("out.pdf", "wb"))