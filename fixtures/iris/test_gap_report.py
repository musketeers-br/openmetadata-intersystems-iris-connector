"""Format of GAP-REPORT.md (spec 001, FR-023, SC-007; ADR-0013). Offline: reads the file only.

Every entry is headed `### GAP-NNN — <title>` and has the bold labels below, in this order. Ids run
from GAP-001 with none skipped or repeated, so two specs cannot silently take the same number.
"""
import re
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[2] / "GAP-REPORT.md"
LABELS = (
    "Component",
    "IRIS tracks",
    "Found in spec",
    "Reproduction",
    "Expected",
    "Actual",
    "Connector behavior",
    "User workaround",
    "Upstream",
)
COMPONENTS = {
    "IRIS SQL catalog",
    "class dictionary",
    "official driver",
    "official dialect",
    "dbt-iris",
    "OpenMetadata",
}
TRACKS = ("latest-em", "latest-cd", "latest-preview")
TRACK_STATES = ("reproduced", "not reproduced", "not tested")
HEADING = re.compile(r"^### (GAP-(\d{3})) — (\S.*)$")
LABEL = re.compile(r"^- \*\*(.+?):\*\*\s?(.*)$")


def parse(text):
    """Return [(id, number, title, {label: field text})], fields in file order."""
    entries = []
    current = None
    label = None
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            current = (heading.group(1), int(heading.group(2)), heading.group(3), {})
            entries.append(current)
            label = None
            continue
        if line.startswith("#"):
            current = None
            continue
        if current is None:
            continue
        match = LABEL.match(line)
        if match:
            label = match.group(1)
            current[3][label] = match.group(2)
        elif label is not None:
            current[3][label] += "\n" + line
    return entries


def problems(entries):
    """Every format problem in the parsed entries, as readable strings."""
    found = []
    numbers = [number for _, number, _, _ in entries]
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        found.append(f"ids must run GAP-001..GAP-{len(numbers):03d} in order, found {numbers}")
    for gap, _, _, fields in entries:
        if tuple(fields) != LABELS:
            found.append(f"{gap}: labels {list(fields)}, expected {list(LABELS)}")
            continue
        if fields["Component"].strip() not in COMPONENTS:
            found.append(f"{gap}: Component {fields['Component'].strip()!r} is not one of {sorted(COMPONENTS)}")
        tracks = fields["IRIS tracks"]
        for tag in TRACKS:
            if not re.search(rf"\b{tag} ({'|'.join(TRACK_STATES)})\b", tracks):
                found.append(f"{gap}: IRIS tracks must say '{tag} reproduced|not reproduced|not tested'")
        reproduction = fields["Reproduction"]
        if "```" not in reproduction and not re.search(r"pending SPIKE-\d{2}", reproduction):
            found.append(f"{gap}: Reproduction needs a fenced code block or 'pending SPIKE-NN'")
        upstream = fields["Upstream"].strip()
        if not (upstream.startswith(("not raised yet", "not applicable")) or "https://" in upstream):
            found.append(f"{gap}: Upstream must be an issue link, 'not raised yet' or 'not applicable'")
    return found


def test_report_exists():
    assert REPORT.is_file(), f"{REPORT} is missing"


def test_report_has_at_least_the_nine_seed_entries():
    entries = parse(REPORT.read_text(encoding="utf-8"))
    assert len(entries) >= 9, f"{len(entries)} entries: {[gap for gap, *_ in entries]}"


def test_every_entry_follows_the_format():
    found = problems(parse(REPORT.read_text(encoding="utf-8")))
    assert not found, "\n".join(found)


GOOD = """### GAP-001 — Something breaks

- **Component:** official dialect
- **IRIS tracks:** latest-em reproduced; latest-cd not reproduced; latest-preview not tested
- **Found in spec:** 001-test-harness
- **Reproduction:**

  ```sql
  SELECT 1
  ```

- **Expected:** one thing.
- **Actual:** another.
- **Connector behavior:** none.
- **User workaround:** none.
- **Upstream:** not raised yet.
"""


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("GAP-001", "GAP-002"), "ids must run"),
        (("official dialect", "the dialect"), "Component"),
        (("latest-cd not reproduced", "latest-cd maybe"), "latest-cd"),
        (("  ```sql\n  SELECT 1\n  ```\n", "  later\n"), "Reproduction"),
        (("not raised yet.", "soon."), "Upstream"),
        (("- **Expected:** one thing.\n", ""), "labels"),
    ],
    ids=["skipped-id", "component", "track-state", "reproduction", "upstream", "missing-label"],
)
def test_the_check_can_fail(change, message):
    assert problems(parse(GOOD)) == []
    found = problems(parse(GOOD.replace(*change)))
    assert any(message in problem for problem in found), found


def test_not_applicable_is_a_valid_upstream():
    # For a limitation the connector handles itself, with nothing to report upstream (agreed 2026-11-26).
    text = GOOD.replace("not raised yet.", "not applicable: the connector handles it.")
    assert problems(parse(text)) == []


def test_pending_spike_is_a_valid_reproduction():
    text = GOOD.replace("  ```sql\n  SELECT 1\n  ```\n", "  pending SPIKE-03 (spec 005).\n")
    assert problems(parse(text)) == []
