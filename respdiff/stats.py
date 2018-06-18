import collections
import math
import statistics
from typing import Any, Dict, List, Mapping, Optional, Sequence  # noqa

from .dataformat import Counter, JSONDataObject, Summary


class Stats(JSONDataObject):
    _ATTRIBUTES = {
        'sequence': (None, None),
    }

    def __init__(
                self,
                sequence: Sequence[float] = None,
                data: Mapping[str, float] = None
            ) -> None:
        super(Stats, self).__init__()
        self.sequence = sequence
        if data is not None:
            self.restore(data)

    @property
    def median(self):
        return statistics.median(self.sequence)

    @property
    def mad(self):
        mdev = [math.fabs(val - self.median) for val in self.sequence]
        return statistics.median(mdev)


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


ALL_FIELDS = [
    'timeout', 'malformed', 'opcode', 'qcase', 'qtype', 'rcode', 'flags', 'answertypes',
    'answerrrsigs', 'answer', 'authority', 'additional', 'edns', 'nsid']


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
