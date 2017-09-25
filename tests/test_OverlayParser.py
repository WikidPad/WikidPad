# coding: utf-8
"""Test OverlayParser.

* Do basic tests of the parsr. OverlayParser is like WikidPadParser,
  but with double square brackets instead of single square brackets.



"""
import os
import sys

# run from WikidPad directory
wikidpad_dir = os.path.abspath('.')
sys.path.append(os.path.join(wikidpad_dir, 'lib'))
sys.path.append(wikidpad_dir)

from tests.helper import MockWikiDocument, getApp, parse, NodeFinder


LANGUAGE_NAME = 'wikidpad_overlaid_2_0'


def test_parse_wikiwords():
    page_name = 'PageName'
    text_fragments = [  # (text, wikiword)
        ('WikiWord', 'WikiWord'),
        ('[[wikiword]]', 'wikiword'),
        ('WikiWord!anchor', 'WikiWord'),
        ('[[WikiWord|title]]', 'WikiWord'),
        ('[[WikiWord|title]]!anchor', 'WikiWord'),
        ('[[WikiWord#search_fragment]]', 'WikiWord'),
        ('[[WikiWord#search_fragment|title]]', 'WikiWord'),
        ('[[WikiWord#search_fragment|title]]!anchor', 'WikiWord'),
        ('[[.]]', page_name),
        ('Is sentence [WikiWord].', 'WikiWord'),
        # recognizes WikiWord, but square brackets are not part of it...
        ('+ Heading\nThis is a sentence.', None),
    ]
    for text_fragment, wikiword in text_fragments:
        text = '\n%s\n\n' % text_fragment
        ast = parse(text, page_name, LANGUAGE_NAME)
        nf = NodeFinder(ast)
        if wikiword is not None:
            assert nf.count('wikiWord') == 1
            assert nf.wikiWord().wikiWord == wikiword
        else:
            assert nf.count('wikiWord') == 0


def test_generate_text_1():
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    pageName = 'PageName'
    text = """
    [[test]]
    """
    wiki_content = {pageName: text}
    wikidoc = MockWikiDocument(wiki_content, LANGUAGE_NAME)
    page = wikidoc.getWikiPage(pageName)
    ast = page.getLivePageAst()
    result = langHelper.generate_text(ast, page)
    assert result == text


def test_generate_text_2():
    pageName = 'PageName'
    wikidoc = MockWikiDocument({pageName: ''}, LANGUAGE_NAME)
    page = wikidoc.getWikiPage(pageName)
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    text_fragments = [
        ('[[wikiword]]', 'wikiWord'),
        ('[[wikiword]]!anchor', 'wikiWord'),
        ('[[wikiword|title]]', 'wikiWord'),
        ('[[WikiWord|title]]', 'wikiWord'),
        ('[[wikiword|title]]!anchor', 'wikiWord'),
        ('[[WikiWord|title]]!anchor', 'wikiWord'),
        ('[[wikiword#search_fragment]]', 'wikiWord'),
        ('[[wikiword#search fragment]]', 'wikiWord'),
        ('[[WikiWord#search# fragment]]', 'wikiWord'),
        ('[[wikiword#search_fragment]]!anchor', 'wikiWord'),
        ('[[WikiWord#search_fragment]]!anchor', 'wikiWord'),
        ('[[wikiword#search_fragment|title]]', 'wikiWord'),
        ('[[WikiWord#search_fragment|title]]', 'wikiWord'),
        ('[[wikiword#search_fragment|title]]!anchor', 'wikiWord'),
        ('[[WikiWord#search-fragment|title]]!anchor', 'wikiWord'),
        ('WikiWord', 'wikiWord'),
        ('WikiWord!anchor', 'wikiWord'),
        ('WikiWord#searchfragment', 'wikiWord'),
        ('[[key: value]]', 'attribute'),
        ('[[test: ok; nok]]', 'attribute'),
        ('[[:page: wikiword]]', 'insertion'),
        ('this is a sentence', None),
    ]
    for text_fragment, node_name in text_fragments:
        text = '\n%s\n\n' % text_fragment
        page.setContent(text)
        ast = page.getLivePageAst()
        nf = NodeFinder(ast)
        if node_name:
            assert nf.count(node_name) == 1
        result = langHelper.generate_text(ast, page)
        assert result == text
