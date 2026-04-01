import os


class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_research_model: str = os.getenv("GEMINI_RESEARCH_MODEL", "gemini-2.5-pro")
    gemini_slide_model: str = os.getenv("GEMINI_SLIDE_MODEL", "gemini-2.5-pro")
    gcp_bucket_name: str = os.getenv("GCP_BUCKET_NAME", "")
    gcp_project_id: str = os.getenv("GCP_PROJECT_ID", "")
    mock_mode: bool = os.getenv("MOCK_MODE", "false").lower() == "true"
    research_max_attempts: int = int(os.getenv("RESEARCH_MAX_ATTEMPTS", "3"))
    slide_max_attempts: int = int(os.getenv("SLIDE_MAX_ATTEMPTS", "3"))


settings = Settings()
