# coding: utf-8
"""Test WikidPadParser.

* Do basic tests of the parser.
* Test WikiLinkPath.
* Test creating and resolving wiki links.
* Test text generator.

  To test the text generator, run over the *complete* WikidPadHelp wiki:
  parse each page, generate text from the page's AST using the text
  generator, and check if generated text matches the original text, see
  test_generate_WikidPadHelp.

  At first, I did find some differences, but it turned out that these
  literal differences are in fact no errors, but small differences in syntax
  with the same semantics, e.g., [key:  value  ] is equal to [key: value]
  (note no extra spaces). I annotated these to mark the real errors (in
  fact I did not find any real errors) and stored them in an annotation
  file. The test loads these annotations and takes them into account when
  evaluating the output of the text generator (so that literal differences
  with the same semantics will not be reported as errors). The annotations
  are stored in WIKIDPADHELP_ANNOTATIONS.

  WIKIDPADHELP_DATA_DIR points to the location of the WikidPadHelp wiki.

"""
from collections import defaultdict
import glob
import io
import os
import re
import sys

import pytest

# run from WikidPad directory
wikidpad_dir = os.path.abspath(u'.')
sys.path.append(wikidpad_dir)
sys.path.append(os.path.join(wikidpad_dir, u'lib'))

from tests.helper import (
    TESTS_DIR, get_text, parse, MockWikiDocument, getApp,
    WikiWordNotFoundException, NodeFinder, ast_eq)


LANGUAGE_NAME = 'wikidpad_default_2_0'
WIKIDPADHELP_DATA_DIR = os.path.abspath(u'WikidPadHelp/data')
WIKIDPADHELP_ANNOTATIONS = os.path.join(
    TESTS_DIR, u'WikidPadHelp_WikidPadParser_annotations.txt')


def test_parse_1():
    """
    getLivePageAst
    """
    text = u"""+ Heading 1

This is a sentence.

"""
    wiki_content = {u'TestPage': text}
    wikidoc = MockWikiDocument(wiki_content, LANGUAGE_NAME)
    page = wikidoc.getWikiPage(u'TestPage')
    ast = page.getLivePageAst()
    nf = NodeFinder(ast)
    assert nf.count('heading') == 1
    assert nf.count('wikiWord') == 0
    assert nf.heading.headingContent().getString() == u'Heading 1'
    ast_ = parse(text, u'TestPage', LANGUAGE_NAME)
    assert ast_eq(ast, ast_)


def test_parse_2():
    text = u"""+ WikidPad

http://wikidpad.sourceforge.net/

WikidPad is an open source, [Python]-based wiki-like outliner for storing
thoughts, ideas, to-do lists, contacts, and other notes with wiki-like
linking between pages.

WikidPad!Help


++ Features

    * On the fly WikiWord linking, as you type
    * WikiWord auto-completion
    * Easy WikiWord navigation
    * Wiki text styling
    * ...


anchor:Help
++ Help

A complete online documentation for beginners and advanced users is here: GettingStarted.


WikiDocumentAttributes#*short_hint*

"""
    ast = parse(text, u'WikidPad', LANGUAGE_NAME)
    nf = NodeFinder(ast)
    assert nf.count('heading') == 3
    assert nf.count('urlLink') == 1
    assert nf.count('wikiWord') == 9  # title is also a wikiword...!
    assert nf.count('anchorDef') == 1
    assert nf.count('unorderedList') == 1
    assert nf.heading.headingContent().getString() == u'WikidPad'
    assert nf.urlLink().url == u'http://wikidpad.sourceforge.net/'
    ww_3_node = nf.wikiWord_3()
    assert ww_3_node.wikiWord == u'Python'
    assert ww_3_node.linkPath.getLinkCore() == u'Python'
    ww_9_node = nf.wikiWord_9()
    assert ww_9_node.wikiWord == u'WikiDocumentAttributes'
    assert ww_9_node.linkPath.getLinkCore() == u'WikiDocumentAttributes'
    assert ww_9_node.anchorLink is None
    assert ww_9_node.fragmentNode is not None
    assert ww_9_node.searchFragment == u'*short_hint*'
    assert ww_9_node.titleNode is None
    begin = nf.unorderedList.bullet_3().pos
    end = nf.unorderedList.bullet_4().pos
    assert text[begin:end] == u'* Easy WikiWord navigation\n    '
    assert nf.wikiWord_4().anchorLink == u'Help'
    assert nf[0].name == 'heading'
    assert nf[231].name == 'heading'
    assert nf[401].name == 'heading'

    wiki_content = {u'WikidPad': text}
    wikidoc = MockWikiDocument(wiki_content, LANGUAGE_NAME)
    page = wikidoc.getWikiPage(u'WikidPad')
    ast_ = page.getLivePageAst()
    assert ast_eq(ast, ast_)


