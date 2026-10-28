"""Auto-compacting conversations (rolling summary) and recall of things said long ago."""

import time
import unittest

from tests.helpers import FakeProvider, build_test_neko, temp_dir

from neko.core.types import ChatMessage, Role
from neko.orchestration import coordinator as coord


class CompactionTests(unittest.TestCase):
    def fill(self, n, conv, count):
        for i in range(count):
            n.conversations.add(conv, ChatMessage(Role.USER, f"message number {i} about topic{i}"))
            n.conversations.add(conv, ChatMessage(Role.ASSISTANT, f"answer number {i}"))
        # distinct, ordered times (Windows' clock can give many messages the same timestamp)
        n.db.execute("UPDATE messages SET created_at = 1000000 + rowid WHERE conversation_id=?", (conv,))

    def test_old_messages_fold_into_summary_and_leave_the_window(self):
        p = FakeProvider(responses=["- earlier: user talked about topic0 to topic24", "ok reply"])
        n = build_test_neko(temp_dir(), p)
        self.addCleanup(n.shutdown)
        conv = n.conversations.create()
        self.fill(n, conv, 25)  # 50 messages > keep 30 + batch 10
        pending = n.conversations.unsummarised(conv)
        n.coordinator._compact(conv, n.router.installed()[0], p, pending, coord.COMPACT_KEEP)
        self.assertIn("topic0", n.conversations.summary(conv))
        self.assertGreater(n.conversations.summary_upto(conv), 0)
        left = len(n.conversations.unsummarised(conv))  # (messages stored in the same instant may stay too)
        self.assertEqual(left, coord.COMPACT_KEEP)
        history = n.conversations.history_since_summary(conv)
        self.assertNotIn("message number 0 about topic0", [m.content for m in history])
        # the summary goes along with the next request
        n.coordinator.handle("and what's next?", conversation_id=conv)
        sent = "\n".join(m.content for m in p.requests[-1].messages)
        self.assertIn("earlier: user talked about topic0", sent)

    def test_compaction_runs_in_background_only_when_needed(self):
        p = FakeProvider(responses=["hi"])
        n = build_test_neko(temp_dir(), p)
        self.addCleanup(n.shutdown)
        conv = n.conversations.create()
        self.fill(n, conv, 5)
        started = []
        n.coordinator._compact = lambda *a: started.append(a)
        n.coordinator._schedule_compaction(conv, None, p, crowded=False)
        time.sleep(0.1)
        self.assertEqual(started, [])  # 10 messages: nothing to fold yet


class RecallTests(unittest.TestCase):
    def test_finds_old_messages_from_other_conversations(self):
        p = FakeProvider(responses=["You said your sister studies medicine in Dhaka."])
        n = build_test_neko(temp_dir(), p)
        self.addCleanup(n.shutdown)
        old = n.conversations.create()
        n.conversations.add(old, ChatMessage(Role.USER, "my sister studies medicine in Dhaka"))
        new = n.conversations.create()
        n.coordinator.handle("what did I tell you about my sister earlier?", conversation_id=new)
        sent = "\n".join(m.content for m in p.requests[0].messages)
        self.assertIn("my sister studies medicine in Dhaka", sent)
        self.assertIn("UNTRUSTED", sent.upper())  # fenced, like any outside text

    def test_no_recall_for_ordinary_questions(self):
        p = FakeProvider(responses=["Paris."])
        n = build_test_neko(temp_dir(), p)
        self.addCleanup(n.shutdown)
        old = n.conversations.create()
        n.conversations.add(old, ChatMessage(Role.USER, "the capital of France came up in class"))
        n.coordinator.handle("what is the capital of France?", conversation_id=n.conversations.create())
        sent = "\n".join(m.content for m in p.requests[0].messages)
        self.assertNotIn("came up in class", sent)


if __name__ == "__main__":
    unittest.main()
