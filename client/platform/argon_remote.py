"""The Argon ONE case's IR receiver and the Argon remote, without LIRC: the kernel decodes the
remote (NEC) and a keymap turns each button into a key the FS42 remote controller understands.

    sudo env/bin/python3 -m client.platform.argon_remote setup    # turn the receiver on, then reboot
    sudo env/bin/python3 -m client.platform.argon_remote learn    # press each button when asked

The case's power button is handled by the case itself.
"""
import glob
import os
import subprocess
import sys

# the case wires its receiver to GPIO 23
OVERLAY = "dtoverlay=gpio-ir,gpio_pin=23"
KEYMAP = "/etc/rc_keymaps/argon.toml"
RC_MAP = f"gpio_ir_recv * {KEYMAP}"

# button on the remote -> key sent to client/input/remote_controller.py (see its DEFAULT_KEY_MAPPINGS)
BUTTONS = [
    ("UP", "KEY_UP"),               # channel up
    ("DOWN", "KEY_DOWN"),           # channel down
    ("LEFT", "KEY_LEFT"),           # volume down
    ("RIGHT", "KEY_RIGHT"),         # volume up
    ("OK", "KEY_ENTER"),            # confirm (menus, PPV)
    ("HOME", "KEY_HOME"),           # guide
    ("BACK", "KEY_BACKSPACE"),      # last channel
    ("MENU", "KEY_V"),              # subtitles on/off
    ("PLAY/PAUSE", "KEY_A"),        # next audio track (dubbed <-> original)
    ("MUTE", "KEY_M"),              # mute
    ("VOL+", "KEY_RIGHT"),          # volume up
    ("VOL-", "KEY_LEFT"),           # volume down
]

# kernel input event codes: a decoded IR scancode arrives as EV_MSC / MSC_SCAN
EV_MSC, MSC_SCAN = 0x04, 0x04


def learn(receiver, ask=print):
    """Ask for each button in turn and return {button: scancode}."""
    learned = {}
    events = receiver.read_loop()
    for name, _ in BUTTONS:
        ask(name)
        for event in events:
            if event.type == EV_MSC and event.code == MSC_SCAN and event.value not in learned.values():
                learned[name] = event.value
                break
    return learned


def keymap_toml(learned):
    keys = dict(BUTTONS)
    lines = ['[[protocols]]', 'name = "argon"', 'protocol = "nec"', '[protocols.scancodes]']
    lines += [f'{code:#x} = "{keys[name]}"' for name, code in learned.items()]
    return "\n".join(lines) + "\n"


def add_overlay(config_path):
    with open(config_path) as f:
        text = f.read()
    if OVERLAY in text.splitlines():
        return False
    # under [all]: appended after a conditional section such as [cm4] it would only apply there
    with open(config_path, "a") as f:
        f.write(("" if text.endswith("\n") else "\n") + f"\n[all]\n{OVERLAY}\n")
    return True


def add_rc_map(rc_maps_path):
    text = open(rc_maps_path).read() if os.path.exists(rc_maps_path) else ""
    if RC_MAP in text.splitlines():
        return
    # the first matching line wins, so ours goes before any catch-all
    with open(rc_maps_path, "w") as f:
        f.write(f"{RC_MAP}\n{text}")


def find_receiver():
    from evdev import InputDevice

    for path in glob.glob("/dev/input/event*"):
        device = InputDevice(path)
        if device.name == "gpio_ir_recv":
            return device
    return None


def _rc_sysdev():
    for name_file in glob.glob("/sys/class/rc/rc*/input*/name"):
        if open(name_file).read().strip() == "gpio_ir_recv":
            return name_file.split("/")[4]
    return None


def main(argv=sys.argv[1:]):
    command = argv[0] if argv else ""
    if command == "setup":
        config = "/boot/firmware/config.txt" if os.path.exists("/boot/firmware/config.txt") else "/boot/config.txt"
        if add_overlay(config):
            print(f"Turned the IR receiver on in {config}. Reboot, then run: "
                  "sudo env/bin/python3 -m client.platform.argon_remote learn")
        else:
            print("The IR receiver is already on. Run: sudo env/bin/python3 -m client.platform.argon_remote learn")
    elif command == "learn":
        receiver = find_receiver()
        if receiver is None:
            raise SystemExit("No IR receiver found: run 'setup' first and reboot.")
        # decode NEC so every press reports its scancode
        subprocess.run(["ir-keytable", "-s", _rc_sysdev() or "rc0", "-p", "nec"], check=True, capture_output=True)
        learned = learn(receiver, ask=lambda name: print(f"Press {name} on the Argon remote"))
        os.makedirs(os.path.dirname(KEYMAP), exist_ok=True)
        with open(KEYMAP, "w") as f:
            f.write(keymap_toml(learned))
        add_rc_map("/etc/rc_maps.cfg")
        subprocess.run(["ir-keytable", "-s", _rc_sysdev() or "rc0", "-c", "-w", KEYMAP], check=True)
        print(f"Saved {KEYMAP}; it loads at every boot. The FS42 remote controller service reads the remote now.")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
