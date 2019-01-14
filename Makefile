ISORT_PARAMS = --ignore-whitespace --settings-path . --recursive monitoring_service/
CODE_DIRS = monitoring_service/ request_collector/

all: lint mypy

lint: mypy
	flake8 $(CODE_DIRS)
	isort $(ISORT_PARAMS) --diff --check-only

mypy:
	mypy --ignore-missing-imports --check-untyped-defs $(CODE_DIRS)

isort:
	isort $(ISORT_PARAMS)

test:
	py.test -v