def test_parse_wikiwords():
    """
    assert text fragments are recognized as wiki words by parser
    """
    text_fragments = [  # (text, wikiword)
        (u'WikiWord', u'WikiWord'),
        (u'[wikiword]', u'wikiword'),
        (u'WikiWord!anchor', u'WikiWord'),
        (u'[WikiWord|title]', u'WikiWord'),
        (u'[WikiWord|title]!anchor', u'WikiWord'),
        (u'[wikiword]#searchfragment', u'wikiword'),
        (u'[wikiword#searchfragment]', u'wikiword'),
        (u'WikiWord#searchfragment', u'WikiWord'),
        (u'WikiWord#search# fragment', u'WikiWord'),
        (u'[WikiWord#search fragment]', u'WikiWord'),
        (u'[wikiword#search fragment]', u'wikiword'),
        (u'[WikiWord#searchfragment|title]', u'WikiWord'),
        (u'[WikiWord#searchfragment|title]!anchor', u'WikiWord'),
        (u'[.]', u'PageName'),
        (u'This is a sentence', None),
        (u'+ Heading\n\n    * item\n    * item 2\n\n', None),
        (u'wikiword', None),
        (u'wikiword!thisisnotananchor', None),
        (u'wikiword#hash', None),
        (u'wikiword|thisisnotitle', None),
    ]
    wiki_content = {u'PageName': u''}
    wikidoc = MockWikiDocument(wiki_content, LANGUAGE_NAME)
    for (text_fragment, wikiword) in text_fragments:
        text = u'\n%s\n\n' % text_fragment
        page = wikidoc.getWikiPage(u'PageName')
        page.setContent(text)
        ast = page.getLivePageAst()
        assert ast.getString() == text
        nf = NodeFinder(ast)
        if wikiword is not None:
            assert nf.count('wikiWord') == 1
            assert nf.wikiWord().wikiWord == wikiword
        else:
            assert nf.count('wikiWord') == 0


def parse_columns(columns):
    # x | y | z
    # x | y -> z
    # x -> y | z
    # x <- y | z
    # x | y -> z
    # ans['left_to_right'] = [(x,y,z), ...]
    # ans['right_to_left'] = [(x,y,z), ...]
    column_sep = re.compile(ur'->|<-|\|')

    def g(w):
        w = w.strip()
        if w == u'EMPTY_LIST':
            return []
        elif w == u'EMPTY_STRING':
            return u''
        elif w == u'ASSERTION_ERROR':
            return AssertionError()
        elif w == u'VALUE_ERROR':
            return ValueError()
        elif w == u'None':
            w = None
        else:
            return w

    def split_column_line(line):
        return [g(s.strip()) for s in column_sep.split(line)]

    ans = dict(left_to_right=[], right_to_left=[])
    for line in columns.splitlines():
        line = line.strip()
        if not line or line.startswith(u'#'):
            continue
        x, y, z = split_column_line(line)
        if u'->' in line:
            ans['left_to_right'].append((x, y, z))
        elif u'<-' in line:
            ans['right_to_left'].append((x, y, z))
        else:
            ans['left_to_right'].append((x, y, z))
            ans['right_to_left'].append((x, y, z))
    return ans


def test_WikiLinkPath_init():
    """
    WikiLinkPath(linkCore)
    WikiLinkPath(upwardCount, components)
    """
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    WikiLinkPath = langHelper.WikiLinkPath
    test_values = u"""
    #
    # linkCore              <->  upwardCount     |  components
    #
    # ABSOLUTE LINKS

       //pagename            |       -1          |   pagename
       //a/b                 |       -1          |   a b
       VALUE_ERROR          <-       -1          |   EMPTY_LIST
       //                    ->  VALUE_ERROR     |   VALUE_ERROR

    # RELATIVE LINKS

       /                     ->  VALUE_ERROR     |   VALUE_ERROR
       /d/e                  |        0          |   d e
       /d                    |        0          |   d
       .                     |        0          |   EMPTY_LIST
       x                     |        1          |   x
       a/b                   |        1          |   a b
       ..                    |        1          |   EMPTY_LIST
       ../                   ->  VALUE_ERROR     |   VALUE_ERROR
       ../c                  |        2          |   c
       ../x                  |        2          |   x
       ../x/                 ->  VALUE_ERROR     |   VALUE_ERROR
       ../..                 |        2          |   EMPTY_LIST
       ../../..              |        3          |   EMPTY_LIST
       ../../Amazon          |        3          |   Amazon
       ../../Super/SubPage   |        3          |   Super SubPage
       ../../d               |        3          |   d
       ../../c/d             |        3          |   c d
       ../../../d/e          |        4          |   d e
       ../../../d/e/f        |        4          |   d e f
       ../../../d/e/f/       ->  VALUE_ERROR     |   VALUE_ERROR

       EMPTY_STRING          ->  VALUE_ERROR     |   VALUE_ERROR
    """

    values = parse_columns(test_values)

    def tests(direction):
        for linkCore, upwardCount, components in values[direction]:
            if not isinstance(upwardCount, Exception):
                upwardCount = int(upwardCount)
            if not isinstance(components, Exception):
                if not isinstance(components, list):
                    components = components.split()
            yield linkCore, upwardCount, components

    def left_to_right_err_msg_1():
        msg = u'%r -> upwardCount = %d != %d'
        return msg % (linkCore, res.upwardCount, upwardCount)

    def left_to_right_err_msg_2():
        msg = u'%r -> components = %r != %r'
        return msg % (linkCore, res.components, components)

    def left_to_right_err_msg_3():
        return u'%r !-> %r' % (linkCore, upwardCount)

    # ->
    for linkCore, upwardCount, components in tests('left_to_right'):
        if not isinstance(upwardCount, Exception):
            res = WikiLinkPath(linkCore=linkCore)
            assert res.upwardCount == upwardCount, left_to_right_err_msg_1()
            assert res.components == components, left_to_right_err_msg_2()
        else:
            exc = type(upwardCount)
            with pytest.raises(exc, message=left_to_right_err_msg_3()):
                WikiLinkPath(linkCore=linkCore)

    def right_to_left_err_msg_1():
        return u'%d, %r -> %r != %r' % (upwardCount, components, res, linkCore)

    def right_to_left_err_msg_2():
        return u'%d, %r !-> %r' % (upwardCount, components, linkCore)

    # <-
    for linkCore, upwardCount, components in tests('right_to_left'):
        if not isinstance(linkCore, Exception):
            res = WikiLinkPath(upwardCount=upwardCount, components=components)
            res = res.getLinkCore()
            assert res == linkCore, right_to_left_err_msg_1()
        else:
            exc = type(linkCore)
            with pytest.raises(exc, message=right_to_left_err_msg_2()):
                WikiLinkPath(upwardCount=upwardCount, components=components)


