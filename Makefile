CODE_DIRS = monitoring/monitoring_service/ monitoring/request_collector/ pathfinding/pathfinding_service
ISORT_PARAMS = --ignore-whitespace --settings-path . --recursive $(CODE_DIRS)

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
