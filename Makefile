.DEFAULT_GOAL := test
INSTALL_STAMP := .venv/venv.touch

.PHONY: venv
venv: $(INSTALL_STAMP)

$(INSTALL_STAMP): pyproject.toml poetry.lock
	poetry install --remove-untracked
	.venv/bin/pre-commit install

.PHONY: publish
publish:
	poetry publish --build

.PHONY: test
test: $(INSTALL_STAMP)
	.venv/bin/tox

.PHONY: clean
clean: ## Clean working directory
	find . -iname '*.pyc' | xargs rm -f
	rm -rf ./.venv/ ./.tox/ ./.coverage build/ ./dist/ ./pytest_antilru.egg-info/
