import os
import re
import json
import itertools
import multiprocessing as mp
from tqdm import tqdm
from Levenshtein import ratio
import graph_tool.all as gt
from pyvis.network import Network

import db
from db import Paper, Author, PaperData

label_pattern = re.compile(r"\[[\d\w]+\]")
url_pattern = re.compile(r"(http|https)://[^\s]*")

def find_target(bibitem: str, papers: list[PaperData]) -> int | None:
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
        })
    return vertex


# worker function in gen_edge
def gen_edge_deal_vertex(idx: int) -> list[dict[str, str]]:
    global papers
    paper = papers[idx]
    targets: set[str] = set()
    for cite in paper.paper_citation[1]:
        if cite[2] != -1:
            targets.add(str(cite[2]))
            continue
        if len(cite) > 3 and cite[3] != '':
            target = find_target_by_title(cite[3], papers)
        else:
            target = find_target(cite[1], papers)
        if target is not None:
            targets.add(str(target))
    edges = []
    paper_id = str(paper.paper_id)
    for target in targets:
        edges.append({
            'source': paper_id,
            'target': str(target),
        })
    return edges

# worker init in gen_edge
def gen_edge_worker_init(papers_):
    global papers
    papers = papers_

def gen_edge(papers: list[PaperData], V: list[dict]):
    cache_file = f'edge_cache_{len(papers)}.json'
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)
    with mp.Pool(initializer=gen_edge_worker_init, initargs=(papers,)) as p:
        results = list(tqdm(p.imap(gen_edge_deal_vertex, range(len(papers))), total=len(papers)))
    edges = list(itertools.chain.from_iterable(results))
    with open(cache_file, 'w') as f:
        json.dump(edges, f, indent=4)
    return edges

def export_graph(vertices: list[dict], edges: list[dict], filename: str):
    net = Network(notebook=True, directed=True)
    
    for vertex in vertices:
        net.add_node(vertex['id'], label=vertex['label'], title=vertex['title'], author=vertex['author'])
    
    for edge in tqdm(edges):
        net.add_edge(edge['source'], edge['target'])
    
    net.show_buttons(filter_=['physics'])
    net.show(filename)

if __name__ == '__main__':
    db.init_engine('sqlite:///../phocus/database.db')
    papers = db.select_paper_all()
    papers = [PaperData.from_Paper(paper) for paper in papers if paper.paper_citation.startswith("[true")]

    V = gen_vertex(papers)
    print(f"{len(V)} valid papers")
    E = gen_edge(papers, V)
    V_set = set([v['id'] for v in V])
    E = [e for e in E if e['source'] in V_set and e['target'] in V_set]
    print(f"{len(E)} valid references")
    
    export_graph(V, E, "interactive_graph.html")
