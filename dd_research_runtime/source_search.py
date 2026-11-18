"""Read-only scholarly source discovery. Results are bibliographic leads."""
import json
import re
import ssl
import sys
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

MAX_QUERY_LENGTH = 300
MAX_RESPONSE_BYTES = 256 * 1024
RESULT_LIMIT = 8


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def search_publications(query):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= MAX_QUERY_LENGTH:
        raise ValueError('Enter search terms between 1 and 300 characters.')
    params = urlencode({
        'query.bibliographic': query.strip(),
        'rows': RESULT_LIMIT,
        'select': 'DOI,title,publisher',
    })
    request = Request('https://api.crossref.org/works?' + params, headers={
        'Accept': 'application/json',
        'User-Agent': 'DoubleDiamondResearchRuntime/155',
    })
    try:
        handlers = [_NoRedirect()]
        # Some macOS Python installations ship without a configured trust store.
        paths = ssl.get_default_verify_paths()
        system_bundle = Path('/etc/ssl/cert.pem')
        if sys.platform == 'darwin' and not (paths.cafile or paths.capath) and system_bundle.is_file():
            handlers.append(HTTPSHandler(context=ssl.create_default_context(cafile=str(system_bundle))))
        with build_opener(*handlers).open(request, timeout=8) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError('Oversized response')
        items = json.loads(data)['message']['items']
        if not isinstance(items, list):
            raise ValueError('Invalid results')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('Crossref search is unavailable. Try again or add a source you already have.') from exc

    results = []
    seen = set()
    for item in items[:RESULT_LIMIT]:
        if not isinstance(item, dict):
            continue
        doi, titles = item.get('DOI'), item.get('title')
        if not isinstance(doi, str) or not re.fullmatch(r'10\.[0-9]{4,9}/[^\s]{1,240}', doi):
            continue
        if not isinstance(titles, list) or not titles or not isinstance(titles[0], str) or not titles[0].strip():
            continue
        if doi.lower() in seen:
            continue
        seen.add(doi.lower())
        publisher = item.get('publisher')
        results.append({
            'title': titles[0].strip()[:500],
            'publisher': publisher.strip()[:300] if isinstance(publisher, str) else '',
            'url': 'https://doi.org/' + quote(doi, safe='/'),
        })
    return results
