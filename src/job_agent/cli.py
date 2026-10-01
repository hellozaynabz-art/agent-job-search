"""Find jobs, score fit against your resume, update the tracker, write a shortlist.

uv run job-agent                       # bundled sample jobs
uv run job-agent --source remotive     # live remote jobs
uv run job-agent --source kaggle       # LinkedIn postings dataset
uv run job-agent --no-llm              # similarity ranking only, no API key
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

from job_agent import scoring, sources, tracker
from job_agent.llm import Claude

console = Console()
PROFILE = Path("profile")


def _profile_file(name: str, example: str) -> Path:
    path = PROFILE / name
    if path.exists():
        return path
    console.print(f"[yellow]Using {example}. Copy it to profile/{name} and make it yours.[/]")
    return PROFILE / example


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["sample", "remotive", "kaggle"], default="sample")
    parser.add_argument("--no-llm", action="store_true", help="rank by text similarity only")
    args = parser.parse_args()

    resume = _profile_file("resume.md", "resume.example.md").read_text()
    prefs = json.loads(_profile_file("preferences.json", "preferences.example.json").read_text())

    jobs = sources.fetch(args.source, prefs["target_titles"])
    ranked = scoring.prerank(jobs, resume, prefs.get("must_have", []))
    shortlist = ranked[: prefs.get("max_jobs_to_score", 15)]
    console.print(
        f"{len(jobs)} jobs found · {len(ranked)} meet must-haves · scoring {len(shortlist)}"
    )

    claude = None if args.no_llm else Claude()
    rows = []
    for job, sim in shortlist:
        if claude:
            with console.status(f"Scoring {job.title} at {job.company}…"):
                fit = scoring.score(job, resume, prefs, claude)
            fit_score, matched, gaps, pitch = fit.fit_score, fit.matched_skills, fit.gaps, fit.pitch
        else:
            fit_score, matched, gaps, pitch = round(sim * 100), [], [], ""
        rows.append(
            {
                "id": job.id,
                "fit_score": fit_score,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "salary": job.salary,
                "url": job.url,
                "source": job.source,
                "matched_skills": "; ".join(matched),
                "gaps": "; ".join(gaps),
                "pitch": pitch,
            }
        )
    rows.sort(key=lambda r: r["fit_score"], reverse=True)

    _, added = tracker.upsert(rows)
    table = Table(title="Shortlist", show_lines=False)
    for col in ["fit_score", "title", "company", "location", "gaps"]:
        table.add_column(col)
    for r in rows[:10]:
        table.add_row(str(r["fit_score"]), r["title"], r["company"], r["location"], r["gaps"][:60])
    console.print(table)

    lines = [f"# Job shortlist — {date.today():%d %b %Y}", ""]
    for r in rows:
        lines += [
            f"## {r['fit_score']} · [{r['title']} — {r['company']}]({r['url']})",
            f"{r['location']} · {r['salary'] or 'salary not listed'} · via {r['source']}",
            "",
        ]
        if r["matched_skills"]:
            lines += [
                f"- **Matches:** {r['matched_skills']}",
                f"- **Gaps:** {r['gaps']}",
                f"- **Pitch:** {r['pitch']}",
                "",
            ]
    if args.source == "remotive":
        lines.append("_Remote job listings provided by [Remotive](https://remotive.com)._")
    out = Path("reports") / f"shortlist_{date.today():%Y-%m-%d}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines))
    cost = f" · ${claude.usage.cost_usd:.3f}" if claude else ""
    console.print(
        f"[green]{added} new jobs added to {tracker.TRACKER} · shortlist saved to {out}{cost}[/]"
    )


if __name__ == "__main__":
    main()
