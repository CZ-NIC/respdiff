import binascii

import pytest

from qprep import wrk_process_frame, wrk_process_wire_packet


@pytest.mark.parametrize('wire', [
    b'',
    b'x',
    b'xx',
])
def test_wire_input_invalid(wire):
    assert wrk_process_wire_packet(1, wire, 'invalid') == (1, wire)
    assert wrk_process_wire_packet(1, wire, 'invalid') == (1, wire)


@pytest.mark.parametrize('wire_hex', [
    # www.audioweb.cz A
    'ed21010000010000000000010377777708617564696f77656202637a00000100010000291000000080000000',
])
def test_wire_input_valid(wire_hex):
    wire_in = binascii.unhexlify(wire_hex)
    qid, wire_out = wrk_process_wire_packet(1, wire_in, 'qid 1')
    assert wire_in == wire_out
    assert qid == 1


@pytest.mark.parametrize('wire_hex', [
    # test.dotnxdomain.net. A
    ('ce970120000100000000000104746573740b646f746e78646f6d61696e036e657400000'
     '10001000029100000000000000c000a00084a69fef0f174d87e'),
    # 0es-u2af5c077-c56-s1492621913-i00000000.eue.dotnxdomain.net A
    ('d72f01000001000000000001273065732d7532616635633037372d6335362d733134393'
     '23632313931332d693030303030303030036575650b646f746e78646f6d61696e036e65'
     '7400000100010000291000000080000000'),
])
def test_pcap_input_blacklist(wire_hex):
    wire = binascii.unhexlify(wire_hex)
    assert wrk_process_wire_packet(1, wire, 'qid 1') == (None, None)


@pytest.mark.parametrize('frame_hex, wire_hex', [
    # UPD nic.cz A
    ('deadbeefcafecafebeefbeef08004500004bf9d000004011940d0202020201010101b533003500375520',
     'b90001200001000000000001036e696302637a0000010001000029100000000000000c000a00081491f8'
     '93b0c90b2f'),
    # TCP nic.cz A
    ('deadbeefcafebeefbeefcafe080045000059e2f2400040066ae80202020201010101ace7003557b51707'
     '47583400501800e5568c0000002f', '49e501200001000000000001036e696302637a00000100010000'
     '29100000000000000c000a0008a1db546e1d6fa39f'),
])
def test_wrk_process_frame(frame_hex, wire_hex):
    data = binascii.unhexlify(frame_hex + wire_hex)
    wire = binascii.unhexlify(wire_hex)
    assert wrk_process_frame((1, data, 'qid 1')) == (1, wire)
