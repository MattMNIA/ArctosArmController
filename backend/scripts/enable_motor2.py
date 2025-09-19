import can, time

CAN_IFACE = "COM4"
CAN_ID = 5  # your motor ID
BITRATE = 500000  # try 1000000 if no response

def crc_for(can_id, payload):
    return (can_id + sum(payload)) & 0xFF

def send(bus, can_id, code, params=()):
    payload = [code] + list(params)
    payload.append(crc_for(can_id, payload))
    msg = can.Message(arbitration_id=can_id, data=bytes(payload), is_extended_id=False)
    bus.send(msg)

def recv(bus, can_id, expected_code, timeout=0.2):
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = bus.recv(timeout)
        if msg and msg.arbitration_id == can_id and msg.data[0] == expected_code:
            return list(msg.data)
    return None

def read_enable(bus, can_id):
    send(bus, can_id, 0x3A)
    r = recv(bus, can_id, 0x3A)
    return None if not r else r[1]

def enable_motor(bus, can_id, en=1):
    send(bus, can_id, 0xF3, [en])
    return recv(bus, can_id, 0xF3)

bus = can.interface.Bus(bustype="slcan", channel=CAN_IFACE, bitrate=BITRATE)

print("Reading initial enable state...")
print("Enable =", read_enable(bus, CAN_ID))

print("Trying to ENABLE motor...")
print(enable_motor(bus, CAN_ID))
time.sleep(0.2)
print("Enable =", read_enable(bus, CAN_ID))

print("Trying to DISABLE motor...")
print(enable_motor(bus, CAN_ID, 0))
time.sleep(0.2)
print("Enable =", read_enable(bus, CAN_ID))
