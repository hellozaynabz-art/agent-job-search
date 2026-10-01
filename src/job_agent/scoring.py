"""Two-stage scoring: cheap TF-IDF pre-ranking for every job, then Claude for the shortlist."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from job_agent.llm import Claude, text_of
from job_agent.sources import Job


class Fit(BaseModel):
    fit_score: int = Field(description="0-100 overall fit for this candidate")
    seniority_match: str = Field(description="'below', 'match' or 'above' the candidate's level")
    matched_skills: list[str] = Field(description="Requirements the candidate clearly meets")
    gaps: list[str] = Field(description="Requirements the candidate lacks or that are unclear")
    dealbreakers_hit: list[str] = Field(description="Candidate dealbreakers this job triggers")
    pitch: str = Field(description="One sentence the candidate could open a cover letter with")


FIT_SCHEMA = {
    "type": "object",
    "properties": {
        "fit_score": {"type": "integer"},
        "seniority_match": {"type": "string", "enum": ["below", "match", "above"]},
        "matched_skills": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "dealbreakers_hit": {"type": "array", "items": {"type": "string"}},
        "pitch": {"type": "string"},
    },
    "required": [
        "fit_score",
        "seniority_match",
        "matched_skills",
        "gaps",
        "dealbreakers_hit",
        "pitch",
    ],
    "additionalProperties": False,
}

SYSTEM = """You are an experienced tech recruiter screening jobs for one candidate.
Score fit honestly from the job description and resume only; do not invent requirements.
Scoring guide: 85-100 strong match worth applying today; 70-84 good match with minor gaps;
50-69 stretch; below 50 poor fit. Cap the score at 40 if any dealbreaker applies or the role is
clearly a different profession. Keep matched_skills and gaps to at most 5 short items each."""


def prerank(jobs: list[Job], resume: str, must_have: list[str]) -> list[tuple[Job, float]]:
    """Similarity of each job to the resume; jobs missing a must-have keyword are dropped."""

    def has_all(job: Job) -> bool:
        text = f"{job.title} {job.description}".lower()
        return all(re.search(rf"\b{re.escape(k.lower())}\b", text) for k in must_have)

    kept = [j for j in jobs if has_all(j)]
    if not kept:
        return []
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    matrix = vec.fit_transform([resume] + [f"{j.title} {j.title} {j.description}" for j in kept])
    sims = cosine_similarity(matrix[0], matrix[1:]).ravel()
    return sorted(zip(kept, sims, strict=True), key=lambda x: x[1], reverse=True)


def score(job: Job, resume: str, preferences: dict, claude: Claude) -> Fit:
    prompt = (
        f"<resume>\n{resume}\n</resume>\n\n"
        f"<preferences>\n{json.dumps(preferences, indent=1)}\n</preferences>\n\n"
        f"<job>\nTitle: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n"
        f"Salary: {job.salary or 'not listed'}\n\n{job.description}\n</job>"
    )
    response = claude.create(
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4_000,
        output_config={"format": {"type": "json_schema", "schema": FIT_SCHEMA}},
    )
    return Fit.model_validate_json(text_of(response))
