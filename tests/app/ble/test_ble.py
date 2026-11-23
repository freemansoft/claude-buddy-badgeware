"""Host-side tests for the BLE layer (buddy_ble), with stand-ins for
MicroPython's bluetooth, micropython and machine modules: the advertised
name, line framing of received data, and dropping a silent link."""

import sys
import types
import unittest

import support  # noqa: F401 - puts apps/claude_buddy on sys.path


def install_bluetooth_stub():
    class UUID:
        def __init__(self, s):
            self.s = s

        def __bytes__(self):
            return bytes(16)

    class BLE:
        def active(self, *a):
            return True

        def config(self, *a, **k):
            if a == ("mac",):
                return (0, b"\x00\x11\x22\xa1\xb2\xc3")
            return None

        def gatts_register_services(self, services):
            return ((10, 11),)

        def gatts_set_buffer(self, *a):
            pass

        def irq(self, handler):
            self.handler = handler

        def gap_advertise(self, *a, **k):
            pass

    bt = types.ModuleType("bluetooth")
    bt.UUID = UUID
    bt.BLE = BLE
    mp = types.ModuleType("micropython")
    mp.const = lambda x: x
    machine = types.ModuleType("machine")
    # Folds to A1B2C3: bytes 3..7 XOR to zero in each lane.
    machine.unique_id = lambda: bytes([0xA1, 0xB2, 0xC3, 0x5A, 0x3C, 0x00, 0x5A, 0x3C])
    sys.modules["bluetooth"] = bt
    sys.modules["micropython"] = mp
    sys.modules["machine"] = machine


install_bluetooth_stub()

import buddy_ble


class AdvertisingTest(unittest.TestCase):
    def setUp(self):
        self.ble = buddy_ble.BuddyBLE()

    def test_name_from_chip_unique_id(self):
        # XOR-fold of the stub's 8-byte unique ID into 3 bytes.
        self.assertEqual(self.ble.name, "Claude_A1B2C3")

    def test_id_suffix_is_stable_and_uses_all_bytes(self):
        uid = bytes(range(1, 9))
        # Lanes: 1^4^7 = 0x02, 2^5^8 = 0x0F, 3^6 = 0x05.
        self.assertEqual(buddy_ble.id_suffix(uid), "020F05")
        other = bytes(range(1, 8)) + b"\x99"
        self.assertNotEqual(buddy_ble.id_suffix(uid), buddy_ble.id_suffix(other))
        self.assertEqual(len(buddy_ble.id_suffix(uid)), 6)

    def test_advertising_payloads_fit(self):
        self.assertLessEqual(len(self.ble._adv), 31)
        self.assertLessEqual(len(self.ble._resp), 31)


class FramingTest(unittest.TestCase):
    def setUp(self):
        self.ble = buddy_ble.BuddyBLE()

    def feed(self, *chunks):
        for c in chunks:
            self.ble._q.append(("rx", c))
        return self.ble.poll()

    def test_lines_split_across_chunks(self):
        out = self.feed(b'{"a":', b'1}\n{"b"', b":2}\n")
        self.assertEqual(out, [("line", b'{"a":1}'), ("line", b'{"b":2}')])

    def test_multiple_lines_in_one_chunk(self):
        out = self.feed(b"x\ny\n\nz")
        self.assertEqual(out, [("line", b"x"), ("line", b"y")])
        self.assertEqual(self.feed(b"\n"), [("line", b"z")])

    def test_overlong_line_dropped_then_recovers(self):
        big = b"q" * (buddy_ble._MAX_LINE + 10)
        out = self.feed(big[:4000], big[4000:], b"\nok\n")
        self.assertEqual(out, [("line", b"ok")])

    def test_connect_resets_partial_line(self):
        self.feed(b"partial")
        self.ble._q.append(("connect", None))
        out = self.feed(b"fresh\n")
        self.assertEqual(out, [("connect", None), ("line", b"fresh")])


class DropTest(unittest.TestCase):
    """Dropping a dead or silent link (BuddyBLE.drop)."""

    def setUp(self):
        self.ble = buddy_ble.BuddyBLE()
        self.disconnects = []
        self.ble._ble.gap_disconnect = self.disconnects.append
        # CPython's time has no ticks_*.
        self.real_time = buddy_ble.time
        buddy_ble.time = types.SimpleNamespace(
            ticks_diff=lambda a, b: a - b, ticks_add=lambda a, b: a + b
        )

    def tearDown(self):
        buddy_ble.time = self.real_time

    def test_drop_only_when_connected_and_rate_limited(self):
        self.assertFalse(self.ble.drop(0))  # nothing to drop
        self.ble._irq(buddy_ble._IRQ_CENTRAL_CONNECT, (7, 0, b""))
        self.assertTrue(self.ble.drop(0))
        self.assertEqual(self.disconnects, [7])
        self.assertFalse(self.ble.drop(buddy_ble._DROP_RETRY_MS - 1))
        self.assertTrue(self.ble.drop(buddy_ble._DROP_RETRY_MS))  # retry
        self.assertTrue(self.ble.drop(-1))  # ticks wrapped: retry, don't stall
        self.ble._irq(buddy_ble._IRQ_CENTRAL_DISCONNECT, (7, 0, b""))
        self.assertFalse(self.ble.drop(10**6))
        self.assertEqual(len(self.disconnects), 3)


if __name__ == "__main__":
    unittest.main()
