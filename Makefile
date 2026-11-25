# Overlay workflow for the IRIS connector (ADR-0014). Targets stay small; logic is in scripts/.
.PHONY: om-import om-export om-check om-image om-ui-codegen

om-import:
	@scripts/om-import.sh

om-export:
	@scripts/om-export.sh

om-check:
	@scripts/om-check.sh

om-image:
	@scripts/om-image.sh

om-ui-codegen:
	@scripts/om-ui-codegen.sh

# --- 001: test harness ---
# One local cell: make test-cell TAG=latest-cd LOGIN=reader_dict [PORT=11972]. Host port 1972 stays free.
TAG ?= latest-em
LOGIN ?= reader
PORT ?= 11972
FIXTURES_PYTHON ?= $(if $(wildcard .om/env/bin/python),.om/env/bin/python,python3)
.PHONY: om-test-deps iris-up iris-seed iris-down test-cell

# make om-import resets .om/env to the dev profile, so run this after every om-import.
om-test-deps:
	@scripts/om-test-deps.sh

iris-up:
	@PYTHON=$(FIXTURES_PYTHON) fixtures/iris/start-iris.sh $(TAG) $(PORT) omd-test-iris-$(TAG)

iris-seed:
	@IRIS_HOST=127.0.0.1 IRIS_PORT=$(PORT) $(FIXTURES_PYTHON) fixtures/iris/seed.py

iris-down:
	@docker rm -f omd-test-iris-$(TAG) >/dev/null && echo "removed omd-test-iris-$(TAG)"

test-cell: om-test-deps iris-up iris-seed
	@cd .om/ingestion && IRIS_HOST=127.0.0.1 IRIS_PORT=$(PORT) IRIS_TAG=$(TAG) IRIS_LOGIN=$(LOGIN) \
		../env/bin/python -m pytest tests/integration/iris -m iris -rs
