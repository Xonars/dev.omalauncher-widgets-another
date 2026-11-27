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

    def test_private_notebooks(self):
        g = Game.new("classic", 5, 2, False, seed=8)
        a,b = g.d["local"]
        self.assertIsNone(g.notebook_view())
        g.d["round"] = 1
        g.set_phase("mail", [a])
        key = str(g.d["board"][0][0])
        before = (g.phase, g.actor, g.d["rev"])
        g.save_notebook({"marks": {key:"likely"}, "suspects": {str(b):"likely"}, "text":"private A"})
        self.assertEqual(g.notebook_view()["text"], "private A")
        self.assertEqual(before, (g.phase, g.actor, g.d["rev"]))
        g.set_phase("mail", [b])
        self.assertEqual(g.notebook_view()["text"], "")
        g.save_notebook({"marks": {key:"unlikely"}, "text":"private B"})
        g.set_phase("mail", [a])
        self.assertEqual(g.notebook_view()["marks"][key], "likely")
        with self.assertRaises(ValueError):
            g.save_notebook({"marks": {"9999":"likely"}})
        g.set_phase("discussion")
        self.assertIsNone(g.notebook_view())
        self.assertIsNone(g.view()["notebook"])

    def test_solo_notebook_during_public_discussion(self):
        g = Game.new("classic", 4, 1, False, seed=3)
        g.d["round"] = 1
        g.set_phase("discussion")
        g.save_notebook({"text":"case notes"})
        self.assertEqual(g.view()["notebook"]["text"], "case notes")
        g.d["round"] = 2
        self.assertEqual(Game(json.loads(json.dumps(g.d))).notebook_view()["text"], "case notes")

    def test_history_uses_corresponding_round(self):
        g = Game.new("classic", 4, 1, False, marked=True, seed=3)
        card = g.d["board"][0][0]
        g.d["round"] = 2
        g.d["letters"] = [dict(round=1, echo=[card], silence=[], seal=None, missing=0),
                          dict(round=2, echo=[], silence=[], seal=None, missing=0)]
        n = dict(pid=1, leads={}, suspect=None, round=1, claim=card, tests=[], check=None, speech="old")
        g.d["history"] = [n]
        g.d["notes"] = [dict(n, round=2)]
        history = g.history_view()
        self.assertFalse(history[0]["entries"][0]["claim"]["opened"])
        self.assertTrue(history[1]["entries"][0]["claim"]["opened"])
        self.assertEqual(history[1]["entries"][0]["claim"]["mark"], "Эхо")

    def test_final_round_dialogue(self):
        g = Game.new("classic", 5, 1, False, seed=4)
        g.d["round"] = g.d["rounds"]
        pid = g.role_id("detective")
        k = g.player_knowledge(pid)
        k["profile"] = "strategist"
        cid = g.d["board"][0][0]
        g.d["letters"] = []
        speech = g.bot_speech(k, cid, [cid], {"0":cid})
        self.assertNotIn("в следующем раунде", speech)
        self.assertIn("голосовани", speech)

    def test_ghost_hints_and_shared_signal(self):
        g = Game.new("classic", 5, 1, False, seed=9)
        g.d["truth"] = [row[0] for row in g.d["board"]]
        for pid in range(5):
            g.refill(pid)
        sent = [g.d["players"][pid]["hand"][0] for pid in range(1,5)]
        hand = g.d["players"][0]["hand"]
        for marked in (False,True):
            g.d["marked"] = marked
            echo, silence, own, discard = g.choose_ghost_letters(sent, hand)
            self.assertTrue(set(echo) <= set(sent))
            self.assertTrue(set(own) <= set(hand))
            self.assertLessEqual(len(own),1)
            self.assertNotIn(discard,own)
            self.assertNotIn(silence,echo)
            if marked:
                self.assertLessEqual(len(echo),1)
            else:
                self.assertIsNone(silence)

    def test_knowledge_deduplicates_completed_discussion(self):
        g = Game.new("classic", 5, 1, False, seed=2)
        pid = g.role_id("detective")
        n = dict(pid=pid, leads={"0":g.d["board"][0][0]}, suspect=None,
                 round=1, claim=None, tests=[])
        g.d["history"] = [n]
        g.d["notes"] = [n.copy()]
        self.assertEqual(len(g.player_knowledge(pid)["notes"]),1)

    def test_card_gestures_have_one_owner(self):
        # Structural regression: the card renderer must not intercept gestures.
        # Actual Android dispatch still needs an on-device test.
        for path in (ROOT / "local/phone-widgets/ghost-letters.owl",
                     ROOT / "apps/xonars/ghost-letters/app.owl"):
            source = path.read_text()
            face = source.split("  component PlayingCard(", 1)[1].split("  component CategoryLabel(", 1)[0]
            self.assertNotIn("onTap:", face)
            self.assertNotIn("onLongPress:", face)
            for action, preview in (
                ("let current = get(choices, handAction, null)", "previewCard = option"),
                ("if canExplain { ghostNotes = remove(ghostNotes, section.key) }", "previewCard = option"),
                ("notebookMarks = set(notebookMarks, k,", "previewCard = clue"),
            ):
                before = source.split(action, 1)[0].rsplit("onTap:", 1)[0]
                self.assertIn(preview, before.split("onLongPress:", 1)[-1])

    def test_package_matches_source(self):
        row = next(x for x in json.loads((ROOT / "store-collection.json").read_text()) if x["source"] == "ghost-letters.owl")
        with zipfile.ZipFile(ROOT / row["resources"]) as z:
            for name in ("game.py", "deck.txt", "deck.json"):
                self.assertEqual(z.read("widgets/ghost-letters/" + name), (SOURCE / name).read_bytes())
            assets = [f"assets/cards/{i:03d}.webp" for i in range(131)]
            self.assertEqual(len(list((SOURCE / "assets/cards").glob("*.webp"))), 131)
            for name in assets + ["assets/manifest.json"]:
                data = (SOURCE / name).read_bytes()
                self.assertEqual(z.read("widgets/ghost-letters/" + name), data)
                if name.endswith(".webp"):
                    self.assertEqual(data[:4], b"RIFF")
                    self.assertEqual(data[8:12], b"WEBP")
            for cid in range(131):
                self.assertEqual(Path(mod.card_view(cid)["artwork"]), SOURCE / assets[cid])
            g = Game.new("classic", 5, 1, False, seed=2)
            self.assertTrue(all("artwork" not in p for p in g.people([1,2,3,4])))


if __name__ == "__main__":
    unittest.main()
