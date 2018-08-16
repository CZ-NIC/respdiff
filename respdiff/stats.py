import collections
from enum import Enum
import math
import statistics
from typing import Any, Dict, List, Mapping, Optional, Sequence  # noqa

import numpy
import scipy.stats

from .dataformat import Counter, JSONDataObject, Summary
from .cfg import ALL_FIELDS


class Stats(JSONDataObject):
    """
    Represents statistical data for a single parameter (field/mismatch/...)

    It contains the entire sequence of the original data, e.g. number of
    total mismatches. This allows further statistical processing which also
    takes place here.
    """
    _ATTRIBUTES = {
        'sequence': (None, None),
        'upper_boundary': (None, None),
    }

    MAX_NUMBINS = 50  # maximum amount of bins in histogram

    class SamplePosition(Enum):
        """Position of a single sample against the rest of the distribution."""
        BELOW_MIN = 1
        ABOVE_UPPER_BOUNDARY = 2
        ABOVE_MAX = 3
        WITHIN_BOUNDARIES = 4

    def __init__(
                self,
                sequence: Sequence[float] = None,
                upper_boundary: Optional[float] = None,
                data: Mapping[str, float] = None
            ) -> None:
        """
        sequence should contain the entire data set of values of this parameter.
        If no custom upper_boundary is provided, it is calculated automagically.
        """
        super(Stats, self).__init__()
        self.sequence = sequence if sequence is not None else []
        if data is not None:
            self.restore(data)
        if upper_boundary is None:
            self.upper_boundary = self.calculate_upper_boundary()
        else:
            self.upper_boundary = upper_boundary

    @property
    def median(self) -> float:
        return statistics.median(self.sequence)

    @property
    def mad(self) -> float:
        mdev = [math.fabs(val - self.median) for val in self.sequence]
        return statistics.median(mdev)

    @property
    def min(self) -> float:
        return min(self.sequence)

    @property
    def max(self) -> float:
        return max(self.sequence)

    def get_percentile_rank(self, sample: float) -> float:
        return scipy.stats.percentileofscore(self.sequence, sample, kind='weak')

    def evaluate_sample(self, sample: float) -> 'Stats.SamplePosition':
        if sample < self.min:
            return Stats.SamplePosition.BELOW_MIN
        elif sample > self.max:
            return Stats.SamplePosition.ABOVE_MAX
        elif sample > self.upper_boundary:
            return Stats.SamplePosition.ABOVE_UPPER_BOUNDARY
        return Stats.SamplePosition.WITHIN_BOUNDARIES

    # TODO: this is a very magical detection of the upper boundary
    def calculate_upper_boundary(
                self,
                change_cutoff: float = -0.3,  # to detect cutoff in histogram; value < 0
                minimum: float = 0.9,  # relative point where to start looking for cutoff
            ) -> float:
        """Detect uppper cutoff value in histogram to ignore outliers"""
        # choose number of bins in histogram
        numbins = max(self.sequence) - min(self.sequence) + 1  # separate bins for all values
        if numbins > self.MAX_NUMBINS:
            numbins = self.MAX_NUMBINS
        hist, _ = numpy.histogram(
            numpy.array(self.sequence), numbins)
        hist_cumulative_rel = (numpy.cumsum(hist) / len(self.sequence)).tolist()

        # traverse the histogram and find unique thresholds and calculate efficiency
        # efficiency: how_much_of_the_distribution_is_covered / how_many_bins_are_needed
        Threshold = collections.namedtuple('Threshold', ['threshold', 'efficiency'])
        thresholds = []
        last_thr = None
        for i, thr in enumerate(hist_cumulative_rel):
            if thr < minimum:
                continue  # skip until start
            if thr == last_thr:
                continue  # skip non-unique
            thresholds.append(Threshold(thr, thr / (i+1)))
            last_thr = thr

        # calculate change efficiency ratio and find cutoff point in change ratio
        for i, _ in enumerate(thresholds):
            if i == 0:
                continue
            curr = thresholds[i]
            prev = thresholds[i-1]
            eff_change = (curr.efficiency - prev.efficiency) / (curr.threshold - prev.threshold)
            if eff_change < change_cutoff:
                cutoff_threshold = prev.threshold
                break
        else:
            cutoff_threshold = thresholds[-1].threshold

        # find the cutoff value
        icutoff = int(round(len(self.sequence) * cutoff_threshold)) - 1
        return sorted(self.sequence)[icutoff]


