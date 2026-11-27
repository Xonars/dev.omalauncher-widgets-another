#!/usr/bin/env python3
"""Compare Ghost Letters engines using the same seeds, without touching user saves."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "ghost_letters_game", ROOT / "local/phone-widgets/ghost-letters/game.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--players", type=int, default=6, choices=range(4, 13))
    parser.add_argument("--difficulty", choices=["easy", "normal", "hard", "all"], default="all")
    parser.add_argument("--marked", action="store_true")
    args = parser.parse_args()
    if args.games <= 0:
        parser.error("--games must be positive")
    levels = ("easy", "normal", "hard") if args.difficulty == "all" else (args.difficulty,)
    results = []
    for level in levels:
        stats = dict(difficulty=level, games=args.games, detectives_won=0,
                     clues_solved=0, killer_arrested=0, innocent_arrested=0,
                     empty_rounds=0, rounds=0)
        for seed in range(args.seed, args.seed + args.games):
            g = mod.simulate_game(seed, level, args.players, marked=args.marked)
            stats["detectives_won"] += int(g.d["winner"] == "detectives")
            stats["clues_solved"] += g.d["successes"]
            stats["killer_arrested"] += int(g.d["arrested"] == g.role_id("killer"))
            stats["innocent_arrested"] += int(g.d["arrested"] is not None and
                                              g.d["players"][g.d["arrested"]]["role"] not in ("killer", "accomplice"))
            stats["rounds"] += g.d["rounds"]
            stats["empty_rounds"] += sum(not entry["echo"] and not entry["silence"]
                                         and entry["seal"] is None and not entry.get("extra")
                                         for entry in g.d["letters"] if entry["round"] > 0)
        results.append(stats)
    print(json.dumps(dict(game_version=mod.GAME_VERSION, bot_version=mod.BOT_VERSION,
                          seed=args.seed, players=args.players, marked=args.marked,
                          results=results), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
