#!/usr/bin/env python3
"""Local game state and computer players for the OWL app."""

import argparse
from collections import Counter
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "ghost-letters"
CATEGORIES = ("Мотив", "Место", "Способ")
MARKS = {"echo": "Эхо", "silence": "Тишина", "seal": "Печать"}
MODES = {
    "classic": "Классическая партия",
    "coop": "Кооператив",
    "killer": "Один убийца",
    "accomplice": "Убийца и сообщник",
    "witness": "Убийца и свидетель",
    "expert": "Убийца и эксперт",
}
ROLES = {
    "ghost": ("Призрак", "Передавай ассоциации через почту. Секретные улики увидишь перед первым письмом."),
    "killer": ("Убийца", "Назначь по одной истинной улике в каждой категории. Путай расследование письмами, версиями и голосами."),
    "accomplice": ("Сообщник", "Узнаешь убийцу и истинные улики. Помогай уводить дело по ложному следу."),
    "witness": ("Свидетель", "Ты знаешь убийцу. Наводи на него подозрения осторожно: в финале он может раскрыть твою роль."),
    "expert": ("Эксперт", "Ты узнаешь истинные улики, но не имя убийцы. В финале убийца может раскрыть твою роль."),
    "detective": ("Детектив", "Проверяй версии письмами и по подсказкам восстанови дело."),
}
NAMES = ("Сова", "Астра", "Север", "Лис", "Ива", "Риф", "Мята", "Иней", "Штиль", "Руна", "Клён")
CARDS = []
for line in (HERE / "deck.txt").read_text(encoding="utf-8").splitlines():
    name, glyph, main, secondary = line.split("|")
    CARDS.append({"id": len(CARDS), "name": name, "glyph": glyph, "main": main, "secondary": secondary})


def card_view(card_id, **fields):
    card = CARDS[card_id]
    return dict(value=card_id, label=card["name"], glyph=card["glyph"], **fields)


def group(key, label, options, required=True, *, multiple=False):
    return dict(key=key, label=label, options=options, required=required, multiple=multiple)


def clue_list(record, plural, singular):
    if plural in record:
        return record[plural]
    clue = record.get(singular)
    return [] if clue is None else [clue]


def association(left, right):
    a, b = CARDS[left], CARDS[right]
    if a["main"] == b["main"]:
        return 3, a["main"]
    if a["main"] == b["secondary"]:
        return 2, a["main"]
    if a["secondary"] == b["main"]:
        return 2, b["main"]
    if a["secondary"] == b["secondary"]:
        return 1, a["secondary"]
    return 0, None


def affinity(left, right):
    return association(left, right)[0]


