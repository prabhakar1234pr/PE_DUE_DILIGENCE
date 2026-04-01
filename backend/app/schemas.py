from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class ResearchRequest(BaseModel):
    company: str = Field(..., min_length=1, max_length=120)


class SourceItem(BaseModel):
    id: int
    title: str
    url: str
    snippet: str


class SlideItem(BaseModel):
    slide_number: int
    title: str
    subtitle: str = ""
    bullets: list[str]
    key_stat: str = ""
    source_ids: list[int] = Field(default_factory=list)
    dashboard_metrics: list[dict] = Field(default_factory=list)


class ResearchResponse(BaseModel):
    company: str
    generated_at: str
    research_summary: dict
    slides: list[SlideItem]
    sources: list[SourceItem]
    pptx_url: str
