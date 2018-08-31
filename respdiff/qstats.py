import collections
from enum import Enum
import logging
from typing import Any, Mapping, Optional, Set, Sequence

from .dataformat import DiffReport, JSONDataObject, QueryData
from .typing import QID


UPSTREAM_UNSTABLE_THRESHOLD = 0.1  # consider query unstable when 10 % of results are unstable
ALLOWED_FAIL_THRESHOLD = 0.05  # ignore up to 5 % of FAIL results for a given query (as noise)


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
        'unstable': (set, list),
    }

    def __init__(
                self,
                failing: Optional[Set[QID]] = None,
                unstable: Optional[Set[QID]] = None,
                _restore_dict: Optional[Mapping[str, Any]] = None
            ) -> None:
        super().__init__()
        self.failing = failing if failing is not None else set()
        self.unstable = unstable if unstable is not None else set()
        if _restore_dict is not None:
            self.restore(_restore_dict)

    def add_query(self, qid: QID, query_data: QueryData) -> None:
        status = get_query_status(query_data)
        if status == QueryStatus.FAILING:
            self.failing.add(qid)
        elif status == QueryStatus.UNKNOWN:
            self.unstable.add(qid)

    @staticmethod
    def from_reports(reports: Sequence[DiffReport]) -> 'QueryStatistics':
        """Create query statistics from multiple reports - usually used as a reference"""
        others_disagree = collections.Counter()   # type: collections.Counter
        target_disagrees = collections.Counter()  # type: collections.Counter
        reprodata_present = False

        # collect query results
        for report in reports:
            if report.reprodata is not None:
                reprodata_present = True
            assert report.other_disagreements is not None
            assert report.target_disagreements is not None
            for qid in report.other_disagreements.queries:
                others_disagree[qid] += 1
            for qid in report.target_disagreements:
                target_disagrees[qid] += 1
        if reprodata_present:
            logging.warning("reprodata ignored when creating query stability statistics")

        # evaluate
        total = len(reports)
        query_statistics = QueryStatistics()
        suspect_queries = set(others_disagree.keys())
        suspect_queries.update(target_disagrees.keys())
        for qid in suspect_queries:
            query_statistics.add_query(
                qid, QueryData(total, others_disagree[qid], target_disagrees[qid]))
        return query_statistics
