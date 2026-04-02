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
    subtitle: str | None = ""
    bullets: list[str] = Field(default_factory=list)
    key_stat: str | None = ""
    slide_type: str = "content"
    source_ids: list[int] = Field(default_factory=list)
    dashboard_metrics: list[dict] = Field(default_factory=list)
    chart: dict | None = None
    table_data: dict | None = None
    risk_blocks: list[dict] | None = None
    progress_bars: list[dict] | None = None

    def model_post_init(self, __context: object) -> None:
        if self.subtitle is None:
            self.subtitle = ""
        if self.key_stat is None:
            self.key_stat = ""


class ResearchResponse(BaseModel):
    company: str
    generated_at: str
    research_summary: dict
    slides: list[SlideItem]
    sources: list[SourceItem]
    pptx_url: str
