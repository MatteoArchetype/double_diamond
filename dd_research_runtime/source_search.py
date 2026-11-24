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


def search_publications(query, *, from_date='', to_date='', publication_type=''):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= MAX_QUERY_LENGTH:
        raise ValueError('Enter search terms between 1 and 300 characters.')
    if not isinstance(from_date,str) or not isinstance(to_date,str) or not isinstance(publication_type,str):
        raise ValueError('Invalid search filters.')
    for _name,value in (('start',from_date),('end',to_date)):
        if value and not re.fullmatch(r'(19|20)\d{2}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?',value):
            raise ValueError('Choose publication dates in YYYY or YYYY-MM-DD format.')
    allowed_types={'','journal-article','proceedings-article','book-chapter','book','report','dataset','dissertation'}
    if publication_type not in allowed_types:
        raise ValueError('Choose a supported publication type.')
    if from_date and to_date and to_date < from_date:
        raise ValueError('The publication end date must not precede the start date.')
    filters=[]
    if from_date:filters.append('from-pub-date:'+from_date)
    if to_date:filters.append('until-pub-date:'+to_date)
    if publication_type:filters.append('type:'+publication_type)
    parameters={
        'query.bibliographic': query.strip(),
        'rows': RESULT_LIMIT,
        'select': 'DOI,title,publisher,author,published-print,published-online,created,type',
    }
    if filters:parameters['filter']=','.join(filters)
    params = urlencode(parameters)
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
    def date_value(item):
        for key in ('published-print','published-online','created'):
            date=item.get(key)
            if not isinstance(date,dict):continue
            parts=date.get('date-parts')
            if not isinstance(parts,list) or not parts or not isinstance(parts[0],list):continue
            values=parts[0]
            if not values or any(type(value) is not int or value<0 for value in values[:3]):continue
            if len(values)==1:return str(values[0])
            if len(values)==2:return f"{values[0]:04d}-{values[1]:02d}"
            return f"{values[0]:04d}-{values[1]:02d}-{values[2]:02d}"
        return ''
    def authors(item):
        rows=item.get('author')
        if not isinstance(rows,list):return ''
        names=[]
        for row in rows[:6]:
            if not isinstance(row,dict):continue
            family=row.get('family')
            given=row.get('given')
            if isinstance(family,str) and family.strip():
                name=family.strip()
                if isinstance(given,str) and given.strip():
                    name=given.strip().split()[0]+' '+name
            elif isinstance(given,str) and given.strip():
                name=given.strip()
            else:
                name=row.get('name')
                name=name.strip() if isinstance(name,str) else ''
            if name:names.append(name[:150])
        if len(rows)>6:names.append('et al.')
        return '; '.join(names)[:500]
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
        publication_type=item.get('type')
        result={
            'title': titles[0].strip()[:500],
            'publisher': publisher.strip()[:300] if isinstance(publisher, str) else '',
            'url': 'https://doi.org/' + quote(doi, safe='/'),
            'authors': authors(item),
            'date': date_value(item),
            'type': publication_type.strip()[:100] if isinstance(publication_type,str) else '',
        }
        results.append({key:value for key,value in result.items() if key not in {'authors','date','type'} or value})
    return results
