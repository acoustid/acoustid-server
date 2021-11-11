venv: venv
	virtualenv -p python3 venv
	venv/bin/pip install pip-tools
	$(MAKE) sync-reqs

update-reqs:
	venv/bin/pip-compile --output-file requirements.txt requirements.in
	venv/bin/pip-compile --output-file requirements_dev.txt requirements_dev.in

sync-reqs:
	venv/bin/pip-sync requirements.txt requirements_dev.txt

lint:
	tox -e flake8,mypy

check:
	tox

clean:
	rm -rf venv

.PHONY: venv update-reqs sync-reqs lint check
