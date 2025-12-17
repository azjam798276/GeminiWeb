.PHONY: test run lint build distcheck

test:
	pytest -q

lint:
	ruff check .
	mypy src

run:
	bash scripts/run_server.sh

build:
	python3 -m build

distcheck:
	python3 -m twine check dist/*
