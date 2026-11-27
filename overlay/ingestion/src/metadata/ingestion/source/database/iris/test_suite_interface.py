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
The IRIS test-suite interface (spec 006 FR-012a, ADR-0016 amendment).

Some built-in tests give a wrong verdict on IRIS without any error: the regex tests (IRIS SQL has no regular-expression
predicate, and OpenMetadata falls back to LIKE with the regex as the pattern), and in-set, not-in-set and unique on
stream columns (IRIS compares stream values without their content). Value lengths and missing count on stream columns
end in raw SQL errors. For those tests the interface returns an Aborted result naming the reason, records one
IRIS-PROFILER-UNSUPPORTED warning per test type per run, and does not run the validator. Every other test runs
through the base interface unchanged. The decision uses only the test definition's name and the column's type; no
SQL is added and no verdict is computed.
"""

from metadata.data_quality.api.models import TestCaseResultResponse
from metadata.data_quality.interface.sqlalchemy.sqa_test_suite_interface import SQATestSuiteInterface
from metadata.generated.schema.entity.data.table import DataType
from metadata.generated.schema.tests.basic import TestCaseStatus
from metadata.generated.schema.tests.testCase import TestCase
from metadata.generated.schema.tests.testDefinition import TestDefinition
from metadata.ingestion.source.database.iris.sampler import UNSUPPORTED, report_once
from metadata.utils import entity_link

NO_REGEX = "IRIS SQL has no regular-expression predicate"
ANY_COLUMN = {
    "columnValuesToMatchRegex": NO_REGEX,
    "columnValuesToNotMatchRegex": NO_REGEX,
}
STREAM_COLUMN = {
    "columnValuesToBeInSet": "IN on a stream column returns no rows",
    "columnValuesToBeNotInSet": "IN on a stream column returns no rows",
    "columnValueLengthsToBeBetween": "length functions are not supported on stream columns",
    "columnValuesToBeUnique": "IRIS does not compare stream values in GROUP BY",
    "columnValuesMissingCount": "conditions on stream columns are not supported",
}
# The stream types of spec 003's map: longvarchar -> TEXT, longvarbinary -> BLOB.
STREAM_TYPES = frozenset({DataType.TEXT, DataType.BLOB})


class IrisTestSuiteInterface(SQATestSuiteInterface):
    """SQATestSuiteInterface that aborts the tests IRIS cannot evaluate correctly."""

    def run_test_case(self, test_case: TestCase) -> TestCaseResultResponse | None:
        definition = (test_case.testDefinition.fullyQualifiedName or "").split(".")[-1]
        column = self._column(test_case)
        if definition in ANY_COLUMN:
            reason, kind = ANY_COLUMN[definition], "any"
        elif definition in STREAM_COLUMN and column is not None and column.dataType in STREAM_TYPES:
            reason, kind = STREAM_COLUMN[definition], "stream"
        else:
            return super().run_test_case(test_case)

        where = f"{self.table_entity.fullyQualifiedName.root}.{column.name.root if column is not None else ''}"
        message = f"{UNSUPPORTED}: test {definition} on {kind} columns is not supported on IRIS: {reason} ({where})"
        report_once(self.ometa_client, f"test:{definition}:{kind}", f"{message}, first seen on this column")
        return self._aborted(test_case, message)

    def _column(self, test_case: TestCase):
        name = entity_link.get_decoded_column(test_case.entityLink.root) if "::columns::" in test_case.entityLink.root else None
        return next((c for c in self.table_entity.columns or [] if c.name.root == name), None)

    def _aborted(self, test_case: TestCase, message: str) -> TestCaseResultResponse:
        """An Aborted result built by the test's own validator, so its shape is the framework's."""
        test_definition = self.ometa_client.get_by_id(TestDefinition, test_case.testDefinition.id, nullable=False)
        validator = self._get_validator_builder(test_case, test_definition.entityType.value).validator
        result = validator.get_test_case_result_object(validator.execution_date, TestCaseStatus.Aborted, message, [])
        return TestCaseResultResponse(testCase=test_case, testCaseResult=result)
