import sys
from dataclasses import dataclass
from itertools import groupby, chain, islice
import re
import copy
from Levenshtein import ratio

import PyPDF2
from PyPDF2 import PdfReader
from PyPDF2.generic import (
    Destination as PDFDestination,
    DictionaryObject,
    IndirectObject,
    TextStringObject,
    ByteStringObject,
    ArrayObject,
    Fit,
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
    LTTextContainer,
    LTFigure,
    LTItem,
    LTTextGroup,
)
from pdfminer.high_level import extract_pages, extract_text
from pdfminer.utils import fsplit

try:
    # from pdf_image import get_images, cut_img, save_img
    from utils import Rect, Point, contains, overlap, area, parscit_batch
except ImportError:
    from .utils import Rect, Point, contains, overlap, area, parscit_batch

from loguru import logger

from typing import cast, Iterator, Optional, Iterable, Sequence

# (cid:xxx)
cid_pattern = re.compile(r"\(cid:\d+\)")
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
        self.text = text.replace('\n', ' ') # the text of the bibitem
        self.text = cid_pattern.sub('', self.text)
        self.label = label # "[xx]" if exists, or None
        self.title: Optional[str] = None # the title of the bibitem
    def __repr__(self) -> str:
        return f"<Bibitem: {f'{{{self.title}}}' if self.title else self.text} on page {self.page} with label {self.label}>"

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
            return (self.pos[0], self.pos[1] - 40, self.pos[0] + 50, self.pos[1] + 10) # TODO: not sure
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
        return f"<Citation: [{''.join(self.text) if self.text else None}] on page {self.page} at {self.rect} {detail}>"
        

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
    ok_labels: list[int] # labels which exist and are matched to citations

@dataclass
class UnnumberedIntegrity(ResultIntegrity):
    ok_labels: list[str] # labels which exist and are matched to bibitems
    pass # TODO

@dataclass
class PDFResult:
    cites: list[Citation]
    dests: list[Destination]
    bibs: list[Bibitem]
    _valids: Optional[list[Citation]] = None
    def summary(self, need_sort: bool = True) -> list[str]:
        valids = self.valids
        res = []
        if need_sort:
            def key(cite: Citation) -> tuple[int, int|str]:
                if cite.target and cite.target.label:
                    if cite.target.label.isdigit():
                        return (0, int(cite.target.label))
                    return (1, cite.target.label)
                return (2, 0)
            valids.sort(key=key)
        logger.info(f"Valid citations: {len(valids)} / {len(self.cites)}")
        for cite in valids:
            assert cite.context
            assert cite.target
            context = " ".join(cite.context).replace("\n", " ")
            context = f"{context[:150]}..." if len(context) > 50 else context
            if cite.target.title:
                target = f"{{{cite.target.title}}}"
            else:
                target = cite.target.text.replace("\n", " ")
                target = f"{target[:150]}..." if len(target) > 50 else target
            smy = f"""
label: {''.join(cite.text) if cite.text and cite.text!=[] else '<empty>'}
context: {context}
bibitem [{cite.target.label}]: {target}
"""
            logger.info(smy)
            res.append(smy)
        return res
            
    @property
    def valids(self) -> list[Citation]:
        if self._valids is None:
            self._valids = [cite for cite in self.cites if cite.target is not None]
        return self._valids
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
            ok_labels = [''.join(cite.text) for cite in self.valids if cite.text]
            ok_labels = list(set(ok_labels))
            return UnnumberedIntegrity(
                ok=False,
                ok_labels=ok_labels
            ) # TODO
        
        # numbered integrity
        bib_labels = [bib.label for bib in self.bibs if bib.label]
        unexpected_labels = [label for label in bib_labels if not label.isdigit()]
        existing_bibs = set(int(label) for label in bib_labels if label.isdigit())
        num_range = 1, max(existing_bibs)+1 # assume number start from 1
        
        missing_bibs = [i for i in range(*num_range) if i not in existing_bibs]
        matched_bibs = set(int(cite.target.label) for cite in self.cites if cite.target and cite.target.label and cite.target.label.isdigit())
        unmatched_bibs = [i for i in existing_bibs if i not in matched_bibs]
        ok = len(missing_bibs) == 0 and len(unmatched_bibs) == 0
        return NumberedIntegrity(
            ok=ok,
            bib_labels=bib_labels,
            num_range=num_range,
            missing_bibs=missing_bibs,
            unmatched_bibs=unmatched_bibs,
            unexpected_labels=unexpected_labels,
            ok_labels=list(matched_bibs),
        )

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
            assert obj.left is not None and obj.top is not None
            res.append(Destination(
                obj,
                reader.get_destination_page_number(obj),
                linkname=name,
                pos=(obj.left.as_numeric(), obj.top.as_numeric()),
            ))
        elif obj['/Type'] == '/FitH':
            assert obj.top is not None
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
            rect: Rect = tuple(rect_obj[i].as_numeric() for i in range(4)) # type: ignore
            if '/Dest' in obj:
                dest_obj = obj['/Dest']
                if isinstance(dest_obj, TextStringObject|ByteStringObject): # Named Destination
                    linkname = str(dest_obj) if isinstance(dest_obj, TextStringObject) else dest_obj.original_bytes.decode()
                    res.append(Citation(
                        page_idx,
                        rect,
                        linkname=linkname,
                    ))
                elif isinstance(dest_obj, ArrayObject): # Explicit Destination
                    target_page, fit, *args = dest_obj
                    dest_obj = PDFDestination('', target_page, Fit(fit, tuple(args)))
                    res.append(Citation(
                        page_idx,
                        rect,
                        destination=Destination(
                            dest_obj,
                            reader.get_destination_page_number(dest_obj),
                        ),
                    ))
                    # page, 
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

