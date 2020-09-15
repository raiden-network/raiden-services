CODE_DIRS = src/ tests/ setup.py
ISORT_PARAMS = --ignore-whitespace --settings-path . --recursive $(CODE_DIRS)

all: lint

lint: mypy
	black --check --diff $(CODE_DIRS)
	flake8 $(CODE_DIRS)
	isort $(ISORT_PARAMS) --diff --check-only
	pylint $(CODE_DIRS)

mypy:
	mypy $(CODE_DIRS)

isort:
	isort $(ISORT_PARAMS)

black:
	black $(CODE_DIRS)

format: isort black

test:
	pytest-gevent -v tests -n 4

install:
	pip install -r requirements.txt

install-dev:
	pip install -U -r requirements-dev.txt
	pip install -e .

dist:
	python3 setup.py sdist bdist_wheel

clean: clean-build clean-pyc

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -delete
	find . -name '*.egg' -delete

clean-pyc:
	find . -name '*.pyc' -delete
	find . -name '*.pyo' -delete
	find . -name '__pycache__' -delete

.PHONY: dist
