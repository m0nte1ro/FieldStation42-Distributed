from types import SimpleNamespace

import pytest

from client.platform import argon_remote
from client.platform.argon_remote import BUTTONS, add_overlay, add_rc_map, keymap_toml, learn

EV_KEY, EV_MSC, MSC_SCAN = 0x01, 0x04, 0x04


def _scan(code):
    return SimpleNamespace(type=EV_MSC, code=MSC_SCAN, value=code)


class FakeReceiver:
    """The case's IR receiver: one NEC scancode per press, repeated while the button is held."""

    def __init__(self, presses):
        self.presses = presses

    def read_loop(self):
        for code in self.presses:
            yield SimpleNamespace(type=EV_KEY, code=0, value=1)  # unmapped key noise
            yield _scan(code)


def test_every_button_does_what_the_fs42_remote_expects():
    # the keymap turns each button into a key client/input/remote_controller.py already understands
    assert dict(BUTTONS) == {
        "UP": "KEY_UP", "DOWN": "KEY_DOWN", "LEFT": "KEY_LEFT", "RIGHT": "KEY_RIGHT", "OK": "KEY_ENTER",
        "HOME": "KEY_HOME", "BACK": "KEY_BACKSPACE", "MENU": "KEY_V", "PLAY/PAUSE": "KEY_A", "MUTE": "KEY_M",
        "VOL+": "KEY_RIGHT", "VOL-": "KEY_LEFT",
    }


def test_learning_asks_for_each_button_and_keeps_its_scancode():
    codes = [0xCA11 + i for i in range(len(BUTTONS))]
    asked = []
    learned = learn(FakeReceiver(codes), ask=asked.append)
    assert asked == [name for name, _ in BUTTONS]
    assert learned == dict(zip((name for name, _ in BUTTONS), codes))


def test_a_held_button_or_a_repeat_is_not_taken_for_the_next_one():
    # holding UP repeats its code; the next button must be a different one
    codes = [0xCA11 + i for i in range(len(BUTTONS))]
    presses = [codes[0], codes[0], codes[0]] + codes[1:]
    assert list(learn(FakeReceiver(presses), ask=lambda name: None).values()) == codes


def test_the_keymap_is_an_nec_table_for_ir_keytable():
    toml = keymap_toml({"UP": 0x807F, "VOL+": 0x80FF})
    assert toml == ('[[protocols]]\nname = "argon"\nprotocol = "nec"\n[protocols.scancodes]\n'
                    '0x807f = "KEY_UP"\n0x80ff = "KEY_RIGHT"\n')


def test_the_receiver_overlay_is_added_once_for_every_pi(tmp_path):
    config = tmp_path / "config.txt"
    config.write_text("[cm4]\notg_mode=1\n")
    assert add_overlay(str(config)) is True
    assert add_overlay(str(config)) is False
    # appended under [all]: after a [cm4] section it would only apply to a CM4
    assert config.read_text() == "[cm4]\notg_mode=1\n\n[all]\ndtoverlay=gpio-ir,gpio_pin=23\n"


def test_the_keymap_loads_at_every_boot(tmp_path):
    rc_maps = tmp_path / "rc_maps.cfg"
    rc_maps.write_text("# driver table file\n* rc-rc6-mce rc6_mce.toml\n")
    add_rc_map(str(rc_maps))
    add_rc_map(str(rc_maps))
    # first match wins, so the receiver's line goes before the catch-all
    assert rc_maps.read_text() == ("gpio_ir_recv * /etc/rc_keymaps/argon.toml\n"
                                   "# driver table file\n* rc-rc6-mce rc6_mce.toml\n")


def test_learning_needs_the_receiver(monkeypatch):
    monkeypatch.setattr(argon_remote, "find_receiver", lambda: None)
    with pytest.raises(SystemExit, match="setup"):
        argon_remote.main(["learn"])
