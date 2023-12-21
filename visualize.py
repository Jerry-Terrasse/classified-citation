import re
from Levenshtein import ratio
import json
import itertools

import db
from db import Paper, Author, PaperData
from tqdm import tqdm
import multiprocessing as mp

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

def find_target_by_title(title: str, papers: list[PaperData]):
    for paper in papers:
        r = ratio(title, paper.paper_title)
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

# worker function in gen_edge
def gen_edge_deal_vertex(idx: int) -> list[dict[str, str]]:
    global papers
    paper = papers[idx]
    edges = []
    for cite in paper.paper_citation[1]:
        if cite[2] != -1:
            edges.append({
                'source': str(paper.paper_id),
                'target': str(cite[2]),
            })
            continue
        if len(cite) > 3 and cite[3] != '':
            target = find_target_by_title(cite[3], papers)
        else:
            target = find_target(cite[1], papers)
        if target is not None:
            edges.append({
                'source': str(paper.paper_id),
                'target': str(target),
            })
    return edges

# worker init in gen_edge
def gen_edge_worker_init(papers_):
    global papers
    papers = papers_

def gen_edge(papers: list[PaperData], V: list[dict]):
    with mp.Pool(initializer=gen_edge_worker_init, initargs=(papers,)) as p:
        # token_list = list(tqdm(p.imap(quote2tokens, self.quotes, chunksize=chunksize), total=len(self.quotes)))
        results = list(tqdm(p.imap(gen_edge_deal_vertex, range(len(papers))), total=len(papers)))
    edges = list(itertools.chain.from_iterable(results))
    return edges

if __name__ == '__main__':
    db.init_engine('sqlite:///../phocus/database.db')
    papers = db.select_paper_all()
    papers = [PaperData.from_Paper(paper) for paper in papers if paper.paper_citation.startswith("[true")]
    
    V = gen_vertex(papers)
    print(f"{len(V)} valid papers")
    E = gen_edge(papers, V)
    print(f"{len(E)} valid references")
    
    data = json.dumps({
        'nodes': V,
        'edges': E,
    })
    
    with open("visualize.template.html", 'r') as f:
        template = f.read()
    result = template.replace('"PLACEHOLDER"', data)
    
    with open("visualize.html", 'w') as f:
        f.write(result)