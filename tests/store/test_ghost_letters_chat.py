import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ghost_chat_game", ROOT / "local/phone-widgets/ghost-letters/game.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GhostChatTests(unittest.TestCase):
    def game(self):
        g = mod.Game.new("classic", 5, 1, False, seed=37)
        g.d["round"] = 1
        g.d["truth"] = [r[0] for r in g.d["board"]]
        g.set_phase("discussion")
        return g

    def test_chat_addressed_persistent_and_public(self):
        g = self.game()
        owner = g.chat_owner()
        target = next(p for p in g.d["turn_order"] if p != owner)
        card = g.d["board"][0][0]
        text = "Почему " + mod.CARDS[card]["name"] + "?"
        g.send_chat(dict(target=target, text=text))
        messages = g.chat_view()["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["text"], text)
        self.assertEqual(messages[1]["player"], g.name(target))
        self.assertIn(mod.CARDS[card]["name"], messages[1]["text"])
        self.assertEqual(g.chat_view()["remaining"], 5)
        restored = mod.Game(json.loads(json.dumps(g.d)))
        self.assertEqual(restored.chat_view(), g.chat_view())
        self.assertEqual(g.phase, "discussion")

    def test_invalid_or_out_of_phase_chat(self):
        g = self.game()
        for payload in [dict(text=" "), dict(text="x"*401), dict(text="test",target=0),
                        dict(text="test",target=g.chat_owner()), dict(text="test",target=True)]:
            with self.assertRaises(ValueError):
                g.send_chat(payload)
        g.set_phase("reveal")
        with self.assertRaises(ValueError):
            g.send_chat(dict(text="test"))

    def test_chat_bounded_and_no_accusation_from_free_text(self):
        g = self.game()
        owner = g.chat_owner()
        target = next(p for p in g.d["turn_order"] if p != owner)
        before = g.suspicion_factors(target, owner)
        for _ in range(6):
            g.send_chat(dict(text="Ты убийца!", target=target))
        self.assertEqual(g.suspicion_factors(target, owner), before)
        self.assertEqual(g.chat_view()["remaining"], 0)
        with self.assertRaises(ValueError):
            g.send_chat(dict(text="ещё",target=target))
        g.d["round"] += 1
        self.assertEqual(g.chat_view()["remaining"], 6)

    def test_repeat_conflict_requires_confident_public_statements(self):
        g = self.game()
        observer = g.chat_owner()
        target = next(p for p in g.d["turn_order"] if p != observer)
        truth, rival = g.d["board"][0][:2]
        g.d["round"] = 3
        g.d["exchanges"] = {"1": [dict(kind="theory", target=target, key="0", rival=rival, gap=0.8, supported=False, answer="Не уверен")]}
        g.d["history"] = [dict(pid=target,round=n,leads={"0":rival},stance=2,
                              claim=None,tests=[],suspect=None) for n in (1,2,3)]
        with patch.object(mod,"evidence_score",side_effect=lambda k,c,i: 2.0 if c==truth else 0.0):
            self.assertEqual(len(g.repeated_public_conflicts(g.player_knowledge(observer),target)),1)
            g.d["history"][1]["stance"] = 0
            self.assertEqual(g.repeated_public_conflicts(g.player_knowledge(observer),target),[])

if __name__ == "__main__":
    unittest.main()
