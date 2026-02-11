.DEFAULT_GOAL := test
INSTALL_STAMP := .venv/venv.touch

.PHONY: venv
venv: $(INSTALL_STAMP)

$(INSTALL_STAMP): pyproject.toml uv.lock
	uv sync
	uv run pre-commit install

.PHONY: lock
lock:
	uv lock
	poetry lock

.PHONY: publish
publish:
	uv build
	uv publish

.PHONY: test
test: $(INSTALL_STAMP)
	uv run tox

.PHONY: clean
clean: ## Clean working directory
	find . -iname '*.pyc' | xargs rm -f
	rm -rf ./.venv/ ./.tox/ ./.coverage build/ ./dist/ ./pytest_antilru.egg-info/
