import json
from types import SimpleNamespace

from job_agent import scoring, sources, tracker
from job_agent.llm import Claude

RESUME = open("profile/resume.example.md").read()


def test_clean_html():
    assert sources.clean_html("<p>SQL &amp; Python</p><ul><li>dbt</li></ul>") == "SQL & Python\ndbt"


def test_prerank_puts_relevant_jobs_first_and_applies_must_haves():
    ranked = scoring.prerank(sources.sample(), RESUME, must_have=["SQL"])
    titles = [j.title for j, _ in ranked]
    assert "Junior Data Entry Clerk" not in titles  # no SQL in the posting
    assert titles[0] in {
        "Senior Product Analyst",
        "Senior Data Analyst, Risk",
        "Analytics Engineer",
        "AI Product Analyst",
    }


def test_score_parses_structured_output():
    payload = {
        "fit_score": 88,
        "seniority_match": "match",
        "matched_skills": ["SQL", "A/B testing"],
        "gaps": ["Snowflake"],
        "dealbreakers_hit": [],
        "pitch": "I build funnels.",
    }
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(payload))],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0),
        )

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    fit = scoring.score(sources.sample()[0], RESUME, {"must_have": ["SQL"]}, Claude(client=client))
    assert fit.fit_score == 88 and fit.gaps == ["Snowflake"]
    assert seen["output_config"]["format"]["type"] == "json_schema"


def test_tracker_keeps_user_edits(tmp_path):
    path = tmp_path / "tracker.csv"
    row = {"id": "a", "fit_score": 80, "title": "T", "company": "C"}
    df, added = tracker.upsert([row], path)
    assert added == 1
    df.loc[0, "status"] = "applied"
    df.to_csv(path, index=False)
    df, added = tracker.upsert([row, {**row, "id": "b"}], path)
    assert added == 1
    assert df.set_index("id").loc["a", "status"] == "applied"