def test_WikiLinkPath_getLinkCore():
    """
    WikiLinkPath(linkCore).getLinkCore()
    """
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    WikiLinkPath = langHelper.WikiLinkPath
    test_values = u"""
    ## linkCore

        //                      VALUE_ERROR
        //pagename/a/b
        //pagename/a/b/         VALUE_ERROR
        //pagename/a
        //pagename
        /a/b/c
        /a/b
        /a
        .
        a
        a/b
        a/b/c
        ..
        ../a
        ../../a
        ../a/b
        ../a/b/c
        ../                     VALUE_ERROR
        ../..
        ../../                  VALUE_ERROR
        ../../..
        EMPTY_STRING            VALUE_ERROR
    """

    def tests():
        for line in test_values.splitlines():
            line = line.strip()
            if not line or line.startswith(u'#'):
                continue
            try:
                linkCore, exception = line.split()
            except ValueError:
                linkCore, exception = line, None
            if linkCore == u'EMPTY_STRING':
                linkCore = u''
            if exception == u'VALUE_ERROR':
                exception = ValueError()
            yield linkCore, exception

    def err_msg_1():
        return u'linkCore of %r = %r != %r' % (linkCore, res, linkCore)

    for linkCore, exception in tests():
        if exception is None:
            res = WikiLinkPath(linkCore=linkCore).getLinkCore()
            assert res == linkCore, err_msg_1()
        else:
            with pytest.raises(type(exception)):
                WikiLinkPath(linkCore=linkCore)


def test_WikiLinkPath_join():
    """
    WikiLinkPath(linkCore).join(other)
    WikiLinkPath(linkCore).joinTo(other)
    """
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    WikiLinkPath = langHelper.WikiLinkPath
    test_values = u"""
    ## linkCore                |  otherLinkCore   ->  joinedLinkCore

       //a/b                   |  //b             ->  //b
       //a                     |  //b             ->  //b
       /a                      |  //b             ->  //b
       /a/b                    |  //b             ->  //b
       .                       |  //b             ->  //b
       a                       |  //b             ->  //b
       a/b                     |  //b             ->  //b
       ..                      |  //b             ->  //b
       ../a                    |  //b             ->  //b
       ../..                   |  //b             ->  //b
       ../../a                 |  //b             ->  //b

       //a                     |  /c              ->  //a/c
       //a/b                   |  /c              ->  //a/b/c
       /a                      |  /c              ->  /a/c
       /a/b                    |  /c              ->  /a/b/c
       .                       |  /c              ->  /c
       a                       |  /c              ->  a/c
       a/b                     |  /c              ->  a/b/c
       ..                      |  /c              ->  c
       ../a                    |  /c              ->  ../a/c
       ../..                   |  /c              ->  ../c
       ../../a                 |  /c              ->  ../../a/c

       //a                     |  .               ->  //a
       //a/b                   |  .               ->  //a/b
       /a                      |  .               ->  /a
       /a/b                    |  .               ->  /a/b
       .                       |  .               ->  .
       a                       |  .               ->  a
       a/b                     |  .               ->  a/b
       ..                      |  .               ->  ..
       ../a                    |  .               ->  ../a
       ../..                   |  .               ->  ../..
       ../../a                 |  .               ->  ../../a

       //a                     |  c               ->  //c
       //a/b                   |  c               ->  //a/c
       /a                      |  c               ->  /c
       /a/b                    |  c               ->  /a/c
       .                       |  c               ->  c
       a                       |  c               ->  c
       a/b                     |  c               ->  a/c
       ..                      |  c               ->  ../c
       ../a                    |  c               ->  ../c
       ../..                   |  c               ->  ../../c
       ../../a                 |  c               ->  ../../c

       //a                     |  ..              ->  VALUE_ERROR
       //a/b                   |  ..              ->  //a
       /a                      |  ..              ->  .
       /a/b                    |  ..              ->  /a
       .                       |  ..              ->  ..
       a                       |  ..              ->  ..
       a/b                     |  ..              ->  a
       ..                      |  ..              ->  ../..
       ../a                    |  ..              ->  ../..
       ../..                   |  ..              ->  ../../..
       ../../a                 |  ..              ->  ../../..

       //a                     |  ../c            ->  VALUE_ERROR
       //a/b                   |  ../c            ->  //c
       /a                      |  ../c            ->  c
       /a/b                    |  ../c            ->  /c
       .                       |  ../c            ->  ../c
       a                       |  ../c            ->  ../c
       a/b                     |  ../c            ->  c
       ..                      |  ../c            ->  ../../c
       ../a                    |  ../c            ->  ../../c
       ../..                   |  ../c            ->  ../../../c
       ../../a                 |  ../c            ->  ../../../c

       //a                     |  ../..           ->  VALUE_ERROR
       //a/b                   |  ../..           ->  VALUE_ERROR
       /a                      |  ../..           ->  ..
       .                       |  ../..           ->  ../..
       a                       |  ../..           ->  ../..
       a/b                     |  ../..           ->  ..
       ..                      |  ../..           ->  ../../..
       ../a                    |  ../..           ->  ../../..
       ../..                   |  ../..           ->  ../../../..
       ../../a                 |  ../..           ->  ../../../..

       //a                     |  ../../..        ->  VALUE_ERROR
       //a/b                   |  ../../..        ->  VALUE_ERROR
       /a                      |  ../../..        ->  ../..
       .                       |  ../../..        ->  ../../..
       a                       |  ../../..        ->  ../../..
       a/b                     |  ../../..        ->  ../..
       ..                      |  ../../..        ->  ../../../..
       ../a                    |  ../../..        ->  ../../../..
       ../..                   |  ../../..        ->  ../../../../..
       ../../a                 |  ../../..        ->  ../../../../..
    """

    values = parse_columns(test_values)

    def tests(direction):
        return values[direction]

    def err_msg_1():
        msg = u'%r joined with %r != %r'
        return msg % (linkCore, otherLinkCore, joinedLinkCore)

    def err_msg_2():
        msg = u'%r joined with %r !-> %r'
        return msg % (linkCore, otherLinkCore, joinedLinkCore)

    for linkCore, otherLinkCore, joinedLinkCore in tests('left_to_right'):
        linkPath = WikiLinkPath(linkCore=linkCore)
        otherLinkPath = WikiLinkPath(linkCore=otherLinkCore)

        if not isinstance(joinedLinkCore, Exception):
            joinedPath = WikiLinkPath(linkCore=joinedLinkCore)
            res = linkPath.joinTo(otherLinkPath)
            assert res == joinedPath, err_msg_1()
        else:
            exc = type(joinedLinkCore)
            with pytest.raises(exc, message=err_msg_2()):
                linkPath.joinTo(otherLinkPath)


