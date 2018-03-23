all: lint mypy

lint:
	flake8 monitoring_service/

mypy:
	mypy --ignore-missing-imports monitoring_service/
