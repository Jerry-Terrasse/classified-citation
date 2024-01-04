import json
import sqlalchemy
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    select,
    update,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
)

from typing import Sequence

engine = None

class ModelBase(DeclarativeBase):
    pass

class Author(ModelBase):
    __tablename__ = "author_data"
    author_id = Column(Integer, primary_key=True)
    author_name = Column(Text)
    author_paper_list = Column(Text) # JSON

class Paper(ModelBase):
    __tablename__ = "paper_data"
    paper_id = Column(Integer, primary_key=True)
    paper_title = Column(Text)
    website_url = Column(Text)
    author_list = Column(Text) # JSON
    paper_citation = Column(Text) # JSON
    paper_year = Column(Text) # JSON

Cite = tuple[str, str, int, str]
class PaperData:
    paper_id: int
    paper_title: str
    website_url: str
    author_list: tuple[bool, list[str]]
    paper_citation: tuple[bool, list[Cite]]
    paper_year: tuple[bool, str]

    def __init__(
            self,
            paper_title: str,
            website_url: str,
            author_list: tuple[bool, list[str]],
            paper_citation: tuple[bool, list[Cite]],
            paper_year: tuple[bool, str],
            paper_id: int = -1,
    ):
        self.paper_title = paper_title
        self.website_url = website_url
        self.author_list = author_list
        self.paper_citation = paper_citation
        self.paper_year = paper_year
        self.paper_id = paper_id
    
    def __repr__(self) -> str:
        return f"PaperData({self.paper_title!r}, {self.website_url!r}, {self.author_list!r}, {self.paper_citation!r}, {self.paper_year!r}, {self.paper_id!r})"
    
    @staticmethod
    def from_Paper(paper: Paper) -> 'PaperData':
        paper_title = str(paper.paper_title)
        website_url = str(paper.website_url)
        
        author_list_obj = json.loads(str(paper.author_list))
        assert author_list_obj[0]
        author_list = author_list_obj[1]
        
        paper_citation_obj = json.loads(str(paper.paper_citation))
        # assert paper_citation_obj[0]
        paper_citation = paper_citation_obj[1]
        
        paper_year_obj = json.loads(str(paper.paper_year))
        assert paper_year_obj[0]
        paper_year = paper_year_obj[1]
        
        return PaperData(
            paper_title,
            website_url,
            (True, author_list),
            (True, paper_citation),
            (True, paper_year),
            paper.paper_id
        )
    def to_Paper(self) -> Paper:
        author_list_obj = json.dumps(self.author_list)
        paper_citation_obj = json.dumps(self.paper_citation)
        paper_year_obj = json.dumps(self.paper_year)
        return Paper(
            paper_title=self.paper_title,
            website_url=self.website_url,
            author_list=author_list_obj,
            paper_citation=paper_citation_obj,
            paper_year=paper_year_obj,
            paper_id=self.paper_id,
        )

def init_engine(db_path: str):
    global engine
    engine = sqlalchemy.create_engine(db_path)

def select_paper_by_id(paper_id: int) -> Paper|None:
    stmt = select(Paper).where(Paper.paper_id == paper_id)
    with Session(engine) as session:
        res = session.scalar(stmt)
        return res

paper_data_cache: dict[int, PaperData] = {}
def paper_data_by_id(paper_id: int) -> PaperData:
    global paper_data_cache
    if paper_id in paper_data_cache:
        return paper_data_cache[paper_id]
    paper = select_paper_by_id(paper_id)
    assert paper
    paper_data = PaperData.from_Paper(paper)
    paper_data_cache[paper_id] = paper_data
    return paper_data

def select_paper_all() -> Sequence[Paper]:
    stmt = select(Paper)
    with Session(engine) as session:
        res = session.execute(stmt)
        return res.scalars().all()

def update_paper(paper: Paper, column: str):
    stmt = update(Paper).where(Paper.paper_id == paper.paper_id).values({column: paper.__getattribute__(column)})
    with Session(engine) as session:
        session.execute(stmt)
        session.commit()

if __name__ == '__main__':
    init_engine("sqlite:///database.db")
    papers = select_paper_all()
    for paper in papers:
        print(paper)
        print(PaperData.from_Paper(paper))
        print()