def extract_text_in_figures(pages: list[LTPage]):
    for page in pages:
        text_objs = []
        for obj in page:
            if isinstance(obj, LTFigure):
                text_obj, _ = fsplit(lambda o: isinstance(o, LTChar), obj)
                if len(text_obj) > 100: # It's not only a figure
                    text_objs.extend(text_obj)
        if text_objs:
            page.extend(text_objs)
            page.analyze(LAParams())
    return

def walk_context(layout: LTComponent, cite: Citation, depth: int = 0) -> None:
    """
    walk on the layout tree to match context to the citation
    TextBox & TextLine **near** the citation is collected as "context"
    and then every Text & Char **overlaps** with the citation is collected as "text"
    """
    if isinstance(layout, LTChar):
        if overlap(layout.bbox, cite.rect) > area(layout.bbox) * 0.5:
            assert cite.text is not None
            cite.text.append(layout.get_text())
        return
    elif isinstance(layout, LTTextLine):
        if not contains(layout.bbox, cite.rect, 0.01):
            return
        if cite.text is None:
            cite.text = [] # prepare for collecting text
        if cite.context is None:
            cite.context = [] # prepare for collecting context
    elif isinstance(layout, LTTextBox):
        if not contains(layout.bbox, cite.rect):
            return
        match_idx = -1 # index of matched line
        if cite.context is not None:
            logger.warning(f"Skippig overlaped TextBox({layout}) on {cite}")
            return
        for idx, line in enumerate(layout):
            walk_context(line, cite, depth + 1)
            if match_idx < 0 and cite.context is not None:
                match_idx = idx
        if match_idx < 0:
            logger.warning(f"Geometry Error: no valid line for {cite} even though TextBox({layout}) contains it")
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

LayoutPath = list[LTItem]
ImuLayoutPath = tuple[LTItem, ...] # immutable
def flatten_page(layout: LTItem, path: LayoutPath, dest: list[tuple[str, ImuLayoutPath]]) -> None:
    """
    flatten the layout tree into a linear format
    """
    if isinstance(layout, LTContainer):
        for child in layout:
            path.append(child)
            flatten_page(child, path, dest)
            path.pop()
    elif isinstance(layout, LTChar|LTAnno):
        if len(layout.get_text()) == 1:
            dest.append((layout.get_text(), tuple(path)))
        else:
            path_t = tuple(path)
            for c in layout.get_text():
                dest.append((c, path_t))
    else:
        logger.warning(f"[Flatten] Unknown layout type {layout}")

