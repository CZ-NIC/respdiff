# Cusom data structures and JSON utility functions

from collections import Counter
import collections.abc
import json
from typing import (  # noqa
    Any, Callable, Dict, Hashable, ItemsView, Iterator, KeysView, Mapping,
    Optional, Set, Sequence, Tuple, Union)

from .match import DataMismatch
from .typing import FieldLabel, QID

RestoreFunction = Optional[Callable[[Any], Any]]
SaveFunction = Optional[Callable[[Any], Any]]


class InvalidFileFormat(Exception):
    pass


class JSONDataObject:
    """Object class for (de)serialization into JSON-compatible dictionary."""
    _ATTRIBUTES = {}  # type: Mapping[str, Tuple[RestoreFunction, SaveFunction]]

    def __init__(self, **kwargs):  # pylint: disable=unused-argument
        self.fileorigin = ''

    def export_json(self, filename: str) -> None:
        json_string = json.dumps(self.save(), indent=2)
        with open(filename, 'w') as f:
            f.write(json_string)

    @classmethod
    def from_json(cls, filename: str):
        try:
            with open(filename) as f:
                restore_dict = json.load(f)
        except json.decoder.JSONDecodeError:
            raise InvalidFileFormat("Couldn't parse JSON file: {}".format(filename))
        inst = cls(_restore_dict=restore_dict)
        inst.fileorigin = filename
        return inst

    def restore(self, restore_dict: Mapping[str, Any]) -> None:
        for key, (restore_func, _) in self._ATTRIBUTES.items():
            self._restore_attr(restore_dict, key, restore_func)

    def save(self) -> Optional[Dict[str, Any]]:
        restore_dict = {}
        for key, (_, save_func) in self._ATTRIBUTES.items():
            restore_dict[key] = self._save_attr(key, save_func)
        if not restore_dict:
            return None
        return restore_dict

    def _restore_attr(
                self,
                restore_dict: Mapping[str, Any],
                key: str,
                restore_func: RestoreFunction = None
            ) -> None:
        """
        Restore attribute from key in dictionary.
        If it's missing or None, don't call restore_func() and leave attribute's value default.
        """
        try:
            value = restore_dict[key]
        except KeyError:
            pass
        else:
            if restore_func is not None and value is not None:
                value = restore_func(value)
            setattr(self, key, value)

    def _save_attr(
                self,
                key: str,
                save_func: SaveFunction = None
            ) -> Mapping[str, Any]:
        """
        Save attribute as a key in dictionary.
        If the attribute is None, save it as such (without calling save_func()).
        """
        value = getattr(self, key)
        if save_func is not None and value is not None:
            value = save_func(value)
        return value


class Diff(collections.abc.Mapping):
    """Read-only representation of mismatches in each field for a single query"""
    __setitem__ = None
    __delitem__ = None

    def __init__(self, qid: QID, mismatches: Mapping[FieldLabel, DataMismatch]) -> None:
        super(Diff, self).__init__()
        self.qid = qid
        self._mismatches = mismatches

    def __getitem__(self, field: FieldLabel) -> DataMismatch:
        return self._mismatches[field]

    def __len__(self) -> int:
        return len(self._mismatches)

    def __iter__(self) -> Iterator[FieldLabel]:
        return iter(self._mismatches)

    def get_significant_field(
                self,
                field_weights: Sequence[FieldLabel]
            ) -> Tuple[Optional[FieldLabel], Optional[DataMismatch]]:
        for significant_field in field_weights:
            if significant_field in self:
                return significant_field, self[significant_field]
        return None, None

    def __repr__(self) -> str:
        return 'Diff({})'.format(
            ', '.join([
                repr(mismatch) for mismatch in self.values()
            ]))

    def __eq__(self, other) -> bool:
        if len(self) != len(other):
            return False
        for field, mismatch in self.items():
            if field not in other:
                return False
            if mismatch != other[field]:
                return False
        return True


