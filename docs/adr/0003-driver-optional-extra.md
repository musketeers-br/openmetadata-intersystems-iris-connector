# ADR-0003 — Driver shipped as the optional `iris` extra

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-3 · **Binds:** FR-23, NFR-3 · **Constitution:** II, VII

## Context

The official driver and dialect are distributed under the InterSystems External Repository Terms of Use, which is not an OSI licence. OpenMetadata already ships proprietary drivers as optional plugin extras, for example `sap-hana` (`hdbcli`) and `teradata` (`teradatasql`). OpenMetadata's `ingestion/` folder is under the Collate Community License v1.0.

## Decision

- `ingestion/setup.py` gets an `"iris"` entry in its `plugins` map with `intersystems-irispython` and `sqlalchemy-intersystems-iris`. The pinned versions follow OpenMetadata's convention in that file.
- The packages are never vendored or modified.
- The connector docs (spec 008) state the licence terms of the extra and link to them.
- Our repository's README (spec 009) states the same.

## Consequences

- `pip install "openmetadata-ingestion[iris]"` is the install path. The base ingestion package stays free of non-OSI dependencies.
- Whether the extra is included in OpenMetadata's published ingestion image is the maintainers' call. The PR description raises it explicitly (spec 009).

## Alternatives rejected

- **Core dependency:** imposes non-OSI terms on every OpenMetadata user.
- **Vendoring:** forbidden by the terms (redistribute unmodified with the terms included) and by constitution II.

## Validation

Spec 000: `pip install -e "ingestion[iris]"` installs the stack, and without the extra, importing the IRIS connector fails with OpenMetadata's standard missing-extra message. Spec 009: the PR checklist confirms the extra is listed in the docs.
