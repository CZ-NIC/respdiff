import collections
from enum import Enum
from typing import Any, Mapping, Optional, Set, Sequence

from .dataformat import JSONDataObject, DiffReport
from .typing import QID


UPSTREAM_UNSTABLE_THRESHOLD = 0.1
ALLOWED_FAIL_THRESHOLD = 0.05


class QueryStatus(Enum):
    PASSING = 1
    UNKNOWN = 2  # upstream is unstable
    FAILING = 3


def get_query_status(
            total: int,
            target_disagrees: int,
            others_disagree: int
        ) -> QueryStatus:
    if others_disagree / total >= UPSTREAM_UNSTABLE_THRESHOLD:
        return QueryStatus.UNKNOWN
    if target_disagrees / total < ALLOWED_FAIL_THRESHOLD:
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

    @staticmethod
    def from_reports(reports: Sequence[DiffReport]) -> 'QueryStatistics':
        others_disagree = collections.Counter()   # type: collections.Counter
        target_disagrees = collections.Counter()  # type: collections.Counter

        # collect query results
        for report in reports:
            if report.reprodata is not None:
                raise NotImplementedError(
                    "Query stability analysis doesn't support diffrepro data!")
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
            status = get_query_status(total, target_disagrees[qid], others_disagree[qid])
            if status == QueryStatus.FAILING:
                query_statistics.failing.add(qid)
            elif status == QueryStatus.UNKNOWN:
                query_statistics.unknown.add(qid)
        return query_statistics