class Disagreements(collections.abc.Mapping, JSONDataObject):
    """Collection of mismatches for all fields

    Adding a mismatch: self.fields[name][mismatch].add(qid)
    Get qids for a particular mismatch field: self.fields[name][mismatch]
    Get all qids which have a mismatch: self.keys()
    Get a diff (collection of mismatches) for a qid: self[qid]
    """

    def __init__(
                self,
                _restore_dict: Optional[Mapping[str, Any]] = None,
            ) -> None:
        """
        `_restore_dict` is used to restore from JSON, minimal format:
            "fields": {
              "<field_label>": {
                "mismatches": [
                  {
                    "exp_val": <exp_val>,
                    "got_val": <got_val>
                    "queries": [<qid>, ...]
                  }
                ]
              }
            }
        """
        super(Disagreements, self).__init__()
        self._fields = collections.defaultdict(
                lambda: collections.defaultdict(set)
            )  # type: Dict[FieldLabel, Dict[DataMismatch, Set[QID]]]
        if _restore_dict is not None:
            self.restore(_restore_dict)

    def restore(self, restore_dict: Mapping[str, Any]) -> None:
        super(Disagreements, self).restore(restore_dict)
        for field_label, field_data in restore_dict['fields'].items():
            for mismatch_data in field_data['mismatches']:
                mismatch = DataMismatch(
                    mismatch_data['exp_val'],
                    mismatch_data['got_val'])
                self._fields[field_label][mismatch] = set(mismatch_data['queries'])

    def save(self) -> Dict[str, Any]:
        fields = {}
        for field, field_data in self._fields.items():
            mismatches = []
            for mismatch, mismatch_data in field_data.items():
                mismatches.append({
                    'count': len(mismatch_data),
                    'exp_val': mismatch.exp_val,
                    'got_val': mismatch.got_val,
                    'queries': list(mismatch_data),
                })
            fields[field] = {
                'count': len(mismatches),
                'mismatches': mismatches,
            }
        restore_dict = super(Disagreements, self).save() or {}
        restore_dict.update({
            'count': self.count,
            'fields': fields,
        })
        return restore_dict

    def add_mismatch(self, field: FieldLabel, mismatch: DataMismatch, qid: QID) -> None:
        self._fields[field][mismatch].add(qid)

    @property
    def field_labels(self) -> KeysView[FieldLabel]:
        return self._fields.keys()

    def get_field_mismatches(
                self,
                field: FieldLabel
            ) -> ItemsView[DataMismatch, Set[QID]]:
        return self._fields[field].items()

    @property
    def count(self):
        return len(self.keys())

    def __getitem__(self, qid: QID) -> Diff:
        diff_mismatches = {}
        for field, mismatches in self._fields.items():
            for mismatch, qids in mismatches.items():
                if qid in qids:
                    diff_mismatches[field] = mismatch
        return Diff(qid, diff_mismatches)

    def __iter__(self) -> Iterator[QID]:
        for qid in self.keys():
            yield qid

    def __len__(self) -> int:
        return len(self.keys())

    def keys(self) -> Set[QID]:
        qids = set()
        for mismatches in self._fields.values():
            for qid_set in mismatches.values():
                qids.update(qid_set)
        return qids


class DisagreementsCounter(JSONDataObject):
    _ATTRIBUTES = {
        'queries': (set, list),
    }

    def __init__(self, _restore_dict: Mapping[str, int] = None) -> None:
        super(DisagreementsCounter, self).__init__()
        self.queries = set()  # type: Set[QID]
        if _restore_dict is not None:
            self.restore(_restore_dict)

    def __len__(self) -> int:
        return len(self.queries)

    def __eq__(self, other) -> bool:
        return self.queries == other.queries


class Summary(Disagreements):
    """Disagreements, where each query has no more than one mismatch."""
    _ATTRIBUTES = {
        'upstream_unstable': (None, None),
        'usable_answers': (None, None),
        'not_reproducible': (None, None),
    }

    def __init__(
                self,
                _restore_dict: Optional[Mapping[FieldLabel, Mapping[str, Any]]] = None
            ) -> None:
        self.usable_answers = 0
        self.upstream_unstable = 0
        self.not_reproducible = 0
        super(Summary, self).__init__(_restore_dict=_restore_dict)

    def add_mismatch(self, field: FieldLabel, mismatch: DataMismatch, qid: QID) -> None:
        if qid in self.keys():
            raise ValueError('QID {} already exists in Summary!'.format(qid))
        self._fields[field][mismatch].add(qid)

    @staticmethod
    def from_report(
                report: 'DiffReport',
                field_weights: Sequence[FieldLabel],
                reproducibility_threshold: float = 1,
                without_diffrepro: bool = False
            ) -> 'Summary':
        """Get summary of disagreements above the specified reproduciblity threshold (0, 1]."""
        if (report.other_disagreements is None
                or report.target_disagreements is None
                or report.total_answers is None):
            raise RuntimeError("Report has insufficient data to create Summary")

        summary = Summary()
        summary.upstream_unstable = len(report.other_disagreements)

        for qid, diff in report.target_disagreements.items():
            if not without_diffrepro and report.reprodata is not None:
                reprocounter = report.reprodata[qid]
                if reprocounter.retries > 0:
                    if reprocounter.retries != reprocounter.upstream_stable:
                        summary.upstream_unstable += 1
                        continue  # filter unstable upstream
                    reproducibility = float(reprocounter.verified) / reprocounter.retries
                    if reproducibility < reproducibility_threshold:
                        summary.not_reproducible += 1
                        continue  # filter less reproducible than threshold
            # add mismatch to summary
            field, mismatch = diff.get_significant_field(field_weights)
            summary.add_mismatch(field, mismatch, qid)

        summary.usable_answers = (
            report.total_answers - summary.upstream_unstable - summary.not_reproducible)
        return summary

    def get_field_counters(self) -> Mapping[FieldLabel, Counter]:
        field_counters = collections.defaultdict(Counter)  # type: Dict[str, Counter]
        for field in self.field_labels:
            counter = Counter()  # type: Counter
            for mismatch, qids in self.get_field_mismatches(field):
                counter[mismatch] = len(qids)
            field_counters[field] = counter
        return field_counters


