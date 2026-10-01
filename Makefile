.PHONY: setup profile run run-live run-offline test lint clean

setup:  ## install dependencies into .venv
	uv sync

profile:  ## create your private profile files from the examples (gitignored)
	cp -n profile/resume.example.md profile/resume.md || true
	cp -n profile/preferences.example.json profile/preferences.json || true

run:  ## score the bundled sample jobs with Claude
	uv run job-agent

run-live:  ## search live remote jobs (Remotive) and score them
	uv run job-agent --source remotive

run-offline:  ## similarity ranking only, no API key
	uv run job-agent --no-llm

test:  ## offline tests (no API key needed)
	uv run pytest -q

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

clean:
	rm -rf data/tracker.csv data/kaggle .pytest_cache .ruff_cache
