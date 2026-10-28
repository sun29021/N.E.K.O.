"""App control (buttons/menus inside apps): risk levels and the windows/fields it must never touch."""

import os
import unittest

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko import automation
from neko.core.errors import PermissionDeniedError
from neko.core.types import RiskLevel
from neko.tools import pc


class RiskTests(unittest.TestCase):
    def test_levels(self):
        r = automation._risk
        self.assertEqual(r({"action": "list"}), RiskLevel.READ_ONLY)
        self.assertEqual(r({"action": "read", "target": "display"}), RiskLevel.READ_ONLY)
        self.assertEqual(r({"action": "click", "target": "Seven"}), RiskLevel.LOW)
        self.assertEqual(r({"action": "menu", "target": "View > Zoom in"}), RiskLevel.LOW)
        self.assertEqual(r({"action": "fill", "target": "Search"}), RiskLevel.MATERIAL)
        for word in ("Delete", "Send", "Pay now", "Buy", "Uninstall", "Sign out", "File > Empty trash", "Submit"):
            self.assertEqual(r({"action": "click", "target": word}), RiskLevel.HIGH, word)

    def test_registered_with_verifier(self):
        n = build_test_neko(temp_dir(), FakeProvider(), tools={"computer_control_enabled": True})
        self.addCleanup(n.shutdown)
        spec = n.tools.get("app_control")
        self.assertIsNotNone(spec.verifier)
        self.assertEqual(spec.effective_risk({"action": "click", "target": "Delete account"}), RiskLevel.HIGH)


class FakeWin:
    def __init__(self, title):
        self.title = title

    def window_text(self):
        return self.title


class FakeDesktop:
    def window(self, handle):
        return FakeWin("x")


class ProtectedWindowTests(unittest.TestCase):
    def setUp(self):
        old_desk, old_find = automation._desktop, pc.find_window
        self.addCleanup(setattr, automation, "_desktop", old_desk)
        self.addCleanup(setattr, pc, "find_window", old_find)
        automation._desktop = FakeDesktop

    def test_security_and_own_windows_refused(self):
        for title in ("User Account Control", "Windows Security", "N.E.K.O. needs your approval",
                      "Enter your password", "N.E.K.O. Command Center"):
            pc.find_window = lambda name, t=title: (1, t)
            with self.assertRaises(PermissionDeniedError, msg=title):
                automation.find_app_window("anything")

    def test_own_process_refused(self):
        import ctypes

        pc.find_window = lambda name: (1, "Some window")
        old = ctypes.windll.user32.GetWindowThreadProcessId
        self.addCleanup(setattr, ctypes.windll.user32, "GetWindowThreadProcessId", old)

        def own_pid(hwnd, ref):
            ref._obj.value = os.getpid()
            return 1
        ctypes.windll.user32.GetWindowThreadProcessId = own_pid
        with self.assertRaises(PermissionDeniedError):
            automation.find_app_window("some window")


class PasswordTests(unittest.TestCase):
    def test_password_fields_never_filled(self):
        class Field:
            class element_info:  # noqa: N801
                control_type = "Edit"

                class element:  # noqa: N801
                    CurrentIsPassword = True

            def window_text(self):
                return "Password"

            def is_visible(self):
                return True

            def set_edit_text(self, text):
                raise AssertionError("typed into a password field")

        class Win:
            def descendants(self):
                return [Field()]

        old = automation.find_app_window
        self.addCleanup(setattr, automation, "find_app_window", old)
        automation.find_app_window = lambda name: (Win(), "Login")
        for action in ("fill", "read"):
            with self.assertRaises(PermissionDeniedError):
                automation._run({"action": action, "target": "password", "text": "x", "window": ""}, None)


if __name__ == "__main__":
    unittest.main()