citation_patterns_str = [
    r'\[[\d\w\s]+\]', # [42]
    r'[A-Z][A-Za-z]+,? +\(?(18|19|20)\d{2}[a-z]?\)?', # Cortes, 2017b
    r'[A-Z][A-Za-z]+ +(and|&) +[A-Z][A-Za-z]+,? \(?(18|19|20)\d{2}[a-z]?\)?', # Cortes and Haffner, 2017b
    r'[A-Z][A-Za-z]+ +et +al.,? +\(?(18|19|20)\d{2}[a-z]?\)?', # Cortes et al., 2017b
]
citation_patterns = [re.compile(p) for p in citation_patterns_str]
def detect_citation(flat_pages: list[tuple[str, list[ImuLayoutPath]]]) -> list[Citation]:
    result: list[Citation] = []
    for page_idx, (text, paths) in enumerate(flat_pages):
        for pattern in citation_patterns:
            for match in pattern.finditer(text):
                s, e = match.span()
                layout = LTTextGroup(p[-1] for p in paths[s:e] if isinstance(p[-1], LTChar)) # type: ignore
                logger.debug(f"Detected citation {text[s:e]} on page {page_idx} at {layout.bbox}")
                logger.debug(f"Context: {text[max(0, s-20):min(len(text), e+20)]}")
                result.append(Citation(
                    page_idx,
                    layout.bbox,
                ))
    return result

def match_context_page(page: LTPage, cites: list[Citation]) -> None:
    for cite in cites: # maybe slow
        walk_context(page, cite)
        logger.debug(f"Citation: {cite.text} on page {cite.page} at {cite.rect} with context {cite.context}")

def match_context(pages: list[LTPage], cites: list[Citation]) -> None:
    cites.sort(key=lambda c: c.page)
    cites_on_pages = {k: list(l) for k, l in groupby(cites, lambda c: c.page)}
    for page in pages:
        match_context_page(page, cites_on_pages.get(page.pageid-1, []))

bib_label_pattern = re.compile(r"\[([\d\w\s]+)\]")
def detect_bib_label(text: str, len_limit: int = 20) -> str|None:
    match = bib_label_pattern.search(text)
    if match and match.start(1) < len_limit: # label must be at the beginning
        return match.group(1).strip()
    return None

def detect_bib_label_all(text: str, len_limit: int = sys.maxsize) -> list[str]:
    matchs = bib_label_pattern.finditer(text, endpos=len_limit)
    return [match.group(1).strip() for match in matchs]

def split_page(page: LTPage) -> Iterator[LTComponent]:
    """
    re-arrange items on the page, left part first, then right part
    """
    x0, _, x1, _ = page.bbox
    lmb = 0.4
    left_thresh = x0*lmb + x1*(1-lmb)
    right_thresh = x0*(1-lmb) + x1*lmb
    left_boxes = filter(lambda o: o.bbox[2] < left_thresh, page)
    right_boxes = filter(lambda o: o.bbox[0] > right_thresh, page)
    return chain(left_boxes, right_boxes)

def detect_bibs(page: LTPage, split_LR: bool = False) -> list[Bibitem]:
    items = split_page(page) if split_LR else page
    textboxes = filter(lambda o: isinstance(o, LTTextBox), items)
    textboxes = cast(Iterator[LTTextBox], textboxes)
    
    bibs = map(lambda t: Bibitem(t, page.pageid-1, t.get_text()), textboxes)
    bibs = list(bibs)
    for bib in bibs:
        if label:=detect_bib_label(bib.text):
            bib.label = label
    return bibs

