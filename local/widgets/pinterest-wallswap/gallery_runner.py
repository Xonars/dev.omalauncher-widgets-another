#!/usr/bin/env python3
"""gallery-dl runner supporting both Pinterest bookmark response formats."""
from gallery_dl import main
from gallery_dl.extractor.pinterest import PinterestAPI


def pagination(self, resource, options):
    seen = set()
    while True:
        result = self._call(resource, options)
        response = result['resource_response']
        items = response['data']
        yield from (items['results'] if isinstance(items, dict) else items)
        bookmarks = result.get('resource', {}).get('options', {}).get('bookmarks') or []
        mark = response.get('bookmark') or (bookmarks[0] if bookmarks else None)
        if not mark or mark == '-end-':
            return
        if mark in seen:
            raise self.extractor.exc.AbortExtraction('Pinterest repeated a pagination bookmark')
        seen.add(mark)
        options['bookmarks'] = [mark]


PinterestAPI._pagination = pagination
if __name__ == '__main__': main()
