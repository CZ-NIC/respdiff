import sys

# LMDB isn't portable between LE/BE platforms
# upon import, check we're on a little endian platform
assert sys.byteorder == 'little', 'Big endian platforms are not supported'
