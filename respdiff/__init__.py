import sys

# LMDB isn't portable between LE/BE platforms
# upon import, check we're on a little endian platform
assert sys.byteorder == "little", "Big endian platforms are not supported"

# Check minimal Python version
assert sys.version_info >= (3, 5, 2), "Minimal supported Python version is 3.5.2"
