# coding: utf-8
"""Test OverlayParser.

* Do basic tests of the parsr. OverlayParser is like WikidPadParser,
  but with double square brackets instead of single square brackets.



"""
import os
import sys

# run from WikidPad directory
wikidpad_dir = os.path.abspath(u'.')
sys.path.append(os.path.join(wikidpad_dir, u'lib'))
sys.path.append(wikidpad_dir)

from tests.helper import MockWikiDocument, getApp, parse, NodeFinder


LANGUAGE_NAME = 'wikidpad_overlaid_2_0'


def test_parse_wikiwords():
    page_name = u'PageName'
    text_fragments = [  # (text, wikiword)
        (u'WikiWord', u'WikiWord'),
        (u'[[wikiword]]', u'wikiword'),
        (u'WikiWord!anchor', u'WikiWord'),
        (u'[[WikiWord|title]]', u'WikiWord'),
        (u'[[WikiWord|title]]!anchor', u'WikiWord'),
        (u'[[WikiWord#search_fragment]]', u'WikiWord'),
        (u'[[WikiWord#search_fragment|title]]', u'WikiWord'),
        (u'[[WikiWord#search_fragment|title]]!anchor', u'WikiWord'),
        (u'[[.]]', page_name),
        (u'Is sentence [WikiWord].', u'WikiWord'),
        # recognizes WikiWord, but square brackets are not part of it...
        (u'+ Heading\nThis is a sentence.', None),
    ]
    for text_fragment, wikiword in text_fragments:
        text = u'\n%s\n\n' % text_fragment
        ast = parse(text, page_name, LANGUAGE_NAME)
        nf = NodeFinder(ast)
        if wikiword is not None:
            assert nf.count('wikiWord') == 1
            assert nf.wikiWord().wikiWord == wikiword
        else:
            assert nf.count('wikiWord') == 0


def test_generate_text_1():
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    pageName = u'PageName'
    text = u"""
    [[test]]
    """
    wiki_content = {pageName: text}
    wikidoc = MockWikiDocument(wiki_content, LANGUAGE_NAME)
    page = wikidoc.getWikiPage(pageName)
    ast = page.getLivePageAst()
    result = langHelper.generate_text(ast, page)
    assert result == text


def test_generate_text_2():
    pageName = u'PageName'
    wikidoc = MockWikiDocument({pageName: u''}, LANGUAGE_NAME)
    page = wikidoc.getWikiPage(pageName)
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    text_fragments = [
        (u'[[wikiword]]', 'wikiWord'),
        (u'[[wikiword]]!anchor', 'wikiWord'),
        (u'[[wikiword|title]]', 'wikiWord'),
        (u'[[WikiWord|title]]', 'wikiWord'),
        (u'[[wikiword|title]]!anchor', 'wikiWord'),
        (u'[[WikiWord|title]]!anchor', 'wikiWord'),
        (u'[[wikiword#search_fragment]]', 'wikiWord'),
        (u'[[wikiword#search fragment]]', 'wikiWord'),
        (u'[[WikiWord#search# fragment]]', 'wikiWord'),
        (u'[[wikiword#search_fragment]]!anchor', 'wikiWord'),
        (u'[[WikiWord#search_fragment]]!anchor', 'wikiWord'),
        (u'[[wikiword#search_fragment|title]]', 'wikiWord'),
        (u'[[WikiWord#search_fragment|title]]', 'wikiWord'),
        (u'[[wikiword#search_fragment|title]]!anchor', 'wikiWord'),
        (u'[[WikiWord#search-fragment|title]]!anchor', 'wikiWord'),
        (u'WikiWord', 'wikiWord'),
        (u'WikiWord!anchor', 'wikiWord'),
        (u'WikiWord#searchfragment', 'wikiWord'),
        (u'[[key: value]]', 'attribute'),
        (u'[[test: ok; nok]]', 'attribute'),
        (u'[[:page: wikiword]]', 'insertion'),
        (u'this is a sentence', None),
    ]
    for text_fragment, node_name in text_fragments:
        text = u'\n%s\n\n' % text_fragment
        page.setContent(text)
        ast = page.getLivePageAst()
        nf = NodeFinder(ast)
        if node_name:
            assert nf.count(node_name) == 1
        result = langHelper.generate_text(ast, page)
        assert result == text