def test_WikiLinkPath_getRelativePathByAbsPaths():
    """
    WikiLinkPath.getRelativePathByAbsPaths(targetAbsPath, baseAbsPath,
                                           downwardOnly=False)
    """
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    WikiLinkPath = langHelper.WikiLinkPath
    test_values = u"""
    ## targetPageName     |  basePageName        ->  rel. linkCore

       pagename           |  pagename            ->  pagename
       a                  |  b                   ->  a
       a                  |  a                   ->  a
       a                  |  a/a                 ->  ..
       a                  |  a/b                 ->  ..
       a                  |  b/c                 ->  ../a
       a                  |  b/c/d               ->  ../../a

       a/b                |  c                   ->  a/b
       a/b                |  c/d                 ->  ../a/b
       a/b                |  c/d/e               ->  ../../a/b
       a/b                |  a/b                 ->  b
       a/b                |  a/b/c               ->  ..
       a/b                |  a/b/c/d             ->  ../..

       a/b/c              |  d                   ->  a/b/c
       a/b/c              |  a                   ->  /b/c
       a/b/c              |  a/b                 ->  /c
       a/b/c              |  a/b/c               ->  c
       a/b/c              |  a/b/d               ->  c
       a/b/c              |  a/b/d/e             ->  ../c

       Super/SubPage      |  Main/SubPage2       ->  ../Super/SubPage
       Bar                |  Bar/SubPage         ->  ..
       main1renamed       |  main1renamed/sub    -> ..
    """

    values = parse_columns(test_values)

    def tests(direction):
        return values[direction]

    def err_msg_1():
        msg = u'link to %r on %r = %r != %r'
        return msg % (targetPageName, basePageName, res, linkCore)

    def err_msg_2():
        msg = u'link to %r on %r !-> %r'
        return msg % (targetPageName, basePageName, linkCore)

    # ->
    for targetPageName, basePageName, linkCore in tests('left_to_right'):
        target = WikiLinkPath(pageName=targetPageName)
        base = WikiLinkPath(pageName=basePageName)

        if not isinstance(linkCore, Exception):
            res = WikiLinkPath.getRelativePathByAbsPaths(target, base,
                                                         downwardOnly=False)
            res = res.getLinkCore() if res is not None else None
            assert res == linkCore, err_msg_1()
        else:
            exc = type(linkCore)
            with pytest.raises(exc, message=err_msg_2()):
                WikiLinkPath.getRelativePathByAbsPaths(target, base,
                                                       downwardOnly=False)


