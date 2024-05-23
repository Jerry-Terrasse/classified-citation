import re
import json
import itertools
import multiprocessing as mp
from tqdm import tqdm
from Levenshtein import ratio
import graph_tool.all as gt
import os

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

def visualize_graph(vertices: list[dict], edges: list[dict]):
    g = gt.Graph(directed=True)
    vertex_map = {}
    
    v_prop_id = g.new_vertex_property("string")
    v_prop_label = g.new_vertex_property("string")
    v_prop_title = g.new_vertex_property("string")
    v_prop_author = g.new_vertex_property("string")
    
    for v in vertices:
        vertex = g.add_vertex()
        vertex_map[v['id']] = vertex
        v_prop_id[vertex] = v['id']
        v_prop_label[vertex] = v['label']
        v_prop_title[vertex] = v['title']
        v_prop_author[vertex] = v['author']
    
    e_prop_source = g.new_edge_property("string")
    e_prop_target = g.new_edge_property("string")
    
    for e in edges:
        if e['source'] in vertex_map and e['target'] in vertex_map:
            edge = g.add_edge(vertex_map[e['source']], vertex_map[e['target']])
            e_prop_source[edge] = e['source']
            e_prop_target[edge] = e['target']
    
    g.vertex_properties['id'] = v_prop_id
    g.vertex_properties['label'] = v_prop_label
    g.vertex_properties['title'] = v_prop_title
    g.vertex_properties['author'] = v_prop_author
    g.edge_properties['source'] = e_prop_source
    g.edge_properties['target'] = e_prop_target
    
    pos = gt.sfdp_layout(g)
    gt.graph_draw(g, pos, output_size=(1000, 1000),
                  vertex_text=g.vertex_properties['label'],
                  vertex_font_size=10,
                  output="graph_tool_visualization.png")

if __name__ == '__main__':
    db.init_engine('sqlite:///../phocus/database.db')
    papers = db.select_paper_all()
    papers = [PaperData.from_Paper(paper) for paper in papers if paper.paper_citation.startswith("[true")]

    V = gen_vertex(papers)
    print(f"{len(V)} valid papers")
    E = gen_edge(papers, V)
    print(f"{len(E)} valid references")
    
    visualize_graph(V, E)
