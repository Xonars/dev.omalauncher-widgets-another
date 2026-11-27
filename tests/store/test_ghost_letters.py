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

    def test_ghost_listens_to_public_versions(self):
        for difficulty in ("normal", "hard"):
            g = Game.new("classic", 6, 1, False, difficulty=difficulty, seed=9)
            g.d["truth"] = [row[0] for row in g.d["board"]]
            g.d["round"] = 2
            before = g.ghost_priorities(g.ghost_context())
            wrong = g.d["board"][2][1]
            for pid in range(1, 6):
                g.d["history"].append(dict(pid=pid, round=1, leads={"0": g.d["truth"][0],
                    "1": g.d["truth"][1], "2": wrong}, suspect=None, claim=None, tests=[]))
            context = g.ghost_context()
            weights = g.ghost_priorities(context)
            self.assertGreater(weights[2], before[2])
            self.assertGreater(weights[2], weights[0])
            self.assertEqual(context["public"][2][wrong], 1.0)
            # The ghost only uses the public record, not private hands or unpublished plans.
            for pid in range(1, 6):
                g.d["players"][pid]["hand"] = [pid]
            self.assertEqual(context, g.ghost_context())

    def test_ghost_projection_and_easy_policy(self):
        for difficulty in ("easy", "normal", "hard"):
            g = Game.new("classic", 6, 1, False, difficulty=difficulty, seed=157814185689306)
            g.d["truth"] = [row[0] for row in g.d["board"]]
            for pid in range(6):
                g.refill(pid)
            hand = g.d["players"][0]["hand"][:]
            context = g.ghost_context()
            cid = hand[0]
            before = [dict(row) for row in context["scores"]]
            g.ghost_apply_hint(context, cid)
            for i, row in enumerate(g.d["board"]):
                for c in row:
                    self.assertAlmostEqual(context["scores"][i][c],
                        before[i][c] + mod.hint_signal(g.d["board"], c, i, cid))
            g.enable_analytics()
            g.choose_ghost_letters([], hand)
            event = g.d["analytics"]["events"][-1]
            self.assertEqual(event["kind"], "bot_ghost")
            self.assertEqual("priorities" in event["decisions"][0], difficulty != "easy")

    def test_suspicion_is_explainable(self):
        g = Game.new("classic", 6, 1, False, seed=17)
        pid = g.role_id("detective")
        target = next(i for i in range(1, 6) if i != pid)
        factors = g.suspicion_factors(pid, target)
        self.assertAlmostEqual(sum(factors.values()), g.suspicion(pid, target))
        self.assertIn("evidence_conflict", factors)
        self.assertIn("claim_conflict", factors)

    def test_social_deduction_uses_time_and_persistence(self):
        from unittest.mock import patch
        g = Game.new("classic", 6, 1, False, difficulty="normal", seed=42)
        pid = g.role_id("detective")
        target, other = [i for i in range(1, 6) if i != pid][:2]
        right, wrong = g.d["board"][0][:2]
        g.d["round"] = 3
        def statement(who, number, card):
            return dict(pid=who, round=number, leads={"0": card},
                        suspect=None, claim=None, tests=[])
        g.d["history"] = [statement(target, n, wrong) for n in (1, 2, 3)]
        g.d["history"] += [statement(other, 1, wrong), statement(other, 2, right),
                           statement(other, 3, right)]
        # In round one nothing distinguished either card; later evidence is strong.
        def score(knowledge, cid, category):
            return float(knowledge["round"] >= 2 and cid == right)
        with patch.object(mod, "evidence_score", side_effect=score):
            persistent = g.suspicion_factors(pid, target)
            revised = g.suspicion_factors(pid, other)
        self.assertGreater(persistent["persistence"], 0)
        self.assertGreater(persistent["evidence_conflict"], revised["evidence_conflict"])
        self.assertEqual(revised["evidence_conflict"], 0)
        self.assertLess(revised["revision"], 0)
        self.assertGreater(sum(persistent.values()), sum(revised.values()))
        self.assertLessEqual(persistent["noise"], 0.95 * 0.22)

    def test_social_deduction_does_not_read_private_roles_or_mail(self):
        g = Game.new("classic", 6, 1, False, difficulty="hard", seed=42)
        pid = g.role_id("detective")
        target = next(i for i in range(1, 6) if i != pid)
        before = g.suspicion_factors(pid, target)
        g.d["players"][target]["role"] = "killer"
        g.d["players"][target]["hand"] = [0, 1, 2]
        g.d["truth"] = [row[1] for row in g.d["board"]]
        self.assertEqual(before, g.suspicion_factors(pid, target))

    def test_public_evidence_snapshot_excludes_future_and_private_mail(self):
        g = Game.new("classic", 6, 1, False, difficulty="normal", seed=42)
        pid = g.role_id("detective")
        knowledge = g.player_knowledge(pid)
        knowledge["letters"] = [dict(round=n, hints=[(0, 1)]) for n in (0, 1, 2)]
        knowledge["own_mail"] = [dict(round=1, missing=[1])]
        snapshot = mod.public_evidence_at(knowledge, 1)
        self.assertEqual([letter["round"] for letter in snapshot["letters"]], [0, 1])
        self.assertEqual(snapshot["own_mail"], [])
        self.assertEqual(snapshot["round"], 1)
        self.assertEqual(len(knowledge["letters"]), 3)

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

    def test_atmospheric_assets_are_public_and_complete(self):
        keys = {"ghost", "detective", "killer", "accomplice", "witness", "expert", "back", "table"}
        public = mod.public_view(None)["atmosphere"]
        self.assertEqual(set(public), keys)
        g = Game.new("classic", 5, 1, False, seed=2)
        self.assertEqual(mod.public_view(g)["atmosphere"], public)
        for key, path in public.items():
            self.assertEqual(Path(path), SOURCE / "assets/atmosphere" / (key + ".webp"))

    def test_analytics_does_not_change_seeded_games(self):
        import random
        for mode,total,ghost in (("classic",5,False),("classic",10,False),("coop",2,True),("coop",4,False)):
            for seed in (1,7):
                first=Game.new(mode,total,1,ghost,seed=seed)
                second=Game(json.loads(json.dumps(first.d)))
                second.enable_analytics()
                rng=random.Random(seed)
                for step in range(500):
                    self.assertEqual(first.d,{k:v for k,v in second.d.items() if k!="analytics"})
                    self.assertNotIn("analytics",mod.public_view(second))
                    if first.phase=="result":
                        break
                    if first.actor is None:
                        first.advance()
                        second.advance()
                        continue
                    picks={}
                    for group in first.groups():
                        if group["required"]:
                            options=[o["value"] for o in group["options"]]
                            if group["key"]=="send2":
                                options.remove(picks["send"])
                            picks[group["key"]]=rng.choice(options)
                    if first.phase=="mail":
                        picks["intent"]=first.d["board"][0][0]
                    first.submit(picks.copy())
                    second.submit(picks.copy())
                else:
                    self.fail("Game did not finish")
                events=second.d["analytics"]["events"]
                self.assertEqual([e["seq"] for e in events],list(range(1,len(events)+1)))
                self.assertTrue(any(e["kind"]=="vote_result" for e in events))
                for event in events:
                    knowledge=event.get("knowledge",{})
                    if knowledge.get("role")=="detective":
                        self.assertFalse(knowledge["truth"])
                        self.assertIsNone(knowledge["killer"])

    def test_completed_archive_and_export_privacy(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            g=Game.new("classic",5,1,False,seed=4)
            g.enable_analytics()
            mod.archive_game(g,root/"games")
            self.assertEqual(mod.archived_games(root/"games"),[])
            g.d["truth"]=[row[0] for row in g.d["board"]]
            g.d["decided"]={str(i):cid for i,cid in enumerate(g.d["truth"])}
            g.d["successes"]=3
            g.d["solved"]=True
            g.d["notebooks"]={"1":{"text":"PRIVATE-NOTE"}}
            g.d["letters"]=[dict(round=0,echo=[g.d["board"][1][1]],silence=[],seal=None,missing=0,comments={"echo":"PRIVATE-COMMENT"})]
            g.end()
            mod.archive_game(g,root/"games")
            mod.archive_game(g,root/"games")
            records=mod.archived_games(root/"games")
            self.assertEqual(len(records),1)
            self.assertNotIn("notebooks",records[0])
            self.assertEqual(mod.statistics(records)["correct"],3)
            self.assertEqual(mod.filter_records(records,{"players":12}),[])
            path=mod.export_analysis(records,root/"export")
            with zipfile.ZipFile(path) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(json.loads(z.read("manifest.json"))["games"],1)
                payload=z.read("games/"+g.d["id"]+".json")
                self.assertNotIn(b"PRIVATE-NOTE",payload)
                self.assertNotIn(b"PRIVATE-COMMENT",payload)
                self.assertEqual(json.loads(payload)["capture"]["schema"],1)
                events=[json.loads(line) for line in z.read("events/"+g.d["id"]+".jsonl").splitlines()]
                self.assertTrue(any(e["kind"]=="result" for e in events))

    def test_dynamic_flow_stops_at_public_reveal_or_local_input(self):
        for ghost in (False,True):
            g=Game.new("classic",5,1,ghost,seed=3)
            g.d["truth"]=[row[0] for row in g.d["board"]]
            for pid in range(5):
                g.refill(pid)
            g.start_round()
            mod.advance_automatically(g)
            self.assertIn(g.phase,("mail","sort","reveal"))
            self.assertNotEqual(g.phase,"intro")
            if g.phase in ("mail","sort"):
                self.assertIsNotNone(g.actor)
        g=Game.new("classic",5,2,False,seed=3)
        g.set_phase("intro")
        mod.advance_automatically(g)
        self.assertEqual(g.phase,"intro")

    def test_simulation_is_deterministic(self):
        for difficulty in ("easy", "normal", "hard"):
            a = mod.simulate_game(42, difficulty)
            b = mod.simulate_game(42, difficulty)
            self.assertEqual(a.d["decided"], b.d["decided"])
            self.assertEqual(a.d["winner"], b.d["winner"])
            self.assertEqual(a.d["local"], [])
            self.assertEqual(a.d["round"], a.d["rounds"])

    def test_verified_claim_conflict_uses_only_own_receipt(self):
        g = Game.new("classic", 6, 1, False, seed=42)
        pid = g.role_id("detective")
        target, observer = [i for i in range(1, 6) if i != pid][:2]
        g.d["round"] = 1
        g.d["history"] = [dict(pid=target, round=1, leads={}, suspect=None,
                                 claim=12, tests=[])]
        g.d["mail_log"] = {"1": {str(pid): {"sent": 12, "sent_cards": [12]}}}
        self.assertGreater(g.suspicion_factors(pid, target)["verified_conflict"], 0)
        self.assertEqual(g.suspicion_factors(observer, target)["verified_conflict"], 0)

    def test_single_test_is_not_an_endorsed_lead(self):
        g = Game.new("classic", 6, 1, False, seed=42)
        pid = g.d["local"][0]
        g.d["round"] = 1
        g.d["speakers"] = [pid]
        g.set_phase("note", [pid])
        card = g.d["board"][0][0]
        g.submit({"lead": [card]})
        note = g.d["history"][0]
        self.assertEqual(note["tests"], [card])
        self.assertEqual(note["leads"], {})

    def test_arrest_ballot_excludes_self(self):
        g = Game.new("classic", 6, 1, False, seed=42)
        pid = g.d["local"][0]
        g.start_vote(["suspect"])
        options = g.ballot_groups()[0]["options"]
        self.assertNotIn(pid, [o["value"] for o in options])

    def test_package_matches_source(self):
        row = next(x for x in json.loads((ROOT / "store-collection.json").read_text()) if x["source"] == "ghost-letters.owl")
        with zipfile.ZipFile(ROOT / row["resources"]) as z:
            for name in ("game.py", "deck.txt", "deck.json"):
                self.assertEqual(z.read("widgets/ghost-letters/" + name), (SOURCE / name).read_bytes())
            assets = [f"assets/cards/{i:03d}.webp" for i in range(131)]
            self.assertEqual(len(list((SOURCE / "assets/cards").glob("*.webp"))), 131)
            assets += [f"assets/atmosphere/{key}.webp" for key in ("ghost", "detective", "killer", "accomplice", "witness", "expert", "back", "table")]
            for name in assets + ["assets/manifest.json", "assets/atmosphere/manifest.json"]:
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
