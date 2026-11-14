"""Nordic UART Service (NUS) peripheral for the Claude Hardware Buddy.

Runs on Badgeware's MicroPython ``bluetooth`` module (BTstack on the
RM2 / CYW43 radio).

Security: Badgeware's rp2 build compiles BTstack without
``MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING``, so the link cannot be
encrypted. Any central in range can connect. The device reports
``sec: false`` in its status ack and only sends a permission decision
when someone presses a button on the badge.

Threading: on rp2 the BLE IRQ handler runs from the MicroPython
scheduler. It only appends to a queue. ``poll()`` (main loop) drains
the queue with ``list.pop(0)``, a single native call, so the two never
interleave halfway through an update.
"""

import json
import time

import bluetooth
from micropython import const

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_MTU_EXCHANGED = const(21)

_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

_NUS_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_NUS_RX = (
    bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"),
    _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE,
)
_NUS_TX = (
    bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"),
    _FLAG_READ | _FLAG_NOTIFY,
)
_NUS_SERVICE = (_NUS_UUID, (_NUS_TX, _NUS_RX))

# Advertising data types.
_ADV_FLAGS = const(0x01)
_ADV_UUID128_COMPLETE = const(0x07)
_ADV_NAME_SHORT = const(0x08)
_ADV_NAME_COMPLETE = const(0x09)

_NAME_PREFIX = "Claude"
_ADV_INTERVAL_US = const(100000)
_ADV_RETRY_MS = const(2000)
_DROP_RETRY_MS = const(5000)

_PREFERRED_MTU = const(247)
_DEFAULT_MTU = const(23)
_RX_BUFFER = const(1024)

# Turn events can be up to 4 KB; anything longer is dropped whole.
_MAX_LINE = const(6144)
_MAX_QUEUE = const(256)


def _ad(ad_type, payload):
    return bytes((len(payload) + 1, ad_type)) + payload


def id_suffix(uid):
    """Six hex digits from the chip's unique ID, XOR-folded to 3 bytes.

    The RP2350 unique ID never changes, so the advertised name stays
    the same across reboots. The BLE address isn't used: if the radio
    reports no public address, BTstack falls back to a random static
    address, which could differ every boot and break Claude Desktop's
    reconnect and the user's ability to match the name.
    """
    folded = bytearray(3)
    for i, b in enumerate(bytes(uid)):
        folded[i % 3] ^= b
    return "".join("{:02X}".format(b) for b in folded)


def _device_suffix():
    import machine

    return id_suffix(machine.unique_id())


