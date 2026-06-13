from typing import Literal, Annotated
from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict

def parse_cors_origins(v: any) -> list[str]:
    if isinstance(v, str):
        if not v.strip():
            return []
        if v.startswith("[") and v.endswith("]"):
            try:
                import json
                return json.loads(v)
            except Exception:
                pass
        return [item.strip() for item in v.split(",") if item.strip()]
    elif isinstance(v, list):
        return [str(item).strip() for item in v]
    return v


class Settings(BaseSettings):
    # API Keys
    gemini_api_key: str = ""
    gemini_api_key_1: str = ""
    gemini_api_key_2: str = ""
    gemini_api_key_3: str = ""
    openai_api_key: str = ""
    pubmed_email: str = ""
    pubmed_api_key: str = ""
    pubmed_email_1: str = ""
    pubmed_api_key_1: str = ""
    pubmed_email_2: str = ""
    pubmed_api_key_2: str = ""

    # LLM Config
    extraction_model: str = "gemini-2.5-flash"
    judge_model: str = "gemini-2.5-flash"
    llm_provider: Literal["gemini", "openai"] = "gemini"

    # Pipeline Thresholds
    max_papers: int = 25
    min_papers: int = 5
    claims_per_abstract_cap: int = 7
    quote_anchor_pass_threshold: float = 85.0
    quote_anchor_flag_threshold: float = 70.0
    faiss_top_k: int = 10
    nli_contradiction_threshold: float = 0.7
    max_contradictions_displayed: int = 15

    # Concurrency
    pubmed_concurrency: int = 3
    llm_concurrency: int = 3
    section_concurrency: int = 1

    # Section extraction filtering
    # When True, only extract from sections listed in primary_section_names.
    # This improves claim precision and reduces LLM cost by ~40% for full-text papers.
    # Set PRIMARY_SECTIONS_ONLY=false in .env to restore all-sections behavior.
    primary_sections_only: bool = True
    primary_section_names: list[str] = [
        "abstract",
        "results",
        "result",
        "discussion",
        "discussions",
        "conclusions",
        "conclusion",
        "findings",
        "summary",
    ]

    # Cost Estimation (approximate USD costs per paper, contradiction pair, and synthesis run)
    cost_per_paper: float = 0.0008         # Extraction cost per paper
    cost_per_contradiction: float = 0.008   # Judgment cost per candidate pair
    cost_synthesis: float = 0.045           # Base cost for summary synthesis report

    # Paths
    db_path: str = "data/claims.db"
    faiss_index_path: str = "data/claims.faiss"
    synonym_map_path: str = "data/synonym_map.json"

    # CORS configuration
    allowed_origins: Annotated[list[str], BeforeValidator(parse_cors_origins)] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @property
    def gemini_api_keys(self) -> list[str]:
        keys = []
        for k in [self.gemini_api_key_1, self.gemini_api_key_2, self.gemini_api_key_3]:
            if k and k.strip():
                keys.append(k.strip())
        if not keys and self.gemini_api_key and self.gemini_api_key.strip():
            keys.append(self.gemini_api_key.strip())
        return keys

    @property
    def pubmed_credentials(self) -> list[tuple[str, str]]:
        pairs = []
        # Check pool 1
        email_1 = self.pubmed_email_1.strip() if self.pubmed_email_1 else ""
        key_1 = self.pubmed_api_key_1.strip() if self.pubmed_api_key_1 else ""
        if email_1 or key_1:
            pairs.append((email_1, key_1))
            
        # Check pool 2
        email_2 = self.pubmed_email_2.strip() if self.pubmed_email_2 else ""
        key_2 = self.pubmed_api_key_2.strip() if self.pubmed_api_key_2 else ""
        if email_2 or key_2:
            pairs.append((email_2, key_2))
            
        # Fallback to main ones
        if not pairs:
            email_main = self.pubmed_email.strip() if self.pubmed_email else ""
            key_main = self.pubmed_api_key.strip() if self.pubmed_api_key else ""
            if email_main or key_main:
                pairs.append((email_main, key_main))
        return pairs

    # Configuration for Pydantic Settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