def test_WikiLink_resolve_and_create():
    """
    Resolve
    -------

    1. langHelper.resolveWikiWordLink(linkCore, basePage)
        == WikidPadParser.resolveWikiWordLink

    2. WikiLinkPath(linkCore).resolveWikiWord(basePath)


    Create
    ------

    1. langHelper.createRelativeLinkFromWikiWord(pageName, basePageName,
                                                 downwardOnly=False)

    2. langHelper.createWikiLinkPathFromPageName(targetPageName, basePageName,
                                                 absolute)

    """
    wikidoc = MockWikiDocument(None, LANGUAGE_NAME)
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    WikiLinkPath = langHelper.WikiLinkPath
    test_values = u"""
    ## linkCore            |  basePageName              |  targetPageName
    ##                    <- = create                   -> = resolve

    ## ABSOLUTE LINKS

    //ebay/Circlet         |  PageName                  |  ebay/Circlet
    //ebay/Circlet         |  ebay                      |  ebay/Circlet
    //ebay/Circlet         |  ebay/Circlet              |  ebay/Circlet
    //Foo/SubPage          |  PageName                  |  Foo/SubPage
    //Foo/SubPage          |  Foo                       |  Foo/SubPage
    //Foo/Foo              |  Foo                       |  Foo/Foo
    //Foo/Foo/Foo          |  Foo                       |  Foo/Foo/Foo

    ## RELATIVE LINKS

    /Couch                 |  ebay                      |  ebay/Couch
    /Couch                 |  ebay/Furniture            |  ebay/Furniture/Couch
    /Circlet               |  ebay                      |  ebay/Circlet
    /d/e                   |  a/b/c                     |  a/b/c/d/e
    /d                     |  a/b/c                     |  a/b/c/d
    /SubPage               |  Foo                       |  Foo/SubPage
    /Foo                   |  Foo                       |  Foo/Foo

    SubPage                |  Super/SubPage2            |  Super/SubPage
    SubPage               <-  Main/SubPage2             |  Main/SubPage
    WikiWord               |  PageName                  |  WikiWord
    Chaise                 |  ebay/Couch                |  ebay/Chaise
    Circlet                |  ebay/Cerebrum             |  ebay/Circlet
    OldCar                 |  ebay/Cerebrum             |  ebay/OldCar
    x                      |  a/b/c                     |  a/b/x
    ebay/Circlet           |  PageName                  |  ebay/Circlet
    Foo/SubPage            |  PageName                  |  Foo/SubPage

    .                      |  a/b/c                     ->  a/b/c
    c                      |  a/b/c                     ->  a/b/c
    c                     <-  a/b/c                     |  a/b/c
    .                      |  _                         ->  _
    .                      |  a/b/c                     -> a/b/c
    ../../a/b/c            |  a/b/c                     -> a/b/c
    Foo                    |  Foo                       -> Foo
    .                      |  Foo                       ->  Foo
    Foo                   <-  Foo                       |  Foo

    ..                     |  a/b/c                     -> a/b
    ..                     |  a/b/c                     |  a/b
    ..                     |  TestWiki/SubPage          |  TestWiki
    ..                     |  ebay/Couch/BuyerAddress   |  ebay/Couch
    ..                     |  TestWiki/SubPage          |  TestWiki
    ..                     |  a/b/c                     |  a/b
    ../TestWiki            |  TestWiki/SubPage          -> TestWiki
    ../x                   |  a/b/c                     |  a/x
    ..                     |  TestWiki/SubPage          |  TestWiki
    ../..                  |  ebay/Couch/BuyerAddress   |  ebay
    ../..                  |  a/b/c                     -> a
    ../..                 <-  a/b/c                     |  a
    ../..                  |  a/b/c/d                   |  a/b

    ../../Amazon           |  ebay/Couch/BuyerAddress   |  Amazon
    ../../y                |  a/b/c                     |  y
    ../../d/e/f            |  a/b/c                     -> d/e/f
    ../Super/SubPage       |  Main/SubPage2             |  Super/SubPage
    ../c/d                 |  a/b                       |  c/d
    ../c                   |  a/b                       |  c
    ../../d                |  a/b/c                     |  d
    ../../d/e/f            |  a/b/c                     |  d/e/f
    ../../d/e              |  a/b/c                     |  d/e
    ../main1renamed        |  main1renamed/sub          -> main1renamed

    //                     |  a                         -> VALUE_ERROR
    ../                    |  a/b/c                     -> VALUE_ERROR
    ../../                 |  a/b/c/d                   -> VALUE_ERROR
    EMPTY_STRING           |  PageName                  -> VALUE_ERROR
    ..                     |  TopLevel                  -> VALUE_ERROR
    ../..                  |  TopLevel                  -> VALUE_ERROR

    VALUE_ERROR            <-  TestPage                 |  EMPTY_STRING
    """

    values = parse_columns(test_values)

    def tests(direction):
        return values[direction]

    # ->

    def resolve_v1(linkCore, basePageName):
        try:
            basePage = wikidoc.getWikiPage(basePageName)
        except WikiWordNotFoundException:
            basePage = wikidoc.createWikiPage(basePageName)
        return langHelper.resolveWikiWordLink(linkCore, basePage)

    def resolve_v2(linkCore, basePageName):
        linkPath = WikiLinkPath(linkCore)
        basePath = langHelper.WikiLinkPath(pageName=basePageName)
        ans = linkPath.resolveWikiWord(basePath)
        return ans

    def left_to_right_err_msg_1(ver):
        msg = u'ver %d: resolve link %r on %r = %r != %r'
        return msg % (ver, linkCore, basePageName, res, targetPageName)

    def left_to_right_err_msg_2(ver):
        msg = u'ver %d: link %r on %r !-> %r'
        return msg % (ver, linkCore, basePageName, targetPageName)

    for linkCore, basePageName, targetPageName in tests('left_to_right'):
        if not isinstance(targetPageName, Exception):
            res = resolve_v1(linkCore, basePageName)
            assert res == targetPageName, left_to_right_err_msg_1(1)
            res = resolve_v2(linkCore, basePageName)
            assert res == targetPageName, left_to_right_err_msg_1(2)
        else:
            exc = type(targetPageName)
            with pytest.raises(exc, message=left_to_right_err_msg_2(1)):
                res = resolve_v1(linkCore, basePageName)
            with pytest.raises(exc, message=left_to_right_err_msg_2(2)):
                resolve_v2(linkCore, basePageName)

    # <-

    def create_v1(targetPageName, basePageName, absolute):
        if absolute:
            if not targetPageName:
                raise ValueError
            return u'//' + targetPageName
        else:
            return langHelper.createRelativeLinkFromWikiWord(
                targetPageName, basePageName, downwardOnly=False)

    def create_v2(targetPageName, basePageName, absolute):
        linkPath = langHelper.createWikiLinkPathFromPageName(
            targetPageName, basePageName, absolute)
        return linkPath.getLinkCore()

    def right_to_left_err_msg_1(ver):
        msg = u'ver %d: create link to %r on %r = %r != %r'
        return msg % (ver, targetPageName, basePageName, res, linkCore)

    def right_to_left_err_msg_2(ver):
        msg = u'ver %d: link to %r on %r !-> %r'
        return msg % (ver, targetPageName, basePageName, linkCore)

    for linkCore, basePageName, targetPageName in tests('right_to_left'):
        if not isinstance(linkCore, Exception):
            absolute = linkCore.startswith(u'//')
            res = create_v1(targetPageName, basePageName, absolute)
            assert res == linkCore, right_to_left_err_msg_1(1)
            res = create_v2(targetPageName, basePageName, absolute)
            assert res == linkCore, right_to_left_err_msg_1(2)
        else:
            exc = type(linkCore)
            with pytest.raises(exc, message=right_to_left_err_msg_2(1)):
                create_v1(targetPageName, basePageName, False)
            with pytest.raises(exc, message=right_to_left_err_msg_2(2)):
                create_v2(targetPageName, basePageName, False)


