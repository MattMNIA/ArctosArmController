import can
import time

# Set up CAN bus interface (modify 'channel' and 'bitrate' to match your setup)
bus = can.interface.Bus(channel='COM4', interface='slcan', bitrate=500000)

def calculate_crc(data):
    """Simple CRC-8 calculation as used in many servo protocols.
       Replace with your servo’s exact CRC formula if documented."""
    crc = 0
    for b in data:
        crc ^= b
    return crc

def send_command_and_check(motor_id, direction):
    """
    Sends motor direction command and waits for response.
    direction: 0 (CW), 1 (CCW)
    """
    # Try both message formats: with and without header
    for include_header in [True, False]:
        tx_data = []
        if include_header:
            tx_data.append(0xFA)  # Head byte (per manual)

        tx_data += [motor_id, 0x86, direction]
        tx_crc = calculate_crc(tx_data)
        tx_data.append(tx_crc)

        # Using a generic arbitration ID for now (we’ll adjust if needed)
        msg = can.Message(arbitration_id=0x141 + motor_id - 1, data=tx_data, is_extended_id=False)
        print(f"➡️ Sending to ID 0x{msg.arbitration_id:X}: {tx_data}")
        try:
            bus.send(msg)
        except can.CanError:
            print("❌ Failed to send CAN frame.")
            continue

        # Listen for any response for 0.5s
        start = time.time()
        while time.time() - start < 0.5:
            rx = bus.recv(timeout=0.1)
            if rx:
                print(f"⬅️ Received: ID=0x{rx.arbitration_id:X}, Data={[hex(b) for b in rx.data]}")
                data = list(rx.data)
                if len(data) >= 5 and data[0] in [0xFB, 0xFA]:
                    if data[1] == motor_id and data[2] == 0x86:
                        status = data[3]
                        print(f"✅ Motor {motor_id} {'success' if status == 1 else 'fail'} (CRC {data[-1]:02X})")
                        return
        print(f"⚠️ No response from motor {motor_id} (include_header={include_header})")
        time.sleep(0.1)

# Set specific directions for each joint
# id = 1 (Joint 1): CCW
send_command_and_check(1, 1)
time.sleep(0.05)

# Joint 2: CW
send_command_and_check(2, 0)
time.sleep(0.05)

# Joint 4: CCW
send_command_and_check(4, 1)
time.sleep(0.05)

# Joint 5: CW
send_command_and_check(5, 0)
time.sleep(0.05)

print("Selected direction commands sent.")
