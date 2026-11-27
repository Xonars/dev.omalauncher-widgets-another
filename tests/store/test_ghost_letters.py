import importlib.util
import json
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "local/phone-widgets/ghost-letters"
spec = importlib.util.spec_from_file_location("ghost_letters_game", SOURCE / "game.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
Game = mod.Game

class GhostLettersRules(unittest.TestCase):
    def test_roles_and_rounds(self):
        for total in range(4, 13):
            g = Game.new("classic", total, 1, False, seed=total)
            self.assertFalse(g.marked)
            self.assertEqual(len(g.role_ids("accomplice")), 2 if total >= 10 else int(total >= 7))
            self.assertEqual(len(g.role_ids("witness")), int(total >= 7))
            self.assertEqual(len(g.role_ids("expert")), int(total >= 10))
            self.assertEqual(g.d["rounds"], 5 if total == 4 else 4 if total <= 7 else 3 if total <= 10 else 2)

    def test_optional_marks(self):
        for marked in (False, True):
            g = Game.new("classic", 4, 1, True, marked=marked, seed=1)
            g.d["truth"] = [r[0] for r in g.d["board"]]
            for pid in range(4):
                g.refill(pid)
            for pid in range(1, 4):
                g.post(pid, g.d["players"][pid]["hand"][0], None)
            mail = g.d["mail"][:]
            hand = g.d["players"][0]["hand"][:]
            g.publish(mail[:2] if not marked else mail[0], mail[1] if marked else None, hand[0])
            self.assertEqual(len(g.d["archive"][0]), 1)
            self.assertEqual(len(g.d["letters"][0]["echo"]), 1 if marked else 2)
            self.assertEqual(any(c.get("mark") for c in g.letter_cards(g.d["letters"][0])), marked)
            self.assertEqual(len(g.d["players"][0]["hand"]), 5)

    def test_coop_duel(self):
        g = Game.new("coop", 2, 2, True, seed=1)
        self.assertEqual(g.role_ids("killer"), [])
        while g.phase == "role":
            g.submit({})
        g.advance()
        self.assertEqual(g.actor, 0)
        g.submit({str(i): row[0] for i,row in enumerate(g.d["board"])})
        g.submit({})
        g.advance()
        hand = g.d["players"][g.actor]["hand"][:]
        g.submit({"send":hand[0], "send2":hand[1]})
        self.assertEqual(g.phase, "sort")
        self.assertEqual(len(g.d["mail"]), 2)
        ghost = g.d["players"][0]["hand"][:]
        g.submit({"echo":g.d["mail"][:], "seal":ghost[0], "seal2":ghost[1]})
        self.assertEqual(len(g.view_letter_cards()), 4)
        self.assertEqual(len(g.d["players"][0]["hand"]), 5)

    def test_individual_winners(self):
        g = Game.new("classic", 10, 1, False, seed=3)
        a,b = g.role_ids("accomplice")
        g.d["excluded"] = [a]
        g.d["solved"] = False
        g.end()
        self.assertNotIn(a, g.d["winners"])
        self.assertIn(b, g.d["winners"])

    def test_knowledge_isolated(self):
        g = Game.new("classic", 10, 1, False, seed=12)
        pid = g.role_id("detective")
        g.d["truth"] = [row[0] for row in g.d["board"]]
        first = g.player_knowledge(pid)
        score = g.theories(pid, 0, "vote")
        g.d["truth"] = [row[1] for row in g.d["board"]]
        g.d["archive"] = [[1, 2, 3]]
        self.assertEqual(first, g.player_knowledge(pid))
        self.assertEqual(score, g.theories(pid, 0, "vote"))
        self.assertFalse(first["truth"])
        self.assertIsNone(first["killer"])
        self.assertEqual(first["allies"], [])

    def test_card_associations_and_stable_ids(self):
        names = {c["name"]: c["id"] for c in mod.CARDS}
        for line, card in zip((SOURCE / "deck.txt").read_text().splitlines(), mod.CARDS):
            self.assertEqual(line.split("|")[0], card["name"])
        for a,b in (("Зонт", "Гроза"), ("Крыша", "Стена"), ("Фартук", "Зонт"), ("Батарея", "Гроза")):
            self.assertGreater(mod.affinity(names[a], names[b]), 0)
            self.assertEqual(mod.affinity(names[a], names[b]), mod.affinity(names[b], names[a]))

    def test_full_games(self):
        import random
        for total in range(2, 13):
            for marked in (False, True):
                for seed in range(4):
                    rng = random.Random(seed)
                    mode = "coop" if total < 4 else "classic"
                    ghost = seed % 2 == 0
                    g = Game.new(mode, total, 1, ghost, marked=marked,
                                 difficulty=("easy", "normal", "hard")[seed % 3], seed=seed)
                    for step in range(500):
                        g.view()
                        if g.phase == "result":
                            break
                        if g.actor is None:
                            g.advance()
                            continue
                        picks = {}
                        for group in g.groups():
                            if group["required"]:
                                options = [o["value"] for o in group["options"]]
                                if group["key"] == "send2":
                                    options.remove(picks["send"])
                                picks[group["key"]] = rng.choice(options)
                            elif group["key"] == "echo":
                                picks["echo"] = [o["value"] for o in group["options"]] if group["multiple"] else group["options"][0]["value"]
                        g.submit(picks)
                    else:
                        self.fail(f"Stuck game: {total}, {marked}, {seed}, {g.phase}")
                    self.assertTrue(g.d["winner"])
                    self.assertEqual(g.d["round"], g.d["rounds"])
                    for note in g.d["history"]:
                        if not g.d["players"][note["pid"]]["local"] and note.get("claim") is not None:
                            self.assertTrue(note.get("speech"))

    def test_package_matches_source(self):
        row = next(x for x in json.loads((ROOT / "store-collection.json").read_text()) if x["source"] == "ghost-letters.owl")
        with zipfile.ZipFile(ROOT / row["resources"]) as z:
            for name in ("game.py", "deck.txt", "deck.json"):
                self.assertEqual(z.read("widgets/ghost-letters/" + name), (SOURCE / name).read_bytes())

if __name__ == "__main__":
    unittest.main()
