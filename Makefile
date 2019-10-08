venv: venv-py2 venv-py3

venv-py2:
	virtualenv -p python2 venv2
	venv2/bin/pip install pip-tools
	$(MAKE) sync-reqs-py2

venv-py3:
	virtualenv -p python3 venv3
	venv3/bin/pip install pip-tools
	$(MAKE) sync-reqs-py3

update-reqs: update-reqs-py2 update-reqs-py3

update-reqs-py2:
	venv2/bin/pip-compile --output-file requirements_py2.txt requirements.in
	venv2/bin/pip-compile --output-file requirements_dev_py2.txt requirements_dev.in

update-reqs-py3:
	venv3/bin/pip-compile --output-file requirements_py3.txt requirements.in
	venv3/bin/pip-compile --output-file requirements_dev_py3.txt requirements_dev.in

sync-reqs: sync-reqs-py2 sync-reqs-py3

sync-reqs-py2:
	venv2/bin/pip-sync requirements_py2.txt requirements_dev_py2.txt

sync-reqs-py3:
	venv3/bin/pip-sync requirements_py3.txt requirements_dev_py3.txt

lint:
	tox -e flake8-py2,flake8-py3,mypy-py2,mypy-py3

check:
	tox

clean:
	rm -rf venv2 venv3

.PHONY: venv-py2 venv-py3 update-reqs-py2 update-reqs-py3 sync-reqs-venv-py2 sync-reqs-venv-py3 lint check
