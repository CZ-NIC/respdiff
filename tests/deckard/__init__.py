import os
import sys

import pytest


try:
    DECKARD_PATH = os.environ['DECKARD_PATH']
except KeyError:
    pytest.skip("DECKARD_PATH env var not set", allow_module_level=True)
else:
    sys.path.append(DECKARD_PATH)
    pytest.importorskip("pydnstest")

    if not os.path.exists(os.path.join(DECKARD_PATH, 'env.sh')):
        pytest.skip(
            "env.sh script doesn't exist in DECKARD_PATH",
            allow_module_level=True)
