env:
	virtualenv -p python e
	e/bin/pip install pip-tools
	$(MAKE) sync-reqs

update-reqs:
	e/bin/pip-compile --output-file requirements.txt requirements.in
	e/bin/pip-compile --output-file requirements_dev.txt requirements_dev.in

sync-reqs:
	e/bin/pip-sync requirements.txt requirements_dev.txt

lint:
	tox -e flake8,mypy-py2,mypy-py3

check:
	tox

.PHONY: env update-reqs sync-reqs lint check