peple_pattern = re.compile(r"[A-Z][A-Za-z]+")
and_pattern = re.compile(r"([A-Z][A-Za-z]+)and([A-Z][A-Za-z]+)") # almost nobody use "and" to end his name
etal_pattern = re.compile(r"([A-Z][A-Za-z]+)etal\.?")
def match_bibitem_candidate(cands: list[Bibitem], cite: str) -> Bibitem|None:
    cite = cite.replace('[', '').replace(']', '').strip()
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
    # try peple name
    # 1. Alice
    # 2. Alice and Bob
    # 3. Alice et al.
    if m:=and_pattern.search(cite):
        peoples = [m.group(1), m.group(2)]
    elif m:=etal_pattern.search(cite):
        peoples = [m.group(1)]
    else:
        peoples = peple_pattern.findall(cite)
    if peoples == []:
        logger.warning(f"Cannot find people name in {cite}")
        return None
    # if len(label) < 4:
    #     logger.debug(f"Ignore too short alphabet citation text {cite}")
    #     return None
    for bib in cands:
        for people in peoples:
            if people in '#'.join(bib.text.split(maxsplit=10)[:10]):
                return bib
    logger.warning(f"Cannot find bibitem for {cite}")
    return None

def match_bibitem(bibs: list[list[Bibitem]], cites: list[Citation]):
    """
    match destinations to bibitems
    """
    nolink_cites, cites = fsplit(lambda c: c.destination is None, cites)
    cites.sort(key=lambda c: c.destination.page) # type: ignore
    cites_on_pages = {k: list(l) for k, l in groupby(cites, lambda c: c.destination.page)} # type: ignore
    for idx, page_bibs in enumerate(bibs):
        for cite in cites_on_pages.get(idx, []):
            assert cite.destination
            destination = cite.destination
            if destination.target is not None:
                continue # No need to match again
            assert cite.text is not None
            cand_box = destination.candidate_box()
            destination.candidates = [bib for bib in page_bibs if overlap(cand_box, bib.obj.bbox) > 20]
            target = match_bibitem_candidate(destination.candidates, ''.join(cite.text))
            destination.target = target
    for cite in cites:
        assert cite.destination
        cite.target = cite.destination.target
            
    all_bibs = list(chain.from_iterable(bibs))
    for cite in nolink_cites:
        assert cite.text is not None
        target = match_bibitem_candidate(all_bibs, ''.join(cite.text))
        cite.target = target
    return

def judge_split_LR(pages: list[LTPage]) -> bool:
    sieded_area = 0.
    total_area = 0.
    total_num = 0
    for page in pages[: 3]:
        x0, y0, x1, y1 = page.bbox
        lmb = 0.4
        left_thresh = x0*lmb + x1*(1-lmb)
        right_thresh = x0*(1-lmb) + x1*lmb
        textboxes = list(filter(lambda o: isinstance(o, LTTextBox), page))
        sided_boxes = filter(lambda o: o.bbox[2] < left_thresh or o.bbox[0] > right_thresh, textboxes)
        total_num += len(textboxes)
        total_area += sum(area(o.bbox) for o in textboxes)
        sieded_area += sum(area(o.bbox) for o in sided_boxes)
    assert total_num > 10
    return sieded_area / total_area > 0.5

def make_textbox(lines: Iterable[LTTextLine]) -> LTTextBox:
    box = LTTextBox()
    box.extend(lines)
    return box

def detect_title(bibs: list[list[Bibitem]]):
    logger.info(f"Detecting bibitem titles by ParsCit")
    bib_list = list(chain.from_iterable(bibs))
    bib_list.sort(key=lambda b: len(b.text.split()))
    for i in range(0, len(bib_list), 32):
        batch = bib_list[i: i+32]
        texts = [b.text for b in batch]
        res = parscit_batch(texts)
        logger.debug(f"Received batch {i//32}")
        for pred, bib in zip(res, batch):
            labels: list[str] = pred['tags'].split()
            tokens: list[str] = pred['text_tokens']
            title_tokens = []
            
            flag = False
            for i in range(len(tokens)):
                if labels[i] == 'title':
                    title_tokens.append(tokens[i])
                elif title_tokens:
                    if flag:
                        break
                    else:
                        flag = True
            
            if len(title_tokens) < 2:
                logger.warning(f"Cannot detect title for {bib.text}")
                continue
            bib.title = ' '.join(title_tokens).replace('- ', '')
            if bib.title.endswith(' In'):
                bib.title = bib.title[:-3]
    return

