import re
import glob

from pylatexenc.latexwalker import LatexWalker
from pylatexenc.latexwalker import LatexMacroNode, LatexNode, LatexEnvironmentNode, LatexNodeList, LatexGroupNode
from pylatexenc.latex2text import LatexNodes2Text

class Bibitem:
    def __init__(self, key: str = "", s: str = "") -> None:
        self.s = s.strip().replace("\n", " ")
        self.key = key
        self.structured = False
        self.sl = 150 # summary length
    def __str__(self) -> str:
        if self.key == "":
            return "Unresolved"
        if self.structured:
            return f"" # TODO
        return self.s
    def summary(self) -> str:
        if self.key == "":
            return "Unresolved"
        if self.structured:
            return f"" # TODO
        first_line = self.s.split("\n")[0]
        return first_line[: self.sl] + '...' if len(first_line) > self.sl else first_line

class ArXiv:
    def __init__(self, identifier: str) -> None:
        self.identifier = identifier

class Context:
    def __init__(self, latex: str, text: str, start: int, end: int, complex: bool = False) -> None:
        self.latex = latex
        self.text = text
        self.start = start
        self.end = end
        self.complex = complex

class Citation:
    def __init__(self, match_: re.Match, context: Context) -> None:
        self.match = match_
        keys: list[str] = [key.strip() for key in match_.group(2).split(",")]
        self.keys = keys
        self.context = context
        self.bibitems: dict[str, Bibitem] = {}
    def bind(self, key: str, bibitem: Bibitem) -> None:
        self.bibitems[key] = bibitem
    def get_bibitem(self, key: str) -> Bibitem:
        if key in self.bibitems:
            return self.bibitems[key]
        return Bibitem()
    def display_bibitems(self) -> str:
        return "\n".join(f"{key} => {self.get_bibitem(key).summary()}" for key in self.keys)
    def __str__(self) -> str:
        return f"""```
{self.context.text}
```
{self.display_bibitems()}
"""

def get_citations(doc: str) -> list[Citation]:
    p = re.compile(r"\\(cite|citep|citet){(.*?)}")
    sentence_flag = re.compile(r"((\.|\?|!)(\s|})+)|\\(begin|end)")
    sentence_flag_inv = re.compile(r"(\s+(\.|\?|!))|}.*?{(nigeb|dne)\\")
    doc_inv = doc[::-1]
    citations: list[Citation] = []
    for m in p.finditer(doc):
        context_start = re.search(sentence_flag_inv, doc_inv[len(doc) - m.start() - 1:])
        context_end = re.search(sentence_flag, doc[m.end():])
        if context_start is None or context_end is None:
            breakpoint()
        start_pos = m.start() - context_start.start() + 1
        end_pos = m.end() + context_end.end()
        context_latex = doc[start_pos: end_pos].replace("\n", " ")
        
        # context_latex = re.sub(m, f"##CITE[ {m.group(2)} ]", context_latex)
        context_latex = f"{context_latex[: m.start() - start_pos]}##CITE[ {m.group(2)} ]{context_latex[m.end() - start_pos:]}"
        
        try:
            text = LatexNodes2Text().latex_to_text(context_latex)
            # print(text)
        except Exception as e:
            print(e)
            breakpoint()
            text = context_latex
        
        context = Context(context_latex, text, start_pos, m.end() + context_end.start())
        citation = Citation(m, context)
        citations.append(citation)
        # print(str(citation), end="\n\n")
    return citations

def search_thebibliography(node: LatexNode) -> LatexEnvironmentNode|None:
    if node.nodeType().__name__ == "LatexEnvironmentNode" and node.environmentname == "thebibliography":
        return node
    if hasattr(node, "nodelist"):
        for child in node.nodelist:
            if res := search_thebibliography(child):
                return res
    return None

def get_bibitems(doc: str) -> list[Bibitem]:
    walker = LatexWalker(doc)
    nodelist, pos, len_ = walker.get_latex_nodes(pos=0)
    for node in nodelist:
        if thebib := search_thebibliography(node):
            break
    else:
        raise Exception("No thebibliography found")
    
    thebibliography_inner_nodes: LatexNodeList = thebib.nodelist
    def is_bibitem_macro(node: LatexNode) -> bool:
        return node.nodeType().__name__ == "LatexMacroNode" and node.macroname == "bibitem"
    splited_nodelist = thebibliography_inner_nodes.split_at_node(is_bibitem_macro, keep_separators=True)
    
    results: dict[str, Bibitem] = {}
    
    for bibitem_nodelist in splited_nodelist:
        if not is_bibitem_macro(bibitem_nodelist[0]):
            continue
        key_node = bibitem_nodelist[1]
        assert isinstance(key_node, LatexGroupNode)
        assert key_node.delimiters == ('{', '}')
        key = key_node.latex_verbatim()
        key = key[1: -1]
        s_nodelist = LatexNodeList(bibitem_nodelist[2:])
        # s = s_nodelist.get_content_as_chars()
        # s = s_nodelist.latex_verbatim()
        s = LatexNodes2Text().nodelist_to_text(s_nodelist)
        bibitem = Bibitem(key, s)
        # breakpoint()
        if key in results:
            raise Exception(f"Duplicate key: {key}")
        results[key] = bibitem
    return results

def assign_citations(citations: list[Citation], bibitems: dict[str, Bibitem]) -> None:
    for citation in citations:
        for key in citation.keys:
            if key not in bibitems:
                print(f"WARNING: Unresolved: {key}")
            else:
                citation.bind(key, bibitems[key])

if __name__ == "__main__":
    path = "data/1011.2313"
    path = "data/1706.03762"
    texes = glob.glob(f"{path}/*.tex")
    doc = '\n\n'.join(f.read() for f in map(open, texes))
    citations = get_citations(doc)
    
    bibitems = get_bibitems(doc)
    assign_citations(citations, bibitems)
    
    for i, citation in enumerate(citations):
        print(f"The {i + 1}th citation:")
        print(citation)
        print()