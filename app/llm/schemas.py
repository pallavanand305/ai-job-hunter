from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JDAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role_title: str = ""
    seniority: str = ""
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ExperienceRewrite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    company: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class ProjectRewrite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    bullets: list[str] = Field(default_factory=list)


class TailorOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceRewrite] = Field(default_factory=list)
    projects: list[ProjectRewrite] = Field(default_factory=list)
    cover_letter: str = ""
    gaps: list[str] = Field(default_factory=list)

    def meaningful(self) -> bool:
        return bool(
            self.summary.strip()
            or self.skills
            or self.experience
            or self.projects
            or self.cover_letter.strip()
        )


class LLMTestResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ok: bool = False
