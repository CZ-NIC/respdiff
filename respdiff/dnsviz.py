from collections import abc, defaultdict
import json
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Tuple  # noqa

import dns
import dns.name


TYPES = 'A,AAAA,CNAME'
KEYS_ERROR = ['error', 'errors']
KEYS_WARNING = ['warnings']


class DnsvizDomainResult:
    def __init__(
                self,
                errors: Optional[Mapping[str, List]] = None,
                warnings: Optional[Mapping[str, List]] = None,
            ) -> None:
        super().__init__()
        self.errors = defaultdict(list)    # type: Dict[str, List]
        self.warnings = defaultdict(list)  # type: Dict[str, List]
        if errors is not None:
            self.errors.update(errors)
        if warnings is not None:
            self.warnings.update(warnings)

    @property
    def is_error(self):
        return len(self.errors) > 0


def _find_keys(
            kv_iter: Iterable[Tuple[Any, Any]],
            keys: Optional[List[Any]] = None,
            path: Optional[List[Any]] = None
        ) -> Iterator[Tuple[Any, Any]]:
    assert isinstance(keys, list)
    if path is None:
        path = []
    for key, value in kv_iter:
        key_path = path + [key]
        if key in keys:
            yield key_path, value
        if isinstance(value, abc.Mapping):
            yield from _find_keys(value.items(), keys, key_path)
        elif isinstance(value, list):
            yield from _find_keys(enumerate(value), keys, key_path)


class DnsvizGrok(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.domains = {}
        self._initialize_domains()

    def _initialize_domains(self):
        for key_path, messages in _find_keys(self.items(), KEYS_ERROR + KEYS_WARNING):
            domain = key_path[0]
            if domain not in self.domains:
                self.domains[domain] = DnsvizDomainResult()
            path = '_'.join([str(value) for value in key_path])
            if key_path[-1] in KEYS_ERROR:
                self.domains[domain].errors[path] += messages
            else:
                self.domains[domain].warnings[path] += messages

    @staticmethod
    def from_json(filename: str) -> 'DnsvizGrok':
        with open(filename, encoding='UTF-8') as f:
            grok_data = json.load(f)
        if not isinstance(grok_data, dict):
            raise RuntimeError(
                "File {} doesn't contain dnsviz grok json data".format(filename))
        return DnsvizGrok(grok_data)

    def error_domains(self) -> List[dns.name.Name]:
        err_domains = []
        for domain, data in self.domains.items():
            if data.is_error:
                assert domain[-1] == '.'
                err_domains.append(dns.name.from_text(domain))
        return err_domains
