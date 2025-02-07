import collections
from enum import Enum
import logging
import math
import statistics
from typing import Any, Dict, List, Mapping, Optional, Sequence  # noqa

import numpy
import scipy.stats

from .cfg import ALL_FIELDS
from .dataformat import Counter, DiffReport, JSONDataObject, Summary
from .qstats import QueryStatistics


class Stats(JSONDataObject):
    """
    Represents statistical (reference) data for a single parameter.

    It contains all the samples from the reference data, e.g. number of
    total mismatches. This allows further statistical processing which also
    takes place in this class.

    Example: samples = [1540, 1613, 1489]
    """

    _ATTRIBUTES = {
        "samples": (None, None),
        "threshold": (None, None),
    }

    class SamplePosition(Enum):
        """Position of a single sample against the rest of the distribution."""

        ABOVE_REF = 1
        ABOVE_THRESHOLD = 2
        NORMAL = 3
        BELOW_REF = 4

    def __init__(
        self,
        samples: Sequence[float] = None,
        threshold: Optional[float] = None,
        _restore_dict: Optional[Mapping[str, float]] = None,
    ) -> None:
        """
        samples contain the entire data set of reference values of this parameter.
        If no custom threshold is provided, it is calculated automagically.
        """
        super().__init__()
        self.samples = samples if samples is not None else []
        if threshold is None:
            if self.samples:
                self.threshold = self.calculate_threshold()
        else:
            self.threshold = threshold
        if _restore_dict is not None:
            self.restore(_restore_dict)

    @property
    def median(self) -> float:
        return statistics.median(self.samples)

    @property
    def mad(self) -> float:
        mdev = [math.fabs(val - self.median) for val in self.samples]
        return statistics.median(mdev)

    @property
    def min(self) -> float:
        return min(self.samples)

    @property
    def max(self) -> float:
        return max(self.samples)

    def get_percentile_rank(self, sample: float) -> float:
        return scipy.stats.percentileofscore(self.samples, sample, kind="weak")

    def evaluate_sample(self, sample: float) -> "Stats.SamplePosition":
        if sample < self.min:
            return Stats.SamplePosition.BELOW_REF
        elif sample > self.max:
            return Stats.SamplePosition.ABOVE_REF
        elif sample > self.threshold:
            return Stats.SamplePosition.ABOVE_THRESHOLD
        return Stats.SamplePosition.NORMAL

    def calculate_threshold(self) -> float:
        """Return upper threshold for data using modified IQR outlier detection"""
        # This algorhitm is based on inter-quartile range outlier detection
        # See https://en.wikipedia.org/wiki/Interquartile_range#Outliers
        # Differences:
        #   - 20th percentile and 80th percentile is used instead of 25/75
        #   - threshold is capped at maximum sample in the data
        pctl20, pctl80 = numpy.percentile(self.samples, [20, 80])
        inpctl = pctl80 - pctl20
        return min(pctl80 + inpctl * 1.5, self.max)


