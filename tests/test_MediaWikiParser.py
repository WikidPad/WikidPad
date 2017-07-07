# coding: utf-8
"""Test MediaWikiParser.

* Do basic tests of the parsr. MediaWikiParser is like WikidPadParser, but
  with double square brackets instead of single square brackets, and
  no camelcase wiki words.


"""
import os
import sys

# run from WikidPad directory
wikidpad_dir = os.path.abspath(u'.')
sys.path.append(os.path.join(wikidpad_dir, u'lib'))
sys.path.append(wikidpad_dir)

from tests.helper import MockWikiDocument, NodeFinder, getApp


LANGUAGE_NAME = 'mediawiki_1'


def test_parse_wikiwords():
    page_name = u'PageName'
    text_fragments = [  # (text, is_wikiword)
        (u'WikiWord', None),
        (u'[[wikiword]]', u'wikiword'),
        (u'WikiWord!anchor', None),
        (u'[[WikiWord|title]]', u'WikiWord'),
        (u'[[WikiWord|title]]!anchor', u'WikiWord'),
        (u'[[WikiWord#search_fragment]]', u'WikiWord'),
        (u'[[WikiWord#search_fragment|title]]', u'WikiWord'),
        (u'[[WikiWord#search_fragment|title]]!anchor', u'WikiWord'),
        (u'[[.]]', page_name),
        (u'CamelCase is not seen as a WikiWord.', None),
    ]
    wiki_content = {page_name: u''}
    wikidoc = MockWikiDocument(wiki_content, LANGUAGE_NAME)
    for (text_fragment, wikiword) in text_fragments:
        text = u'\n%s\n\n' % text_fragment
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
    pageName = u'PageName'
    wikidoc = MockWikiDocument({pageName: u''}, LANGUAGE_NAME)
    page = wikidoc.getWikiPage(pageName)
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    text_fragments = [
        (u'[[wikiword]]', 'wikiWord'),  # 1
        (u'[[wikiword]]!anchor', 'wikiWord'),
        (u'[[wikiword|title]]', 'wikiWord'),
        (u'[[WikiWord|title]]', 'wikiWord'),
        (u'[[wikiword|title]]!anchor', 'wikiWord'),
        (u'[[WikiWord|title]]!anchor', 'wikiWord'),
        (u'[[wikiword#search_fragment]]', 'wikiWord'),
        (u'[[wikiword#search fragment]]', 'wikiWord'),
        (u'[[WikiWord#search# fragment]]', 'wikiWord'),
        (u'[[wikiword#search_fragment]]!anchor', 'wikiWord'),  # 10
        (u'[[WikiWord#search_fragment]]!anchor', 'wikiWord'),
        (u'[[wikiword#search_fragment|title]]', 'wikiWord'),
        (u'[[WikiWord#search_fragment|title]]', 'wikiWord'),
        (u'[[wikiword#search_fragment|title]]!anchor', 'wikiWord'),
        (u'[[WikiWord#search_fragment|title]]!anchor', 'wikiWord'),
        (u'WikiWord', None),
        (u'WikiWord!anchor', None),  # 17
        (u'WikiWord#search_fragment', None),
        (u'[[key: value]]', 'attribute'),
        (u'[[test: ok; nok]]', 'attribute'),
        (u'[[:page: wikiword]]', 'insertion'),
        (u'this is a sentence', None),
    ]
    for nr, (text_fragment, node_name) in enumerate(text_fragments, 1):
        text = u'\n%s\n\n' % text_fragment
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