def collect_bibs(pages: list[LTPage], split_LR: bool = False) -> list[list[Bibitem]]:
    """
    collect bibitems from pages
      step 1: re-arrange textboxes according to split_LR
      step 2: try to find out REFERENCES section
      step 3: judge whether the bibitem is numbered
      step 4: re-group textlines
      step 5: collect bibitems
    @return detected bibitems on each page
    """
    all_bibs: list[list[Bibitem]] = [[] for _ in pages]
    items_list = [split_page(page) if split_LR else page for page in pages]
    textboxes_list = [filter(lambda o: isinstance(o, LTTextBox), items) for items in items_list]
    textboxes_list = cast(list[Iterator[LTTextBox]], textboxes_list)
    bib_boxes_list: list[Iterable[LTTextBox]] = []
    ref_title_id = -1
    for idx, items in enumerate(textboxes_list):
        if ref_title_id != -1: # found the ref in previous page
            # TODO: judge section end?
            bib_boxes_list.append(list(items))
            continue
        
        # step 2
        # lines = chain.from_iterable(items)
        # lines_contain_ref = filter(lambda l: "reference" in l.get_text().lower(), lines)
        # # candidates = []
        # for line in lines_contain_ref:
        #     # judge whether the line is the reference section title
        #     text = line.get_text().lower()
        #     if len(text) > 10: # title should be short
        #         continue
        #     # TODO: maybe other rules?
        #     break
        # else:
        #     # not on this page
        #     lines_list.append([])
        #     continue
        # # found the reference section title
        # ref_title_id = id(line)
        # for i, line in enumerate(lines):
        #     if id(line) == ref_title_id:
        #         lines_list.append(islice(lines, i+1, None))
        #         break
        # else:
        #     raise RuntimeError("found line disappear")
        items = list(items)
        for i, textbox in enumerate(items):
            for line in textbox:
                text = line.get_text().lower()
                # logger.debug(f"Found line: {text}")
                if len(text) < 15 and "reference" in text:
                    logger.success(f"Found reference title: {line}")
                    ref_title_id = id(line)
                    break
            else:
                continue
            bib_boxes_list.append(items[i:])
            break
        else:
            bib_boxes_list.append([])
        
    assert len(bib_boxes_list) == len(pages)
    if ref_title_id == -1:
        logger.warning(f"Cannot find reference section")
        # raise RuntimeError("Cannot find reference section")
        return list(map(detect_bibs, pages, [split_LR]*len(pages)))
    
    # step 3
    samples = islice(chain.from_iterable(bib_boxes_list), 0, 20) # the first 20 textboxes 
    samples = islice(chain.from_iterable(samples), 0, 20) # the first 20 lines
    numbered = sum(map(lambda o: bib_label_pattern.match(o.get_text()) is not None, samples)) > 5
    logger.success(f"Detected numbered: {numbered}")
    
    if not numbered:
        # not to re-group, just use textboxes
        # step 5
        for page in pages:
            idx = page.pageid - 1
            all_bibs[idx] = [Bibitem(t, idx, t.get_text()) for t in bib_boxes_list[idx]]
        return all_bibs
    
    # step 4
    boxes_list: list[Iterable[LTTextBox]] = []
    for idx, boxes in enumerate(bib_boxes_list):
        groups: list[list[LTTextLine]] = []
        lines = chain.from_iterable(boxes)
        for line in lines:
            logger.debug(f"Found line: {line.get_text()}")
            if (m := bib_label_pattern.search(line.get_text())) and m.start(1) < 5:
                groups.append([line])
            elif groups:
                groups[-1].append(line)
        boxes = map(make_textbox, groups)
        boxes_list.append(boxes)
    
    # step 5
    for idx, boxes in enumerate(boxes_list):
        all_bibs[idx] = [Bibitem(t, idx, t.get_text()) for t in boxes]
        for bib in all_bibs[idx]:
            if label:=detect_bib_label(bib.text):
                bib.label = label
    return all_bibs

