#!/usr/bin/env python3
"""Play the radio, YouTube mix, or local playlist in a dedicated mpv instance."""

import fcntl
import json
from pathlib import Path
import random
import socket
import subprocess
import sys
import time


ASSETS = Path(__file__).resolve().parent
CACHE = Path.home() / ".cache/omalauncher-lofi-radio"
SOCKET = CACHE / "player.sock"
SCENE_PATH = CACHE / "scene"
PLAYLISTS_PATH = ASSETS / "playlists.json"
SOURCES = {
    "radio": "https://streams.fluxfm.de/Chillhop/mp3-128/streams.fluxfm.de/",
    "video": "https://www.youtube.com/watch?v=nx32Ue0AAA0",
}


def offline_playlist(playlist_id):
    catalog = json.loads(PLAYLISTS_PATH.read_text(encoding="utf-8"))
    return next((album for album in catalog if album["id"] == playlist_id), catalog[0])


def request(connection, replies, *command):
    connection.sendall(json.dumps({"command": command, "request_id": 1}).encode() + b"\n")
    for line in replies:
        reply = json.loads(line)
        if reply.get("request_id") == 1:
            return reply.get("data")
    raise ConnectionError("mpv disconnected")


def connect():
    connection = socket.socket(socket.AF_UNIX)
    connection.settimeout(0.6)
    try:
        connection.connect(str(SOCKET))
    except OSError:
        connection.close()
        raise
    return connection


def status():
    try:
        with connect() as connection, connection.makefile("rb") as replies:
            path = request(connection, replies, "get_property", "path")
            paused = request(connection, replies, "get_property", "pause")
            buffering = request(connection, replies, "get_property", "core-idle")
            index = request(connection, replies, "get_property", "playlist-pos")
            count = request(connection, replies, "get_property", "playlist-count")
            first = request(connection, replies, "get_property", "playlist/0/filename")
            has_stream = bool(first and first.startswith(("https://", "http://")))
            is_local = bool(path and not path.startswith(("https://", "http://")))
            fallback = request(connection, replies, "get_property", "user-data/lofi-fallback")
            playlist_id = request(connection, replies, "get_property", "user-data/lofi-playlist")
            duration = request(connection, replies, "get_property", "duration") if is_local else None
            position = request(connection, replies, "get_property", "time-pos") if is_local else None
            stream_title = request(connection, replies, "get_property", "metadata/by-key/icy-title") if path == SOURCES["radio"] else None
        mode = next((mode for mode, uri in SOURCES.items() if uri == path), "")
        album = offline_playlist(playlist_id)
        title = None
        if is_local:
            local_track = Path(path)
            title = next(
                (track["title"] for track in album["tracks"] if ASSETS / track["path"] == local_track),
                local_track.stem,
            )
        return {
            "active": True,
            "mode": "offline" if is_local else mode,
            "playing": not paused,
            "buffering": buffering,
            "fallback": fallback is True or (is_local and has_stream and (index or 0) > 0),
            "title": title,
            "playlistId": album["id"],
            "album": album["title"],
            "artist": album["artist"],
            "streamTitle": stream_title.strip() if isinstance(stream_title, str) else "",
            "duration": round(duration or 0, 1),
            "position": position or 0,
            "available": len(album["tracks"]),
            "queued": (count or 0) - int(has_stream),
        }
    except (OSError, ValueError):
        return {"active": False}


def stop():
    try:
        with connect() as connection:
            connection.sendall(b'{"command":["quit"]}\n')
            while connection.recv(4096):
                pass
    except (FileNotFoundError, ConnectionRefusedError, ConnectionResetError):
        pass
    SOCKET.unlink(missing_ok=True)


def start(mode, paused=False, playlist_id="jazz", track_index=None):
    album = offline_playlist(playlist_id)
    playlist = [str(ASSETS / track["path"]) for track in album["tracks"]]
    if track_index is None and album.get("shuffle"):
        random.shuffle(playlist)
    if mode != "offline":
        playlist.insert(0, SOURCES[mode])
    subprocess.Popen(
        [
            "mpv", "--no-config", "--no-video", "--no-terminal", "--network-timeout=8",
            # Match the Android pipe's sample rate and leave headroom for scheduling jitter.
            "--ao=pulse", "--audio-samplerate=48000", "--audio-buffer=1", "--pulse-buffer=500",
            "--ytdl-format=bestaudio/best[height<=360]/best",
            "--loop-playlist=inf", "--script=" + str(ASSETS / "fallback.lua"),
            "--script-opts=lofi-playlist=" + album["id"],
            "--playlist-start=" + str(track_index if track_index is not None else 0),
            "--pause=" + ("yes" if paused else "no"),
            "--input-ipc-server=" + str(SOCKET), *playlist,
        ],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(25):
        try:
            with connect():
                return
        except (FileNotFoundError, ConnectionRefusedError):
            time.sleep(0.04)
    raise OSError("mpv did not open its control socket")


def main():
    action = sys.argv[1]
    if action == "status":
        print(json.dumps(status()))
        return
    CACHE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if action == "scene":
        scene = sys.argv[2]
        catalog = json.loads((ASSETS / "scenes.json").read_text(encoding="utf-8"))
        if scene != "auto" and not any(item["id"] == scene for item in catalog):
            raise ValueError("Unknown animation scene")
        temporary = SCENE_PATH.with_suffix(".tmp")
        with (CACHE / "scene.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            temporary.write_text(scene, encoding="ascii")
            temporary.replace(SCENE_PATH)
        return
    with (CACHE / "player.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = status()
        if action == "stop":
            stop()
        elif action in ("toggle", "pause", "resume"):
            if current["active"]:
                with connect() as connection, connection.makefile("rb") as replies:
                    if action == "toggle":
                        request(connection, replies, "cycle", "pause")
                    else:
                        request(connection, replies, "set_property", "pause", action == "pause")
            elif action == "toggle":
                stop()
                start(sys.argv[2], playlist_id=sys.argv[3] if len(sys.argv) > 3 else "jazz")
        elif action == "select" and current["active"]:
            stop()
            if current["playing"]:
                start(sys.argv[2], playlist_id=sys.argv[3] if len(sys.argv) > 3 else "jazz")
        elif action == "album":
            album = offline_playlist(sys.argv[2])
            track_index = int(sys.argv[3]) if len(sys.argv) > 3 else None
            if track_index is not None and not 0 <= track_index < len(album["tracks"]):
                raise ValueError("Unknown track number")
            stop()
            start("offline", playlist_id=album["id"], track_index=track_index)
        elif action in ("previous", "next") and current.get("mode") == "offline":
            if current["queued"] == 1 and current["available"] > 1:
                stop()
                start("offline", paused=not current["playing"], playlist_id=current["playlistId"])
            else:
                with connect() as connection, connection.makefile("rb") as replies:
                    command = "playlist-prev" if action == "previous" else "playlist-next"
                    request(connection, replies, command, "force")


if __name__ == "__main__":
    main()
