import json
import queue

import db
from db import Paper, Author, PaperData
from visualize import gen_vertex, gen_edge

def calc_vertex_in_num(E: list[dict[str, str]]) -> dict[str, int]:
    res = {}
    for edge in E:
        if edge['target'] in res:
            res[edge['target']] += 1
        else:
            res[edge['target']] = 1
    return res

def mark_age(E: dict[str, list[str]], S: list[str]) -> dict[str, int]:
    res = {}
    q = queue.Queue()
    for s in S:
        q.put(s)
        res[s] = 0
    while not q.empty():
        v = q.get()
        for u in E.get(v, []):
            if u not in res:
                res[u] = res[v] + 1
                q.put(u)
    return res

def calc_density(E: dict[str, list[str]], V: list[str], age: dict[str, int], thresh: int) -> float:
    v = {v for v in V if age.get(v, 999) <= thresh}
    e = 0
    for u in v:
        e += len([to for to in E[u] if to in v])
    return e / (len(v) * (len(v) - 1))

if __name__ == '__main__':
    db.init_engine('sqlite:///../phocus/database.db') # new 573
    # db.init_engine('sqlite:///../phocus/database.3w.db')
    # db.init_engine('sqlite:///../phocus/database.bak0227.db') # 1w
    # db.init_engine('sqlite:///../phocus/database.bak0204.db') # 4k
    # db.init_engine('sqlite:///../Downloads/database.db') # 2.8w
    # db.init_engine('sqlite:///database.db')
    # db.init_engine('sqlite:///../Downloads/db0509.db') # 2.8w
    papers = db.select_paper_all()
    papers = [PaperData.from_Paper(paper) for paper in papers if paper.paper_citation.startswith("[true")]
    
    V = gen_vertex(papers)
    V_id: list[str] = [v['id'] for v in V]
    print(f"{len(V)} valid papers")
    E = gen_edge(papers, V)
    print(f"{len(E)} valid references")
    
    # E: list[dict[str, str]]
    '''
    {
        'source': str(source_id),
        'target': str(target_id),
    }
    '''
    vertex_in_num = calc_vertex_in_num(E)
    source = [v for v in V_id if v not in vertex_in_num]
    
    E_per_v: dict[str, list[str]] = {v: [] for v in V_id}
    for edge in E:
        E_per_v[edge['source']].append(edge['target'])
    
    age = mark_age(E_per_v, source)
    json.dump(age, open('age.json', 'w'), indent=4)
    json.dump(V_id, open('V_id.json', 'w'), indent=4)
    # assert len(age) == len(V_id), f"{len(age)} != {len(V_id)}"
    
    for age_max in range(max(age.values()) + 1):
        print(f"age: {age_max}, density: {calc_density(E_per_v, V_id, age, age_max)}")
