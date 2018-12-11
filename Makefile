ISORT_PARAMS = --ignore-whitespace --settings-path . --recursive monitoring_service/

all: lint mypy

lint:
	flake8 monitoring_service/
	isort $(ISORT_PARAMS) --diff --check-only

mypy:
	mypy --ignore-missing-imports monitoring_service/

isort:
	isort $(ISORT_PARAMS)
