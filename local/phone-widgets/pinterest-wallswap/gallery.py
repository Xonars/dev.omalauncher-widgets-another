#!/usr/bin/env python3
"""Board gallery using downloaded files when available, public pins otherwise."""
import contextlib
import io
import json
import sys
import downloads
import pinterest


def gallery(cfg):
    board_id = cfg['boards'][0]
    local, job = downloads.local_items(board_id)
    if local or job.get('status') == 'completed':
        return dict(boardId=board_id, items=local, more=False)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        pinterest.candidates(cfg)
    items = []
    for line in output.getvalue().splitlines():
        image, title, credit, page, width, height = line.split('\t')
        items.append(dict(image=image, title=title, credit=credit, page=page,
                          width=int(width or 0), height=int(height or 0)))
    cache = pinterest.read(pinterest.ROOT / ('pins-' + board_id + '.json'))
    return dict(boardId=board_id, items=items,
                more=bool(cache.get('bookmark') and cache['bookmark'] != '-end-' and len(cache['pins']) < 1000))


if __name__ == '__main__':
    cfg = json.loads(sys.argv[1])
    try:
        result = gallery(cfg)
    except Exception as error:
        result = dict(boardId=cfg['boards'][0], items=[], error=str(error), more=False)
    print(json.dumps(result, ensure_ascii=False))
