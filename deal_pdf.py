import sys
from dataclasses import dataclass
from itertools import groupby
import re
from Levenshtein import ratio

import PyPDF2
from PyPDF2 import PdfReader
from PyPDF2.generic import (
    Destination as PDFDestination,
    DictionaryObject,
    IndirectObject,
    TextStringObject,
    ArrayObject,
)

from pdfminer.layout import (
    LAParams,
    LTPage,
    LTContainer,
    LTComponent,
    LTTextBox,
    LTTextLine,
    LTChar,
    LTAnno,
)
from pdfminer.converter import PDFPageAggregator
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter

from utils import Rect, Point, contains, overlap

from loguru import logger

from typing import cast


class Bibitem:
    def __init__(
        self,
        obj: LTTextBox,
        page: int,
        text: str,
        label: str = None,
    ) -> None:
        self.obj = obj # the text box in layout tree
        self.page = page # the page index, start from 0
        self.text = text # the text of the bibitem
        self.label = label # "[xx]" if exists, or None
    def __repr__(self) -> str:
        return f"<Bibitem: {self.text} on page {self.page} with label {self.label}>"

class Destination:
    def __init__(
        self,
        obj: PDFDestination,
        page: int,
        linkname: str = None,
        pos: float|Point = None,
        target: Bibitem = None,
    ) -> None:
        self.obj = obj
        self.page = page
        self.linkname = linkname
        self.pos = pos
        self.target = target
        self.candidates: list[Bibitem] = []
    def __repr__(self) -> str:
        if self.target is not None:
            detail = f"to {self.target}"
        elif self.pos is not None:
            detail = f"to {self.pos}"
        else:
            detail = "without target"
        return f"<Destination: {self.linkname} on page {self.page} {detail}>"
    def candidate_box(self) -> Rect:
        assert self.pos is not None # maybe the whole page?
        if isinstance(self.pos, tuple):
            return (self.pos[0], self.pos[1] - 40, self.pos[0] + 20, self.pos[1] + 10) # TODO: not sure
        else:
            return (0, self.pos - 40, 500, self.pos + 10)

class Citation: # get from links
    def __init__(
        self,
        page: int,
        rect: Rect,
        text: list[str] = None, linkname: str = None,
        context: list[str] = None,
        destination: Destination = None,
        target: Bibitem = None,
    ) -> None:
        self.page = page # page index start from 0
        self.rect = rect # bbox of citation link, (x0, y0, x1, y1)
        self.text = text # [42] | Cortes et al. (2017)
        self.linkname = linkname # cite.corte2017adanet
        self.context = context # the context of the citation
        self.destination = destination # (x, y) | y
        self.target = target # the target of the citation
    def __repr__(self) -> str:
        if self.target is not None:
            detail = f"to {self.target}"
        elif self.destination is not None:
            detail = f"to {self.destination}"
        else:
            detail = "without destination"
        return f"<Citation: {self.text} on page {self.page} at {self.rect} {detail}>"
        

@dataclass
class ResultIntegrity:
    ok: bool

@dataclass
class NumberedIntegrity(ResultIntegrity):
    bib_labels: list[str] # detected labels, '1' '42' ...
    num_range: tuple[int, int] # gussed number range, [start, end)
    missing_bibs: list[int] # missing numbers which should be in range
    unmatched_bibs: list[int] # bibs which are not matched to any citation
    unexpected_labels: list[str] # labels which are not number
    existing_labels: list[int] # fine labels

@dataclass
class UnnumberedIntegrity(ResultIntegrity):
    pass # TODO

@dataclass
class PDFResult:
    cites: list[Citation]
    dests: list[Destination]
    bibs: list[Bibitem]
    def summary(self, need_sort: bool = True) -> None:
        valid = [cite for cite in self.cites if cite.target is not None]
        if need_sort:
            def key(cite: Citation) -> tuple[int, int|str]:
                if cite.target and cite.target.label:
                    if cite.target.label.isdigit():
                        return (0, int(cite.target.label))
                    return (1, cite.target.label)
                return (2, 0)
            valid.sort(key=key)
        logger.info(f"Valid citations: {len(valid)} / {len(self.cites)}")
        for cite in valid:
            assert cite.context
            assert cite.target
            context = " ".join(cite.context).replace("\n", " ")
            context = f"{context[:150]}..." if len(context) > 50 else context
            target = cite.target.text.replace("\n", " ")
            target = f"{target[:150]}..." if len(target) > 50 else target
            logger.info(f"""
label: {''.join(cite.text) if cite.text and cite.text!=[] else '<empty>'}
context: {context}
bibitem [{cite.target.label}]: {target}
"""
)
    def integrity(self) -> ResultIntegrity:
        # First, judge numbered or unnumbered
        digit_cnt = 0
        numbered = False
        for bib in self.bibs[::-1]: # reference section is usually at the end
            if bib.label and bib.label.isdigit():
                digit_cnt += 1
                if digit_cnt >= 3:
                    numbered = True
                    break
        else:
            return UnnumberedIntegrity(ok=False) # TODO
        
        # numbered integrity
        bib_labels = [bib.label for bib in self.bibs if bib.label]
        unexpected_labels = [label for label in bib_labels if not label.isdigit()]
        existing = set(int(label) for label in bib_labels if label.isdigit())
        num_range = 1, max(existing)+1 # assume number start from 1
        
        missing_bibs = [i for i in range(*num_range) if i not in existing]
        matched_bibs = set(int(cite.target.label) for cite in self.cites if cite.target and cite.target.label and cite.target.label.isdigit())
        unmatched_bibs = [i for i in existing if i not in matched_bibs]
        ok = len(missing_bibs) == 0 and len(unmatched_bibs) == 0
        return NumberedIntegrity(
            ok=ok,
            bib_labels=bib_labels,
            num_range=num_range,
            missing_bibs=missing_bibs,
            unmatched_bibs=unmatched_bibs,
            unexpected_labels=unexpected_labels,
            existing_labels=list(existing),
        )

