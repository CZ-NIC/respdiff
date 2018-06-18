import os
import subprocess
import sys

import pytest


DECKARD_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'ci', 'deckard'))
try:
    subprocess.run(
        'test -f "{path}/env.sh" || make depend -C "{path}"'.format(path=DECKARD_PATH),
        cwd=DECKARD_PATH,
        shell=True,
        check=True)
except subprocess.CalledProcessError as exc:
    pytest.skip(
        "Failed to compile deckard: {}".format(exc), allow_module_level=True)
else:
    sys.path.append(DECKARD_PATH)
    pytest.importorskip("pydnstest")
