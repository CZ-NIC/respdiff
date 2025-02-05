import itertools
import json

import pytest

from respdiff.dataformat import (
    Diff,
    DiffReport,
    Disagreements,
    DisagreementsCounter,
    JSONDataObject,
    ReproCounter,
    ReproData,
    Summary,
)
from respdiff.match import DataMismatch


MISMATCH_DATA = [
    ("timeout", "answer"),
    (["A"], ["A", "CNAME"]),
    (["A"], ["A", "RRSIG(A)"]),
]

DIFF_DATA = [
    ("timeout", MISMATCH_DATA[0]),
    ("answertypes", MISMATCH_DATA[1]),
    ("answerrrsigs", MISMATCH_DATA[2]),
    ("answerrrsigs", MISMATCH_DATA[1]),
]

QUERY_DIFF_DATA = list(
    enumerate(
        [
            (),
            (DIFF_DATA[0],),
            (DIFF_DATA[0], DIFF_DATA[1]),
            (DIFF_DATA[1], DIFF_DATA[0]),
            (DIFF_DATA[0], DIFF_DATA[1], DIFF_DATA[2]),
            (DIFF_DATA[0], DIFF_DATA[3], DIFF_DATA[1]),
        ]
    )
)

QUERY_DIFF_JSON = """
{
  "count": 5,
  "fields": {
    "timeout": {
      "count": 5,
      "mismatches": [
        {
          "count": 5,
          "exp_val": "timeout",
          "got_val": "answer",
          "queries": [ 1, 2, 3, 4, 5 ]
        }
      ]
    },
    "answertypes": {
      "count": 4,
      "mismatches": [
        {
          "count": 4,
          "exp_val": [ "A" ],
          "got_val": [ "A", "CNAME" ],
          "queries": [ 2, 3, 4, 5 ]
        }
      ]
    },
    "answerrrsigs": {
      "count": 2,
      "mismatches": [
        {
          "count": 1,
          "exp_val": [ "A" ],
          "got_val": [ "A", "RRSIG(A)" ],
          "queries": [ 4 ]
        },
        {
          "count": 1,
          "exp_val": [ "A" ],
          "got_val": [ "A", "CNAME" ],
          "queries": [ 5 ]
        }
      ]
    }
  }
}
"""

DIFF_REPORT_JSON = """
{
  "start_time": 1,
  "end_time": 2,
  "total_answers": 23100,
  "total_queries": 23122,
  "other_disagreements": {
    "queries": [7, 8, 9]
  },
  "target_disagreements": {
    "count": 4,
    "fields": {
      "timeout": {
        "count": 4,
        "mismatches": [
          {
            "count": 4,
            "exp_val": "timeout",
            "got_val": "answer",
            "queries": [ 1, 2, 3, 4 ]
          }
        ]
      },
      "answerrrsigs": {
        "count": 1,
        "mismatches": [
          {
            "count": 1,
            "exp_val": [ "A" ],
            "got_val": [ "A", "RRSIG(A)" ],
            "queries": [ 4 ]
          }
        ]
      }
    }
  }
}
"""

REPRODATA_JSON = """
{
  "1": {
    "retries": 2,
    "upstream_stable": 1,
    "verified": 1
  },
  "2": {
    "retries": 3,
    "upstream_stable": 3,
    "verified": 3
  },
  "3": {
    "retries": 3,
    "upstream_stable": 3,
    "verified": 2
  }
}
"""


def test_data_mismatch_init():
    with pytest.raises(Exception):
        DataMismatch(1, 1)


@pytest.mark.parametrize(
    "mismatch_data, expected_key",
    zip(
        MISMATCH_DATA,
        [
            ("timeout", "answer"),
            (("A",), ("A", "CNAME")),
            (("A",), ("A", "RRSIG(A)")),
        ],
    ),
)
def test_data_mismatch(mismatch_data, expected_key):
    mismatch1 = DataMismatch(*mismatch_data)
    mismatch2 = DataMismatch(*mismatch_data)

    # equality, inequality
    assert mismatch1 == mismatch2
    assert not mismatch1 != mismatch2  # pylint: disable=unneeded-not
    assert mismatch1.key == mismatch2.key
    assert hash(mismatch1) == hash(mismatch2)

    # check key
    assert mismatch1.key == expected_key


@pytest.mark.parametrize(
    "mismatch1_data, mismatch2_data", itertools.combinations(MISMATCH_DATA, 2)
)
def test_data_mismatch_differnet_key_hash(mismatch1_data, mismatch2_data):
    if mismatch1_data == mismatch2_data:
        return
    mismatch1 = DataMismatch(*mismatch1_data)
    mismatch2 = DataMismatch(*mismatch2_data)

    assert mismatch1 != mismatch2
    assert mismatch1.key != mismatch2.key
    assert hash(mismatch1) != hash(mismatch2)