def pdfminer_pages(fname: str, params: LAParams = None) -> list[LTPage]:
    resource_manager = PDFResourceManager()
    laparams = LAParams() if params is None else params
    device = PDFPageAggregator(resource_manager, laparams=laparams)
    interpreter = PDFPageInterpreter(resource_manager, device)
    
    pages: list[LTPage] = []
    with open(fname, 'rb') as file:
        for page in PDFPage.get_pages(file):
            interpreter.process_page(page)
            # 获得页面的布局对象
            layout = device.get_result()
            pages.append(layout)

    device.close()
    return pages

def collect_dests(reader: PdfReader) -> list[Destination]:
    """
    collect named destinations
    unamed bibitems are not collected
    """
    res: list[Destination] = []
    for name, obj in reader.named_destinations.items():
        obj = cast(PDFDestination, obj)
        # logger.debug(f"{name} {obj} {obj['/Type']}")
        if obj['/Type'] == '/XYZ':
            assert obj.left and obj.top
            res.append(Destination(
                obj,
                reader.get_destination_page_number(obj),
                linkname=name,
                pos=(obj.left.as_numeric(), obj.top.as_numeric()),
            ))
        elif obj['/Type'] == '/FitH':
            assert obj.top
            res.append(Destination(
                obj,
                reader.get_destination_page_number(obj),
                linkname=name,
                pos=obj.top.as_numeric(),
            ))
        else:
            logger.warning(f"Ignoring destination type {obj['/Type']}, {obj}")
    return res

def collect_cites(reader: PdfReader) -> list[Citation]:
    """
    collect citations from links
    it does not do anything about the context
    """
    res: list[Citation] = []
    for page_idx, page in enumerate(reader.pages):
        annots = page.annotations or []
        for annot in annots:
            obj = cast(DictionaryObject, annot.get_object())
            if obj['/Subtype'] != '/Link':
                continue
            rect_obj = obj['/Rect']
            assert isinstance(rect_obj, ArrayObject)
            rect: Rect = tuple(rect_obj[i].as_numeric() for i in range(4))
            if '/Dest' in obj: # Named Destination
                linkname_obj = obj['/Dest']
                assert isinstance(linkname_obj, TextStringObject)
                res.append(Citation(
                    page_idx,
                    rect,
                    linkname=str(linkname_obj),
                ))
            elif '/A' in obj: # Action
                action_obj = obj['/A']
                assert isinstance(action_obj, DictionaryObject)
                if action_obj['/S'] != '/GoTo':
                    # logger.warning(f"Ignoring action type {action_obj['/S']}, {action_obj}")
                    continue
                dest_obj = action_obj['/D']
                assert isinstance(dest_obj, TextStringObject)
                res.append(Citation(
                    page_idx,
                    rect,
                    linkname=str(dest_obj),
                ))
            else:
                logger.warning(f"Ignoring link {obj}")
    return res

def walk_context(layout: LTComponent, cite: Citation, depth: int = 0) -> None:
    """
    walk on the layout tree to match context to the citation
    TextBox & TextLine **near** the citation is collected as "context"
    and then every Text & Char **overlaps** with the citation is collected as "text"
    """
    if isinstance(layout, LTChar):
        if contains(layout.bbox, cite.rect, 0.1):
            assert cite.text is not None
            cite.text.append(layout.get_text())
        return
    elif isinstance(layout, LTTextLine):
        if not contains(layout.bbox, cite.rect, 0.01):
            return
        cite.text = [] # prepare for collecting text
        cite.context = [] # prepare for collecting context
    elif isinstance(layout, LTTextBox):
        if not contains(layout.bbox, cite.rect):
            return
        match_idx = -1 # index of matched line
        assert cite.context is None
        for idx, line in enumerate(layout):
            walk_context(line, cite, depth + 1)
            if match_idx < 0 and cite.context is not None:
                match_idx = idx
        if match_idx < 0:
            logger.warning(f"Geometry Error")
            return
        cite.context = cast(list[str], cite.context)
        for i in range(match_idx-1, match_idx+2): # near 2 lines
            if 0 <= i < len(layout):
                cite.context.append(layout._objs[i].get_text())
        return
    
    if isinstance(layout, LTContainer):
        for child in layout:
            if not isinstance(child, LTAnno):
                walk_context(child, cite, depth + 1)