class Game:
    def __init__(self, data):
        self.d = data

    @classmethod
    def new(cls, mode, total, humans, human_ghost, *, marked=False, seed=None):
        if (mode not in MODES or type(total) is not int or type(humans) is not int
                or not (2 if mode == "coop" else 4) <= total <= 12 or not 1 <= humans <= total
                or type(marked) is not bool or type(human_ghost) is not bool
                or (not human_ghost and humans == total)):
            raise ValueError("Неверный состав стола.")
        seed = random.SystemRandom().randrange(1 << 48) if seed is None else seed
        rng = random.Random(seed)
        if mode == "coop":
            roles = []
        elif mode == "classic":
            roles = ["killer"]
            if total >= 7:
                roles += ["accomplice", "witness"]
            if total >= 10:
                roles += ["accomplice", "expert"]
        else:
            roles = ["killer"] + ([mode] if mode != "killer" else [])
        roles += ["detective"] * (total - len(roles) - 1)
        rng.shuffle(roles)
        nicknames = list(NAMES)
        rng.shuffle(nicknames)
        players = [dict(name="Призрак", role="ghost", local=None, hand=[])]
        players += [dict(name=nicknames[i], role=role, local=None, hand=[])
                    for i, role in enumerate(roles)]
        local = rng.sample(list(range(1, total)), humans - int(human_ghost))
        if human_ghost:
            local.append(0)
        rng.shuffle(local)
        for number, pid in enumerate(local, 1):
            players[pid]["local"] = number
        deck = list(range(len(CARDS)))
        rng.shuffle(deck)
        board = []
        for _ in CATEGORIES:
            if mode in ("classic", "coop"):
                board.append([deck.pop() for _ in range(4)])
                continue
            row, themes = [], set()
            for cid in tuple(deck):
                main = CARDS[cid]["main"]
                if main not in themes:
                    row.append(cid)
                    themes.add(main)
                    deck.remove(cid)
                    if len(row) == 4:
                        break
            board.append(row)
        rounds = 5 if total <= 4 else 4 if total <= 7 else 3 if total <= 10 else 2
        return cls(dict(
            id=uuid.uuid4().hex, rev=0, seed=seed, mode=mode, phase="role", queue=local[:],
            players=players, local=local, board=board, deck=deck, discard=[], truth=[],
            schema=2, marked=marked, sequential=True, exposed_role=None, winners=[],
            rounds=rounds, round=0, letters=[], mail=[], notes=[], history=[], archive=[],
            ballots={}, counts=[], decided={}, tie=[], pass_no=0, arrested=None,
            excluded=[], successes=0, solved=False, winner="", exposed=None,
        ))

    @property
    def phase(self):
        return self.d["phase"]

    @property
    def actor(self):
        return self.d["queue"][0] if self.d["queue"] else None

    def role_id(self, role):
        return next((i for i, p in enumerate(self.d["players"]) if p["role"] == role), None)

    def role_ids(self, role):
        return [i for i, p in enumerate(self.d["players"]) if p["role"] == role]

    @property
    def marked(self):
        return self.d.get("marked", True)

    @property
    def cooperative(self):
        return self.d["mode"] == "coop"

    @property
    def duel(self):
        return len(self.d["players"]) == 2

    def name(self, pid):
        return self.d["players"][pid]["name"]

    def noise(self, purpose, *parts):
        return random.Random(repr((self.d["seed"], self.d["round"], purpose, parts))).random()

    def set_phase(self, phase, queue=()):
        self.d["phase"] = phase
        self.d["queue"] = list(queue)

    def refill(self, pid):
        player = self.d["players"][pid]
        while len(player["hand"]) < 5:
            if not self.d["deck"]:
                # These cards never entered the post, so returning them gives no false history.
                self.d["deck"] = sorted(self.d["discard"],
                                        key=lambda cid: self.noise("recycle", cid))
                self.d["discard"] = []
            player["hand"].append(self.d["deck"].pop())

    def move_to_opening(self):
        for pid in range(len(self.d["players"])):
            self.refill(pid)
        if self.d["players"][0]["local"]:
            self.set_phase("opening", [0])
            return
        hand = self.d["players"][0]["hand"]
        best = max(hand, key=lambda cid: self.relative(cid))
        self.open_letter(best if self.relative(best) > 0 else None)

    def open_letter(self, cid, comment=""):
        if cid is not None:
            self.d["players"][0]["hand"].remove(cid)
            self.d["letters"].append(dict(round=0, echo=[cid], silence=[], seal=None, missing=0,
                                          comments={"echo": comment} if comment else {}))
            self.refill(0)
        self.start_round()

    def start_round(self):
        self.d["round"] += 1
        self.d["mail"] = []
        self.d["notes"] = []
        local = [pid for pid in self.d["local"] if pid != 0]
        offset = (self.d["round"] - 1) % len(local) if local else 0
        self.set_phase("intro")
        self.d["writers"] = local[offset:] + local[:offset]
        self.d["first_sender"] = None

    def advance(self):
        if self.phase == "board":
            killer = self.role_id("killer")
            if self.cooperative and 0 in self.d["local"]:
                self.set_phase("truth", [0])
            elif killer in self.d["local"]:
                self.set_phase("truth", [killer])
            else:
                self.d["truth"] = [row[int(self.noise("secret", i) * len(row))]
                                   for i, row in enumerate(self.d["board"])]
                self.move_to_opening()
        elif self.phase == "intro":
            self.set_phase("mail", self.d["writers"])
            if not self.actor:
                self.collect_bot_mail()
        elif self.phase == "reveal":
            order = list(range(1, len(self.d["players"])))
            first = self.d.get("first_sender") or order[0]
            offset = order.index(first)
            self.d["speakers"] = order[offset:] + order[:offset]
            self.next_speaker()
        elif self.phase == "statement":
            self.next_speaker()
        elif self.phase == "discussion":
            if self.d["round"] < self.d["rounds"]:
                self.start_round()
            else:
                self.start_vote(["0"] if self.d.get("sequential") else ["0", "1", "2", "suspect"])
        elif self.phase == "appeal":
            self.start_vote(self.d["tie"], retry=True)
        elif self.phase == "arrest":
            self.d["decided"].pop("suspect", None)
            self.start_vote(["suspect"])
        else:
            raise ValueError("Сейчас требуется выбор.")

    def relative(self, cid):
        strengths = [affinity(cid, target) for target in self.d["truth"]]
        decoys = [affinity(cid, candidate) for row in self.d["board"]
                  for candidate in row if candidate not in self.d["truth"]]
        return max(strengths) * 1.35 + sum(strengths) * 0.2 - max(decoys) * 0.72

    def theories(self, pid, category, purpose):
        role = self.d["players"][pid]["role"]
        row = self.d["board"][category]
        correct = self.d["truth"][category]
        results = {}
        for cid in row:
            score = 0.0
            for entry in self.d["letters"]:
                for hint in entry["echo"]:
                    score += 0.56 * affinity(cid, hint)
                for hint in entry.get("extra", []):
                    score += 0.56 * affinity(cid, hint)
                if entry["seal"] is not None:
                    score += (0.43 if self.marked else 0.56) * affinity(cid, entry["seal"])
                for hint in entry["silence"]:
                    score -= 0.36 * affinity(cid, hint)
            if role in ("killer", "accomplice", "expert"):
                score += (8 if role == "expert" else -10) * (cid == correct)
            if purpose == "vote":
                score += 0.16 * sum(self.note_leads(note).get(str(category)) == cid
                                    for note in self.d["history"])
            spread = {"mail": 1.6, "talk": 2.1, "vote": 2.0}[purpose]
            results[cid] = score + self.noise(purpose, pid, category, cid) * spread
        return results

    def post(self, pid, cid, discard, check=None, second=None):
        hand = self.d["players"][pid]["hand"]
        round_mail = self.d.setdefault("mail_log", {}).setdefault(str(self.d["round"]), {})
        sent = [cid] if second is None else [cid, second]
        round_mail[str(pid)] = dict(sent=cid, sent_cards=sent, hand=hand[:], check=check)
        if self.d.get("first_sender") is None:
            self.d["first_sender"] = pid
        self.d["mail"].extend(sent)
        for card in sent:
            hand.remove(card)
        if discard is not None:
            hand.remove(discard)
            self.d["discard"].append(discard)
        self.refill(pid)

    def collect_bot_mail(self):
        for pid, p in enumerate(self.d["players"]):
            if pid == 0 or p["local"]:
                continue
            check = None
            if p["role"] in ("killer", "accomplice"):
                best = min(p["hand"], key=lambda cid: self.relative(cid) + self.noise("bluff", pid, cid))
            else:
                claims = self.last_round_claims(pid)
                if claims and self.noise("check a claim", pid) < 0.33:
                    candidate = max(claims, key=lambda note: max(
                        affinity(cid, clue) for cid in p["hand"] for clue in clue_list(note, "tests", "test")))
                    leads = clue_list(candidate, "tests", "test")
                    check = dict(pid=candidate["pid"], clues=leads)
                else:
                    leads = [max(scores, key=scores.get) for scores in
                             (self.theories(pid, i, "mail") for i in range(len(CATEGORIES)))]
                best = max(p["hand"], key=lambda cid: max(affinity(cid, lead) for lead in leads)
                           + self.noise("send", pid, cid))
            remaining = [cid for cid in p["hand"] if cid != best]
            second = None
            if self.duel:
                second = max(remaining, key=lambda cid: max(affinity(cid, lead) for lead in leads))
                remaining.remove(second)
            discard = min(remaining, key=lambda cid: self.noise("discard", pid, cid))
            self.post(pid, best, discard if self.noise("redraw", pid) < 0.55 else None, check, second)
        self.d["mail"].sort(key=lambda cid: self.noise("envelope", cid))
        if self.d["players"][0]["local"]:
            self.set_phase("sort", [0])
            return
        sent = self.d["mail"]
        if not self.marked:
            hints = [cid for cid in sent if max(affinity(cid, target) for target in self.d["truth"]) > 0
                     and self.relative(cid) > 0.6]
            hand = sorted(self.d["players"][0]["hand"], key=self.relative, reverse=True)
            own = [cid for cid in hand[:2 if self.duel else 1] if self.relative(cid) >= 1.5]
            self.publish(hints, None, own[0] if own else None, extra=own[1:])
            return
        best = max(sent, key=self.relative)
        echo = best if self.relative(best) > 0.6 else None
        available = [cid for cid in sent if cid != echo]
        most_misleading = min(available, key=self.relative) if available else None
        silence = most_misleading if most_misleading is not None and self.relative(most_misleading) < -0.6 else None
        hand = self.d["players"][0]["hand"]
        seal = max(hand, key=self.relative)
        if self.relative(seal) < (1.5 if echo is None else 2.6):
            seal = None
        extra = []
        if self.duel:
            others = sorted((cid for cid in hand if cid != seal), key=self.relative, reverse=True)
            if seal is not None and self.relative(others[0]) >= 1.5:
                extra = [others[0]]
        self.publish(echo, silence, seal, extra=extra)

    def publish(self, echo, silence, seal, discard=None, comments=None, *, extra=()):
        hints = echo if isinstance(echo, list) else ([] if echo is None else [echo])
        missing = [cid for cid in self.d["mail"] if cid not in hints and cid != silence]
        self.d["letters"].append(dict(round=self.d["round"], echo=hints,
                                      silence=[] if silence is None else [silence], seal=seal, extra=list(extra),
                                      missing=len(missing), comments=comments or {}))
        self.d["archive"].append(missing)
        hand = self.d["players"][0]["hand"]
        for cid in (seal, discard, *extra):
            if cid is not None:
                hand.remove(cid)
        if discard is not None:
            self.d["discard"].append(discard)
        self.refill(0)
        self.d["mail"] = []
        self.set_phase("reveal")

    def next_speaker(self):
        if not self.d["speakers"]:
            self.d["history"].extend(self.d["notes"])
            self.set_phase("discussion")
            return
        pid = self.d["speakers"][0]
        if self.d["players"][pid]["local"]:
            self.set_phase("note", [pid])
            return
        final_round = self.d["round"] == self.d["rounds"]
        categories = range(len(CATEGORIES)) if final_round else [int(self.noise("topic", pid) * 3)]
        leads = {}
        for category in categories:
            scores = self.theories(pid, category, "talk")
            leads[str(category)] = max(scores, key=scores.get)
        suspect = None
        if not self.cooperative and (final_round or self.noise("name a suspect", pid) < 0.48):
            suspects = [i for i in range(1, len(self.d["players"])) if i != pid]
            suspect = max(suspects, key=lambda target: self.suspicion(pid, target))
        receipt = self.mail_receipt(pid)
        claim = receipt.get("sent")
        if claim is not None and self.d["players"][pid]["role"] in ("killer", "accomplice") and not self.claim_opened(claim):
            if self.noise("bluff in discussion", pid) < 0.72:
                alternatives = [cid for cid in receipt["hand"] if cid != claim and not self.claim_opened(cid)]
                if alternatives:
                    claim = max(alternatives, key=lambda cid: max(affinity(cid, lead) for lead in leads.values()))
        tests = []
        if claim is not None and receipt.get("check") is None:
            tests = [max(leads.values(), key=lambda cid: affinity(claim, cid))]
        self.show_statement(pid, leads, suspect, claim, tests)

    def show_statement(self, pid, leads, suspect, claim=None, tests=()):
        check = self.mail_receipt(pid).get("check")
        inherited = clue_list(check, "clues", "clue") if check else []
        tests = list(dict.fromkeys([*inherited, *tests]))
        if leads or suspect is not None or claim is not None or tests:
            self.d["notes"].append(dict(pid=pid, leads=leads, suspect=suspect,
                                        round=self.d["round"], claim=claim, tests=tests, check=check))
        self.d["speaker"] = pid
        self.d["speakers"].pop(0)
        self.set_phase("statement")

    def start_vote(self, keys, retry=False):
        self.d["pass_no"] = int(retry)
        self.d["vote_keys"] = keys
        self.d["ballots"] = {}
        self.set_phase("ballot", [pid for pid in self.d["local"]
                                  if pid and pid not in self.d["excluded"]])
        if self.actor is None:
            self.finish_vote()

    def candidates(self, key):
        if key == "suspect":
            ids = [pid for pid in range(1, len(self.d["players"])) if pid not in self.d["excluded"]]
        else:
            ids = self.d["board"][int(key)]
        if self.d["pass_no"] and not self.d.get("sequential"):
            leaders = self.d["leaders"][key]
            ids = [cid for cid in ids if cid in leaders]
        return ids

    def suspicion(self, pid, target):
        role = self.d["players"][pid]["role"]
        base = (-5 if pid == target else 0) + self.noise("suspect", pid, target) * 2.5
        base += 0.35 * self.public_suspicions()[target]
        for note in self.d["history"]:
            if note["pid"] == target:
                leads = self.note_leads(note).values()
                base += sum(0.17 * affinity(cid, h) for cid in leads
                            for letter in self.d["letters"] for h in letter["silence"]) / max(1, len(leads))
        if role == "witness" and target == self.role_id("killer"):
            base += 9
        if role in ("killer", "accomplice") and target == self.role_id("killer"):
            base -= 9
        return base

    def finish_vote(self):
        keys = self.d["vote_keys"]
        for pid, p in enumerate(self.d["players"]):
            if pid == 0 or pid in self.d["excluded"] or p["local"]:
                continue
            votes = {}
            for key in keys:
                choices = self.candidates(key)
                if key == "suspect":
                    votes[key] = max(choices, key=lambda target: self.suspicion(pid, target))
                else:
                    scores = self.theories(pid, int(key), "vote")
                    votes[key] = max(choices, key=scores.get)
            self.d["ballots"][str(pid)] = votes
        leaders, counts = {}, []
        for key in keys:
            votes = Counter(ballot[key] for ballot in self.d["ballots"].values())
            # In solo play the human chairs the case and breaks tied results they voted for.
            highest = max(votes.values())
            tied = [value for value, count in votes.items() if count == highest]
            chair = self.d["ballots"].get(str(self.d["local"][0]), {}).get(key)
            if not self.d.get("sequential") and len(self.d["local"]) == 1 and chair in tied:
                tied = [chair]
            if len(tied) == 1:
                self.d["decided"][key] = tied[0]
            elif self.d["pass_no"]:
                self.d["decided"][key] = None
            else:
                leaders[key] = tied
            tally = " · ".join(f"{self.label(key, value)} {count}" for value, count in votes.most_common())
            counts.append(tally_line(self.category(key), tally))
        self.d["counts"].append(counts)
        if leaders:
            self.d["leaders"] = leaders
            self.d["tie"] = list(leaders)
            self.set_phase("appeal")
            return
        if self.d.get("sequential") and keys[0] != "suspect":
            index = int(keys[0])
            if index < 2:
                self.start_vote([str(index + 1)])
                return
            if not self.cooperative:
                self.start_vote(["suspect"])
                return
        suspect = self.d["decided"].get("suspect")
        if suspect is not None and suspect in self.role_ids("accomplice"):
            self.d["excluded"].append(suspect)
            self.set_phase("arrest")
            return
        self.d["arrested"] = suspect
        self.d["successes"] = sum(self.d["decided"].get(str(i)) == cid
                                  for i, cid in enumerate(self.d["truth"]))
        killer = self.role_id("killer")
        self.d["solved"] = self.d["successes"] == 3 or (not self.cooperative and self.d["successes"] == 2 and suspect == killer)
        special = [role for role in ("witness", "expert") if self.role_ids(role)]
        if self.d["solved"] and special:
            if self.d["players"][killer]["local"]:
                self.set_phase("counter", [killer])
                return
            others = [pid for pid in range(1, len(self.d["players"])) if pid != killer]
            role, target = max(((role, pid) for role in special for pid in others),
                               key=lambda pair: self.counter_suspicion(pair[1], pair[0]))
            self.end(target, role)
        else:
            self.end()

    def counter_suspicion(self, candidate, role=None):
        mode = role or self.d["mode"]
        score = self.noise("counter", candidate) * 2.1
        for note in self.d["history"]:
            if note["pid"] == candidate:
                if mode == "witness":
                    score += 0.75 * (note["suspect"] == self.role_id("killer"))
                else:
                    leads = self.note_leads(note)
                    matches = sum(cid == self.d["truth"][int(key)] for key, cid in leads.items())
                    score += 0.52 * matches / max(1, len(leads))
        return score

    def end(self, exposed=None, exposed_role=None):
        self.d["exposed"] = exposed
        role = exposed_role or self.d["mode"]
        self.d["exposed_role"] = role if exposed is not None else None
        betrayed = exposed is not None and exposed in self.role_ids(role)
        good = self.d["solved"] and not betrayed
        self.d["winner"] = "detectives" if good else "killer"
        self.d["winners"] = [pid for pid, p in enumerate(self.d["players"])
                             if (good and p["role"] not in ("killer", "accomplice"))
                             or (not good and p["role"] == "killer")
                             or (not self.d["solved"] and p["role"] == "accomplice"
                                 and pid not in self.d["excluded"])]
        self.set_phase("result")

    def category(self, key):
        return "Арест" if key == "suspect" else CATEGORIES[int(key)]

    def label(self, key, value):
        return self.name(value) if key == "suspect" else CARDS[value]["name"]

    def mail_receipt(self, pid):
        return self.d.get("mail_log", {}).get(str(self.d["round"]), {}).get(str(pid), {})

    def last_round_claims(self, pid):
        return [note for note in self.d["history"]
                if note.get("round") == self.d["round"] - 1 and note["pid"] != pid
                and note.get("claim") is not None and clue_list(note, "tests", "test")]

    def public_suspicions(self):
        notes = self.d["history"]
        if self.phase in ("note", "statement"):
            notes = notes + self.d["notes"]
        latest = {note["pid"]: note["suspect"] for note in notes if note["suspect"] is not None}
        return Counter(latest.values())

    def claim_opened(self, cid):
        return any(c["value"] == cid for c in self.view_letter_cards())

    def claim_mark(self, cid):
        if not self.marked:
            return None
        letter = next((letter for letter in self.d["letters"] if letter["round"] == self.d["round"]), None)
        if letter:
            for key in ("echo", "silence"):
                if cid in letter[key]:
                    return MARKS[key]
        return None

    def people(self, ids):
        counts = self.public_suspicions()
        return [dict(value=pid, label=self.name(pid), glyph="●", suspicions=counts[pid]) for pid in ids]

    @staticmethod
    def note_leads(note):
        if "leads" in note:
            return note["leads"]
        return {str(note["category"]): note["card"]} if note["card"] is not None else {}

    def notes_view(self):
        notes = self.d["notes"]
        claim_counts = Counter(note["claim"] for note in notes if note.get("claim") is not None)
        suspicions = self.public_suspicions()
        rows = []
        for note in notes:
            claim, check = note.get("claim"), note.get("check")
            mark = self.claim_mark(claim) if claim is not None else None
            suspect = note["suspect"]
            rows.append(dict(
                player=self.name(note["pid"]),
                suspect=self.name(suspect) if suspect is not None else None,
                suspicions=suspicions[suspect] if suspect is not None else 0,
                claim=card_view(claim, mark=mark, opened=self.claim_opened(claim), disputed=claim_counts[claim] > 1) if claim is not None else None,
                tests=[card_view(cid) for cid in clue_list(note, "tests", "test")],
                checking=self.name(check["pid"]) if check is not None else None,
                clues=[card_view(cid, key=key, category=self.category(key))
                       for key, cid in sorted(self.note_leads(note).items())],
            ))
        return rows

    def mail_audit(self):
        notes = {(str(n.get("round")), str(n["pid"])): n for n in self.d["history"]}
        audit = []
        for number, receipts in self.d.get("mail_log", {}).items():
            entries = []
            for pid, receipt in sorted(receipts.items(), key=lambda item: int(item[0])):
                claim = notes.get((number, pid), {}).get("claim")
                entries.append(dict(player=self.name(int(pid)), sent=" · ".join(CARDS[cid]["name"] for cid in receipt.get("sent_cards", [receipt["sent"]])),
                                    claim=CARDS[claim]["name"] if claim is not None else None,
                                    bluff=claim is not None and claim not in receipt.get("sent_cards", [receipt["sent"]])))
            audit.append(dict(round=int(number), entries=entries))
        return audit

    def ballot_groups(self):
        # A newer public opinion replaces the speaker's previous opinion in that category.
        opinions = {}
        for note in self.d["history"]:
            position = opinions.setdefault(note["pid"], {})
            position.update(self.note_leads(note))
            if note["suspect"] is not None:
                position["suspect"] = note["suspect"]

        groups = []
        for key in self.d["vote_keys"]:
            candidates = self.candidates(key)
            options = (self.people(candidates) if key == "suspect"
                       else [card_view(cid) for cid in candidates])
            for option in options:
                option["supporters"] = [self.name(pid) for pid, position in opinions.items()
                                        if position.get(key) == option["value"]]
            groups.append(group(key, self.category(key), options))
        return groups

    def knowledge(self, pid):
        role = self.d["players"][pid]["role"]
        lines = []
        if role in ("accomplice", "witness"):
            lines.append(tally_line("Убийца", self.name(self.role_id("killer"))))
        if role in ("killer", "accomplice"):
            allies = [self.name(i) for i in self.role_ids("accomplice") if i != pid]
            if allies:
                lines.append(tally_line("Сообщники", ", ".join(allies)))
        if role == "ghost":
            lines += [tally_line(self.name(i), ROLES[p["role"]][0])
                      for i, p in enumerate(self.d["players"]) if i]
        if role in ("killer", "accomplice", "expert", "ghost"):
            lines += [tally_line(CATEGORIES[i], CARDS[cid]["name"])
                      for i, cid in enumerate(self.d["truth"])]
        return lines

    def board_view(self):
        return [dict(key=str(i), label=label, cards=[
            card_view(cid, correct=self.phase == "result" and cid == self.d["truth"][i],
                      voted=self.phase == "result" and cid == self.d["decided"].get(str(i)))
            for cid in self.d["board"][i]]) for i, label in enumerate(CATEGORIES)]

    def board_groups(self):
        return [group(str(i), label, [card_view(cid) for cid in self.d["board"][i]])
                for i, label in enumerate(CATEGORIES)]

    def groups(self):
        phase = self.phase
        if phase == "truth":
            return self.board_groups()
        if phase in ("opening", "mail", "sort"):
            hand = [card_view(cid) for cid in self.d["players"][self.actor]["hand"]]
            if phase == "opening":
                return [group("seal", "Карты на руке", hand, False)]
            if phase == "mail":
                groups = [group("send", "Из руки в ящик", hand)]
                if self.duel:
                    groups.append(group("send2", "Вторая карта", hand))
                checks = self.last_round_claims(self.actor)
                if checks:
                    groups.append(group("check", "Чью версию перепроверяешь", [
                        dict(value=n["pid"], label=self.name(n["pid"]), glyph="↻",
                             detail=" · ".join(CARDS[cid]["name"] for cid in clue_list(n, "tests", "test")))
                        for n in checks], False))
                return groups + [group("discard", "Сбросить и заменить", hand, False)]
            mail = [card_view(cid) for cid in self.d["mail"]]
            groups = ([group("echo", "Эхо · связь с истиной", mail, False),
                       group("silence", "Тишина · ложный след", mail, False),
                       group("seal", "Личная печать · карта с руки", hand, False)]
                      if self.marked else
                      [group("echo", "Открыть подходящие письма", mail, False, multiple=True),
                       group("seal", "Добавить карту с руки", hand, False)])
            if self.duel:
                groups.append(group("seal2", "Вторая карта с руки", hand, False))
            return groups + [group("discard", "Сбросить и заменить", hand, False)]
        if phase == "note":
            suspect = group("person", "Кого подозреваешь", self.people(
                pid for pid in range(1, len(self.d["players"])) if pid != self.actor), False)
            board_options = [card_view(cid, detail=CATEGORIES[i]) for i, row in enumerate(self.d["board"])
                             for cid in row]
            receipt = self.mail_receipt(self.actor)
            groups = []
            if receipt:
                available = receipt["hand"] + [c["value"] for c in self.view_letter_cards()
                                               if not self.marked or c.get("mark") in ("Эхо", "Тишина")]
                groups.append(group("claim", "Какую карту назовёшь", [
                    card_view(cid, detail="Ты отправил эту карту" if cid == receipt["sent"] else None)
                    for cid in dict.fromkeys(available)], False))
            check = receipt.get("check")
            inherited = clue_list(check, "clues", "clue") if check else []
            key = "test" if self.d["round"] == self.d["rounds"] else "lead"
            label = "Дополнительные улики" if inherited else "Какие улики хотел проверить"
            options = [option for option in board_options if option["value"] not in inherited]
            if options:
                groups.append(group(key, label, options, False, multiple=True))
            if self.d["round"] == self.d["rounds"]:
                categories = self.board_groups()
                for category in categories:
                    category["required"] = False
                groups.extend(categories)
            return groups if self.cooperative else groups + [suspect]
        if phase == "ballot":
            return self.ballot_groups()
        if phase == "counter":
            special = [role for role in ("witness", "expert") if self.role_ids(role)]
            groups = [group("person", "Кого раскрыть?", self.people(
                pid for pid in range(1, len(self.d["players"])) if pid != self.actor))]
            if len(special) > 1:
                groups.append(group("role", "Какая тайная роль?", [
                    dict(value=i, label=ROLES[role][0], glyph="●") for i, role in enumerate(special)]))
            return groups
        return []

    def submit(self, picks):
        phase, pid = self.phase, self.actor
        if pid is None:
            raise ValueError("Сейчас ходит весь стол.")
        groups = self.groups()
        for g in groups:
            value = picks.get(g["key"])
            if value is None and not g["required"]:
                continue
            allowed = {option["value"] for option in g["options"]}
            if g["multiple"]:
                selected = [value] if type(value) is int else value
                valid = isinstance(selected, list) and len(selected) <= len(allowed) and all(
                    type(cid) is int and cid in allowed for cid in selected)
                if valid:
                    picks[g["key"]] = list(dict.fromkeys(selected))
            else:
                valid = type(value) is int and value in allowed
            if not valid:
                raise ValueError("Проверь выбранные карты.")
        picks = {key: picks[key] for key in [g["key"] for g in groups] + ["comments"] if key in picks}
        if phase == "role":
            self.d["queue"].pop(0)
            if self.actor is None:
                self.set_phase("board")
        elif phase == "truth":
            self.d["truth"] = [picks[str(i)] for i in range(3)]
            self.move_to_opening()
        elif phase == "opening":
            comments = self.ghost_comments(picks, ("seal",))
            self.open_letter(picks.get("seal"), comments.get("seal", ""))
        elif phase == "mail":
            cid, discard = picks["send"], picks.get("discard")
            second = picks.get("send2")
            selected = [c for c in (cid, second, discard) if c is not None]
            if len(set(selected)) != len(selected):
                raise ValueError("Выбери разные карты.")
            check = next((dict(pid=n["pid"], clues=clue_list(n, "tests", "test"))
                          for n in self.last_round_claims(pid) if n["pid"] == picks.get("check")), None)
            self.post(pid, cid, discard, check, second)
            self.d["queue"].pop(0)
            if self.actor is None:
                self.collect_bot_mail()
        elif phase == "sort":
            echo, silence = picks.get("echo"), picks.get("silence")
            if echo is not None and echo == silence:
                raise ValueError("Одно письмо может получить только одну отметку.")
            seal, discard = picks.get("seal"), picks.get("discard")
            extra = picks.get("seal2")
            selected = [c for c in (seal, extra, discard) if c is not None]
            if len(set(selected)) != len(selected):
                raise ValueError("Выбери разные карты.")
            self.publish(echo, silence, seal, discard, self.ghost_comments(picks, (*MARKS, "seal2")),
                         extra=[] if extra is None else [extra])
        elif phase == "note":
            leads = {g["key"]: picks[g["key"]] for g in groups
                     if g["key"].isdigit() and picks.get(g["key"]) is not None}
            tests = picks.get("test") or picks.get("lead") or []
            if len(tests) == 1 and self.d["round"] < self.d["rounds"]:
                cid = tests[0]
                category = next(i for i, row in enumerate(self.d["board"]) if cid in row)
                leads[str(category)] = cid
            if "speakers" not in self.d:
                # A saved round from before sequential discussion may already have local versions.
                self.d["speakers"] = self.d["queue"] + [
                    i for i, p in enumerate(self.d["players"]) if i and not p["local"]]
            self.show_statement(pid, leads, picks.get("person"), picks.get("claim"), tests)
        elif phase == "ballot":
            self.d["ballots"][str(pid)] = {g["key"]: picks[g["key"]] for g in groups}
            self.d["queue"].pop(0)
            if self.actor is None:
                self.finish_vote()
        elif phase == "counter":
            special = [role for role in ("witness", "expert") if self.role_ids(role)]
            self.end(picks["person"], special[picks.get("role", 0)])

    def ghost_comments(self, picks, marks):
        comments = picks.get("comments", {})
        if not isinstance(comments, dict):
            raise ValueError("Неверный формат заметки.")
        return {mark: comments[mark].strip()[:300] for mark in marks
                if picks.get(mark) is not None and isinstance(comments.get(mark), str)
                and comments[mark].strip()}

    def closest_links(self, card, *, true_clues):
        matches = []
        for index, row in enumerate(self.d["board"]):
            for target in row:
                is_true = target == self.d["truth"][index]
                if is_true != true_clues:
                    continue
                weight, theme = association(card, target)
                if weight:
                    matches.append((weight, dict(category=CATEGORIES[index], theme=theme,
                                                 target=card_view(target))))
        if not matches:
            return []
        best = max(weight for weight, _ in matches)
        return [link for weight, link in matches if weight == best][:3]

    def debrief_view(self):
        human = self.d["players"][0]["local"] is not None
        rounds = []
        for entry in self.d["letters"]:
            number = entry["round"]
            marked = [("echo", cid) for cid in entry["echo"]]
            marked += [("seal2", cid) for cid in entry.get("extra", [])]
            marked += [("silence", cid) for cid in entry["silence"]]
            if entry["seal"] is not None:
                marked.append(("seal", entry["seal"]))
            explanations = []
            for mark, card in marked:
                links, other = [], []
                if human:
                    comment = entry.get("comments", {}).get(mark, "")
                else:
                    links = self.closest_links(card, true_clues=mark != "silence")
                    other = self.closest_links(card, true_clues=mark == "silence")
                    if mark == "silence":
                        comment = "Метка предупреждала: эта ассоциация сильнее вела к ложной улике."
                    elif links and mark == "seal":
                        comment = "Я добавил карту с руки, чтобы дать ещё одну зацепку к истинной улике."
                    elif links:
                        comment = "Я оставил эту карту как подсказку к истинной улике."
                    else:
                        comment = "Прямой связи с истинной уликой не нашлось, но эта карта меньше уводила к ложным версиям."
                explanations.append(dict(card=card_view(card, mark=MARKS.get(mark, "Печать") if self.marked else None), comment=comment,
                                         links=links, other=other))
            archived = [] if number == 0 else self.d["archive"][number - 1]
            if explanations:
                summary = ""
            elif human:
                summary = "В этом раунде я отправил все письма в архив."
            else:
                summary = "Связи на этот раз оказались слишком слабыми. Я оставил письма в архиве."
            rounds.append(dict(round=number, entries=explanations, summary=summary,
                               archived=[card_view(cid) for cid in archived]))
        return rounds

    def verdict_view(self):
        verdict = []
        for i, cid in enumerate(self.d["truth"]):
            vote = self.d["decided"].get(str(i))
            verdict.append(dict(key=str(i), label=CATEGORIES[i], truth=card_view(cid),
                                voted=card_view(vote) if vote is not None else None,
                                correct=vote == cid))
        return verdict

    def letter_cards(self, entry):
        if not self.marked:
            cards = entry["echo"] + entry.get("extra", []) + ([] if entry["seal"] is None else [entry["seal"]])
            rng = random.Random(repr((self.d["seed"], entry["round"], "public hints")))
            rng.shuffle(cards)
            return [card_view(cid) for cid in cards]
        return ([card_view(cid, mark=MARKS["echo"]) for cid in entry["echo"]]
                + [card_view(cid, mark=MARKS["silence"]) for cid in entry["silence"]]
                + ([card_view(entry["seal"], mark=MARKS["seal"])] if entry["seal"] is not None else [])
                 + [card_view(cid, mark=MARKS["seal"]) for cid in entry.get("extra", [])])

    def view_letter_cards(self):
        if self.d["letters"] and self.d["letters"][-1]["round"] == self.d["round"]:
            return self.letter_cards(self.d["letters"][-1])
        return []

    def view(self):
        phase = self.phase
        title, brief, action = SCREENS[phase]
        if phase == "discussion" and self.d["round"] == self.d["rounds"]:
            action = "Перейти к голосованию"
        if phase == "note" and self.d["round"] == self.d["rounds"]:
            brief = "Расскажи о письме, затем озвучь версии перед голосованием."
        if phase == "intro":
            brief = "Выберите версию. Отправьте две карты тайно." if self.duel else "Выберите версию. Отправьте одну карту тайно."
        if phase == "board" and self.cooperative:
            brief = "Придумайте гипотезы для каждой улики. Призрак тайно выберет истину."
        if phase == "sort" and not self.marked:
            brief = "Выбери все подходящие письма. Остальные исчезнут. Можно добавить карты с руки."
        if phase == "mail" and self.duel:
            brief = "Отправь две разные карты. Можно также сбросить третью. Рука пополнится до пяти."
        if phase == "statement" and not self.d["speakers"]:
            action = "К итогам обсуждения"
        if phase == "ballot" and self.d["pass_no"]:
            title = "Повторное голосование"
            brief = "При повторной ничьей решение не принято." if self.d.get("sequential") else "Голосование среди лидеров. При повторной ничьей категория останется без ответа."
        if phase == "arrest":
            brief = f'{self.name(self.d["excluded"][-1])} — сообщник. Он выбывает из голосования за повторный арест.'
        if phase == "counter":
            brief = 'Дело раскрыто. Назови игрока и его тайную роль. У тебя одна попытка.'
        actor = None
        if self.actor is not None:
            p = self.d["players"][self.actor]
            actor = dict(label=f'Игрок {p["local"]} · {p["name"]}', role=ROLES[p["role"]][0],
                         brief=ROLES[p["role"]][1], knowledge=self.knowledge(self.actor))
            if phase == "note":
                check = self.mail_receipt(self.actor).get("check")
                if check:
                    actor["recheck"] = [CARDS[cid]["name"] for cid in clue_list(check, "clues", "clue")]
        suspicions = self.public_suspicions()
        roster = [dict(name=p["name"], seat=f'Игрок {p["local"]}' if p["local"] else "Бот",
                       role=ROLES[p["role"]][0] if phase == "result" else "",
                       suspicions=suspicions[i] if i else None)
                  for i, p in enumerate(self.d["players"])]
        letters = [dict(round=entry["round"], missing=entry["missing"], cards=self.letter_cards(entry))
                   for entry in reversed(self.d["letters"])]
        board = self.board_view() if phase != "role" else []
        result = phase == "result"
        notes = self.notes_view() if phase in ("note", "statement", "discussion", "ballot", "appeal", "result") else []
        speaker = self.name(self.d["speaker"]) if phase == "statement" else None
        statement = notes[-1] if speaker and notes and notes[-1]["player"] == speaker else None
        return dict(id=self.d["id"], rev=self.d["rev"], phase=phase, title=title, brief=brief,
                    action=action, mode=MODES[self.d["mode"]], round=self.d["round"],
                    rounds=self.d["rounds"], marked=self.marked, cooperative=self.cooperative, actor=actor, groups=self.groups(), board=board,
                    roster=roster, letters=letters, notes=notes, speaker=speaker, statement=statement,
                    tallies=self.d["counts"] if phase in ("appeal", "arrest", "result") else [],
                    outcome=self.outcome() if result else [],
                    verdict=self.verdict_view() if result else [],
                    mail_audit=self.mail_audit() if result else [],
                    debrief=self.debrief_view() if result else [],
                    ghost_is_human=self.d["players"][0]["local"] is not None if result else None)

    def outcome(self):
        arrested = self.d["arrested"]
        lines = [] if self.cooperative else [
            tally_line("Арест", "нет решения" if arrested is None else self.name(arrested)),
            tally_line("Убийца", self.name(self.role_id("killer")))]
        for pid in self.d["excluded"]:
            lines.append(tally_line("Арестован сообщник", self.name(pid)))
        if "winners" in self.d:
            lines.append(tally_line("Победители", ", ".join(self.name(pid) for pid in self.d["winners"]) or "нет"))
        if self.d["exposed"] is not None:
            exposed = self.d["exposed"]
            role = self.d.get("exposed_role") or self.d["mode"]
            verdict = "роль раскрыта" if exposed == self.role_id(role) else "ошибка"
            killer = self.name(self.role_id("killer"))
            lines.append(tally_line("Последний ход убийцы",
                                    f"{killer} → {self.name(exposed)} · {ROLES[role][0]} · {verdict}"))
        return lines


