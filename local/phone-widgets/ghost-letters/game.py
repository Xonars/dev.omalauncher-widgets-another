#!/usr/bin/env python3
"""Local game state and computer players for the OWL app."""

import argparse
import csv
import hashlib
import io
import re
import time
import zipfile
from collections import Counter
from contextlib import contextmanager
from functools import lru_cache
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
ANALYTICS_SCHEMA = 1
GAME_VERSION = "2.12.0"
BOT_VERSION = "3.4.0"
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
# Stable card IDs keep 1.x and 2.0 saves playable.
CARDS = json.loads((HERE / "deck.json").read_text(encoding="utf-8"))
DIFFICULTIES = {
    "easy": ("Лёгкая", 1.9, 0.60),
    "normal": ("Обычная", 0.95, 0.82),
    "hard": ("Сложная", 0.35, 1.0),
}
# evidence weight, trust in others, recheck tendency, caution
PROFILES = {
    "analyst": (1.15, 0.18, 0.36, 0.75),
    "skeptic": (1.0, -0.12, 0.70, 0.95),
    "intuitive": (0.85, 0.08, 0.22, 0.45),
    "social": (0.90, 0.55, 0.40, 0.55),
    "strategist": (1.05, 0.24, 0.52, 0.85),
}
PROFILE_NAMES = {
    "analyst": "Аналитик", "skeptic": "Скептик", "intuitive": "Интуитивный",
    "social": "Общительный", "strategist": "Стратег",
}


def card_view(card_id, **fields):
    card = CARDS[card_id]
    artwork = HERE / "assets" / "cards" / f"{card_id:03d}.webp"
    return dict(value=card_id, label=card["name"], glyph=card["glyph"],
                artwork=str(artwork) if artwork.is_file() else None, **fields)


def group(key, label, options, required=True, *, multiple=False):
    return dict(key=key, label=label, options=options, required=required, multiple=multiple)


def clue_list(record, plural, singular):
    if plural in record:
        return record[plural]
    clue = record.get(singular)
    return [] if clue is None else [clue]


@lru_cache(maxsize=None)
def association(left, right):
    a, b = CARDS[left]["tags"], CARDS[right]["tags"]
    links = sorted(((min(a[tag], b[tag]), tag) for tag in a.keys() & b.keys()),
                   key=lambda pair: (-pair[0], pair[1]))
    if not links:
        return 0.0, None
    strength, label = links[0]
    return min(4.0, strength + 0.25 * sum(weight for weight, _ in links[1:3])), label


def affinity(left, right):
    return association(left, right)[0]


def hint_signal(board, cid, category, hint):
    """A shared or cross-category association is weaker than a distinctive one."""
    row = board[category]
    strengths = [affinity(other, hint) for other in row]
    best, second = sorted(strengths, reverse=True)[:2]
    other_best = max((affinity(other, hint) for i, options in enumerate(board)
                      if i != category for other in options), default=0)
    relevance = max(0.12, (best - 0.6 * second) / 4)
    relevance *= 1.0 if best >= other_best else 0.55
    return relevance * (affinity(cid, hint) - sum(strengths) / len(row))


def evidence_score(knowledge, cid, category):
    """Use only information actually visible to this player."""
    score = 0.0
    board = knowledge["board"]
    for entry in knowledge["letters"]:
        age = max(0, knowledge["round"] - entry["round"])
        for hint, sign in entry["hints"]:
            score += sign * (0.91 ** age) * hint_signal(board, cid, category, hint)
    for entry in knowledge["own_mail"]:
        age = max(0, knowledge["round"] - entry["round"])
        for hint in entry["missing"]:
            score -= 0.14 * (0.85 ** age) * hint_signal(board, cid, category, hint)
    return score


def public_evidence_at(knowledge, number):
    """Reconstruct public evidence at a statement's round, without private mail."""
    return dict(knowledge, round=number, own_mail=[],
                letters=[entry for entry in knowledge["letters"] if entry["round"] <= number])


def public_opinions(knowledge, category):
    """Latest explicit endorsements only, never private tests or hidden plans."""
    opinions = {}
    for note in sorted(knowledge["notes"], key=lambda n: n["round"]):
        cid = note["leads"].get(str(category))
        if cid in knowledge["board"][category] and note["pid"] != knowledge["pid"]:
            opinions[note["pid"]] = cid
    return opinions


def sabotage_focus(knowledge):
    """Target a credible competing public theory rather than the weakest clue alone."""
    visible = public_evidence_at(knowledge, knowledge["round"])
    priorities = []
    for i, truth in enumerate(knowledge["truth"]):
        opinions = public_opinions(knowledge, i)
        support = Counter(opinions.values())
        total = max(1, len(opinions))
        correct = evidence_score(visible, truth, i)
        alternatives = [c for c in knowledge["board"][i] if c != truth]
        pressure = max(evidence_score(visible, c, i) - correct +
                       0.9 * (support[c] - support[truth]) / total for c in alternatives)
        priorities.append(pressure)
    return max(range(len(priorities)), key=lambda i: priorities[i])


def belief_scores(knowledge, category, purpose, noise):
    profile = PROFILES[knowledge["profile"]]
    _, spread, skill = DIFFICULTIES[knowledge["difficulty"]]
    role = knowledge["role"]
    correct = knowledge["truth"][category] if knowledge["truth"] else None
    opinions = public_opinions(knowledge, category)
    scores = {}
    adaptive = knowledge["difficulty"] != "easy"
    row = knowledge["board"][category]
    # A hostile player concentrates on the least established true clue.
    sabotage = None
    if adaptive and role in ("killer", "accomplice"):
        sabotage = sabotage_focus(knowledge)
    for cid in row:
        score = profile[0] * skill * evidence_score(knowledge, cid, category)
        # Cap social influence; repeated opinions are not independent evidence.
        agreement = sum(lead == cid for lead in opinions.values()) / max(1, len(opinions))
        # Social agreement cannot substitute for independent card evidence.
        score += profile[1] * agreement * (0.55 if adaptive else 1.0)
        score += (0.07 if adaptive else 0.18 + 0.18 * profile[3]) * (knowledge["own_leads"].get(str(category)) == cid)
        if role == "expert":
            # An expert knows the answer but avoids advertising perfect knowledge in discussion.
            score += (8.0 if purpose == "vote" else 1.8) * (cid == correct)
        elif role in ("killer", "accomplice"):
            # Plausible alternative beats a random wrong answer; do not always suppress every truth.
            if not adaptive:
                score -= (8.0 if purpose == "vote" else 2.2) * (cid == correct)
            elif category == sabotage:
                score -= (8.0 if purpose == "vote" else 2.8) * (cid == correct)
            elif purpose != "mail":
                score += 0.35 * (cid == correct)  # maintain plausible public cover
        if purpose == "vote":
            score += 0.14 * (knowledge["own_leads"].get(str(category)) == cid)
        uncertainty = 1.0 if not adaptive else (0.60 if knowledge["difficulty"] == "normal" else 0.40)
        scores[cid] = score + noise(cid) * spread * uncertainty * (1.3 if knowledge["profile"] == "intuitive" else 0.75 + 0.4 * profile[3])
    return scores


