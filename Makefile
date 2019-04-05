CODE_DIRS = src/ tests/
ISORT_PARAMS = --ignore-whitespace --settings-path . --recursive $(CODE_DIRS)
BLACK_PARAMS = --skip-string-normalization --line-length 99

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