def test_generate_text_1():
    """
    text -> |parser| -> AST -> |text generator| -> result
    assert result == text
    """
    pageName = u'PageName'
    text = u"""+ Heading 1
    A sentence, a link: [test], and some more text, even some *bold*. Something
    _simple_ to start.
    """
    wiki_content = {pageName: text}
    wikidoc = MockWikiDocument(wiki_content, LANGUAGE_NAME)
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    page = wikidoc.getWikiPage(pageName)
    ast = page.getLivePageAst()
    result = langHelper.generate_text(ast, page)
    assert result == text

    tf = langHelper.TextFormatter()
    result = tf.format(ast, page)
    assert result == text
    assert tf.count('heading') == 1
    assert tf.count('wikiWord') == 1
    assert tf.count('bold') == 1
    assert tf.count('italics') == 1


def test_generate_text_2():
    pageName = u'PageName'
    wikidoc = MockWikiDocument({pageName: u''}, LANGUAGE_NAME)
    page = wikidoc.getWikiPage(pageName)
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    text_fragments = [
        (u'[wikiword]', 'wikiWord'),
        (u'[wikiword]!anchor', 'wikiWord'),
        (u'[wikiword|title]', 'wikiWord'),
        (u'[WikiWord|title]', 'wikiWord'),
        (u'[wikiword|title]!anchor', 'wikiWord'),
        (u'[WikiWord|title]!anchor', 'wikiWord'),
        (u'[wikiword#searchfragment]', 'wikiWord'),
        (u'[wikiword#search fragment]', 'wikiWord'),
        (u'[WikiWord#search# fragment]', 'wikiWord'),
        (u'[wikiword#searchfragment]!anchor', 'wikiWord'),
        (u'[WikiWord#searchfragment]!anchor', 'wikiWord'),
        (u'[wikiword#searchfragment|title]', 'wikiWord'),
        (u'[WikiWord#searchfragment|title]', 'wikiWord'),
        (u'[wikiword#searchfragment|title]!anchor', 'wikiWord'),
        (u'[WikiWord#searchfragment|title]!anchor', 'wikiWord'),
        (u'WikiWord', 'wikiWord'),
        (u'WikiWord!anchor', 'wikiWord'),
        (u'WikiWord#searchfragment', 'wikiWord'),
        (u'[key: value]', 'attribute'),
        (u'[test: ok; nok]', 'attribute'),
        (u'[:page: wikiword]', 'insertion'),
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


def test_generate_text_3():
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    tests = [  # page name, text fragment, target
        (u'PageName', u'[//WikiWord]', u'WikiWord'),
        (u'PageName', u'[//wikiword]', u'wikiword'),
        (u'PageName', u'[/wikiword]', u'PageName/wikiword'),
        (u'PageName', u'[/wikiword/subsub]', u'PageName/wikiword/subsub'),
        (u'PageName', u'[.]', u'PageName'),
        (u'PageName', u'PageName', u'PageName'),
        (u'pageName', u'[pageName]', u'pageName'),
        (u'Main/SubPage', u'[.]', u'Main/SubPage'),
        (u'Main/SubPage', u'[Test]', u'Main/Test'),
        (u'Main/SubPage', u'[..]', u'Main'),
        (u'Main/SubPage', u'[../Chair]', u'Chair'),
    ]
    for nr, (pageName, text_fragment, target) in enumerate(tests, 1):
        wikidoc = MockWikiDocument({pageName: u''}, LANGUAGE_NAME)
        page = wikidoc.getWikiPage(pageName)
        text = u'\n%s\n\n' % text_fragment
        page.setContent(text)
        ast = page.getLivePageAst()

        nf = NodeFinder(ast)
        assert nf.count('wikiWord') == 1
        link_core = nf.wikiWord().linkPath.getLinkCore()
        resolved = langHelper.resolveWikiWordLink(link_core, page)
        assert resolved == target, (u'%d: %r on %r -> %r != %r' % (nr,
            link_core, pageName, resolved, target))
        result = langHelper.generate_text(ast, page)
        assert result == text


def test_generate_WikidPadHelp():
    """Run over *complete* WikidPadHelp wiki: parse each page, generate text
    from AST using text generator, and check if generated text matches the
    original text::

        text -> |parser| -> AST -> |text generator| -> result
        assert result == text

    The *first time*, set `add_unknown_differences_to_annotation_file` to
    True and annotate generated file with differences: put '!=' if different,
    and '==' if equal (in semantics, maybe not in syntax, e.g.,
    [key:  value  ] is equal to [key: value] (note the extra spaces)).

    """
    # add_unknown_differences_to_annotation_file = True
    add_unknown_differences_to_annotation_file = False

    def load_annotations(path):
        equivalents = defaultdict(dict)
        known_differences = defaultdict(dict)
        page_name, text, result = None, None, None
        try:
            with io.open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(u'#'):
                        continue
                    if line.startswith(u'-- '):
                        text = line[3:]
                    elif line.startswith(u'== '):
                        result = line[3:]
                        equivalents[page_name][text] = result
                    elif line.startswith(u'!= '):
                        result = line[3:]
                        known_differences[page_name][text] = result
                    else:
                        page_name = line
        except IOError:
            pass  # no file yet?!
        return equivalents, known_differences

    equivalents, known_differences = load_annotations(WIKIDPADHELP_ANNOTATIONS)

    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    wikidoc = MockWikiDocument(None, LANGUAGE_NAME)
    paths = glob.glob(os.path.join(WIKIDPADHELP_DATA_DIR, u'*.wiki'))
    skip = {
        u'MediaWiki%2FTextFormatting',  # Media Wiki syntax, not WikidPadParser
    }
    known_differences = 0
    unknown_differences = 0
    for nr, path in enumerate(sorted(paths), 1):
        pageName, _ = os.path.splitext(os.path.basename(path))
        if pageName in skip:
            continue
        text = get_text(path)
        try:
            page = wikidoc.getWikiPage(pageName)
        except WikiWordNotFoundException:
            page = wikidoc.createWikiPage(pageName)
        page.setContent(text)

        ast = page.getLivePageAst()
        result = langHelper.generate_text(ast, page)
        # assert result == text

        current_page_correct = True
        with io.open(WIKIDPADHELP_ANNOTATIONS, 'a', encoding='utf-8') as f:
            to_compare = zip(result.splitlines(True), text.splitlines(True))
            for result_line, text_line in to_compare:
                result_line = result_line.rstrip()
                text_line = text_line.rstrip()
                if result_line == text_line:
                    continue  # ok, equal
                try:
                    equivalent_line = equivalents[pageName][text_line]
                except KeyError:
                    equivalent_line = None
                if result_line == equivalent_line:
                    continue  # ok, lines are considered equal
                try:
                    known_difference = known_differences[pageName][text_line]
                except KeyError:
                    known_difference = None
                if result_line == known_difference:
                    known_differences += 1
                    continue  # ok, we know about this difference

                # we have an unknown difference here
                unknown_differences += 1
                if add_unknown_differences_to_annotation_file:
                    if current_page_correct:  # first error for this page
                        current_page_correct = False
                        f.write(pageName + u'\n')
                    f.write(u'-- ' + text_line + u'\n')
                    f.write(u'!= ' + result_line + u'\n')

    msg = u'TOTAL: %d known differences, %d unknown differences'
    msg %= (known_differences, unknown_differences)
    assert not unknown_differences, msg


def test_generate_WikidPadHelp_selection():
    test_fragments = [  # (page_name, text, node_name, formatted_text)
        (u'pageName', u'[.]',
         'wikiWord',  u'[.]'),  # 1
        (u'PageName', u'[.]',
         'wikiWord',  u'[.]'),
        (u'PageName', u'PageName',
         'wikiWord',  u'PageName'),
        (u'PageName', u'[PageName]',
         'wikiWord',  u'PageName'),
        (u'PageName', u'[contact: "Carl [Home]"]',
         'attribute', u'[contact: "Carl [Home]"]'),
        (u'PageName', u'[//OptionsDialog]',
         'wikiWord',  u'[//OptionsDialog]'),
        (u'PageName', u'[//ebay/Circlet]', 'wikiWord',  u'[//ebay/Circlet]'),
        (u'PageName', u'[WikiWord|   This is the title  ]',
         'wikiWord',  u'[WikiWord|This is the title]'),
        (u'PageName', u'[:rel: parents]', 'insertion', u'[:rel: parents]'),
        (u'PageName', u'[:rel: parents; aslist]',
         'insertion', u'[:rel: parents; aslist]'),
        (u'PageName', u'[:rel: children; existingonly;columns 2]',
         'insertion', u'[:rel: children; existingonly; columns 2]'),
        (u'PageName', u'[key: value]',
         'attribute', u'[key: value]'),
        (u'PageName', u'[:toc: ]',
         'insertion', u'[:toc:]'),
        (u'ChangeLog2008', u'[test:foo; ]',  # still legal?!
         'attribute',      u'[test: foo]'),
        (u'TestPage', u'[test:foo;; ]',  # still legal?!
         'attribute', u'[test: foo]'),
        (u'PageName', u'[key: value with spaces]',
         'attribute', u'[key: value with spaces]'),
        (u'PageName', u'[key: value; value2]',
         'attribute', u'[key: value; value2]'),
        (u'PageName', u'[key: "value: with special char"]',
         'attribute', u'[key: "value: with special char"]'),
        (u'PageName', u'[key: "value = special"]',
         'attribute', u'[key: "value = special"]'),
        (u'pageName', u'[wikiword]#searchfragment',
         'wikiWord',  u'[wikiword#searchfragment]'),
        (u'pageName', u'[wikiword#searchfragment]',
         'wikiWord',  u'[wikiword#searchfragment]'),
        (u'pageName', u'[wikiword#search fragment]',
         'wikiWord',  u'[wikiword#search fragment]'),
        (u'AutoCompletion', u'[bookmarked=true]',
         'attribute',       u'[bookmarked: true]'),
        (u'ChangeLog', u'[ChangeLog2011]',
         'wikiWord',   u'ChangeLog2011'),
        (u'ChronViewWindow', u'[OptionsDialog#+++ Chron. view]',
         'wikiWord',         u'[OptionsDialog#+++ Chron. view]'),
        (u'ChronViewWindow', u'[OptionsDialog#+++ Chronological]',
         'wikiWord',         u'[OptionsDialog#+++ Chronological]'),
        (u'CommandLineSupport', u'[WikiMaintenance#++ Update ext. modif. wiki files]',
         'wikiWord',            u'[WikiMaintenance#++ Update ext. modif. wiki files]'),
        (u'ExternalGraphicalApplications', u'[:eqn:"a^2 + b^2 = c^2"]',
         'insertion',                      u'[:eqn: "a^2 + b^2 = c^2"]'),
        (u'Icon airbrush', u'[icon:airbrush]',
         'attribute',      u'[icon: airbrush]'),
        (u'Icon cd_audio', u'[icon:cd_audio ]',
         'attribute',      u'[icon: cd_audio]'),
        (u'Insertions', u'[:page: "IncrementalSearch"]',
         'insertion',   u'[:page: IncrementalSearch]'),
        (u'Insertions', u'[:page: "IncrementalSearch"]',
         'insertion',   u'[:page: IncrementalSearch]'),
        (u'Insertions', u'[:rel: children;existingonly;columns 2;coldir down]',
         'insertion',   u'[:rel: children; existingonly; columns 2; coldir down]'),
        (u'Insertions', u'[:search:"todo:todo"]',
         'insertion',  u'[:search: "todo:todo"]'),
        (u'Insertions', u'[:search:"todo:todo";showtext]',
         'insertion',   u'[:search: "todo:todo"; showtext]'),
        (u'Insertions', u'[:eval:"5+6"]',
         'insertion',   u'[:eval: "5+6"]'),
        (u'ExternalGraphicalApplications',
         u'[:dot:"\ndigraph {\na -> b\nb -> c\nb -> d\nd -> a\n}\n"; noerror]',
         'insertion',
         u'[:dot: "\ndigraph {\na -> b\nb -> c\nb -> d\nd -> a\n}\n"; noerror]'),
        (u'ExternalGraphicalApplications',
         (u'[:ploticus:"\n'
          u'#proc areadef\n'
          u'  title: Annual Revenues, in thousands\n'
          u'  rectangle: 1 1 5 2\n'
          u'  xrange: 0 4\n'
          u'  yrange: -5000 15000\n'
          u'  yaxis.stubs: incremental 5000\n'
          u'  yaxis.grid: color=pink\n'
          u'  xaxis.stubs: text\n'
          u'ABC Corp\n'
          u'NetStuff\n'
          u'MicroMason\n'
          u'\n'
          u'#proc getdata\n'
          u'  data: 6430 -780 13470\n'
          u'\n'
          u'#proc processdata\n'
          u'  action: rotate\n'
          u'\n'
          u'#proc bars\n'
          u'  lenfield: 1\n'
          u'  color: dullyellow\n'
          u'  labelword: $ @@N\n'
          u'  crossover: 0\n'
          u'"]'),
         'insertion',
         (u'[:ploticus: "\n#proc areadef\n  title: Annual Revenues, in '
          u'thousands\n  rectangle: 1 1 5 2\n  xrange: 0 4\n  yrange: -5000 '
          u'15000\n  yaxis.stubs: incremental 5000\n  yaxis.grid: color=pink\n'
          u'  xaxis.stubs: text\nABC Corp\nNetStuff\nMicroMason\n\n'
          u'#proc getdata\n  data: 6430 -780 13470\n\n#proc processdata\n'
          u'  action: rotate\n\n#proc bars\n  lenfield: 1\n  color: dullyellow\n'
          u'  labelword: $ @@N\n  crossover: 0\n"]')),

        (u'ExternalGraphicalApplications',
         u"""[:gnuplot:"
set key right nobox
set samples 100
plot [-pi/2:pi] cos(x),-(sin(x) > sin(x+1) ? sin(x) : sin(x+1))
"]""",
          'insertion',
          u"""[:gnuplot: "
set key right nobox
set samples 100
plot [-pi/2:pi] cos(x),-(sin(x) > sin(x+1) ? sin(x) : sin(x+1))
"]"""),
    ]
    langHelper = getApp().createWikiLanguageHelper(LANGUAGE_NAME)
    wikidoc = MockWikiDocument(None, LANGUAGE_NAME)
    tests = enumerate(test_fragments, 1)
    for nr, (pageName, text, node_name, formatted_text) in tests:
        text_ = u'\n%s\n\n' % text
        try:
            page = wikidoc.getWikiPage(pageName)
        except WikiWordNotFoundException:
            page = wikidoc.createWikiPage(pageName)
        page.setContent(text_)
        ast = page.getLivePageAst()
        nf = NodeFinder(ast)
        if node_name is not None:
            assert nf.count(node_name) == 1
        else:
            assert nf.count('wikiWord') == 0
            assert nf.count('attribute') == 0
            assert nf.count('insertion') == 0
        result = langHelper.generate_text(ast, page)[1:-2]
        assert result == formatted_text, u'%d: %r on %r -> %r != %r' % (
            nr, text, pageName, result, formatted_text)
