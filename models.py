from typing import List
from pydantic import BaseModel


class SubTheme(BaseModel):
    id: int
    label: str
    description: str


class Theme(BaseModel):
    id: int
    label: str
    tagline: str
    description: str
    subThemes: List[SubTheme] = []
