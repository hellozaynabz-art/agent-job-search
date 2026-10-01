"""Job sources. Each returns a list of ``Job`` with the same fields.

* ``sample``   bundled demo postings (offline)
* ``remotive`` Remotive's public remote-jobs API (no key; please keep requests to a few per day
               and credit Remotive as the source, per their API terms)
* ``kaggle``   LinkedIn Job Postings dataset (arshkon/linkedin-job-postings), ~120k postings
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

DATA = Path("data")
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


class Job(BaseModel):
    id: str
    title: str
    company: str
    location: str = ""
    salary: str = ""
    url: str = ""
    posted: str = ""
    source: str
    description: str


def clean_html(text: str) -> str:
    text = re.sub(r"<(br|p|li|/li|/p|h\d)[^>]*>", "\n", text or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def sample() -> list[Job]:
    return [Job(**j) for j in json.loads((DATA / "sample_jobs.json").read_text())]


def remotive(queries: list[str], limit: int = 40) -> list[Job]:
    jobs: dict[str, Job] = {}
    for q in queries:
        url = f"{REMOTIVE_URL}?{urllib.parse.urlencode({'search': q, 'limit': limit})}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "job-search-agent (portfolio project)"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
        for j in payload.get("jobs", []):
            jobs[f"remotive-{j['id']}"] = Job(
                id=f"remotive-{j['id']}",
                title=j["title"],
                company=j["company_name"],
                location=j.get("candidate_required_location", ""),
                salary=j.get("salary", ""),
                url=j["url"],
                posted=j.get("publication_date", "")[:10],
                source="remotive",
                description=clean_html(j.get("description", ""))[:6000],
            )
    return list(jobs.values())


def kaggle(queries: list[str], limit: int = 200) -> list[Job]:
    dest = DATA / "kaggle"
    path = dest / "postings.csv"
    if not path.exists():
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "uvx",
                "kaggle",
                "datasets",
                "download",
                "-d",
                "arshkon/linkedin-job-postings",
                "-p",
                str(dest),
                "--unzip",
            ],
            check=True,
        )
    df = pd.read_csv(
        path,
        usecols=[
            "job_id",
            "title",
            "company_name",
            "location",
            "max_salary",
            "min_salary",
            "job_posting_url",
            "description",
        ],
    )
    pattern = "|".join(re.escape(q) for q in queries)
    df = df[df["title"].str.contains(pattern, case=False, na=False)].head(limit)
    return [
        Job(
            id=f"linkedin-{r.job_id}",
            title=r.title,
            company=str(r.company_name),
            location=str(r.location),
            salary=f"${r.min_salary:,.0f}–${r.max_salary:,.0f}"
            if pd.notna(r.max_salary) and pd.notna(r.min_salary)
            else "",
            url=str(r.job_posting_url),
            source="kaggle-linkedin",
            description=str(r.description)[:6000],
        )
        for r in df.itertuples()
    ]


def fetch(source: str, queries: list[str]) -> list[Job]:
    if source == "remotive":
        return remotive(queries)
    if source == "kaggle":
        return kaggle(queries)
    return sample()
