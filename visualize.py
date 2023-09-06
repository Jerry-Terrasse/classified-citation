import re
from Levenshtein import ratio
import json

import db
from db import Paper, Author, PaperData

label_pattern = re.compile(r"\[[\d\w]+\]")
url_pattern = re.compile(r"(http|https)://[^\s]*")
def find_target(bibitem: str, papers: list[PaperData]) -> int|None:
    bibitem = bibitem.replace("\n", " ").strip()
    bibitem = label_pattern.sub("", bibitem)
    bibitem = url_pattern.sub("", bibitem)
    sentences = [s for s in bibitem.split(".") if len(s) > 10]
    for sentence in sentences:
        for paper in papers:
            r = ratio(sentence, paper.paper_title)
            if r > 0.8:
                return paper.paper_id
    return None

def gen_vertex(papers: list[PaperData]) -> list[dict]:
    vertex = []
    for paper in papers:
        vertex.append({
            'id': str(paper.paper_id),
            'label': str(paper.paper_id),
            'title': paper.paper_title,
            'author': paper.author_list,
            # 'url': paper.website_url,
        })
    return vertex

def gen_edge(papers: list[PaperData], V: list[dict]):
    edges = []
    for paper in papers:
        for cite in paper.paper_citation[1]:
            if cite[2] != -1:
                edges.append({
                    'source': str(paper.paper_id),
                    'target': str(cite[2]),
                })
                continue
            target = find_target(cite[1], papers)
            if target is not None:
                edges.append({
                    'source': str(paper.paper_id),
                    'target': str(target),
                })
    return edges
            

if __name__ == '__main__':
    papers = db.select_paper_all()
    papers = [PaperData.from_Paper(paper) for paper in papers]
    
    V = gen_vertex(papers)
    E = gen_edge(papers, V)
    
    data = json.dumps({
        'nodes': V,
        'edges': E,
    })
    
    with open("visualize.template.html", 'r') as f:
        template = f.read()
    result = template.replace('"PLACEHOLDER"', data)
    
    with open("visualize.html", 'w') as f:
        f.write(result)