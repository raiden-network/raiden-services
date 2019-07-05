CODE_DIRS = src/ tests/ setup.py
ISORT_PARAMS = --ignore-whitespace --settings-path . --recursive $(CODE_DIRS)
BLACK_PARAMS = --line-length 99

all: lint

lint: mypy
	black --check $(BLACK_PARAMS) $(CODE_DIRS)
	flake8 $(CODE_DIRS)
	isort $(ISORT_PARAMS) --diff --check-only
	pylint $(CODE_DIRS)

mypy:
	mypy $(CODE_DIRS)

isort:
	isort $(ISORT_PARAMS)

black:
	black $(BLACK_PARAMS) $(CODE_DIRS)

format: isort black

test:
	py.test -v tests

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt
