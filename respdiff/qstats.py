import collections
from enum import Enum
import logging
from typing import Any, Mapping, Optional, Set, Sequence

from .dataformat import DiffReport, JSONDataObject, QueryData
from .typing import QID


UPSTREAM_UNSTABLE_THRESHOLD = 0.1
ALLOWED_FAIL_THRESHOLD = 0.05
MAX_REPRO_ATTEMPTS = int(1 / ALLOWED_FAIL_THRESHOLD) + 1


class QueryStatus(Enum):
    PASSING = 1
    UNKNOWN = 2  # upstream is unstable
    FAILING = 3


def get_query_status(query_data: QueryData) -> QueryStatus:
    if query_data.others_disagree / query_data.total >= UPSTREAM_UNSTABLE_THRESHOLD:
        return QueryStatus.UNKNOWN
    if query_data.target_disagrees / query_data.total < ALLOWED_FAIL_THRESHOLD:
        return QueryStatus.PASSING
    return QueryStatus.FAILING


class QueryStatistics(JSONDataObject):
    _ATTRIBUTES = {
        'failing': (set, list),
        'unknown': (set, list),
    }

    def __init__(
                self,
                failing: Optional[Set[QID]] = None,
                unknown: Optional[Set[QID]] = None,
                _restore_dict: Optional[Mapping[str, Any]] = None
            ) -> None:
        super(QueryStatistics, self).__init__()
        self.failing = failing if failing is not None else set()
        self.unknown = unknown if unknown is not None else set()
        if _restore_dict is not None:
            self.restore(_restore_dict)

    def add_query(self, qid: QID, query_data: QueryData) -> None:
        status = get_query_status(query_data)
        if status == QueryStatus.FAILING:
            self.failing.add(qid)
        elif status == QueryStatus.UNKNOWN:
            self.unknown.add(qid)

    def get_unseen_failures(
                self,
                report: DiffReport,
                max_repro_attempts: int = MAX_REPRO_ATTEMPTS,
                verified: bool = False
            ) -> Set[QID]:
        """Return new failures from a provided report (when compared to this set).

        Failures can be either unverified, which need further reproducing,
        or verified, when the maximum allowed failures (in relation to maximum repro
        attempt) were exceeded during reproduction attempt."""
        assert report.target_disagreements is not None
        candidates = {
            qid: report.get_query_data(qid) for qid in report.target_disagreements
            if qid not in self.unknown}

        # filter upstream unstable
        max_upstream_unstable = int(max_repro_attempts * UPSTREAM_UNSTABLE_THRESHOLD)
        candidates = {
            qid: query_data for qid, query_data in candidates.items()
            if query_data.others_disagree <= max_upstream_unstable}

        max_allowed_failures = int(max_repro_attempts * ALLOWED_FAIL_THRESHOLD)
        verified_failures = {
            qid for qid, query_data in candidates.items()
            if query_data.target_disagrees > max_allowed_failures}

        if verified:
            return verified_failures
        return set(candidates.keys()) - verified_failures

    def get_fixed_queries(
                self,
                report: DiffReport,
                max_repro_attempts: int = MAX_REPRO_ATTEMPTS,
                verified: bool = False
            ) -> Set[QID]:
        """Return newly passing queries from a provided report (when compared to this set).

        New fixes can be either unverified, which need to be reproduced mutliple times to
        verify them, or verified, once the maximum number of reproducer attempts is reached
        and the query is still evaluated as passing."""
        assert report.target_disagreements is not None
        candidates = {
            qid: report.get_query_data(qid) for qid
            in self.failing - set(report.target_disagreements.keys())}

        # filter upstream unstable
        max_upstream_unstable = int(max_repro_attempts * UPSTREAM_UNSTABLE_THRESHOLD)
        candidates = {
            qid: query_data for qid, query_data in candidates.items()
            if query_data.others_disagree <= max_upstream_unstable}

        # filter failing
        max_allowed_failures = int(max_repro_attempts * ALLOWED_FAIL_THRESHOLD)
        candidates = {
            qid: query_data for qid, query_data in candidates.items()
            if query_data.target_disagrees <= max_allowed_failures}

        min_required_passing = max_repro_attempts - max_allowed_failures
        verified_fixed = {
            qid for qid, query_data in candidates.items()
            if query_data.total - query_data.target_disagrees >= min_required_passing}

        if verified:
            return verified_fixed
        return set(candidates.keys()) - verified_fixed

    @staticmethod
    def from_reports(reports: Sequence[DiffReport]) -> 'QueryStatistics':
        """Create query statistics from multiple reports - usually used as a reference"""
        others_disagree = collections.Counter()   # type: collections.Counter
        target_disagrees = collections.Counter()  # type: collections.Counter

        # collect query results
        for report in reports:
            if report.reprodata is not None:
                logging.warning("reprodata ignored when creating query stability statistics")
            assert report.other_disagreements is not None
            assert report.target_disagreements is not None
            for qid in report.other_disagreements.queries:
                others_disagree[qid] += 1
            for qid in report.target_disagreements:
                target_disagrees[qid] += 1

        # evaluate
        total = len(reports)
        query_statistics = QueryStatistics()
        suspect_queries = set(others_disagree.keys())
        suspect_queries.update(target_disagrees.keys())
        for qid in suspect_queries:
            query_statistics.add_query(
                qid, QueryData(total, others_disagree[qid], target_disagrees[qid]))
        return query_statistics