class Game:
    def __init__(self, data):
        self.d = data

    def enable_analytics(self, partial=False):
        if "analytics" not in self.d:
            self.d["analytics"] = dict(schema=ANALYTICS_SCHEMA, version=GAME_VERSION,
                bot_version=BOT_VERSION, started_at=None if partial else int(time.time()),
                partial=partial, events=[])
            self.trace("capture_start", partial=partial, seed=self.d["seed"],
                       mode=self.d["mode"], difficulty=self.d.get("difficulty", "normal"),
                       board=self.d["board"], players=[dict(pid=i, role=p["role"], local=p["local"],
                       profile=self.bot_profile(i) if i and not p["local"] else None)
                       for i,p in enumerate(self.d["players"])])

    def trace(self, kind, **fields):
        analytics = self.d.get("analytics")
        if analytics is not None:
            events = analytics["events"]
            events.append(json.loads(json.dumps(dict(seq=len(events)+1, round=self.d["round"],
                phase=self.phase, rev=self.d["rev"], at=int(time.time()), kind=kind, **fields), ensure_ascii=False)))

    @classmethod
    def new(cls, mode, total, humans, human_ghost, *, marked=False, difficulty="normal", seed=None):
        if (mode not in MODES or type(total) is not int or type(humans) is not int
                or not (2 if mode == "coop" else 4) <= total <= 12 or not 1 <= humans <= total
                or type(marked) is not bool or type(human_ghost) is not bool or difficulty not in DIFFICULTIES
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
            schema=5, marked=marked, difficulty=difficulty, sequential=True, exposed_role=None, winners=[], notebooks={},
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
        self.trace("phase", target=phase, queue=list(queue))
        self.d["phase"] = phase
        self.d["queue"] = list(queue)

    def refill(self, pid):
        player = self.d["players"][pid]
        before = player["hand"][:]
        while len(player["hand"]) < 5:
            if not self.d["deck"]:
                # These cards never entered the post, so returning them gives no false history.
                self.d["deck"] = sorted(self.d["discard"],
                                        key=lambda cid: self.noise("recycle", cid))
                self.d["discard"] = []
            player["hand"].append(self.d["deck"].pop())
        if before != player["hand"]:
            self.trace("refill", pid=pid, before=before, after=player["hand"])

    def prepare_ghost_deal(self):
        """Bounded initial-deal balancing, never a mid-game search of the deck."""
        if (self.d.get("difficulty", "normal") == "easy" or self.d["players"][0]["local"]
                or self.d["round"] or self.d["letters"] or any(p["hand"] for p in self.d["players"])):
            return
        deck = self.d["deck"]
        if len(deck) < 6:
            return
        # Only the undealt deck is available here. Preserve the board, truth, and
        # multiset of cards. At most two exchanges, preserving useful coverage.
        hand = deck[-5:]
        before = hand[:]
        margins = {c: self.ghost_margins(c) for c in deck}
        def quality(cards):
            return [max((margins[c][i] for c in cards if min(margins[c]) >= -0.28), default=0.0)
                    for i in range(len(self.d["truth"]))]
        swaps = []
        for _ in range(2):
            old_quality = quality(hand)
            missing = [i for i, value in enumerate(old_quality) if value < 0.32]
            if not missing:
                break
            options = []
            for index, candidate in enumerate(deck[:-5]):
                m = margins[candidate]
                if min(m) < -0.28 or not any(m[i] >= 0.32 for i in missing):
                    continue
                for slot, removed in enumerate(hand):
                    proposed = hand[:]
                    proposed[slot] = candidate
                    new_quality = quality(proposed)
                    if any(old_quality[i] >= 0.32 and new_quality[i] < 0.32
                           for i in range(len(old_quality))):
                        continue
                    improved = sum(new_quality[i] >= 0.32 for i in missing)
                    # First cover another category, then prefer a stronger distinctive clue.
                    # The final tie-break respects the shuffled deck order.
                    if improved:
                        options.append((improved, sum(min(1.0, new_quality[i]) for i in missing),
                                        index, -slot, removed, candidate))
            if not options:
                break
            _, _, index, neg_slot, removed, candidate = max(options)
            slot = -neg_slot
            deck[index], deck[len(deck) - 5 + slot] = removed, candidate
            hand[slot] = candidate
            swaps.append(dict(removed=removed, added=candidate))
        self.trace("ghost_deal", before=before, after=hand, swaps=swaps,
                   coverage_before=quality(before), coverage_after=quality(hand))

    def move_to_opening(self):
        self.prepare_ghost_deal()
        for pid in range(len(self.d["players"])):
            self.refill(pid)
        if self.d["players"][0]["local"]:
            self.set_phase("opening", [0])
            return
        hand = self.d["players"][0]["hand"]
        context = self.ghost_context() if self.d.get("difficulty", "normal") != "easy" else None
        scores = {c: self.adaptive_ghost_gain(c, context) if context is not None else self.relative(c) for c in hand}
        best = max(hand, key=scores.get)
        selected = best if scores[best] > 0.22 else None
        if "analytics" in self.d:
            self.trace("bot_opening", pid=0, knowledge=self.player_knowledge(0), scores=scores, selected=selected, context=context)
        self.open_letter(selected)

    def open_letter(self, cid, comment=""):
        self.trace("opening", pid=0, card=cid)
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
        self.trace("advance")
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

    def ghost_margins(self, cid):
        board = self.d["board"]
        return [hint_signal(board, truth, i, cid) -
                max(hint_signal(board, other, i, cid) for other in board[i] if other != truth)
                for i, truth in enumerate(self.d["truth"])]

    def ghost_coverage(self):
        coverage = [0.0, 0.0, 0.0]
        for entry in self.d["letters"]:
            positive = entry["echo"] + entry.get("extra", []) + ([] if entry["seal"] is None else [entry["seal"]])
            for sign, cards in ((1, positive), (-1, entry["silence"])):
                for cid in cards:
                    margins = self.ghost_margins(cid)
                    if sign < 0:
                        # For a negative clue, recompute the best surviving decoy.
                        margins = [min(hint_signal(self.d["board"], other, i, cid)
                                       for other in self.d["board"][i] if other != truth) -
                                   hint_signal(self.d["board"], truth, i, cid)
                                   for i, truth in enumerate(self.d["truth"])]
                    for i, margin in enumerate(margins):
                        coverage[i] += margin
        return coverage

    def ghost_gain(self, cid, coverage, negative=False):
        board = self.d["board"]
        margins = self.ghost_margins(cid)
        if negative:
            margins = [min(hint_signal(board, other, i, cid) for other in board[i] if other != truth) -
                       hint_signal(board, truth, i, cid) for i, truth in enumerate(self.d["truth"])]
        positive = [max(0, m) / (1 + 0.6 * max(0, coverage[i])) for i, m in enumerate(margins)]
        # Avoid misleading other categories, but allow imperfect clues.
        return max(positive, default=0) + 0.25 * sum(positive) + 0.32 * sum(min(0, m) for m in margins)

    def relative(self, cid):
        return self.ghost_gain(cid, [0.0, 0.0, 0.0])

    def ghost_context(self):
        """Estimate public understanding; never consult other players' private hands or bot scores."""
        knowledge = self.player_knowledge(0)
        rows = knowledge["board"]
        scores = [{c: evidence_score(knowledge, c, i) for c in row}
                  for i, row in enumerate(rows)]
        opinions = [{} for _ in rows]
        for note in sorted(knowledge["notes"], key=lambda n: n["round"]):
            for key, cid in note["leads"].items():
                i = int(key)
                if cid in rows[i]:
                    opinions[i][note["pid"]] = (cid, note["round"], 1.0)
            # A stated test is a weaker signal than an endorsed lead.
            for i, row in enumerate(rows):
                candidates = [cid for cid in note["tests"] if cid in row]
                if len(candidates) == 1 and str(i) not in note["leads"]:
                    # Multiple hypotheses in one category are not an endorsement.
                    opinions[i][note["pid"]] = (candidates[0], note["round"], 0.25)
        public = []
        for i, row in enumerate(rows):
            counts = {c: 0.0 for c in row}
            for cid, number, confidence in opinions[i].values():
                counts[cid] += confidence * 0.75 ** max(0, knowledge["round"] - number - 1)
            total = sum(counts.values())
            public.append({c: counts[c] / total if total else 0.0 for c in row})
        local_ids = {p for p, player in enumerate(self.d["players"]) if p and player["local"]}
        # Local-player status is table metadata; their private notes and mail remain hidden.
        human = []
        for i, row in enumerate(rows):
            human.append([dict(pid=pid, card=opinions[i][pid][0],
                               confidence=opinions[i][pid][2], round=opinions[i][pid][1])
                          for pid in sorted(local_ids) if pid in opinions[i]])
        return dict(scores=scores, public=public, human=human, confirmed=[],
                    difficulty=knowledge["difficulty"],
                    remaining=max(1, knowledge["rounds"] - knowledge["round"] + 1))

    def ghost_priorities(self, context):
        weights = []
        for i, truth in enumerate(self.d["truth"]):
            scores, public = context["scores"][i], context["public"][i]
            gap = scores[truth] - max(v for c, v in scores.items() if c != truth)
            disagreement = max(0.0, max((v for c, v in public.items() if c != truth), default=0) - public[truth])
            # A confidently wrong table needs correction, not more confirmation of easy clues.
            weight = 1.0 / (1.0 + 2.0 * max(0.0, gap) ** 2)
            if gap >= 0.55 and public[truth] >= 0.65:
                weight *= 0.25
            weight *= 1.0 + 1.5 * disagreement + 0.35 * (1.0 - public[truth])
            recent_human = [n for n in context.get("human", [[] for _ in self.d["truth"]])[i]
                            if n["round"] >= self.d["round"] - 1]
            if any(n["card"] != truth for n in recent_human):
                weight = max(weight, 0.35) * 1.35
            if context["difficulty"] == "hard":
                weight *= 1.0 + (0.75 + 0.5 / context["remaining"]) * disagreement
            weights.append(weight)
        return weights

    def ghost_confirmation(self, cid, context):
        """A final-round, one-per-category bonus for clear positive confirmation."""
        if context["remaining"] != 1:
            return []
        margins = self.ghost_margins(cid)
        if min(margins) < -0.28:
            return []
        result = []
        for i, truth in enumerate(self.d["truth"]):
            if i in context.get("confirmed", []) or margins[i] < 0.32:
                continue
            public = context["public"][i]
            human = context.get("human", [[] for _ in self.d["truth"]])[i]
            uncertain = any(n["card"] != truth or n["confidence"] < 1.0 or
                            n["round"] < self.d["round"] - 1 for n in human)
            local_present = any(p["local"] for p in self.d["players"][1:])
            scores = context["scores"][i]
            gap = scores[truth] - max(v for c, v in scores.items() if c != truth)
            # Do not repeat an already decisive clue just because a human stayed silent.
            if gap >= 1.25 and not any(n["card"] != truth and n["round"] >= self.d["round"] - 1 for n in human):
                continue
            if public[truth] < 0.86 or uncertain or (local_present and not human):
                # Favor understandable direct associations over merely accumulated scores.
                result.append((i, min(0.42, 0.10 + 0.42 * margins[i])))
        return result

    def adaptive_ghost_gain(self, cid, context, negative=False):
        board = self.d["board"]
        weights = self.ghost_priorities(context)
        gains = []
        sign = -1 if negative else 1
        for i, truth in enumerate(self.d["truth"]):
            scores, public = context["scores"][i], context["public"][i]
            signals = {c: sign * hint_signal(board, c, i, cid) for c in board[i]}
            before = scores[truth] - max(v for c, v in scores.items() if c != truth)
            after = scores[truth] + signals[truth] - max(v + signals[c] for c, v in scores.items() if c != truth)
            gain = after - before
            # The leading-gap metric alone misses elimination of one of several
            # equally plausible alternatives. Explicit Silence can narrow the row
            # even when another alternative remains tied. Do not infer negatives
            # from unopened mail or use Silence in unmarked games.
            if negative and self.marked:
                rivals = [c for c in board[i] if c != truth]
                plausible = [c for c in rivals if scores[c] >= max(scores.values()) - 0.65]
                if plausible:
                    pair_gains = [signals[truth] - signals[c] for c in plausible]
                    elimination = sum(max(0.0, x) for x in pair_gains) / len(plausible)
                    harm = max(0.0, -min(pair_gains))
                    if harm <= 0.10:
                        gain += (0.40 if context["difficulty"] == "normal" else 0.55) * elimination
            # Correct popular false theories at both adaptive difficulties.
            rival = max((c for c in board[i] if c != truth), key=lambda c: (public[c], scores[c]))
            disagreement = max(0.0, public[rival] - public[truth])
            correction = min(0.65, (0.30 if context["difficulty"] == "normal" else 0.45) + 0.20 * disagreement)
            if disagreement > 0:
                gain = (1 - correction) * gain + correction * (signals[truth] - signals[rival])
            # Never discount misleading cross-category associations merely because a clue was solved.
            weighted = weights[i] * max(0.0, gain) + max(0.75, weights[i]) * min(0.0, gain)
            gains.append(weighted)
        confirmation = max((bonus for _, bonus in self.ghost_confirmation(cid, context)), default=0.0) if not negative else 0.0
        return max(0.0, *gains) + 0.15 * sum(max(0, g) for g in gains) + 1.25 * sum(min(0, g) for g in gains) + confirmation

    def ghost_apply_hint(self, context, cid, negative=False):
        if not negative:
            context.setdefault("confirmed", []).extend(i for i, _ in self.ghost_confirmation(cid, context))
        sign = -1 if negative else 1
        for i, row in enumerate(self.d["board"]):
            for c in row:
                context["scores"][i][c] += sign * hint_signal(self.d["board"], c, i, cid)

    def choose_ghost_letters(self, sent, hand):
        coverage = self.ghost_coverage()
        context = self.ghost_context() if self.d.get("difficulty", "normal") != "easy" else None
        def gain(cid, negative=False):
            return self.adaptive_ghost_gain(cid, context, negative) if context is not None else self.ghost_gain(cid, coverage, negative)
        def select(pool, threshold, following=()):
            best = max(pool, key=gain)
            if context is None:
                return best
            eligible = [cid for cid in pool if gain(cid) > threshold]
            if not eligible:
                return best
            def plan(cid):
                projected = dict(context, scores=[dict(row) for row in context["scores"]],
                                 confirmed=list(context.get("confirmed", [])))
                self.ghost_apply_hint(projected, cid)
                future = max((self.adaptive_ghost_gain(other, projected)
                              for other in following if other != cid), default=0.0)
                return gain(cid) + (0.20 if context["difficulty"] == "normal" else 0.35) * max(0.0, future)
            return max(eligible, key=plan)

        def snapshot():
            if context is None:
                return {}
            return dict(priorities=self.ghost_priorities(context),
                        public=[dict(row) for row in context["public"]],
                        predicted_scores=[dict(row) for row in context["scores"]],
                        human=[list(row) for row in context["human"]], confirmed=list(context["confirmed"]))
        decisions = []
        echo, silence, own = [], None, []
        def add_positive(cid):
            for i, margin in enumerate(self.ghost_margins(cid)):
                coverage[i] += margin
            if context is not None:
                self.ghost_apply_hint(context, cid)
        pool = list(sent)
        while pool:
            best = select(pool, 0.16, hand if self.marked else pool + list(hand))
            if "analytics" in self.d:
                decisions.append(dict(stage="echo", coverage=coverage[:], **snapshot(), scores={c:gain(c) for c in pool}, best=best, threshold=0.16))
            if gain(best) <= 0.16:
                break
            echo.append(best)
            add_positive(best)
            pool.remove(best)
            if self.marked:
                break
        if self.marked and pool:
            candidate = max(pool, key=lambda cid: gain(cid, negative=True))
            if "analytics" in self.d:
                decisions.append(dict(stage="silence", coverage=coverage[:], **snapshot(), scores={c:gain(c, negative=True) for c in pool}, best=candidate, threshold=0.22))
            if gain(candidate, negative=True) > 0.22:
                silence = candidate
                if context is not None:
                    self.ghost_apply_hint(context, candidate, negative=True)
        pool = list(hand)
        for _ in range(2 if self.duel else 1):
            if not pool:
                break
            best = select(pool, 0.24 if echo else 0.16, pool if self.duel and not own else ())
            if "analytics" in self.d:
                decisions.append(dict(stage="seal", coverage=coverage[:], **snapshot(), scores={c:gain(c) for c in pool}, best=best, threshold=0.24 if echo else 0.16))
            if gain(best) <= (0.24 if echo else 0.16):
                break
            own.append(best)
            add_positive(best)
            pool.remove(best)
        def retention(cid):
            if context is None:
                return gain(cid)
            # Save cards useful for the weakest unresolved category.
            # Never inspect the hidden deck.
            priorities = self.ghost_priorities(context)
            margins = self.ghost_margins(cid)
            # Retain a distinct clue for ANY unresolved category, not just the
            # current maximum priority (which can change after the next discussion).
            useful = []
            for i, truth in enumerate(self.d["truth"]):
                scores = context["scores"][i]
                gap = scores[truth] - max(v for c, v in scores.items() if c != truth)
                if gap < 1.25:
                    useful.append(max(0.0, margins[i]) * priorities[i])
            # Redundant cards should make room for new draws using the legal
            # one-card discard, even if another category has a small gain.
            return max(useful, default=0.0) + 0.15 * max(0.0, gain(cid))

        discard = min(pool, key=retention) if pool else None
        if discard is not None and (retention(discard) >= 0.12 or (context is not None and context["remaining"] <= 1)):
            discard = None
        if "analytics" in self.d:
            self.trace("bot_ghost", pid=0, knowledge=self.player_knowledge(0), incoming=sent, decisions=decisions, echo=echo, silence=silence, own=own, discard=discard,
                       discard_scores={c:retention(c) for c in pool})
        return echo, silence, own, discard

    def bot_profile(self, pid):
        # Personality is independent of hidden role; no role can be inferred from a name.
        return tuple(PROFILES)[int(random.Random(repr((self.d["seed"], "profile", pid))).random() * len(PROFILES))]

    def player_knowledge(self, pid):
        role = self.d["players"][pid]["role"]
        truth = self.d["truth"][:] if role in ("ghost", "expert", "killer", "accomplice") else []
        killer = self.role_id("killer") if role in ("ghost", "witness", "killer", "accomplice") else None
        allies = self.role_ids("accomplice") if role in ("ghost", "killer", "accomplice") else []
        letters = []
        own_mail = []
        for letter in self.d["letters"]:
            number = letter["round"]
            positive = letter["echo"] + letter.get("extra", []) + ([] if letter["seal"] is None else [letter["seal"]])
            hints = [(cid, 1) for cid in positive] + [(cid, -1) for cid in letter["silence"]]
            letters.append(dict(round=number, hints=sorted(hints)))
            receipt = self.d.get("mail_log", {}).get(str(number), {}).get(str(pid), {})
            if receipt:
                opened = {cid for cid, _ in hints}
                own_mail.append(dict(round=number, missing=[cid for cid in receipt.get("sent_cards", [receipt["sent"]]) if cid not in opened]))
        notes = []
        unique = {}
        for note in self.d["history"] + self.d["notes"]:
            unique[(note.get("round", 0), note["pid"])] = note
        for note in unique.values():
            notes.append(dict(pid=note["pid"], round=note.get("round", 0), leads=self.note_leads(note).copy(),
                              suspect=note.get("suspect"), claim=note.get("claim"),
                              tests=clue_list(note, "tests", "test")[:]))
        own_leads = {}
        for note in notes:
            if note["pid"] == pid:
                own_leads.update(note["leads"])
        return dict(pid=pid, role=role, truth=truth, killer=killer, allies=allies,
                    profile=self.bot_profile(pid), difficulty=self.d.get("difficulty", "normal"),
                    round=self.d["round"], rounds=self.d["rounds"], board=[row[:] for row in self.d["board"]],
                    letters=letters, notes=notes, own_mail=own_mail, own_leads=own_leads,
                    hand=self.d["players"][pid]["hand"][:])

    def theories(self, pid, category, purpose):
        knowledge = self.player_knowledge(pid)
        return belief_scores(knowledge, category, purpose,
                             lambda cid: (0.72 * self.noise("personal preference", pid, category, cid) +
                                          0.28 * self.noise(purpose, pid, category, cid, self.d.get("pass_no", 0))))

    def post(self, pid, cid, discard, check=None, second=None, planned=()):
        hand = self.d["players"][pid]["hand"]
        round_mail = self.d.setdefault("mail_log", {}).setdefault(str(self.d["round"]), {})
        sent = [cid] if second is None else [cid, second]
        self.trace("mail", pid=pid, hand=hand, sent=sent, discard=discard, check=check, planned=list(planned))
        round_mail[str(pid)] = dict(sent=cid, sent_cards=sent, hand=hand[:], check=check, planned=list(planned))
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
            knowledge = self.player_knowledge(pid)
            profile = PROFILES[knowledge["profile"]]
            hostile = knowledge["role"] in ("killer", "accomplice")
            check = None
            rankings = [self.theories(pid, i, "mail") for i in range(len(CATEGORIES))]
            leads = [max(scores, key=scores.get) for scores in rankings]
            if knowledge["profile"] in ("skeptic", "intuitive") and self.noise("alternative", pid) < profile[2]:
                topic = min(range(3), key=lambda i: sorted(rankings[i].values(), reverse=True)[0] -
                            sorted(rankings[i].values(), reverse=True)[1])
                leads.append(sorted(rankings[topic], key=rankings[topic].get, reverse=True)[1])
            adaptive = knowledge["difficulty"] != "easy"
            sabotage = sabotage_focus(knowledge) if hostile and adaptive else None
            if sabotage is not None:
                # Consider several plausible false targets, but concentrate the sabotage.
                row = knowledge["board"][sabotage]
                truth = knowledge["truth"][sabotage]
                leads = sorted((c for c in row if c != truth),
                               key=rankings[sabotage].get, reverse=True)[:2]
                # A credible cover letter is preferable to a completely unrelated lie.
                leads += [c for i, c in enumerate(knowledge["truth"]) if i != sabotage]
            claims = self.last_round_claims(pid)
            if not hostile and claims and self.noise("check a claim", pid) < profile[2]:
                candidate = max(claims, key=lambda note: max(
                    affinity(cid, clue) for cid in p["hand"] for clue in clue_list(note, "tests", "test")))
                checked = clue_list(candidate, "tests", "test")
                if any(affinity(cid, clue) > 0 for cid in p["hand"] for clue in checked):
                    leads = list(dict.fromkeys(leads + checked)) if adaptive else checked
                    check = dict(pid=candidate["pid"], clues=checked)
            uncertainty = []
            attempted = Counter()
            if adaptive and not hostile:
                # Publicly reported tests only: no access to other players' actual mail or plans.
                for note in knowledge["notes"]:
                    prior = public_evidence_at(knowledge, note["round"])
                    opened = {c for entry in prior["letters"] if entry["round"] == note["round"]
                              for c, sign in entry["hints"] if sign > 0}
                    if note["claim"] is not None and note["claim"] not in opened:
                        for target in note["tests"]:
                            attempted[target] += 0.7 ** max(0, knowledge["round"] - note["round"] - 1)
                # Rotate focus using public seating and round, not other bots' private choices.
                for i, ranking in enumerate(rankings):
                    ordered = sorted(ranking, key=ranking.get, reverse=True)
                    if ranking[ordered[0]] - ranking[ordered[1]] < 0.7 or attempted[ordered[0]] >= 1:
                        leads.append(ordered[1])
                leads = list(dict.fromkeys(leads))
            focus = (pid + knowledge["round"]) % len(CATEGORIES)
            for i, row in enumerate(knowledge["board"]):
                ranked = sorted((evidence_score(knowledge, c, i) for c in row), reverse=True)
                uncertainty.append(1.0 / (1.0 + max(0.0, ranked[0] - ranked[1])))

            def mail_score(card, target):
                row = next(row for row in knowledge["board"] if target in row)
                other = max(affinity(card, cid) for cid in row if cid != target)
                score = affinity(card, target) - 0.55 * other
                if hostile and not adaptive:
                    score -= 0.8 * max(affinity(card, cid) for cid in knowledge["truth"])
                if adaptive:
                    i = knowledge["board"].index(row)
                    if not hostile:
                        score *= 0.25 + uncertainty[i]
                        score += 0.42 * (i == focus) * uncertainty[i]
                        score -= min(1.15, 0.45 * attempted[target])
                        score += 0.35 * max(-1.0, rankings[i][target] - max(rankings[i].values()))
                        # Negative evidence from previous unopened mail is weak, not proof.
                        for entry in knowledge["own_mail"]:
                            if any(affinity(old, target) >= 2 and affinity(old, card) >= 2 for old in entry["missing"]):
                                score -= 0.20
                    else:
                        truth = knowledge["truth"][i]
                        if target != truth:
                            # A good decoy is plausible to the ghost AND misleading to the table.
                            true_link = max(affinity(card, c) for c in knowledge["truth"])
                            decoy_link = affinity(card, target)
                            support = list(public_opinions(knowledge, i).values())
                            popular = support.count(target) / max(1, len(support))
                            score = (0.75 * score + 0.55 * min(true_link, decoy_link)
                                     - 0.45 * max(0.0, decoy_link - true_link)
                                     + 0.65 * popular + 0.55 * uncertainty[i])
                            score += 0.55 * (decoy_link >= 1.5)
                        else:
                            score = 0.55 * score - 0.9  # occasional useful cover
                return score + self.noise("send", pid, card, target) * (0.3 if adaptive else 0.5)

            best, intended = max(((card, lead) for card in p["hand"] for lead in leads),
                                 key=lambda pair: mail_score(*pair))
            remaining = [cid for cid in p["hand"] if cid != best]
            planned = [intended]
            second = None
            if self.duel:
                second, target2 = max(((card, lead) for card in remaining for lead in leads),
                                      key=lambda pair: mail_score(*pair) + 0.25 * (pair[1] != intended))
                planned.append(target2)
                remaining.remove(second)
            discard = min(remaining, key=lambda cid: max(affinity(cid, lead) for lead in leads))
            if adaptive and check and not any(c in check["clues"] for c in planned):
                check = None
            if "analytics" in self.d:
                self.trace("bot_mail", pid=pid, knowledge=knowledge, rankings=rankings, targets=leads,
                           candidates=[dict(card=c, target=t, score=mail_score(c,t)) for c in p["hand"] for t in leads],
                           selected=[best] if second is None else [best,second], planned=planned, check=check,
                           uncertainty=uncertainty if adaptive else None, public_failed_tests=dict(attempted), focus=focus if adaptive and not hostile else None, sabotage_focus=sabotage, second_target_bonus=0.25 if self.duel else None)
            self.post(pid, best, discard if self.noise("redraw", pid) < 0.55 else None, check, second, planned)
        self.d["mail"].sort(key=lambda cid: self.noise("envelope", cid))
        if self.d["players"][0]["local"]:
            self.set_phase("sort", [0])
            return
        sent = self.d["mail"]
        hand = self.d["players"][0]["hand"]
        echo, silence, own, discard = self.choose_ghost_letters(sent, hand)
        self.publish(echo, silence, own[0] if own else None, discard, extra=own[1:])

    def publish(self, echo, silence, seal, discard=None, comments=None, *, extra=()):
        hints = echo if isinstance(echo, list) else ([] if echo is None else [echo])
        missing = [cid for cid in self.d["mail"] if cid not in hints and cid != silence]
        self.d["letters"].append(dict(round=self.d["round"], echo=hints,
                                      silence=[] if silence is None else [silence], seal=seal, extra=list(extra),
                                      missing=len(missing), comments=comments or {}))
        self.trace("publish", pid=0, received=self.d["mail"], opened=hints, silence=silence, seal=seal, extra=list(extra), archived=missing, discard=discard)
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
        knowledge = self.player_knowledge(pid)
        hostile = knowledge["role"] in ("killer", "accomplice")
        receipt = self.mail_receipt(pid)
        claim = receipt.get("sent")
        planned = receipt.get("planned", [])
        rankings = [self.theories(pid, i, "talk") for i in range(len(CATEGORIES))]
        leads = {str(i): max(scores, key=scores.get) for i, scores in enumerate(rankings)}
        if not final_round:
            topic = next((i for i, row in enumerate(self.d["board"]) if planned and planned[0] in row), None)
            if topic is None:
                topic = max(range(3), key=lambda i: max(rankings[i].values()) - min(rankings[i].values()))
            leads = {str(topic): leads[str(topic)]}
        suspect = None
        suspects = []
        if not self.cooperative and (final_round or self.noise("name a suspect", pid) < 0.48):
            suspects = [i for i in range(1, len(self.d["players"])) if i != pid and i not in self.d["excluded"]]
            suspect = max(suspects, key=lambda target: self.suspicion(pid, target))
        tests = planned[:] or ([max(leads.values(), key=lambda cid: affinity(claim, cid))] if claim is not None else [])
        if claim is not None and hostile and not self.claim_opened(claim):
            # Only an unopened letter can safely be misrepresented.
            candidates = [cid for cid in receipt["hand"] if cid != claim and not self.claim_opened(cid)]
            if candidates and self.noise("bluff in discussion", pid) < 0.58:
                alternative, target = max(((c, lead) for c in candidates for lead in leads.values()),
                                          key=lambda pair: affinity(*pair))
                if affinity(alternative, target) >= 1.5 and affinity(alternative, target) >= affinity(claim, target):
                    claim, tests = alternative, [target]
        speech = self.bot_speech(knowledge, claim, tests, leads, receipt.get("check"), suspect=suspect)
        if "analytics" in self.d:
            self.trace("bot_discussion", pid=pid, knowledge=knowledge, rankings=rankings,
                       suspect_scores={target:self.suspicion(pid,target) for target in suspects},
                       suspect_factors={target:self.suspicion_factors(pid,target) for target in suspects},
                       sent=receipt.get("sent_cards", []), claim=claim, leads=leads, tests=tests, suspect=suspect, speech=speech)
        self.show_statement(pid, leads, suspect, claim, tests, speech=speech)

    def bot_speech(self, knowledge, claim, tests, leads, check=None, *, suspect=None):
        """Template-based, grounded in the bot's claim and public evidence, never private truth."""
        if claim is None:
            return ""
        profile = knowledge["profile"]
        final_round = knowledge["round"] >= knowledge["rounds"]
        variant = int(self.noise("speech variant", knowledge["pid"]) * 3)
        names = lambda ids: ", ".join("«" + CARDS[cid]["name"] + "»" for cid in ids)
        parts = []
        if tests:
            target = max(tests, key=lambda cid: affinity(claim, cid))
            weight, tag = association(claim, target)
            if weight:
                parts.append((
                    f"Я проверял карту {names([target])}. Связь с картой {names([claim])} — «{tag}».",
                    f"Между {names([claim])} и {names([target])} я увидел общую тему: «{tag}».",
                    f"Моё письмо {names([claim])} было проверкой карты {names([target])}: «{tag}»."
                )[variant])
            else:
                parts.append(f"Я хотел проверить {names(tests)}, но моя ассоциация непрямая.")
        else:
            parts.append(f"Моя версия началась с карты {names([claim])}.")
        opened = self.claim_opened(claim)
        if opened and self.claim_mark(claim) == MARKS["silence"]:
            parts.append("Призрак обозначил ложный след. Эту связь стоит пересмотреть.")
        elif opened:
            parts.append({"analyst": "Карта открыта, это аргумент в пользу версии, но не доказательство.",
                          "skeptic": "Карта открыта, однако она может указывать на другую категорию.",
                          "intuitive": "Карта открыта. Перед голосованием учту и менее очевидные связи." if final_round else "Карта открыта. Попробую поискать и менее очевидные связи.",
                          "social": "Карта открыта; интересно, увидели ли остальные ту же связь.",
                          "strategist": "Карта открыта. Проверю, не ведут ли другие письма туда же."}[profile])
        else:
            parts.append({"analyst": "Карта исчезла, значит вес этой версии пока ниже.",
                          "skeptic": "Карта исчезла, но это ещё не опровергает версию.",
                          "intuitive": "Возможно, моя ассоциация оказалась слишком необычной.",
                          "social": "Карта исчезла. Сравню её с версиями остальных.",
                          "strategist": "Карта исчезла; перед голосованием стоит пересмотреть эту версию." if final_round else "Карта исчезла; в следующем раунде нужна другая проверка."}[profile])
        if check:
            parts.append(f"Перепроверял версию игрока «{self.name(check['pid'])}».")
        else:
            other = next((n for n in reversed(knowledge["notes"])
                          if n["pid"] != knowledge["pid"] and n["leads"] and
                          any(k in leads for k in n["leads"])), None)
            if other:
                shared = next(k for k in other["leads"] if k in leads)
                rival, own = other["leads"][shared], leads[shared]
                if knowledge["difficulty"] == "easy":
                    agree = any(leads.get(k) == cid for k, cid in other["leads"].items())
                    parts.append(f"С версией игрока «{self.name(other['pid'])}» " +
                                 ("отчасти согласен." if agree else ("не согласен — перед голосованием взвешу уже открытые письма." if final_round else "пока не согласен — нужны новые письма.")))
                else:
                    i = int(shared)
                    visible = [(h, sign) for entry in knowledge["letters"] for h, sign in entry["hints"]]
                    if own == rival:
                        parts.append(f"Согласен с игроком «{self.name(other['pid'])}» насчёт {names([own])}.")
                    else:
                        parts.append(f"Игрок «{self.name(other['pid'])}» предлагает {names([rival])}, а я склоняюсь к {names([own])}.")
                    if visible:
                        hint, sign = max(visible, key=lambda pair: pair[1] * (hint_signal(knowledge["board"], own, i, pair[0]) -
                                                                                            (hint_signal(knowledge["board"], rival, i, pair[0]) if rival != own else 0)))
                        delta = sign * (hint_signal(knowledge["board"], own, i, hint) -
                                        (hint_signal(knowledge["board"], rival, i, hint) if rival != own else 0))
                        if delta > 0.12:
                            parts.append(f"Подсказка {names([hint])} " + ("отмечена как ложный след и помогает исключать варианты." if sign < 0 else f"лучше согласуется с {names([own])}."))
                        elif rival != own:
                            parts.append("По открытым письмам пока не могу уверенно отличить эти версии.")
            elif knowledge["own_leads"]:
                prior = knowledge["own_leads"]
                same = any(prior.get(k) == cid for k, cid in leads.items())
                parts.append("Пока придерживаюсь прежней версии." if same else
                             "Моя версия изменилась после новых подсказок.")
        if knowledge["difficulty"] != "easy":
            for key, cid in leads.items():
                old = knowledge["own_leads"].get(key)
                if old is None or old == cid:
                    continue
                i = int(key)
                delta = evidence_score(knowledge, cid, i) - evidence_score(knowledge, old, i)
                if delta > 0.12:
                    parts.append(f"Открытые письма теперь сильнее поддерживают {names([cid])}, чем {names([old])}.")
                else:
                    parts.append(f"{names([cid])} вместо {names([old])} — пока альтернативная версия, не доказательство.")
                break
            if suspect is not None:
                prior = [n for n in knowledge["notes"] if n["pid"] == suspect]
                for n in reversed(prior):
                    visible = public_evidence_at(knowledge, n["round"])
                    conflicts = [(k, c) for k, c in n["leads"].items()
                                 if max(evidence_score(visible, other, int(k)) for other in visible["board"][int(k)]) -
                                 evidence_score(visible, c, int(k)) > 0.55]
                    if conflicts:
                        k, c = conflicts[0]
                        repeated = sum(old["leads"].get(k) == c for old in prior)
                        if repeated >= 2:
                            parts.append(f"Игрок «{self.name(suspect)}» несколько раз отстаивал {names([c])}, хотя письма поддерживали другую версию. Это повод проверить его, не доказательство.")
                        else:
                            parts.append(f"Версия игрока «{self.name(suspect)}» о {names([c])} плохо согласовалась с тогдашними письмами. Пока это лишь подозрение.")
                        break
        return " ".join(parts)

    def show_statement(self, pid, leads, suspect, claim=None, tests=(), *, speech=""):
        check = self.mail_receipt(pid).get("check")
        inherited = clue_list(check, "clues", "clue") if check else []
        tests = list(dict.fromkeys([*inherited, *tests]))
        if leads or suspect is not None or claim is not None or tests:
            self.d["notes"].append(dict(pid=pid, leads=leads, suspect=suspect,
                                        round=self.d["round"], claim=claim, tests=tests, check=check, speech=speech))
        self.trace("statement", pid=pid, leads=leads, suspect=suspect, claim=claim, tests=tests, speech=speech)
        self.d["speaker"] = pid
        self.d["speakers"].pop(0)
        if self.d["players"][pid]["local"] and len(self.d["local"]) == 1:
            self.next_speaker()
        else:
            self.set_phase("statement")

    def start_vote(self, keys, retry=False):
        self.trace("vote_start", keys=keys, retry=retry)
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
        return sum(self.suspicion_factors(pid, target).values())

    def suspicion_factors(self, pid, target):
        knowledge = self.player_knowledge(pid)
        profile = PROFILES[knowledge["profile"]]
        adaptive = knowledge["difficulty"] != "easy"
        factors = dict(noise=self.noise("suspect", pid, target, self.d.get("pass_no", 0)) *
                       DIFFICULTIES[knowledge["difficulty"]][1], self_penalty=-12 if pid == target else 0,
                       social=0.0, revision=0.0, evidence_conflict=0.0, claim_conflict=0.0, role=0.0)
        factors["social"] = max(0, profile[1]) * self.public_suspicions()[target] / max(1, len(self.d["players"]) - 1)
        if adaptive:
            factors["noise"] *= 0.22 if knowledge["difficulty"] == "normal" else 0.12
            factors["social"] *= 0.04
            factors["persistence"] = 0.0
            factors["unsupported_shift"] = 0.0
            factors["claim_alignment"] = 0.0
            factors["verified_conflict"] = 0.0
            factors["unbacked_churn"] = 0.0
        claims = sorted((note for note in knowledge["notes"] if note["pid"] == target), key=lambda n: n["round"])
        previous = {}
        if adaptive:
            # Use evidence available at the time of a statement.
            # A wrong guess under weak evidence is not deception.
            repeated = Counter()
            distinct = {}
            for note in claims:
                visible = public_evidence_at(knowledge, note["round"])
                for key, cid in note["leads"].items():
                    i = int(key)
                    if cid not in visible["board"][i]:
                        continue
                    scores = {c: evidence_score(visible, c, i) for c in visible["board"][i]}
                    ranking = sorted(scores.values(), reverse=True)
                    gap = max(scores.values()) - scores[cid]
                    confidence = ranking[0] - ranking[1]
                    conflict = min(1.0, max(0.0, gap - 0.38)) * min(1.0, confidence / 0.85)
                    if conflict > 0:
                        factors["evidence_conflict"] += 0.22 * conflict
                        repeated[(key, cid)] += 1
                        if repeated[(key, cid)] > 1:
                            factors["persistence"] += 0.65 * conflict
                    old = previous.get(key)
                    seen = distinct.setdefault(key, set())
                    if old is not None and old != cid:
                        delta = scores[cid] - scores[old]
                        if delta > 0.18:
                            factors["revision"] -= min(0.10, delta * 0.08)
                        elif delta < -0.18 and confidence > 0.18:
                            factors["unsupported_shift"] += min(0.30, -delta * 0.22)
                        # Three distinct endorsed versions with no evidence gain
                        # are a weak signal only; honest uncertainty remains legal.
                        if cid not in seen and len(seen) >= 2 and delta <= 0.18:
                            factors["unbacked_churn"] += 0.12
                    seen.add(cid)
                    previous[key] = cid
                claim = note["claim"]
                tests = note["tests"]
                if claim is not None and tests and all(affinity(claim, c) == 0 for c in tests):
                    factors["claim_alignment"] += 0.04
                if claim is not None:
                    # A claimed card actually sent by ME is direct evidence, not a guess.
                    # Only the observer's own receipt is used, never another player's receipt.
                    receipt = self.d.get("mail_log", {}).get(str(note["round"]), {}).get(str(pid), {})
                    if target != pid and claim in receipt.get("sent_cards", [receipt.get("sent")]):
                        factors["verified_conflict"] += 1.5
            for key, limit in (("evidence_conflict", 0.55), ("persistence", 1.0),
                               ("unsupported_shift", 0.9), ("claim_alignment", 0.24), ("unbacked_churn", 0.24)):
                factors[key] = min(limit, factors[key])
            factors["revision"] = max(-0.20, factors["revision"])
            factors["verified_conflict"] = min(3.0, factors["verified_conflict"])
        for note in ([] if adaptive else claims):
            for key, cid in note["leads"].items():
                if key in previous and previous[key] != cid:
                    if not adaptive:
                        factors["revision"] += 0.04
                    elif evidence_score(knowledge, cid, int(key)) > evidence_score(knowledge, previous[key], int(key)):
                        factors["revision"] -= 0.08
                previous[key] = cid
        for key, cid in ({} if adaptive else previous).items():
            scores = [evidence_score(knowledge, other, int(key)) for other in knowledge["board"][int(key)]]
            factors["evidence_conflict"] += min(0.55, max(0, max(scores) - evidence_score(knowledge, cid, int(key))) * (0.20 if adaptive else 0.12))
        # A contradictory claim is evidence of possible deception, never access to private mail.
        for note in claims:
            if note["claim"] is not None and any(
                n["pid"] != target and n["round"] == note["round"] and n["claim"] == note["claim"]
                for n in knowledge["notes"]):
                factors["claim_conflict"] += 0.48
        if adaptive:
            factors["claim_conflict"] = min(1.44, factors["claim_conflict"])
        if knowledge["role"] == "witness" and target == knowledge["killer"]:
            factors["role"] += 2.5
        if knowledge["role"] in ("killer", "accomplice") and (target == knowledge["killer"] or target in knowledge["allies"]):
            factors["role"] -= 5
        return factors

    def finish_vote(self):
        keys = self.d["vote_keys"]
        for pid, p in enumerate(self.d["players"]):
            if pid == 0 or pid in self.d["excluded"] or p["local"]:
                continue
            votes = {}
            for key in keys:
                choices = self.candidates(key)
                if key == "suspect":
                    choices = [target for target in choices if target != pid] or choices
                    scores = {target: self.suspicion(pid, target) for target in choices}
                else:
                    scores = self.theories(pid, int(key), "vote")
                votes[key] = max(choices, key=scores.get)
                if "analytics" in self.d:
                    self.trace("bot_vote", pid=pid, key=key, candidates=choices, scores=scores,
                               selected=votes[key], knowledge=self.player_knowledge(pid), retry=self.d["pass_no"],
                               suspect_factors={t:self.suspicion_factors(pid,t) for t in choices} if key == "suspect" else None)
            self.d["ballots"][str(pid)] = votes
        leaders, counts = {}, []
        for key in keys:
            votes = Counter(ballot[key] for ballot in self.d["ballots"].values())
            # In solo play the human chairs the case and breaks tied results they voted for.
            highest = max(votes.values())
            tied = [value for value, count in votes.items() if count == highest]
            chair = self.d["ballots"].get(str(self.d["local"][0]), {}).get(key) if self.d["local"] else None
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
        self.trace("vote_result", keys=keys, retry=self.d["pass_no"], ballots=self.d["ballots"], counts=counts, decided=self.d["decided"], ties=leaders)
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
            if "analytics" in self.d:
                self.trace("bot_counter", pid=killer, knowledge=self.player_knowledge(killer), selected=[role,target], candidates=[dict(role=r,pid=p,score=self.counter_suspicion(p,r)) for r in special for p in others])
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
        self.trace("result", winner=self.d["winner"], winners=self.d["winners"], solved=self.d["solved"], truth=self.d["truth"], decided=self.d["decided"], arrested=self.d["arrested"], exposed=exposed, exposed_role=exposed_role)
        if "analytics" in self.d:
            self.d["analytics"]["finished_at"] = int(time.time())
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

    def notebook_owner(self):
        if self.phase in ("role", "result") or self.d["round"] < 1:
            return None
        pid = self.actor
        if pid is None and len(self.d["local"]) == 1:
            pid = self.d["local"][0]
        if pid is not None and pid in self.d["local"] and self.d["players"][pid]["role"] != "ghost":
            return pid
        return None

    def notebook_view(self):
        pid = self.notebook_owner()
        if pid is None:
            return None
        record = self.d.get("notebooks", {}).get(str(pid), {})
        return dict(owner=self.name(pid), pid=pid, marks=record.get("marks", {}).copy(),
                    suspects=record.get("suspects", {}).copy(), text=record.get("text", ""))

    def save_notebook(self, payload):
        pid = self.notebook_owner()
        if pid is None or not isinstance(payload, dict):
            raise ValueError("Личный блокнот недоступен.")
        cards = {str(cid) for row in self.d["board"] for cid in row}
        people = {str(i) for i in range(1, len(self.d["players"])) if i != pid}
        def validate_marks(values, allowed):
            if not isinstance(values, dict) or any(k not in allowed or v not in ("likely", "unlikely", "neutral")
                                                    for k, v in values.items()):
                raise ValueError("Неверная отметка в блокноте.")
            return {k: v for k, v in values.items() if v != "neutral"}
        marks = validate_marks(payload.get("marks", {}), cards)
        suspects = validate_marks(payload.get("suspects", {}), people)
        text = payload.get("text", "")
        if not isinstance(text, str) or len(text) > 2000:
            raise ValueError("Заметка слишком длинная.")
        self.d.setdefault("notebooks", {})[str(pid)] = dict(marks=marks, suspects=suspects, text=text)

    def history_view(self):
        grouped = {}
        for note in self.d["history"] + self.d["notes"]:
            grouped.setdefault(note.get("round", 0), {})[note["pid"]] = note
        return [dict(round=number, entries=self.notes_view(list(grouped[number].values()), number))
                for number in sorted(grouped, reverse=True)]

    def notes_view(self, notes=None, number=None):
        notes = self.d["notes"] if notes is None else notes
        number = self.d["round"] if number is None else number
        letter = next((entry for entry in self.d["letters"] if entry["round"] == number), None)
        opened = {c["value"]: c.get("mark") for c in self.letter_cards(letter)} if letter else {}
        claim_counts = Counter(note["claim"] for note in notes if note.get("claim") is not None)
        suspicions = Counter(n["suspect"] for n in notes if n.get("suspect") is not None)
        rows = []
        for note in notes:
            claim, check = note.get("claim"), note.get("check")
            mark = opened.get(claim) if claim is not None else None
            suspect = note["suspect"]
            rows.append(dict(
                player=self.name(note["pid"]),
                speech=note.get("speech", ""),
                suspect=self.name(suspect) if suspect is not None else None,
                suspicions=suspicions[suspect] if suspect is not None else 0,
                claim=card_view(claim, mark=mark, opened=claim in opened, disputed=claim_counts[claim] > 1) if claim is not None else None,
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
            if key == "suspect":
                candidates = [cid for cid in candidates if cid != self.actor] or candidates
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
                sent = receipt.get("sent_cards", [receipt["sent"]])
                can_bluff = self.d["players"][self.actor]["role"] in ("killer", "accomplice")
                available = sent[:]
                if can_bluff and not self.claim_opened(receipt["sent"]):
                    available += [cid for cid in receipt["hand"] if not self.claim_opened(cid)]
                groups.append(group("claim", "Какую карту назовёшь", [
                    card_view(cid, detail="Ты отправил эту карту" if cid in sent else None)
                    for cid in dict.fromkeys(available)], False))
            check = receipt.get("check")
            inherited = clue_list(check, "clues", "clue") if check else []
            key = "test" if self.d["round"] == self.d["rounds"] else "lead"
            label = "Дополнительные улики" if inherited else "Какие улики хотел проверить"
            options = [option for option in board_options if option["value"] not in inherited]
            if options:
                groups.append(group(key, label, options, False, multiple=True))
            if self.d["round"] == self.d["rounds"] or self.d.get("difficulty", "normal") != "easy":
                categories = self.board_groups()
                for category in categories:
                    category["required"] = False
                    if self.d["round"] < self.d["rounds"]:
                        category["label"] = "Моя версия · " + category["label"]
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
        intent = picks.get("intent")
        if phase == "mail" and intent is not None and (type(intent) is not int or not any(intent in row for row in self.d["board"])):
            raise ValueError("Неизвестная улика.")
        picks = {key: picks[key] for key in [g["key"] for g in groups] + ["comments"] if key in picks}
        if "analytics" in self.d:
            self.trace("human_choice", pid=pid, knowledge=self.player_knowledge(pid), picks={k:v for k,v in picks.items() if k != "comments"},
                       intent=intent if phase == "mail" else None)
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
            if len(tests) == 1 and self.d["round"] < self.d["rounds"] and self.d.get("difficulty", "normal") == "easy":
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

    def flow_view(self):
        phase = self.phase
        stage = {"intro":0,"mail":0,"sort":1,"reveal":1,"note":2,"statement":2,"discussion":3}.get(phase,-1)
        letter = next((x for x in self.d["letters"] if x["round"] == self.d["round"]), None)
        result = dict(stage=stage, opened=len(self.letter_cards(letter)) if letter else 0,
                      archived=letter["missing"] if letter else 0,
                      received=(len(letter["echo"])+len(letter["silence"])+letter["missing"]) if letter else None,
                      spoken=len(self.d["players"])-1-len(self.d.get("speakers", [])) if phase in ("note","statement","discussion") else 0,
                      speakers=len(self.d["players"])-1)
        if phase == "discussion":
            latest = {}
            for note in self.d["history"] + self.d["notes"]:
                for key,cid in self.note_leads(note).items():
                    latest[(note["pid"],key)] = cid
            result["leaders"] = []
            for i,category in enumerate(CATEGORIES):
                counts = Counter(cid for (pid,key),cid in latest.items() if key == str(i))
                result["leaders"].append(dict(label=category, cards=[dict(card=card_view(cid), votes=count)
                    for cid,count in counts.most_common() if count == max(counts.values(),default=0)]))
        if phase in ("ballot","appeal","arrest"):
            result["vote_step"] = (int(self.d["vote_keys"][0])+1 if self.d["vote_keys"][0].isdigit() else 4) if self.d.get("vote_keys") else 1
            result["vote_total"] = 3 if self.cooperative else 4
        return result

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
        if phase == "role" and len(self.d["local"]) == 1:
            brief = "Твоя тайная роль в этом расследовании."
            action = "Продолжить"
        if phase == "board":
            action = "Начать расследование"
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
        roster = [dict(value=i, name=p["name"], seat=f'Игрок {p["local"]}' if p["local"] else "Бот",
                       role=ROLES[p["role"]][0] if phase == "result" else "",
                       personality=PROFILE_NAMES[self.bot_profile(i)] if phase == "result" and i and p["local"] is None else "",
                       won=(i in self.d["winners"]) if phase == "result" and "winners" in self.d else None,
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
                    rounds=self.d["rounds"], marked=self.marked, cooperative=self.cooperative,
                    flow=self.flow_view(), local_count=len(self.d["local"]), difficulty=self.d.get("difficulty", "normal"), actor=actor, groups=self.groups(), board=board,
                    notebook=self.notebook_view(), history=self.history_view(),
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
        if not self.cooperative:
            lines.append(tally_line("Убийца пойман", "да" if arrested == self.role_id("killer") else "нет"))
            lines.append(tally_line("Все три улики раскрыты", "да" if self.d["successes"] == 3 else "нет"))
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


def archive_game(game, directory=None):
    if game.phase != "result":
        return
    directory = STATE_DIR / "games" if directory is None else directory
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    case_id = game.d["id"]
    if not re.fullmatch(r"[0-9a-f]{32}", case_id):
        raise ValueError("Invalid case ID")
    path = directory / (case_id + ".json")
    if path.exists():
        return
    data = json.loads(json.dumps(game.d, ensure_ascii=False))
    data.pop("notebooks", None)
    save(path, data)


def archived_games(directory=None):
    directory = STATE_DIR / "games" if directory is None else directory
    records = []
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            if data.get("phase") == "result" and path.stem == data.get("id") and re.fullmatch(r"[0-9a-f]{32}", path.stem):
                records.append(data)
        except (ValueError, OSError):
            continue
    return sorted(records, key=lambda d: ((d.get("analytics") or {}).get("finished_at") or 0,d["id"]), reverse=True)


def case_summary(data):
    a = data.get("analytics", {})
    start, end = a.get("started_at"), a.get("finished_at")
    return dict(id=data["id"], short=data["id"][:8], mode=data["mode"], mode_label=MODES[data["mode"]],
        difficulty=data.get("difficulty","normal"), marked=data.get("marked",True),
        date=time.strftime("%Y-%m-%d %H:%M",time.localtime(end)) if end else "До обновления",
        duration=max(0,end-start) if start is not None and end is not None else None,
        players=len(data["players"]), humans=len(data["local"]), round=data["round"], rounds=data["rounds"],
        successes=data["successes"], solved=data["solved"], winner=data["winner"],
        killer_arrested=None if data["mode"] == "coop" else any(p["role"] == "killer" and pid == data.get("arrested") for pid, p in enumerate(data["players"])),
        partial=a.get("partial",True), version=a.get("version","legacy"),
        people=[dict(role=data["players"][pid]["role"], label=ROLES[data["players"][pid]["role"]][0],
                     won=pid in data["winners"]) for pid in data["local"]])


def statistics(records, role=None):
    rows=[case_summary(d) for d in records]
    roles=[]
    for key,(label,_) in ROLES.items():
        participants=[p for row in rows for p in row["people"] if p["role"]==key]
        roles.append(dict(key=key,label=label,total=len(participants),wins=sum(p["won"] for p in participants)))
    times=[r["duration"] for r in rows if r["duration"] is not None]
    participants=[p for r in rows for p in r["people"] if not role or p["role"]==role]
    return dict(total=len(rows), wins=sum(p["won"] for p in participants), attempts=len(participants),
                solved=sum(r["solved"] for r in rows), correct=sum(r["successes"] for r in rows),
                all_clues=sum(r["successes"] == 3 for r in rows),
                killer_arrests=sum(r["killer_arrested"] is True for r in rows),
                arrest_games=sum(r["killer_arrested"] is not None for r in rows),
                clues=3*len(rows), average_seconds=round(sum(times)/len(times)) if times else None,
                timed_games=len(times), roles=roles,
                empty_rounds=sum(not (l["echo"] or l["silence"] or l["seal"] is not None or l.get("extra")) for d in records for l in d["letters"] if l["round"]>0),
                rounds=sum(d["round"] for d in records))


def filter_records(records, filters):
    return [d for d in records if
            all(not filters.get(k) or filters[k]==d.get(k,"normal") for k in ("mode","difficulty")) and
            (not filters.get("players") or len(d["players"])==filters["players"]) and
            (not filters.get("role") or any(d["players"][pid]["role"]==filters["role"] for pid in d["local"]))]


def export_analysis(records, directory=None):
    directory = Path.home() / "Downloads" if directory is None else directory
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix="ghost-letters-analysis-", suffix=".zip", dir=directory)
    os.close(fd)
    target=Path(filename)
    def clean(obj):
        if isinstance(obj, dict):
            return {k:clean(v) for k,v in obj.items() if k not in ("notebooks","comments","analytics")}
        if isinstance(obj,list):
            return [clean(v) for v in obj]
        return obj
    try:
        with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
            def write_json(name,obj):
                z.writestr(name,json.dumps(obj,ensure_ascii=False,indent=2))
            write_json("manifest.json",dict(schema=ANALYTICS_SCHEMA, version=GAME_VERSION, games=len(records),
                deck_sha256=hashlib.sha256((HERE/"deck.json").read_bytes()).hexdigest(),
                privacy="Completed games only; private notebook and free-text ghost comments omitted.",
                duration="Wall-clock elapsed, including pauses; null for pre-update sessions."))
            write_json("statistics.json",statistics(records))
            write_json("deck.json",CARDS)
            buf=io.StringIO()
            fields=["id","date","version","mode","difficulty","players","humans","successes","solved","winner","duration","partial"]
            writer=csv.DictWriter(buf,fieldnames=fields,extrasaction="ignore")
            writer.writeheader()
            for d in records:
                cid=d["id"]
                writer.writerow(case_summary(d))
                record=clean(d)
                record["capture"]={k:v for k,v in d.get("analytics",{}).items() if k != "events"}
                write_json("games/"+cid+".json",record)
                events=d.get("analytics",{}).get("events",[])
                z.writestr("events/"+cid+".jsonl","".join(json.dumps(clean(e),ensure_ascii=False)+"\n" for e in events))
            z.writestr("summary.csv",buf.getvalue())
        return str(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def atmosphere_view():
    # Static public assets only: never encode the active role in the resource map.
    keys = ("ghost", "detective", "killer", "accomplice", "witness", "expert", "back", "table")
    paths = {key: HERE / "assets" / "atmosphere" / f"{key}.webp" for key in keys}
    return {key: str(path) for key, path in paths.items() if path.is_file()}


def public_view(game):
    atmosphere = atmosphere_view()
    if game is None:
        return dict(phase="setup", atmosphere=atmosphere, modes=[dict(key=key, label=label) for key, label in MODES.items()],
                    difficulties=[dict(key=key, label=config[0]) for key, config in DIFFICULTIES.items()])
    view = game.view()
    view["atmosphere"] = atmosphere
    if game.phase == "result":
        detectives = game.d["winner"] == "detectives"
        view["title"] = "Детективы победили" if detectives else ("Дело не раскрыто" if game.cooperative else "Убийца победил")
        view["success"] = detectives
        view["personal_results"] = [dict(name=game.name(pid), role=ROLES[game.d["players"][pid]["role"]][0],
                                         won=pid in game.d["winners"]) for pid in game.d["local"]]
        view["brief"] = ("Дело раскрыто." if detectives else
                         "Дело раскрыто, но убийца вычислил особую роль." if game.d["solved"]
                         else "Стол не собрал достаточно верных ответов.")
    return view


def simulate_game(seed, difficulty="normal", total=6, mode="classic", marked=False):
    """Run the production engine with no human players, no UI, and no state writes."""
    game = Game.new(mode, total, 1, False, marked=marked, difficulty=difficulty, seed=seed)
    for player in game.d["players"]:
        player["local"] = None
    game.d["local"] = []
    game.set_phase("board")
    for _ in range(500):
        if game.phase == "result":
            return game
        if game.actor is not None:
            raise RuntimeError(f"Unexpected human actor in {game.phase}")
        game.advance()
    raise RuntimeError(f"Simulation stuck in {game.phase} for seed {seed}")


def advance_automatically(game, include_intro=True):
    """Execute only public transitions, in their original order, and stop before human input."""
    if len(game.d["local"]) != 1:
        return
    phases = ("intro", "statement") if include_intro else ("statement",)
    for _ in range(24):
        if game.actor is not None or game.phase not in phases:
            return
        game.advance()
        game.d["rev"] += 1
    raise ValueError("Too many automatic steps")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("view", "start", "advance", "submit", "advance_dynamic", "submit_dynamic", "advance_fast", "reset", "notebook", "archive", "case", "export", "collection"))
    parser.add_argument("token", nargs="?", default="-")
    parser.add_argument("payload", nargs="?", default="{}")
    args = parser.parse_args()
    with storage() as path:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        game = Game(data) if data is not None else None
        if game is not None and game.phase == "result":
            archive_game(game)
        if args.action == "collection":
            print(json.dumps(dict(cards=[card_view(i) for i in range(len(CARDS))]),ensure_ascii=False))
            return
        if args.action in ("archive", "case", "export"):
            records = archived_games()
            if args.action == "archive":
                filters = json.loads(args.payload)
                filtered = filter_records(records,filters)
                answer = dict(cases=[case_summary(d) for d in filtered], stats=statistics(filtered, filters.get("role")))
            elif args.action == "case":
                record = next((d for d in records if d["id"] == args.token),None)
                if record is None:
                    raise ValueError("Дело не найдено.")
                answer = dict(case=public_view(Game(record)), summary=case_summary(record))
            else:
                answer = dict(export=export_analysis(records))
            print(json.dumps(answer,ensure_ascii=False))
            return
        if args.action == "view":
            print(json.dumps(public_view(game), ensure_ascii=False))
            return
        if args.action == "start" and game is None:
            config = json.loads(args.payload)
            game = Game.new(**config)
            game.enable_analytics()
            save(path, game.d)
        elif game and args.token == f'{game.d["id"]}:{game.d["rev"]}':
            if args.action == "reset":
                save(path, None)
                game = None
            elif args.action == "notebook":
                game.save_notebook(json.loads(args.payload))
                save(path, game.d)
            elif args.action in ("advance", "submit", "advance_dynamic", "submit_dynamic", "advance_fast"):
                game.enable_analytics(partial=True)
                if args.action.startswith("advance"):
                    game.advance()
                else:
                    game.submit(json.loads(args.payload))
                game.d["rev"] += 1
                if args.action.endswith("_dynamic"):
                    advance_automatically(game)
                elif args.action == "advance_fast":
                    advance_automatically(game, include_intro=False)
                save(path, game.d)
                if game.phase == "result":
                    archive_game(game)
        elif args.action == "notebook":
            raise ValueError("Ход уже изменился.")
        print(json.dumps({"game": public_view(game)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(json.dumps({"error": "Ход не сохранён. Попробуй ещё раз."}, ensure_ascii=False))
        print(str(error), file=sys.stderr)
        sys.exit(1)