def tally_line(label, value):
    return dict(label=label, value=value)


SCREENS = {
    "role": ("Тайная роль", "Запомни свою роль и передай телефон дальше.", "Скрыть роль"),
    "board": ("Стол расследования", "На столе 12 улик. Попробуйте придумать, как предметы могут объяснить мотив, место или способ. Затем убийца назначит истинные улики.", "Выбрать истинные улики"),
    "truth": ("Истинные улики", "Выбери одну карту в каждой категории. Выбор сохраняется до конца партии.", "Запечатать дело"),
    "opening": ("Первое письмо", "Если на руке есть подходящая ассоциация, опубликуй её. Этот ход можно пропустить.", "Открыть почту"),
    "intro": ("Почтовый ящик", "", "Начать отправку"),
    "mail": ("Запечатать письмо", "Отправь одну карту. Можно также сбросить другую карту: в конце хода рука снова пополнится до пяти.", "Отправить письмо"),
    "sort": ("Вскрыть конверты", "Можно отметить одно письмо «Эхо», другое — «Тишина». Добавь одну карту из руки как личную печать. Остальное уйдёт в архив.", "Опубликовать письмо"),
    "reveal": ("Ход Призрака", "Все письма собраны. Посмотрите, какие карты Призрак открыл в этом раунде, прежде чем высказывать версии.", "Начать обсуждение"),
    "note": ("Твоя версия", "Назови отправленную карту и отметь улики, которые хотел проверить.", "Озвучить версию"),
    "statement": ("Версия игрока", "", "Следующий участник"),
    "discussion": ("Итоги обсуждения", "Все участники высказались. Сопоставьте их версии с письмами Призрака.", "Следующий раунд"),
    "ballot": ("Бюллетень", "", "Опустить бюллетень"),
    "appeal": ("Голоса разделились", "Переголосуйте по спорным категориям.", "Переголосовать"),
    "arrest": ("Задержан сообщник", "", "Голосовать повторно за арест"),
    "counter": ("Последний ход убийцы", "", "Назвать игрока"),
    "result": ("Дело закрыто", "", ""),
}


