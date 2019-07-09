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
