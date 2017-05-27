import sys
import struct
import msgdiff

if True:
#with open('/tmp/all.dns2', 'wb') as out:
    for d in msgdiff.find_querydirs(sys.argv[1]):
        answers = msgdiff.read_answers(d)
        continue
        # name length
        a_bin = b''
        for name, msg in answers.items():
            msg_bin = msg.to_wire()
            a_bin += struct.pack('10p H', bytes(name, encoding='ascii'), len(msg_bin))
            a_bin += msg_bin
        #print(len(a_bin))
        out.write(struct.pack('H', len(a_bin)))
        out.write(a_bin)

