import json
import re
import urllib.parse
from collections import OrderedDict
from pathlib import Path
from typing import List, Dict, Any

import bs4
import ipapy
import requests
from ipapy.ipachar import IPAChar
from ipapy.ipastring import IPAString
from requests_cache import CachedSession
import wikitextparser

_here = Path(__file__).parent


def _init_session():
    secrets_path = _here / 'secrets.json'

    try:
        with open(secrets_path, 'r') as f:
            secrets = json.load(f)
        key = secrets['httpCache']
    except (FileNotFoundError, KeyError):
        raise Exception(f"""Create this file at "{str(secrets_path)}":
    {{ 
        "httpCache": "<arbitrarily generated string>"
    }}""")

    session = CachedSession(cache_name=str(_here / '.http_cache.sqlite'), secret_key=key)
    return session


_wiki_api = 'https://en.wikipedia.org/w/api.php'


def _get_yale(session: requests.Session):
    # noinspection HttpUrlsUsage
    yale_url = 'http://pinyin.info/romanization/yale/basic.html'
    resp = session.get(yale_url)
    t = resp.text
    html = bs4.BeautifulSoup(t, features='html.parser')

    tbody = html.select_one('div#main > table.ruler > tbody')

    def tr_to_pair(tr: bs4.Tag):
        def strip(td: bs4.Tag):
            return td.text.strip()

        row = tr.select('td')
        return strip(row[0]), strip(row[1])

    # noinspection SpellCheckingInspection
    return {**dict(map(tr_to_pair, tbody.select('tr'))), **{
        'ㄥ': 'eng',
        'ㄛ': 'o',
        'ㄘㄟ': 'tsei',
        'ㄖㄨㄚ': 'rwa',
        'ㄎㄟ': 'kei'
    }}


_page_id = 21727674


def _grab_wiki_section(session: requests.Session, page_id: int, section: int):
    # prop=revisions&rvprop=content&format=json&titles=Standard_Chinese_phonology&rvslots=main
    # action=parse&format=json&page=house&prop=wikitext&section=3&disabletoc=1
    s = session.get(_wiki_api, params={
        'format': 'json',
        'action': 'parse',
        'pageid': page_id,
        'section': section,
        'prop': 'text',
        'disabletoc': 1,
        'sectionpreview': 1,
        'disableeditsection': 1
    })
    d = json.loads(s.text)
    e = d['parse']['text']['*']
    print(e)
    exit()
    return e