# pylint: disable=protected-access
def test_json_data_object():
    empty = JSONDataObject()
    assert empty.save() is None

    # simple scalar, list or dict -- no restore/save callbacks
    attrs = {"a": (None, None)}
    basic = JSONDataObject()
    basic.a = 1
    basic._ATTRIBUTES = attrs
    data = basic.save()
    assert data["a"] == 1
    restored = JSONDataObject()
    restored._ATTRIBUTES = attrs
    restored.restore(data)
    assert restored.a == basic.a

    # with save/restore callback
    attrs = {"b": (lambda x: x + 1, lambda x: x - 1)}
    complex_obj = JSONDataObject()
    complex_obj.b = 1
    complex_obj._ATTRIBUTES = attrs
    data = complex_obj.save()
    assert data["b"] == 0
    restored = JSONDataObject()
    restored._ATTRIBUTES = attrs
    restored.restore(data)
    assert restored.b == complex_obj.b


# pylint: enable=protected-access


@pytest.mark.parametrize("qid, diff_data", QUERY_DIFF_DATA)
def test_diff(qid, diff_data):
    mismatches = {
        field: DataMismatch(*mismatch_data) for field, mismatch_data in diff_data
    }
    diff = Diff(qid, mismatches)
    fields = []

    # verify length and content
    assert len(diff) == len(diff_data)
    for field, mismatch in mismatches.items():
        fields.append(field)
        assert diff[field] == mismatch

    # retrive significant field
    for field_weights in itertools.permutations(fields):
        if not field_weights:
            continue
        field_weights = list(field_weights)
        assert diff.get_significant_field(field_weights) == (
            field_weights[0],
            mismatches[field_weights[0]],
        )
        field_weights.append("custom")
        assert diff.get_significant_field(field_weights) == (
            field_weights[0],
            mismatches[field_weights[0]],
        )
        field_weights.insert(0, "custom2")
        assert diff.get_significant_field(field_weights) == (
            field_weights[1],
            mismatches[field_weights[1]],
        )
    assert diff.get_significant_field(["non_existent"]) == (None, None)

    # adding or removing items isn't possible
    with pytest.raises(Exception):
        diff["non_existent"] = None  # pylint: disable=unsupported-assignment-operation
    with pytest.raises(Exception):
        del diff[list(diff.keys())[0]]  # pylint: disable=unsupported-delete-operation


def test_diff_equality():
    mismatches_tuple = {
        "timeout": DataMismatch("answer", "timeout"),
        "answertypes": DataMismatch(("A",), ("CNAME",)),
    }
    mismatches_list = {
        "timeout": DataMismatch("answer", "timeout"),
        "answertypes": DataMismatch(["A"], ["CNAME"]),
    }

    # tuple or list doesn't matter
    assert Diff(1, mismatches_tuple) == Diff(1, mismatches_list)

    # QID doesn't matter
    assert Diff(1, mismatches_tuple) == Diff(2, mismatches_tuple)

    # different mismatches
    mismatches_tuple["answerrrsigs"] = DataMismatch(("RRSIG(A)",), ("",))
    assert Diff(1, mismatches_tuple) != Diff(1, mismatches_list)


def test_disagreements():
    dis = Disagreements()

    # add mismatches
    qids = set()
    for qid, diff_data in QUERY_DIFF_DATA:
        if diff_data:
            qids.add(qid)
        for field, mismatch_data in diff_data:
            mismatch = DataMismatch(*mismatch_data)
            dis.add_mismatch(field, mismatch, qid)
    assert dis.keys() == qids
    assert len(dis) == len(qids)
    assert dis.count == len(qids)

    # retrieve mismatches by qid
    for qid, diff_data in QUERY_DIFF_DATA:
        diff = dis[qid]
        assert diff.qid == qid
        for field, mismatch_data in diff_data:
            mismatch = DataMismatch(*mismatch_data)
            assert diff[field] == mismatch

    # retrieve all qids by mismatch
    found_qids = set()
    for field in dis.field_labels:
        for mismatch, mismatch_qids in dis.get_field_mismatches(field):
            found_qids.update(mismatch_qids)
    assert found_qids == qids

    # initialize from data (JSON)
    dis_data = json.loads(QUERY_DIFF_JSON)
    dis_loaded = Disagreements(_restore_dict=dis_data)
    assert dis_loaded == dis

    # save and restore data
    dis_restored = Disagreements(_restore_dict=dis.save())
    assert dis_restored == dis


