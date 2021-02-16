"""
Test the respdiff toolchain by mocking DNS traffic using Deckard as a mock server.

https://gitlab.nic.cz/knot/deckard
"""
import os
import subprocess
import tempfile
from typing import Optional, Sequence  # noqa

from pydnstest.augwrap import AugeasWrapper  # pylint: disable=import-error
from respdiff.dataformat import DiffReport

from . import DECKARD_PATH

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
SCENARIO_DIR = os.path.join(TEST_DIR, 'scenarios')
CONFIG_PATH = os.path.join(TEST_DIR, 'respdiff.cfg')
RESPDIFF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')


class MockServer(tempfile.TemporaryDirectory):
    def __init__(self, deckard_path: str, scenario_path: str) -> None:
        super().__init__()
        self.deckard_path = deckard_path
        self.scenario_path = scenario_path
        self.tmpdir = ''
        self.deckard = None  # type: Optional[subprocess.Popen]

    def __enter__(self) -> 'MockServer':
        assert os.path.exists(self.scenario_path), \
            "Scenario {} not found!".format(self.scenario_path)
        assert os.path.exists(os.path.join(self.deckard_path, 'env.sh')), \
            "env.sh file missing in deckard dir; was it compiled?"
        self.tmpdir = super().__enter__()
        assert self.tmpdir is not None

        cmd = (
            '. {ms.deckard_path}/env.sh; '  # 'source' that's compatible with /bin/sh
            'python3 {ms.deckard_path}/pydnstest/testserver.py '
            '--scenario {ms.scenario_path}').format(ms=self)
        my_env = os.environ.copy()
        my_env['PYTHONPATH'] = self.deckard_path
        my_env['SOCKET_WRAPPER_DIR'] = self.tmpdir

        self.deckard = subprocess.Popen(
            [cmd],
            shell=True,
            env=my_env,
            stderr=subprocess.PIPE)
        assert self.deckard is not None

        # run and wait for server to get initialized
        while True:
            out = self.deckard.stderr
            if out is not None and b'server running' in out.readline():
                break
            if self.deckard.poll() is not None:
                raise RuntimeError("Deckard didn't start properly!")

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        assert self.deckard is not None
        self.deckard.terminate()
        self.deckard.wait()
        return super().__exit__(exc_type, exc_value, traceback)

    def execute(self, cmd: str) -> subprocess.Popen:
        my_env = os.environ.copy()
        my_env['SOCKET_WRAPPER_DIR'] = self.tmpdir
        shcmd = '. {ms.deckard_path}/env.sh; {cmd}'.format(ms=self, cmd=cmd)
        process = subprocess.Popen(
            [shcmd],
            shell=True,
            env=my_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        process.wait()
        return process


def qprep(queries: Sequence[str], envdir: str):
    data = b'\n'.join((query.encode('ascii') for query in queries))
    with subprocess.Popen([
                os.path.join(RESPDIFF_DIR, 'qprep.py'),
                envdir],
            stdin=subprocess.PIPE) as proc:
        try:
            proc.communicate(data)
        except Exception:
            proc.kill()
            raise
        finally:
            proc.wait()


def orchestrator(envdir: str, config_path: str, deckard_path: str, scenario_path: str):
    with MockServer(
            deckard_path=deckard_path,
            scenario_path=scenario_path) as mock:
        mock.execute(
            '{respdiffdir}/orchestrator.py -c {config_path} {envdir}'.format(
                respdiffdir=RESPDIFF_DIR,
                config_path=config_path,
                envdir=envdir))


def msgdiff(envdir: str, config_path: str):
    subprocess.call('{respdiffdir}/msgdiff.py -c {config_path} {envdir}'.format(
        respdiffdir=RESPDIFF_DIR,
        config_path=config_path,
        envdir=envdir),
        shell=True)


def diffsum(envdir: str, config_path: str):
    subprocess.call('{respdiffdir}/diffsum.py -c {config_path} {envdir}'.format(
        respdiffdir=RESPDIFF_DIR,
        config_path=config_path,
        envdir=envdir),
        shell=True)


def queries_from_rpl(scenario_path):
    aug = AugeasWrapper(
        confpath=scenario_path,
        lens='Deckard',
        loadpath=os.path.join(DECKARD_PATH, 'pydnstest'))

    queries = []
    for qnode in aug.tree.match('/scenario/range/entry/section/question/record'):
        domain = qnode.get('/domain').value
        type_ = qnode.get('/type').value
        queries.append((domain, type_))

    return [' '.join((domain, type_)) for domain, type_ in set(queries)]


def diffsum_toolchain(scenario):
    def decorator(func):
        def wrapper():
            scenario_path = os.path.join(SCENARIO_DIR, scenario)
            with tempfile.TemporaryDirectory() as envdir:
                qprep(queries_from_rpl(scenario_path), envdir)
                orchestrator(
                    envdir,
                    CONFIG_PATH,
                    deckard_path=DECKARD_PATH,
                    scenario_path=scenario_path)
                msgdiff(envdir, CONFIG_PATH)
                diffsum(envdir, CONFIG_PATH)
                report = DiffReport.from_json(os.path.join(envdir, 'report.json'))
                func(report)
        return wrapper
    return decorator