def compile_chart():
    def dump(obj: Any, filename: str, sort: bool):
        with open(_here / '../recordings' / f'{filename}.json', 'w', encoding='utf8') as dump_file:
            json.dump(obj, dump_file, indent=2, ensure_ascii=True, sort_keys=sort)

    session = _init_session()
    grab = json.loads(_grab_wiki_section(session, _page_id, 6))
    print(json.dumps(grab, indent=2, ensure_ascii=False))
    exit()

    chart_url = 'https://resources.allsetlearning.com/chinese/pronunciation/Pinyin_chart'

    zhuyin_to_yale = _get_yale(session)

    html = bs4.BeautifulSoup(session.get(chart_url).text, features='html.parser')

    table = html.select_one('table#pinyin-table')

    syllables: OrderedDict[str, Dict[str, str]] = OrderedDict()

    ipa_to_wiki = {
        '̯': 'Semivowel',
        'ʰ': 'ʰ',
        't͡ɕ': 't͡ɕ',
        'ɕ': 'ɕ',
    }

    # TODO
    sino_ext = {
        'ɿ': {
            'name': 'laminal denti-alveolar voiced continuant',
            'url': 'https://en.wikipedia.org/wiki/Standard_Chinese_phonology#Syllabic_consonants',
            'extract': "TODO"
        },
        'ʅ': {
            'name': 'apical retroflex voiced continuant',
            'url': 'https://en.wikipedia.org/wiki/Standard_Chinese_phonology#Syllabic_consonants',
            'extract': 'TODO'
        }
    }

    ipa_info = OrderedDict(**sino_ext)

    tr: bs4.Tag
    trs: List[bs4.Tag] = list(table.select('tr'))
    ths = trs[0].select("th,td")
    header_re = re.compile(r"^(?P<is_final>-)?(?P<id>[∅a-uüw-z*]+)(?P<is_initial>-)?$")

    for r, tr in enumerate(trs[1:-1], 1):
        tds = tr.select('th,td')
        td: bs4.Tag
        initial_id = tds[0]['id']
        initial_match = header_re.match(initial_id)
        if not initial_match or initial_match['is_final'] or not initial_match['is_initial']:
            raise ValueError(f"Unexpected initial '{initial_id}'")

        initial = initial_match['id']
        for c, td in enumerate(tds[1:-1], 1):
            if not td.has_attr('id'):
                continue

            final_id = ths[c]['id']
            final_match = header_re.match(final_id)
            if not final_match or final_match['is_initial'] or not final_match['is_final']:
                raise ValueError(f"Unexpected final '{final_id}'")

            final = final_match['id']

            def get_data(name: str):
                return td.select_one(f'div.table-{name}').text.strip()

            id_ = td['id']
            if id_ in syllables:
                raise ValueError(f"duplicate id '{id_}'")

            pinyin = get_data('pinyin')
            if id_ != pinyin:
                raise ValueError(f"Expected '{id_}' == '{pinyin}'")

            ipa = (get_data('ipa')
                   .lstrip('[').rstrip(']')
                   # .replace('ʅ', 'ɻ')
                   # https://en.wikipedia.org/wiki/Sinological_extensions_to_the_International_Phonetic_Alphabet
                   # https://en.wikipedia.org/wiki/Template:Pinyin_table
                   # https://linguistics.stackexchange.com/a/2129
                   # https://www.lotpublications.nl/Documents/526_fulltext.pdf
                   # https://youtu.be/-quzRI-ha6M
                   # https://youtu.be/if9UTOvQkJo
                   # https://en.wikipedia.org/wiki/Standard%20Chinese%20phonology#Syllabic_consonants
                   # https://youtu.be/QMj7rvpoIUo
                   # https://zh.m.wikipedia.org/wiki/%E7%A9%BA%E9%9F%BB
                   # TODO: keep these and resolve links manually
                   # TODO: or just resolve it into standard Mandarin
                   # .replace('ɿ', 'ɹ')
                   )
            invalid_suffix = None

            invalid_chars = ipapy.invalid_ipa_characters(ipa)

            if invalid_chars:
                err = ValueError(f'Unexpected invalid characters in {ipa}')
                if len(invalid_chars) != 1:
                    raise err
                invalid_suffix = invalid_chars.pop()
                if invalid_suffix not in sino_ext:
                    raise err

            ipa_s = IPAString(unicode_string=ipa, ignore=True)
            ipa_c: IPAChar
            ipa_cs = []
            for ipa_c in ipa_s:
                key = ipa_c.unicode_repr
                ipa_cs.append(key)
                if key not in ipa_info:
                    title = ipa_to_wiki.get(key, key + ' (IPA)')
                    resp = session.get(_wiki_api, params={
                        'action': 'query',
                        'format': 'json',
                        'titles': title,
                        'prop': 'extracts',
                        'exintro': 1,
                        'explaintext': 1,
                        'redirects': 1
                    })
                    resp.raise_for_status()
                    result = json.loads(resp.text)
                    pages = list(result['query']['pages'].items())
                    if len(pages) != 1:
                        raise ValueError(f"Expected exactly one page for '{title}'")
                    pid, page_info = pages[0]

                    if int(pid) < 0:
                        raise ValueError(f"English Wikipedia article not found for '{title}'")

                    title_escaped = urllib.parse.quote(page_info['title'].replace(' ', '_'))
                    ipa_info[key] = {
                        'name': ipa_c.name,
                        'url': f"https://en.wikipedia.org/wiki/{title_escaped}",
                        'extract': page_info['extract']
                    }
            if invalid_suffix:
                ipa_cs.append(invalid_suffix)

            url = re.sub(r"^http:", "https:", td.select_one('div.table-link>a[href]')['href'])
            zhuyin = get_data('zhuyin')
            syllables[id_] = {
                'parts': [initial, final],
                'zhuyin': zhuyin,
                'ipa': ipa_cs,
                'yale': zhuyin_to_yale[zhuyin],
                'wadeGiles': get_data('wade-giles'),
                'url': url
            }

    dump(syllables, 'syllables', False)
    dump(ipa_info, 'ipa', True)


if __name__ == '__main__':
    compile_chart()