def test_disagreements_counter():
    dc = DisagreementsCounter()
    assert len(dc) == 0  # pylint: disable=len-as-condition
    dc.queries.add(1)
    dc.queries.add(1)
    dc.queries.add(2)
    assert len(dc) == 2
    dc_restored = DisagreementsCounter(_restore_dict=dc.save())
    assert len(dc_restored) == 2
    assert dc_restored.queries == {1, 2}


def test_diff_report():
    report = DiffReport(_restore_dict=json.loads(DIFF_REPORT_JSON))
    assert report.start_time == 1
    assert report.end_time == 2
    assert report.duration == 1
    assert report.total_queries == 23122
    assert report.total_answers == 23100
    assert len(report.other_disagreements) == 3
    assert {7, 8, 9} == report.other_disagreements.queries
    assert len(report.target_disagreements) == 4

    report_restored = DiffReport(_restore_dict=report.save())
    for attrib in report.__dict__:
        assert getattr(report, attrib) == getattr(report_restored, attrib)

    # report with some missing fields
    partial_data = report.save()
    del partial_data["other_disagreements"]
    del partial_data["target_disagreements"]
    partial_report = DiffReport(_restore_dict=partial_data)
    assert partial_report.other_disagreements is None
    assert partial_report.target_disagreements is None
    for key, value in partial_data.items():
        assert getattr(partial_report, key) == value


def test_summary():
    field_weights = ["timeout", "answertypes", "aswerrrsigs"]
    report = DiffReport(_restore_dict=json.loads(DIFF_REPORT_JSON))

    # no reprodata -- no queries are missing
    summary = Summary.from_report(report, field_weights)
    assert summary.not_reproducible == 0
    assert summary.keys() == report.target_disagreements.keys()

    # exactly one mismatch per query
    mismatch_count = 0
    for field in summary.field_labels:
        for _, mismatch_qids in summary.get_field_mismatches(field):
            mismatch_count += len(mismatch_qids)
    assert mismatch_count == len(summary)

    # filter not reproducible
    report.reprodata = ReproData(_restore_dict=json.loads(REPRODATA_JSON))
    summary = Summary.from_report(report, field_weights)
    assert len(summary) == 2
    assert summary.upstream_unstable == (3 + 1)
    assert summary.usable_answers == (23100 - 3 - 2)
    assert summary.not_reproducible == 1

    # JSON export/import
    restored_summary = Summary(_restore_dict=summary.save())
    assert len(summary) == 2
    assert restored_summary.upstream_unstable == summary.upstream_unstable
    assert restored_summary.usable_answers == summary.usable_answers
    assert restored_summary.not_reproducible == summary.not_reproducible

    # not possible to add additional mismatch for existing uery
    summary = Summary()
    summary.add_mismatch(DIFF_DATA[0][0], DataMismatch(*DIFF_DATA[0][1]), 0)
    summary.add_mismatch(DIFF_DATA[1][0], DataMismatch(*DIFF_DATA[1][1]), 1)
    with pytest.raises(ValueError):
        summary.add_mismatch(DIFF_DATA[0][0], DataMismatch(*DIFF_DATA[0][1]), 0)
    with pytest.raises(ValueError):
        summary.add_mismatch(DIFF_DATA[1][0], DataMismatch(*DIFF_DATA[1][1]), 0)


def test_repro_counter():
    rc = ReproCounter()
    assert rc.retries == 0
    assert rc.upstream_stable == 0
    assert rc.verified == 0
    assert rc.different_failure == 0

    rc = ReproCounter(retries=4, upstream_stable=2, verified=1, different_failure=1)
    assert rc.retries == 4
    assert rc.upstream_stable == 2
    assert rc.verified == 1
    assert rc.different_failure == 1

    rc = ReproCounter(_restore_dict={"retries": 4})
    assert rc.retries == 4
    assert rc.upstream_stable == 0
    assert rc.verified == 0
    assert rc.different_failure == 0

    data = rc.save()
    assert data["retries"] == 4
    assert data["upstream_stable"] == 0
    assert data["verified"] == 0
    assert data["different_failure"] == 0

    assert ReproCounter().save() is None


def test_repro_data():
    rd = ReproData()
    new_qid = 1
    assert rd[new_qid].retries == 0
    assert rd[new_qid].upstream_stable == 0
    assert rd[new_qid].verified == 0
    assert new_qid in rd
    assert len(rd) == 1

    new_qid2 = 2
    rd[new_qid2].retries = 2
    assert rd[new_qid2].retries == 2

    data = rd.save()
    assert len(data) == 1
    assert str(new_qid2) in data

    assert ReproData().save() is None

    rd2 = ReproData(_restore_dict=data)
    assert len(rd2) == 1
    assert str(new_qid2) in rd2
    assert rd2[new_qid2].retries == 2
