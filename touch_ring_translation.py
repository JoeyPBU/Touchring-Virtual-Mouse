"""
Touchring Virtual Mouse

This script captures the inputs sent from a touchring mouse and converts them via
a virtual uinput device. This allows the phone-only ring mouse to work on desktop.

It supports:
- Scaled cursor movement
- Button to click mapping (Left, Right, Middle)
- Tap to click
- Automatic device reconnect handling
- There are two more input codes to be utilised
- 3 Button inputs don't break anything... they just don't do anything useful
"""


import time
import select
from evdev import InputDevice, list_devices, ecodes as e, UInput

DEVICE_NAME = "DEVICE NAME"

MOUSE_SPEED_SCALE = 0.5  # 1.0 = max speed, 0.1 = slowest
TAP_FREEZE_DURATION_MS = 50

last_absolute_x = None
last_absolute_y = None
last_sent_absolute_x = None
last_sent_absolute_y = None
freeze_input_until_timestamp = 0

# Virtual mouse device
virtual_mouse = UInput(
    {
        e.EV_REL: [e.REL_X, e.REL_Y],
        e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
    },
    name="Touchring Virtual Mouse",
)

BUTTON_ACTION_MAP = {
    e.KEY_BACK: "LEFT_CLICK",
    e.KEY_SLEEP: "RIGHT_CLICK",
    e.KEY_VOLUMEDOWN: "MIDDLE_CLICK",
    330: "TOUCH_DOWN",
    320: "TOUCH_UP",
}


def emit_click(mouse_button):
    """
    Emit a full press-and-release cycle for a virtual mouse button.

    Args:
        mouse_button: evdev button code.
    """
    virtual_mouse.write(e.EV_KEY, mouse_button, 1)
    virtual_mouse.syn()
    time.sleep(0.02)
    virtual_mouse.write(e.EV_KEY, mouse_button, 0)
    virtual_mouse.syn()


def handle_button_action(action_name):
    """
    Handle a mapped button or touch action.

    This function translates high-level action names into virtual mouse events
    and manages tap click movement freezes.

    Args:
        action_name: Action string from BUTTON_ACTION_MAP
    """
    global freeze_input_until_timestamp

    if action_name == "LEFT_CLICK":
        emit_click(e.BTN_LEFT)
        print("[ACTION] LEFT_CLICK")

    elif action_name == "RIGHT_CLICK":
        emit_click(e.BTN_RIGHT)
        print("[ACTION] RIGHT_CLICK")

    elif action_name == "MIDDLE_CLICK":
        emit_click(e.BTN_MIDDLE)
        print("[ACTION] MIDDLE_CLICK")

    elif action_name == "TOUCH_DOWN":
        emit_click(e.BTN_LEFT)
        freeze_input_until_timestamp = (
            time.time() + TAP_FREEZE_DURATION_MS / 1000.0
        )
        print("[TOUCH] TAP_LEFT_CLICK")

    elif action_name == "TOUCH_UP":
        pass


def move_cursor_from_absolute(abs_x, abs_y):
    """
    Convert absolute touch coordinates into relative cursor movement.

    Movement is scaled and suppresed temporarily during tap events to prevent
    cursor jumps.

    Args:
        abs_x: Absolute X coordinate from touchring
        abs_y: Absolute Y coordinate from touchring
    """
    global last_sent_absolute_x, last_sent_absolute_y

    current_time = time.time()
    if current_time < freeze_input_until_timestamp:
        last_sent_absolute_x = abs_x
        last_sent_absolute_y = abs_y
        return

    if last_sent_absolute_x is None:
        last_sent_absolute_x = abs_x
        last_sent_absolute_y = abs_y
        return

    delta_x = int((abs_x - last_sent_absolute_x) * MOUSE_SPEED_SCALE)
    delta_y = int((abs_y - last_sent_absolute_y) * MOUSE_SPEED_SCALE)

    if delta_x or delta_y:
        virtual_mouse.write(e.EV_REL, e.REL_X, delta_x)
        virtual_mouse.write(e.EV_REL, e.REL_Y, delta_y)
        virtual_mouse.syn()

    last_sent_absolute_x = abs_x
    last_sent_absolute_y = abs_y


def find_input_devices_by_name(device_name):
    """
    Locate all evdev input devices whose name matches (The Bluetooth device name)

    Args:
        device_name: Bluetooth device name to match

    Returns:
        List of InputDevice objects
    """
    matching_devices = []
    for device_path in list_devices():
        device = InputDevice(device_path)
        if device_name in device.name:
            matching_devices.append(device)
    return matching_devices


print("[INFO] Starting Touchring virtual mouse")

while True:
    """
    Main device management loop.
    Continuously:
        - Searches for matching input devices
        - Grabs them exclusively (This stops the default touchring buttons from affecting PC)
        - Reads input events
        - Translates touch and button events into virtual mouse actions
        - Automatically tries to connect on disconnect or error
    """
    input_devices = find_input_devices_by_name(DEVICE_NAME)

    if not input_devices:
        print(f"[INFO] Device '{DEVICE_NAME}' not found, retrying in 5s...")
        time.sleep(5)
        continue

    print(
        f"[INFO] Found {len(input_devices)} device(s) matching '{DEVICE_NAME}': "
        f"{[device.path for device in input_devices]}"
    )

    for device in input_devices:
        device.grab()
        device.fd = device.fd

    try:
        while True:
            readable_fds, _, _ = select.select(
                [device.fd for device in input_devices], [], [], 1
            )

            for ready_fd in readable_fds:
                active_device = next(
                    device for device in input_devices if device.fd == ready_fd
                )

                for event in active_device.read():
                    if event.type == e.EV_ABS:
                        if event.code == e.ABS_X:
                            last_absolute_x = event.value
                        elif event.code == e.ABS_Y:
                            last_absolute_y = event.value

                        if (
                            last_absolute_x is not None
                            and last_absolute_y is not None
                        ):
                            move_cursor_from_absolute(
                                last_absolute_x, last_absolute_y
                            )

                    elif event.type == e.EV_KEY and event.value == 1:
                        action_name = BUTTON_ACTION_MAP.get(event.code)
                        if action_name:
                            handle_button_action(action_name)
                        else:
                            print(f"[BUTTON] Unmapped: {event.code}")

    except Exception as ex:
        print(f"[WARN] Device disconnected or error: {ex}")
        time.sleep(1)
        print("[INFO] Attempting to reconnec...")
