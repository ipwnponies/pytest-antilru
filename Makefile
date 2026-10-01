SHELL := bash
.DEFAULT_GOAL := test
INSTALL_STAMP := .venv/venv.touch

.PHONY: venv setup hooks
venv: $(INSTALL_STAMP)

setup: venv hooks

hooks: venv
	uv run pre-commit install --install-hooks

$(INSTALL_STAMP): pyproject.toml uv.lock
	uv sync

.PHONY: lock
lock:
	uv lock
	poetry lock

.PHONY: publish
publish:
	uv build
	@read -s -p "PyPI token: " UV_PUBLISH_TOKEN; echo; \
	UV_PUBLISH_TOKEN=$$UV_PUBLISH_TOKEN uv publish

.PHONY: build
build:
	uv build

.PHONY: test
test: $(INSTALL_STAMP)
	uv run tox

.PHONY: clean
clean: ## Clean working directory
	find . -iname '*.pyc' | xargs rm -f
	rm -rf ./.venv/ ./.tox/ ./.coverage build/ ./dist/ ./pytest_antilru.egg-info/