def match_context_page(page: LTPage, cites: list[Citation]) -> None:
    for cite in cites: # maybe slow
        walk_context(page, cite)
        logger.debug(f"Found citation: {cite.text} on page {cite.page} at {cite.rect} with context {cite.context}")

def match_context(pages: list[LTPage], cites: list[Citation]) -> None:
    cites.sort(key=lambda c: c.page)
    cites_on_pages = {k: list(l) for k, l in groupby(cites, lambda c: c.page)}
    for page in pages:
        match_context_page(page, cites_on_pages.get(page.pageid-1, []))

bib_label_pattern = re.compile(r"\[([\d\w]+)\]")
def detect_bib_label(text: str, len_limit: int = 20) -> str|None:
    match = bib_label_pattern.search(text)
    if match and match.start(1) < len_limit: # label must be at the beginning
        return match.group(1).strip()
    return None

def detect_bib_label_all(text: str, len_limit: int = sys.maxsize) -> list[str]:
    matchs = bib_label_pattern.finditer(text, endpos=len_limit)
    return [match.group(1).strip() for match in matchs]

def detect_bibs(page: LTPage, split_LR: bool = False) -> list[Bibitem]:
    if split_LR:
        raise NotImplementedError
    
    # TODO: smarter bibitem detection
    textboxes = filter(lambda o: isinstance(o, LTTextBox), page)
    textboxes = cast(list[LTTextBox], textboxes)
    bibs = map(lambda t: Bibitem(t, page.pageid-1, t.get_text()), textboxes)
    bibs = list(bibs)
    for bib in bibs:
        if 'REFERENCES' in bib.text:
            pass
        if label:=detect_bib_label(bib.text):
            bib.label = label
    return bibs

def match_bibitem_candidate(cands: list[Bibitem], cite: str) -> Bibitem|None:
    cite.strip().replace('[', '').replace(']', '')
    if cite == "":
        logger.warning(f"Empty citation text")
        return None
    # First, try to match the label
    for bib in cands:
        if not bib.label:
            continue
        bib.label = bib.label.strip()
        if bib.label == cite:
            return bib
    # Then, try to match the text
    linkname = cite.lower()
    for bib in cands:
        for word in bib.text.split(maxsplit=5)[:5]:
            if ratio(word.lower(), linkname) > 0.8:
                return bib
    logger.warning(f"Cannot find bibitem for {cite}")
    return None

def match_bibitem(pages: list[LTPage], cites: list[Citation]) -> list[list[Bibitem]]:
    """
    match destinations to bibitems
    @return detected bibitems on each page
    """
    all_bibs: list[list[Bibitem]] = [[] for _ in pages]
    cites.sort(key=lambda c: c.destination.page) # type: ignore
    cites_on_pages = {k: list(l) for k, l in groupby(cites, lambda c: c.destination.page)} # type: ignore
    for page in pages:
        bibs = detect_bibs(page, False)
        all_bibs[page.pageid-1] = bibs
        for cite in cites_on_pages.get(page.pageid-1, []):
            assert cite.destination
            assert cite.text is not None
            cand_box = cite.destination.candidate_box()
            cite.destination.candidates = [bib for bib in bibs if overlap(cand_box, bib.obj.bbox) > 20]
            target = match_bibitem_candidate(cite.destination.candidates, ''.join(cite.text))
            cite.target = cite.destination.target = target
    return all_bibs

def deal(fname: str) -> PDFResult:
    reader = PyPDF2.PdfReader(fname)
    dests = collect_dests(reader)
    cites = collect_cites(reader)
    
    pages = pdfminer_pages(fname) # use pdfminer for layout analysis
    match_context(pages, cites)
    
    dist_map: dict[str, Destination] = {
        dest.linkname: dest for dest in dests if dest.linkname
    }
    for cite in cites:
        assert cite.linkname
        if cite.linkname in dist_map:
            cite.destination = dist_map[cite.linkname]
        else:
            logger.warning(f"Cannot find destination {cite.linkname} for {cite}")
    
    bibs = match_bibitem(pages, cites)
    bibs = sum(bibs, [])
    
    return PDFResult(cites, dests, bibs)

if __name__ == '__main__':
    fname = "pdf/2201.02915.pdf"
    if len(sys.argv) > 1:
        fname = sys.argv[1]
    result = deal(fname)
    result.summary()
    
    integrity = result.integrity()
    if isinstance(integrity, NumberedIntegrity):
        for metric, value in integrity.__dict__.items():
            logger.info(f"{metric}: {value}")
        logger.success(f"Result: {len(integrity.existing_labels)} / {integrity.num_range[1]-integrity.num_range[0]}")
    else:
        logger.info(f"Unnumbered integrity: {integrity.ok}")