class ReproCounter(JSONDataObject):
    _ATTRIBUTES = {
        'retries': (None, None),
        'upstream_stable': (None, None),
        'verified': (None, None),
    }

    def __init__(
                self,
                retries: int = 0,
                upstream_stable: int = 0,
                verified: int = 0,
                _restore_dict: Optional[Mapping[str, int]] = None
            ) -> None:
        super(ReproCounter, self).__init__()
        self.retries = retries
        self.upstream_stable = upstream_stable
        self.verified = verified
        if _restore_dict is not None:
            self.restore(_restore_dict)

    def save(self) -> Optional[Dict[str, int]]:
        if not self.retries:
            return None
        return super(ReproCounter, self).save()

    def __eq__(self, other) -> bool:
        return (
            self.retries == other.retries
            and self.upstream_stable == other.upstream_stable
            and self.verified == other.verified)


class ReproData(collections.abc.Mapping, JSONDataObject):
    def __init__(self, _restore_dict: Optional[Mapping[str, Any]] = None) -> None:
        super(ReproData, self).__init__()
        self._counters = collections.defaultdict(ReproCounter)  # type: Dict[QID, ReproCounter]
        if _restore_dict is not None:
            self.restore(_restore_dict)

    def restore(self, restore_dict: Mapping[str, Any]) -> None:
        super(ReproData, self).restore(restore_dict)
        for qid, counter_data in restore_dict.items():
            self._counters[int(qid)] = ReproCounter(_restore_dict=counter_data)

    def save(self) -> Optional[Dict[str, Any]]:
        restore_dict = super(ReproData, self).save() or {}
        for qid, counter in self._counters.items():
            counter_data = counter.save()
            if counter_data is not None:
                restore_dict[str(qid)] = counter_data
        if not restore_dict:
            return None
        return restore_dict

    def __len__(self) -> int:
        return len(self._counters)

    def __getitem__(self, qid: QID) -> ReproCounter:
        return self._counters[qid]

    def __iter__(self) -> Iterator[QID]:
        yield from self._counters.keys()


class DiffReport(JSONDataObject):  # pylint: disable=too-many-instance-attributes
    _ATTRIBUTES = {
        'start_time': (None, None),
        'end_time': (None, None),
        'total_queries': (None, None),
        'total_answers': (None, None),
        'other_disagreements': (
            lambda x: DisagreementsCounter(_restore_dict=x),
            lambda x: x.save()),
        'target_disagreements': (
            lambda x: Disagreements(_restore_dict=x),
            lambda x: x.save()),
        'summary': (
            lambda x: Summary(_restore_dict=x),
            lambda x: x.save()),
        'reprodata': (
            lambda x: ReproData(_restore_dict=x),
            lambda x: x.save()),
    }

    def __init__(
                self,
                start_time: Optional[int] = None,
                end_time: Optional[int] = None,
                total_queries: Optional[int] = None,
                total_answers: Optional[int] = None,
                other_disagreements: Optional[DisagreementsCounter] = None,
                target_disagreements: Optional[Disagreements] = None,
                summary: Optional[Summary] = None,
                reprodata: Optional[ReproData] = None,
                _restore_dict: Optional[Mapping[str, Any]] = None
            ) -> None:
        super(DiffReport, self).__init__()
        self.start_time = start_time
        self.end_time = end_time
        self.total_queries = total_queries
        self.total_answers = total_answers
        self.other_disagreements = other_disagreements
        self.target_disagreements = target_disagreements
        self.summary = summary
        self.reprodata = reprodata
        if _restore_dict is not None:
            self.restore(_restore_dict)

    @property
    def duration(self) -> Optional[int]:
        if self.end_time is None or self.start_time is None:
            return None
        return self.end_time - self.start_time