@contextmanager
def storage():
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE_DIR / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield STATE_DIR / "session.json"


def save(path, data):
    if data is None:
        path.unlink(missing_ok=True)
        return
    fd, tmp = tempfile.mkstemp(prefix="session-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def public_view(game):
    if game is None:
        return dict(phase="setup", modes=[dict(key=key, label=label) for key, label in MODES.items()])
    view = game.view()
    if game.phase == "result":
        detectives = game.d["winner"] == "detectives"
        view["title"] = "Детективы победили" if detectives else ("Дело не раскрыто" if game.cooperative else "Убийца победил")
        view["success"] = detectives
        view["brief"] = ("Дело раскрыто." if detectives else
                         "Дело раскрыто, но убийца вычислил особую роль." if game.d["solved"]
                         else "Стол не собрал достаточно верных ответов.")
    return view


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("view", "start", "advance", "submit", "reset"))
    parser.add_argument("token", nargs="?", default="-")
    parser.add_argument("payload", nargs="?", default="{}")
    args = parser.parse_args()
    with storage() as path:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        game = Game(data) if data is not None else None
        if args.action == "view":
            print(json.dumps(public_view(game), ensure_ascii=False))
            return
        if args.action == "start" and game is None:
            config = json.loads(args.payload)
            game = Game.new(**config)
            save(path, game.d)
        elif game and args.token == f'{game.d["id"]}:{game.d["rev"]}':
            if args.action == "reset":
                save(path, None)
                game = None
            elif args.action in ("advance", "submit"):
                if args.action == "advance":
                    game.advance()
                else:
                    game.submit(json.loads(args.payload))
                game.d["rev"] += 1
                save(path, game.d)
        print(json.dumps({"game": public_view(game)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(json.dumps({"error": "Ход не сохранён. Попробуй ещё раз."}, ensure_ascii=False))
        print(str(error), file=sys.stderr)
        sys.exit(1)
