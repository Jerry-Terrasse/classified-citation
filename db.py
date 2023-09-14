import json
import sqlalchemy
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    select,
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

Cite = tuple[str, str, int]
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
        assert paper_citation_obj[0]
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

def init_engine(db_path: str):
    global engine
    engine = sqlalchemy.create_engine(db_path)

def select_paper_by_id(paper_id: int) -> Paper|None:
    stmt = select(Paper).where(Paper.paper_id == paper_id)
    with Session(engine) as session:
        res = session.scalar(stmt)
        return res

def select_paper_all() -> Sequence[Paper]:
    stmt = select(Paper)
    with Session(engine) as session:
        res = session.execute(stmt)
        return res.scalars().all()

if __name__ == '__main__':
    init_engine("sqlite:///database.db")
    papers = select_paper_all()
    for paper in papers:
        print(paper)
        print(PaperData.from_Paper(paper))
        print()