class BuddyBLE:
    def __init__(self):
        self._ble = bluetooth.BLE()
        self._ble.active(True)

        self.name = "{}_{}".format(_NAME_PREFIX, _device_suffix())
        try:
            self._ble.config(gap_name=self.name)
        except Exception as e:  # noqa: BLE001
            print("buddy_ble: gap_name:", e)
        try:
            self._ble.config(mtu=_PREFERRED_MTU)
        except Exception as e:  # noqa: BLE001
            print("buddy_ble: mtu:", e)

        ((self._tx_h, self._rx_h),) = self._ble.gatts_register_services((_NUS_SERVICE,))
        # Append mode: writes that arrive before we read accumulate
        # instead of overwriting each other.
        self._ble.gatts_set_buffer(self._rx_h, _RX_BUFFER, True)

        # Primary packet: flags + NUS UUID + short name "Claude" (29 of
        # 31 bytes), so passive scanners see both the service and a
        # name with the right prefix. The full name goes in the scan
        # response.
        self._adv = (
            _ad(_ADV_FLAGS, b"\x06")
            + _ad(_ADV_UUID128_COMPLETE, bytes(_NUS_UUID))
            + _ad(_ADV_NAME_SHORT, _NAME_PREFIX.encode())
        )
        self._resp = _ad(_ADV_NAME_COMPLETE, self.name.encode())

        self._conn = None
        self._mtu = _DEFAULT_MTU
        self._q = []
        self._line = bytearray()
        self._skipping = False
        self._advertising = False
        self._next_adv_ms = None
        # Retry gate for drop(): when the last disconnect was asked for.
        self._drop_ms = None

        self._ble.irq(self._irq)
        self._advertise()

    # -- IRQ (scheduler context): queue only ----------------------------

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self._conn = data[0]
            self._mtu = _DEFAULT_MTU
            self._advertising = False
            self._drop_ms = None
            self._q.append(("connect", None))
        elif event == _IRQ_CENTRAL_DISCONNECT:
            if data[0] == self._conn:
                self._conn = None
            self._q.append(("disconnect", None))
        elif event == _IRQ_GATTS_WRITE:
            conn, handle = data
            if handle == self._rx_h and len(self._q) < _MAX_QUEUE:
                self._q.append(("rx", self._ble.gatts_read(handle)))
        elif event == _IRQ_MTU_EXCHANGED:
            if data[0] == self._conn:
                self._mtu = data[1]

    # -- main loop API ----------------------------------------------------

    @property
    def connected(self):
        return self._conn is not None

    def poll(self):
        """Return queued events in order: ("connect"|"disconnect", None)
        or ("line", bytes) for each complete line received."""
        out = []
        q = self._q
        while q:
            kind, value = q.pop(0)
            if kind == "rx":
                self._feed(value, out)
            else:
                if kind == "connect":
                    self._line = bytearray()
                    self._skipping = False
                elif kind == "disconnect" and self._conn is None:
                    self._advertising = False
                    self._next_adv_ms = None
                out.append((kind, None))
        return out

    def service(self, now_ms):
        """Restart advertising while nothing is connected."""
        if self._conn is not None or self._advertising:
            return
        if self._next_adv_ms is not None and time.ticks_diff(now_ms, self._next_adv_ms) < 0:
            return
        if not self._advertise():
            self._next_adv_ms = time.ticks_add(now_ms, _ADV_RETRY_MS)

    def drop(self, now_ms):
        """Disconnect the current central (a dead or silent link). The
        disconnect IRQ then restarts advertising via service(). Asks at
        most every _DROP_RETRY_MS. Returns True if it asked now."""
        conn = self._conn
        if conn is None:
            return False
        if self._drop_ms is not None:
            since = time.ticks_diff(now_ms, self._drop_ms)
            if 0 <= since < _DROP_RETRY_MS:  # negative: ticks wrapped, retry
                return False
        self._drop_ms = now_ms
        try:
            self._ble.gap_disconnect(conn)
        except OSError as e:
            print("buddy_ble: disconnect failed:", e)
        return True

    def send(self, obj):
        """Send one JSON object as a line. Returns True if queued."""
        conn = self._conn
        if conn is None:
            return False
        data = (json.dumps(obj) + "\n").encode()
        step = max(20, self._mtu - 3)
        try:
            for i in range(0, len(data), step):
                self._ble.gatts_notify(conn, self._tx_h, data[i : i + step])
        except OSError as e:
            print("buddy_ble: notify failed:", e)
            return False
        return True

    def close(self):
        try:
            self._ble.gap_advertise(None)
        except Exception:  # noqa: BLE001, S110
            pass
        if self._conn is not None:
            try:
                self._ble.gap_disconnect(self._conn)
            except Exception:  # noqa: BLE001, S110
                pass
        try:
            self._ble.active(False)
        except Exception:  # noqa: BLE001, S110
            pass
        self._conn = None

    # -- internals --------------------------------------------------------

    def _advertise(self):
        try:
            self._ble.gap_advertise(
                _ADV_INTERVAL_US,
                adv_data=self._adv,
                resp_data=self._resp,
                connectable=True,
            )
        except OSError as e:
            print("buddy_ble: advertise failed:", e)
            return False
        self._advertising = True
        return True

    def _feed(self, data, out):
        start = 0
        while True:
            end = data.find(b"\n", start)
            if end < 0:
                self._append(data[start:])
                return
            self._append(data[start:end])
            if not self._skipping and self._line:
                out.append(("line", bytes(self._line)))
            elif self._skipping:
                print("buddy_ble: dropped over-long line")
            self._line = bytearray()
            self._skipping = False
            start = end + 1

    def _append(self, chunk):
        if self._skipping or not chunk:
            return
        if len(self._line) + len(chunk) > _MAX_LINE:
            self._skipping = True
            self._line = bytearray()
            return
        self._line.extend(chunk)