@logger.catch(reraise=True)
def deal(fname: str, parscit: bool = True, detail: dict = None) -> PDFResult:
    reader = PyPDF2.PdfReader(fname)
    if len(reader.pages) > 100:
        logger.warning(f"Too many pages: {reader.numPages}, maybe not a paper")
        raise RuntimeError("Too many pages")
    dests = collect_dests(reader)
    if detail: detail['dests'] = copy.deepcopy(dests) # for debug
    cites = collect_cites(reader)
    if detail: detail['links'] = copy.deepcopy(cites)
    
    pages = list(extract_pages(fname)) # use pdfminer for layout analysis
    extract_text_in_figures(pages)
    # logger.debug(extract_text(fname))
    
    # page_imgs = get_images(fname)
    # cites.sort(key=lambda c: c.page)
    # cites_on_pages = {k: list(l) for k, l in groupby(cites, lambda c: c.page)}
    # img_cnt = 0
    # for k, items in cites_on_pages.items():
    #     page = pages[k]
    #     items = [item.rect for item in items]
    #     for textbox in page:
    #         if not isinstance(textbox, LTTextBox):
    #             continue
    #         targets = [item for item in items if contains(textbox.bbox, item)]
    #         if not targets:
    #             if area(textbox.bbox) > 10000:
    #                 if img_cnt % 10 != 0:
    #                     continue
    #             else:
    #                 if img_cnt % 30 != 0:
    #                     continue
    #         textbox_img = cut_img(page_imgs[k], textbox.bbox, page.bbox)
    #         save_img(f"cite_img/{img_cnt}", textbox_img, textbox.bbox, targets, 'YOLO')
    #         save_img(f"cite_img/{img_cnt}", textbox_img, textbox.bbox, targets, 'LabelMe')
    #         img_cnt += 1
    
    splited_layout = judge_split_LR(pages) # is the document splited into left and right parts?
    bibs = collect_bibs(pages, splited_layout)
    if detail: detail['bibs'] = copy.deepcopy(bibs)
    if parscit:
        detect_title(bibs)
        bibs = [[bib for bib in page if bib.title] for page in bibs]
    # splited_layout = False
    logger.success(f"Detected split_LR: {splited_layout}")
    
    flat_pages_: list[list[tuple[str, ImuLayoutPath]]] = [[] for _ in pages]
    [flatten_page(page, [page], flat_page) for page, flat_page in zip(pages, flat_pages_)]
    flat_pages: list[tuple[str, list[ImuLayoutPath]]] = []
    for page in flat_pages_:
        text = ''.join(text for text, _ in page)
        assert len(text) == len(page)
        flat_pages.append((text, [path for _, path in page]))
    # doc_text = ''.join(text for text, _ in flat_pages)
    # logger.debug(f"Document text: {doc_text}")
    if len(cites) < 5: # maybe no link
        cites.extend(detect_citation(flat_pages))
    
    match_context(pages, cites)
    cites = [cite for cite in cites if cite.text and cite.context]
    if detail: detail['contexted_cites'] = copy.deepcopy(cites)
    
    dist_map: dict[str, Destination] = {
        dest.linkname: dest for dest in dests if dest.linkname
    }
    for cite in cites:
        if cite.destination: # Explicit Destination
            continue
        if cite.linkname is None: # citation directly from text, without link
            continue
        if cite.linkname in dist_map:
            cite.destination = dist_map[cite.linkname]
        else:
            logger.warning(f"Cannot find destination {cite.linkname} for {cite}")
    cites = [cite for cite in cites if cite.destination or cite.linkname is None]
    if detail: detail['cites'] = copy.deepcopy(cites)
    
    match_bibitem(bibs, cites)
    if detail: detail['cite_cands'] = copy.deepcopy(cites)
    
    bibs = list(chain.from_iterable(bibs))
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
        logger.success(f"Result: {len(integrity.ok_labels)} / {integrity.num_range[1]-integrity.num_range[0]}")
    elif isinstance(integrity, UnnumberedIntegrity):
        logger.warning(f"Unnumbered integrity: {integrity.ok}")
        logger.success(f"ok_labels {len(integrity.ok_labels)} in total: {integrity.ok_labels}")