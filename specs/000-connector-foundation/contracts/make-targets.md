# Contract: Make targets

Owned by spec 000 (`Makefile`); extended by 001 (`test-cell`), 008 (demo image), 009 (`om-branch`).

| Target | Does | Success | Fails when |
|---|---|---|---|
| `om-import` | Shallow-clone OpenMetadata at the tag in `openmetadata.version` into `.om/` if missing or stale; copy `overlay/`; `git apply` `patches/`; `uv lock`; `make install_dev generate` in `.om/ingestion` with Python 3.11. Idempotent | The IRIS connector imports from `.om/ingestion`; its unit tests pass | clone fails, a patch does not apply, Python 3.11 or Docker (ANTLR wrapper) missing; the message names the cause |
| `om-export` | In `.om/`: `git status --porcelain`; new files → `overlay/`; modified tracked files → `patches/<path with / as __>.patch` via `git diff`. Generated and ignored files are never exported | `overlay/` and `patches/` match the tree | a tracked file was deleted (error, nothing written); no `.om/` |
| `om-check` | `om-import`, `om-export`, then `git diff --exit-code overlay patches` | no diff | any diff, which is printed |
| `om-image` | From `.om/`, in Docker (Maven + yarn): build the OpenMetadata server image and the ingestion image (with the `iris` extra) that know `Iris` | both images exist locally | build error. Not required by connector unit or integration tests |

Rules: `om-export` runs before every commit (constitution); CI fails if `om-check` finds a diff
(CI itself is spec 001). Run `make py_format` and `mvn spotless:apply` on touched modules in `.om/`
before `om-export`. Targets stay small shell, with no new tooling dependency beyond Docker, git,
Python 3.11 and `uv`.

Connection fields and Test connection steps: `../data-model.md`.
