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
.PHONY: om-test-deps

om-test-deps:
	@scripts/om-test-deps.sh
