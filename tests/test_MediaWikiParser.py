# coding: utf-8
"""Test MediaWikiParser.

* Do basic tests of the parsr. MediaWikiParser is like WikidPadParser, but
  with double square brackets instead of single square brackets, and
  no camelcase wiki words.


"""
import os
import sys

# run from WikidPad directory
wikidpad_dir = os.path.abspath('.')
sys.path.append(os.path.join(wikidpad_dir, 'lib'))
sys.path.append(wikidpad_dir)

from tests.helper import MockWikiDocument, NodeFinder, getApp


LANGUAGE_NAME = 'mediawiki_1'


def test_parse_wikiwords():
    page_name = 'PageName'
    text_fragments = [  # (text, is_wikiword)
        ('WikiWord', None),
        ('[[wikiword]]', 'wikiword'),
        ('WikiWord!anchor', None),
        ('[[WikiWord|title]]', 'WikiWord'),
        ('[[WikiWord|title]]!anchor', 'WikiWord'),
        ('[[WikiWord#search_fragment]]', 'WikiWord'),
        ('[[WikiWord#search_fragment|title]]', 'WikiWord'),
        ('[[WikiWord#search_fragment|title]]!anchor', 'WikiWord'),
        ('[[.]]', page_name),
        ('CamelCase is not seen as a WikiWord.', None),
    ]
    wiki_content = {page_name: ''}
    wikidoc = MockWikiDocument(wiki_content, LANGUAGE_NAME)
    for (text_fragment, wikiword) in text_fragments:
        text = '\n%s\n\n' % text_fragment
        page = wikidoc.getWikiPage(page_name)
        page.setContent(text)
        ast = page.getLivePageAst()
        nf = NodeFinder(ast)
        if wikiword is not None:
            assert nf.count('wikiWord') == 1
            assert nf.wikiWord().wikiWord == wikiword
        else:
            assert not nf.count('wikiWord')


def test_generate_text():
    pageName = 'PageName'
    wikidoc = MockWikiDocument({pageName: ''}, LANGUAGE_NAME)
    page = wikidoc.getWikiPage(pageName)
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    text_fragments = [
        ('[[wikiword]]', 'wikiWord'),  # 1
        ('[[wikiword]]!anchor', 'wikiWord'),
        ('[[wikiword|title]]', 'wikiWord'),
        ('[[WikiWord|title]]', 'wikiWord'),
        ('[[wikiword|title]]!anchor', 'wikiWord'),
        ('[[WikiWord|title]]!anchor', 'wikiWord'),
        ('[[wikiword#search_fragment]]', 'wikiWord'),
        ('[[wikiword#search fragment]]', 'wikiWord'),
        ('[[WikiWord#search# fragment]]', 'wikiWord'),
        ('[[wikiword#search_fragment]]!anchor', 'wikiWord'),  # 10
        ('[[WikiWord#search_fragment]]!anchor', 'wikiWord'),
        ('[[wikiword#search_fragment|title]]', 'wikiWord'),
        ('[[WikiWord#search_fragment|title]]', 'wikiWord'),
        ('[[wikiword#search_fragment|title]]!anchor', 'wikiWord'),
        ('[[WikiWord#search_fragment|title]]!anchor', 'wikiWord'),
        ('WikiWord', None),
        ('WikiWord!anchor', None),  # 17
        ('WikiWord#search_fragment', None),
        ('[[key: value]]', 'attribute'),
        ('[[test: ok; nok]]', 'attribute'),
        ('[[:page: wikiword]]', 'insertion'),
        ('this is a sentence', None),
    ]
    for nr, (text_fragment, node_name) in enumerate(text_fragments, 1):
        text = '\n%s\n\n' % text_fragment
        page.setContent(text)
        ast = page.getLivePageAst()
        nf = NodeFinder(ast)
        if node_name:
            assert nf.count(node_name) == 1, nr
        else:
            assert not nf.count('wikiWord'), nr
            assert not nf.count('attribute'), nr
            assert not nf.count('insertion'), nr
        result = langHelper.generate_text(ast, page)
        assert result == text
