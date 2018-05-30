"""Shared data types for Mypy"""

from typing import Any, Sequence, Union

import dns.rrset

# data-related types
FieldLabel = str
MismatchValue = Union[str, dns.rrset.RRset, Sequence[Any]]
ResolverID = str
QID = int
QKey = bytes
WireFormat = bytes
