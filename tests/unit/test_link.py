"""Two Nekos linked over loopback: compare features, run a request on the other PC (its own approvals),
share skills, and refuse wrong keys / a switched-off link / addresses outside the tailnet."""

import json
import socket
import unittest

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.core.errors import ToolError
from neko.models.cloud import save_keys
from neko.phone.call import CallServer
from neko.phone.link import LinkClient, compare, parse_code
from neko.phone.service import PhoneService


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LinkTests(unittest.TestCase):
    def setUp(self):
        # "office" = the PC being used
        self.office = build_test_neko(temp_dir(), FakeProvider(responses=["office answer"]),
                                      app={"assistant_name": "Nova"})
        self.addCleanup(self.office.shutdown)
        self.office.settings.phone.link_server = True
        self.office.settings.phone.call_port = free_port()
        self.svc = PhoneService(self.office)
        self.server = CallServer(self.office, self.svc, voice=lambda: None)
        self.key = self.server.link.new_key()
        self.assertEqual(self.server.start(), "running")
        self.addCleanup(self.server.stop)
        self.url = f"http://127.0.0.1:{self.office.settings.phone.call_port}"
        # "laptop" = the PC asking
        self.laptop = build_test_neko(temp_dir(), FakeProvider(responses=["laptop answer"]))
        self.addCleanup(self.laptop.shutdown)
        self.laptop.settings.phone.link_url = self.url
        save_keys(self.laptop.settings.data_dir, {"link_key": self.key})

    def say(self, text):
        return self.laptop.coordinator.handle(text).text

    def test_compare_shows_differences(self):
        self.office.routines.store_skill("monthly sheet", [{"tool": "open_anything", "args": {"target": "excel"}}])
        r = self.say("what can the office PC do that you can't?")
        self.assertIn("Nova", r)
        self.assertIn("monthly sheet", r)

    def test_request_runs_on_the_other_pc(self):
        r = self.say("on the office PC, remind me in 2 hours to call the bank")
        self.assertIn("call the bank", r)
        self.assertEqual(len(self.office.routines.pending_reminders()), 1)   # set THERE
        self.assertEqual(self.laptop.routines.pending_reminders(), [])

    def test_approvals_happen_on_the_other_pc(self):
        asked = []
        self.office.policy.set_approval_handler(lambda req: (asked.append(req.tool), req.resolve(False)))
        self.say("on the office PC, publish the update")
        self.assertEqual(asked, [])  # internet is off there in tests: refused before even asking...
        self.office.settings.privacy.allow_network = self.office.policy.network_allowed = True
        self.say("on the office PC, publish the update")
        self.assertEqual(asked, ["publish_update"])   # ...and when it can, the office side asks its owner

    def test_skills_both_ways(self):
        self.office.routines.store_skill("print invoice", [{"tool": "open_anything", "args": {"target": "print"}}])
        self.assertIn("Copied the skill", self.say("get the skill print invoice from the office PC"))
        self.assertIsNotNone(self.laptop.routines.find_skill("print invoice"))
        self.laptop.routines.store_skill("tidy desk", [{"tool": "window_control", "args": {"name": "x",
                                                                                            "action": "minimize"}}])
        self.assertIn("Sent the skill", self.say("send the skill tidy desk to the office PC"))
        self.assertIsNotNone(self.office.routines.find_skill("tidy desk"))

    def test_wrong_key_and_switched_off(self):
        with self.assertRaises(ToolError):
            LinkClient(self.url, "wrong").call("/link/info")
        self.assertEqual(LinkClient(self.url, self.key).call("/link/info")["name"], "Nova")
        self.office.settings.phone.link_server = False
        with self.assertRaises(ToolError):
            LinkClient(self.url, self.key).call("/link/info")

    def test_call_key_never_opens_the_link_and_vice_versa(self):
        with self.assertRaises(ToolError):
            LinkClient(self.url, self.svc.state.call_key).call("/link/info")

    def test_not_connected_says_how(self):
        self.laptop.settings.phone.link_url = ""
        self.assertIn("Let my other PC connect", self.say("compare with the office PC"))

    def test_link_codes_must_point_into_the_tailnet(self):
        self.assertEqual(parse_code("neko-link:https://office.tail1234.ts.net:8443#abc")[1], "abc")
        for bad in ("neko-link:https://evil.example.com#abc", "https://office.tail1234.ts.net#abc", "hello"):
            with self.assertRaises(ToolError):
                parse_code(bad)

    def test_compare_text(self):
        mine = {"name": "Neko", "version": "0.9.1", "tools": ["a"], "programs": [], "skills": [], "models": ["x"]}
        theirs = {"name": "Nova", "version": "0.9.0", "tools": ["a", "b"], "programs": ["Print SOFT"], "skills": [],
                  "models": ["qwen3:14b"], "telegram": True}
        text = compare(mine, theirs)
        for want in ("I'm newer", "publish the update", "Print SOFT", "qwen3:14b", "Telegram"):
            self.assertIn(want, text)
        self.assertTrue(json.dumps(text))


if __name__ == "__main__":
    unittest.main()