class MismatchStatistics(dict, JSONDataObject):
    """Contains statistics for all mismatches in a single field.

    Example:
        mismatch_stats = MismatchStatistics(...)  # stats for a single field
        mismatch_stats.total -> Stats  # combined stats for this field
        mismatch_stats[DataMismatch('A', 'AAAA')] -> Stats  # stats for specific mismatch
        mismatch_stats[DataMismatch('PTR', 'MX')] -> Stats
    """

    _ATTRIBUTES = {
        "total": (lambda x: Stats(_restore_dict=x), lambda x: x.save()),
    }

    def __init__(
        self,
        mismatch_counters_list: Optional[Sequence[Counter]] = None,
        sample_size: Optional[int] = None,
        _restore_dict: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.total = None
        if mismatch_counters_list is not None and sample_size is not None:
            samples = collections.defaultdict(list)  # type: Dict[str, List[int]]
            for mismatch_counter in mismatch_counters_list:
                n = 0
                for mismatch, count in mismatch_counter.items():
                    n += count
                    mismatch_key = str(mismatch.key)
                    samples[mismatch_key].append(count)
                samples["total"].append(n)

            # fill in missing samples
            for seq in samples.values():
                seq.extend([0] * (sample_size - len(seq)))

            # create stats from samples
            self.total = Stats(samples["total"])
            del samples["total"]
            for mismatch_key, stats_seq in samples.items():
                self[mismatch_key] = Stats(stats_seq)
        elif _restore_dict is not None:
            self.restore(_restore_dict)

    def restore(self, restore_dict: Mapping[str, Any]) -> None:
        super().restore(restore_dict)
        for mismatch_key, stats_data in restore_dict.items():
            if mismatch_key in self._ATTRIBUTES:
                continue  # attributes are already loaded
            self[mismatch_key] = Stats(_restore_dict=stats_data)

    def save(self) -> Dict[str, Any]:
        restore_dict = super().save() or {}
        for mismatch_key, stats_data in self.items():
            restore_dict[mismatch_key] = stats_data.save()
        return restore_dict


class FieldStatistics(dict, JSONDataObject):
    """Contains statistics for all fields.

    Example:
        field_statistics = FieldStatistics(...)  # stats for all fields
        field_statistics['rcode'] -> MismatchStatistics  # stats for single field
        field_statistics['opcode'] -> MismatchStatistics
    """

    def __init__(
        self,
        summaries_list: Optional[Sequence[Summary]] = None,
        _restore_dict: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__()
        if summaries_list is not None:
            field_counters_list = [d.get_field_counters() for d in summaries_list]
            for field in ALL_FIELDS:
                mismatch_counters_list = [fc[field] for fc in field_counters_list]
                self[field] = MismatchStatistics(
                    mismatch_counters_list, len(summaries_list)
                )
        elif _restore_dict is not None:
            self.restore(_restore_dict)

    def restore(self, restore_dict: Mapping[str, Any]) -> None:
        super().restore(restore_dict)
        for field, field_data in restore_dict.items():
            self[field] = MismatchStatistics(_restore_dict=field_data)

    def save(self) -> Dict[str, Any]:
        restore_dict = super().save() or {}
        for field, mismatch_stats in self.items():
            restore_dict[field] = mismatch_stats.save()
        return restore_dict


class SummaryStatistics(JSONDataObject):
    _ATTRIBUTES = {
        "sample_size": (None, None),
        "upstream_unstable": (lambda x: Stats(_restore_dict=x), lambda x: x.save()),
        "usable_answers": (lambda x: Stats(_restore_dict=x), lambda x: x.save()),
        "not_reproducible": (lambda x: Stats(_restore_dict=x), lambda x: x.save()),
        "target_disagreements": (lambda x: Stats(_restore_dict=x), lambda x: x.save()),
        "fields": (lambda x: FieldStatistics(_restore_dict=x), lambda x: x.save()),
        "queries": (lambda x: QueryStatistics(_restore_dict=x), lambda x: x.save()),
    }

    def __init__(
        self,
        reports: Sequence[DiffReport] = None,
        _restore_dict: Mapping[str, Any] = None,
    ) -> None:
        super().__init__()
        self.sample_size = None
        self.upstream_unstable = None
        self.usable_answers = None
        self.not_reproducible = None
        self.target_disagreements = None
        self.fields = None
        self.queries = None
        if reports is not None:
            # use only reports with diffsum
            usable_reports = []
            for report in reports:
                if report.summary is None:
                    logging.warning(
                        "Empty diffsum in %s Omitting...", report.fileorigin
                    )
                else:
                    usable_reports.append(report)

            summaries = [
                report.summary for report in reports if report.summary is not None
            ]
            assert len(summaries) == len(usable_reports)
            if not summaries:
                raise ValueError("No summaries found in reports!")

            self.sample_size = len(summaries)
            self.upstream_unstable = Stats([s.upstream_unstable for s in summaries])
            self.usable_answers = Stats([s.usable_answers for s in summaries])
            self.not_reproducible = Stats([s.not_reproducible for s in summaries])
            self.target_disagreements = Stats([len(s) for s in summaries])
            self.fields = FieldStatistics(summaries)
            self.queries = QueryStatistics.from_reports(usable_reports)
        elif _restore_dict is not None:
            self.restore(_restore_dict)