class MismatchStatistics(dict, JSONDataObject):
    _ATTRIBUTES = {
        'total': (
            lambda x: Stats(data=x),
            lambda x: x.save()),
    }

    def __init__(
                self,
                mismatch_counters_list: Optional[Sequence[Counter]] = None,
                sample_size: Optional[int] = None,
                data: Optional[Mapping[str, Any]] = None
            ) -> None:
        super(MismatchStatistics, self).__init__()
        self.total = None
        if mismatch_counters_list is not None and sample_size is not None:
            samples = collections.defaultdict(list)  # type: Dict[str, List[int]]
            for mismatch_counter in mismatch_counters_list:
                n = 0
                for mismatch, count in mismatch_counter.items():
                    n += count
                    mismatch_key = str(mismatch.key)
                    samples[mismatch_key].append(count)
                samples['total'].append(n)

            # fill in missing samples
            for seq in samples.values():
                seq.extend([0] * (sample_size - len(seq)))

            # create stats from samples
            self.total = Stats(samples['total'])
            del samples['total']
            for mismatch_key, stats_seq in samples.items():
                self[mismatch_key] = Stats(stats_seq)
        elif data is not None:
            self.restore(data)

    def restore(self, data: Mapping[str, Any]) -> None:
        super(MismatchStatistics, self).restore(data)
        for mismatch_key, stats_data in data.items():
            if mismatch_key in self._ATTRIBUTES:
                continue  # attributes are already loaded
            self[mismatch_key] = Stats(data=stats_data)

    def save(self) -> Dict[str, Any]:
        data = super(MismatchStatistics, self).save() or {}
        for mismatch_key, stats_data in self.items():
            data[mismatch_key] = stats_data.save()
        return data


class FieldStatistics(dict, JSONDataObject):
    def __init__(
                self,
                summaries_list: Optional[Sequence[Summary]] = None,
                data: Optional[Mapping[str, Any]] = None
            ) -> None:
        super(FieldStatistics, self).__init__()
        if summaries_list is not None:
            field_counters_list = [d.get_field_counters() for d in summaries_list]
            for field in ALL_FIELDS:
                mismatch_counters_list = [fc[field] for fc in field_counters_list]
                self[field] = MismatchStatistics(
                    mismatch_counters_list, len(summaries_list))
        elif data is not None:
            self.restore(data)

    def restore(self, data: Mapping[str, Any]) -> None:
        super(FieldStatistics, self).restore(data)
        for field, field_data in data.items():
            self[field] = MismatchStatistics(data=field_data)

    def save(self) -> Dict[str, Any]:
        data = super(FieldStatistics, self).save() or {}
        for field, mismatch_stats in self.items():
            data[field] = mismatch_stats.save()
        return data


class SummaryStatistics(JSONDataObject):
    _ATTRIBUTES = {
        'sample_size': (None, None),
        'upstream_unstable': (
            lambda x: Stats(data=x),
            lambda x: x.save()),
        'usable_answers': (
            lambda x: Stats(data=x),
            lambda x: x.save()),
        'not_reproducible': (
            lambda x: Stats(data=x),
            lambda x: x.save()),
        'target_disagreements': (
            lambda x: Stats(data=x),
            lambda x: x.save()),
        'fields': (
            lambda x: FieldStatistics(data=x),
            lambda x: x.save()),
    }

    def __init__(
                self,
                summaries: Sequence[Summary] = None,
                data: Mapping[str, Any] = None
            ) -> None:
        super(SummaryStatistics, self).__init__()
        self.sample_size = None
        self.upstream_unstable = None
        self.usable_answers = None
        self.not_reproducible = None
        self.target_disagreements = None
        self.fields = None
        if summaries is not None:
            self.sample_size = len(summaries)
            self.upstream_unstable = Stats([s.upstream_unstable for s in summaries])
            self.usable_answers = Stats([s.usable_answers for s in summaries])
            self.not_reproducible = Stats([s.not_reproducible for s in summaries])
            self.target_disagreements = Stats([len(s) for s in summaries])
            self.fields = FieldStatistics(summaries)
        elif data is not None:
            self.restore(data)
