#!/usr/bin/env python3
"""Deterministic all-bot benchmark. Not an estimate of human win rates."""
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path


def load(path):
    spec = importlib.util.spec_from_file_location("benchmark_engine", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scenarios():
    # Classic at every supported seat count, plus representative co-op tables.
    return [(mode, total, marked, difficulty)
            for mode, totals in (("classic", range(4, 13)), ("coop", (2, 3, 5, 8, 12)))
            for total in totals for marked in (False, True)
            for difficulty in ("easy", "normal", "hard")]


def play(module, seed, mode, total, marked, difficulty):
    g = module.Game.new(mode, total, 1, True, marked=marked, difficulty=difficulty, seed=seed)
    # Keep the legacy ghost seat in local[] as a sentinel for old finish_vote(),
    # but no player is human and no private queue can be entered.
    g.d["players"][0]["local"] = None
    # In co-op advance() would select a human ghost if 0 is in local[].
    # Use direct bot truth selection, identical to the public board transition.
    g.d["truth"] = [row[int(g.noise("secret", i) * len(row))]
                    for i, row in enumerate(g.d["board"])]
    g.move_to_opening()
    for step in range(500):
        if g.phase == "result":
            break
        if g.actor is not None:
            raise RuntimeError(f"unexpected local turn: {seed} {g.phase}")
        g.advance()
    else:
        raise RuntimeError(f"stuck game: {seed} {g.phase}")
    d = g.d
    final = [n for n in d["history"] if n["round"] == d["rounds"]]
    unanimity = sum(len({g.note_leads(n).get(str(i)) for n in final}) == 1 for i in range(3))
    rounds = [x for x in d["letters"] if x["round"] > 0]
    return dict(games=1, solved=int(d["solved"]), detective_wins=int(d["winner"] == "detectives"),
                correct=d["successes"], unanimous_categories=unanimity,
                arrested_killer=int(mode != "coop" and d["arrested"] == g.role_id("killer")),
                no_hint_rounds=sum(not g.letter_cards(x) for x in rounds),
                rounds=d["rounds"], ties=sum(1 for tally in d["counts"])- (3 if mode=="coop" else 4) - len(d["excluded"])), d


def run(engine, count, seed_start=0, difficulty=None):
    module = load(engine)
    configs = [c for c in scenarios() if difficulty is None or c[-1] == difficulty]
    rows = defaultdict(Counter)
    roles = defaultdict(Counter)
    levels = defaultdict(Counter)
    for index in range(count):
        seed = seed_start + index
        mode, total, marked, difficulty = configs[index % len(configs)]
        metrics, data = play(module, seed, mode, total, marked, difficulty)
        key = f"{mode}/{total}/{int(marked)}/{difficulty}"
        rows[key].update(metrics)
        levels[difficulty].update(metrics)
        for pid, player in enumerate(data["players"]):
            roles[player["role"]]["games"] += 1
            roles[player["role"]]["wins"] += pid in data["winners"]
    overall = Counter()
    for row in rows.values():
        overall.update(row)
    return {"overall": dict(overall), "by_configuration": {k:dict(v) for k,v in sorted(rows.items())},
            "by_role": {k:dict(v) for k,v in sorted(roles.items())},
            "by_difficulty": {k:dict(v) for k,v in sorted(levels.items())}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine", type=Path, required=True)
    p.add_argument("--games", type=int, default=5000)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seed-start", type=int, default=0)
    p.add_argument("--difficulty", choices=("easy", "normal", "hard"))
    p.add_argument("--replay-seed", type=int)
    p.add_argument("--mode", choices=("classic", "coop"), default="classic")
    p.add_argument("--players", type=int, default=6)
    p.add_argument("--marked", action="store_true")
    args = p.parse_args()
    if args.games < 1:
        p.error("--games must be positive")
    if args.replay_seed is not None:
        metrics, data = play(load(args.engine), args.replay_seed, args.mode, args.players,
                             args.marked, args.difficulty or "normal")
        result = {"overall": metrics, "replay": data}
    else:
        result = run(args.engine, args.games, args.seed_start, args.difficulty)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["overall"], ensure_ascii=False))
    if "by_difficulty" in result:
        print(json.dumps(result["by_difficulty"], ensure_ascii=False))


if __name__ == "__main__":
    main()
