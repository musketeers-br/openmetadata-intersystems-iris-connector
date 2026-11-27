#  Copyright 2025 OpenMetadata
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/LICENSE
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""
The IRIS sampler (spec 006, ADR-0016).

IRIS rejects every delimited CTE name and IRIS SQL has no random function. The sampler builds its queries with the
base sampler's code and changes only what IRIS needs: CTE names that are valid unquoted identifiers, row-count
sampling without randomization, and no percentage sampling. It adds no SQL of its own.

Unsupported requests are reported once per run as IRIS-PROFILER-UNSUPPORTED warnings, logged through
ingestion_logger() so that the step's own warning handler records them in the step's status (research R2). A table
that cannot be sampled is skipped by raising IrisSamplingSkipped from the constructor, the only point where
OpenMetadata 2.1.1 lets a sampler skip a table without a substitute result (research R3).
"""

from weakref import WeakKeyDictionary

from metadata.generated.schema.type.basic import ProfileSampleType
from metadata.sampler.sqlalchemy.sampler import SQASampler
from metadata.utils.logger import ingestion_logger

logger = ingestion_logger()

UNSUPPORTED = "IRIS-PROFILER-UNSUPPORTED"
NO_RANDOM = "no random function"

# What was already reported in a run. A workflow's samplers and test-suite interfaces share its OpenMetadata client,
# and a new workflow has a new client, so the client identifies the run.
_REPORTED: "WeakKeyDictionary[object, set[str]]" = WeakKeyDictionary()


class IrisSamplingSkipped(Exception):
    """The table is not sampled on IRIS; the message is the reason, naming the table."""


def report_once(client, key: str, message: str) -> None:
    """Log one WARNING per run for `key`; the step's StatusWarningHandler records it in the status."""
    reported = _REPORTED.setdefault(client, set())
    if key not in reported:
        reported.add(key)
        logger.warning(message)


def table_fqn(entity) -> str:
    fqn = getattr(entity, "fullyQualifiedName", None)
    return fqn.root if fqn is not None else str(getattr(getattr(entity, "name", None), "root", "unknown"))


class IrisSampler(SQASampler):
    """SQASampler with unquoted CTE names, no randomization and no percentage sampling (ADR-0016)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._check_readable()
        static = self._resolve_sample_config
        if static is not None and static.profileSampleType == ProfileSampleType.PERCENTAGE and static.profileSample:
            if static.profileSample < 100:
                report_once(
                    self.ometa_client,
                    "percentage",
                    f"{UNSUPPORTED}: percentage sampling is not supported on IRIS ({NO_RANDOM}); set a row-count "
                    f"sample instead. {table_fqn(self.entity)} was not profiled",
                )
                raise IrisSamplingSkipped(
                    f"{UNSUPPORTED}: percentage sampling is not supported on IRIS ({NO_RANDOM}); "
                    f"{table_fqn(self.entity)} was not profiled"
                )
        # A user sample query is never randomized by the base sampler, so only a configured sample is reported.
        if self.sample_config.randomizedSample is True and self.applies_sampling and not self.sample_query:
            report_once(
                self.ometa_client,
                "randomized",
                f"{UNSUPPORTED}: randomized sampling is not supported on IRIS ({NO_RANDOM}); rows were taken in IRIS's "
                f"order instead (first seen on {table_fqn(self.entity)})",
            )
        if self.sample_config.randomizedSample is True:
            # The base sampler orders by ModuloFn(RandomNumFn(), ...) when randomized; IRIS has no random function.
            self.sample_config = self.sample_config.model_copy(update={"randomizedSample": False})

    def _check_readable(self) -> None:
        """Spec 006 FR-013a: filled in by the readability check (T027)."""

    @classmethod
    def is_skippable_sampling_error(cls, exc: Exception) -> bool:
        """The sample-data step skips a table this sampler refused, with a warning instead of a failure."""
        return isinstance(exc, IrisSamplingSkipped)

    def get_sampler_table_name(self) -> str:
        """IRIS rejects delimited CTE names; a digest starting with a digit would be quoted. Prefix a letter."""
        return "s" + super().get_sampler_table_name()
