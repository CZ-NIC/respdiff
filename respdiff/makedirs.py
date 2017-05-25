import errno
import os
import sys

import makeq


i = 1
with open(sys.argv[1]) as qlist:
    for line in qlist:
        line = line.strip()
        if i == 8000000:
            break

        dirname = '%07d' % i
        qfilename = '%s/q.dns' % dirname
        try:
            os.mkdir(dirname)
        except OSError as ex:
            if not ex.errno == errno.EEXIST:
                raise
        qry = makeq.qfromtext(line.split())
        if makeq.is_blacklisted(qry):
            continue
        with open(qfilename, 'wb') as qfile:
            qfile.write(qry.to_wire())
        i += 1
