import string
import sys

allowed_bytes = (string.ascii_letters + string.digits + '.-_').encode('ascii')
trans = {}
for i in range(0, 256):
    if i in allowed_bytes:
        trans[i] = bytes(chr(i), encoding='ascii')
    else:
        trans[i] = (r'\%03i' % i).encode('ascii')
# pprint(trans)

while True:
    line = sys.stdin.buffer.readline()
    if not line:
        break
    line = line[:-1]  # newline

    typestart = line.rfind(b' ') + 1  # rightmost space
    if not typestart:
        continue  # no RR type!?
    typetext = line[typestart:]
    if not typetext:
        continue

    # normalize name
    normalized = b''
    for nb in line[:typestart - 1]:
        normalized += trans[nb]
    sys.stdout.buffer.write(normalized)
    sys.stdout.buffer.write(b' ')
    sys.stdout.buffer.write(typetext)
    sys.stdout.buffer.write(b'\n')
