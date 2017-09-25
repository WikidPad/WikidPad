# coding: utf-8
"""Some functions and classes needed for testing WikidPad functionality.


If you want to run this module as main, run it from the main
WikidPad directory:

    ..\WikidPad> python tests\helper.py

"""
import builtins
from collections import Counter
import io
from itertools import chain
import os
import re
import sys
import imp
import wx

builtins._ = builtins.N_ = lambda s: s  # see WikidPadStarter
if not hasattr(wx, "NO_3D"):  # cmore addition
    wx.NO_3D = 0

# run test from WikidPad directory, fix path
# todo (pvh): ? fix imports in WikidPad, turn it into a package
wikidpad_dir = os.path.abspath('.')
sys.path.append(wikidpad_dir)
sys.path.append(os.path.join(wikidpad_dir, 'lib'))

EXTENSIONDIR = os.path.join(wikidpad_dir, 'extensions')
sys.path.append(EXTENSIONDIR)



from pwiki.ParseUtilities import WikiPageFormatDetails
from pwiki.Utilities import DUMBTHREADSTOP
from pwiki.WikiDocument import WikiDocument
from pwiki.StringOps import LOWERCASE, UPPERCASE

from wikidPadParser import WikidPadParser
from mediaWikiParser import MediaWikiParser

OverlayParser = imp.load_source('OverlayParser', os.path.join(EXTENSIONDIR,
        "OverlayParser.pyf"))

# import OverlayParser

from Consts import ModifyText

TESTS_DIR = os.path.abspath('tests/')
PARSER_MODULES = [WikidPadParser, MediaWikiParser, OverlayParser]

DEFAULT_WIKI_LANGUAGE = 'wikidpad_default_2_0'


class Error(Exception):
    pass


class UnknownWikiLanguage(Error):
    pass


class WikiWordNotFoundException(Error):
    pass


def get_text(path):
    with io.open(path, mode='r', encoding='utf-8-sig', newline=None) as f:
        return f.read()


class MockWikiConfiguration(object):
    def __init__(self):
        self.configuration = {
            'main': {
                'footnotes_as_wikiwords': False,
                'wiki_language': DEFAULT_WIKI_LANGUAGE,
                'wikiPageTitle_creationMode': 1,
            },
        }

    def getboolean(self, section, option, default=None):
        try:
            return bool(self.configuration[section][option])
        except KeyError:
            return default

    def getint(self, section, option, default=None):
        try:
            return int(self.configuration[section][option])
        except KeyError:
            return default

    def get(self, section, option, default=None):
        try:
            return self.configuration[section][option]
        except KeyError:
            return default

    def set(self, section, option, value):
        self.configuration[section][option] = value


class MockApp(object):
    def __init__(self):
        # get languages
        self.wikiLanguageDescriptions = dict()
        for module in PARSER_MODULES:
            try:
                descriptions = getattr(module, 'describeWikiLanguage')(1, self)
            except AttributeError:
                continue
            for descr in descriptions:
                self.wikiLanguageDescriptions[descr[0]] = descr

    def createWikiLanguageHelper(self, language_name, debugMode=False):
        try:
            descr = self.wikiLanguageDescriptions[language_name]
        except KeyError:
            raise UnknownWikiLanguage(language_name)

        name, hr_name, parserFactory, _, langHelperFactory, _ = descr
        assert name == language_name
        return langHelperFactory(language_name, debugMode)

    def createWikiParser(self, language_name, debugMode=False):
        try:
            descr = self.wikiLanguageDescriptions[language_name]
        except KeyError:
            raise UnknownWikiLanguage(language_name)

        name, hr_name, parserFactory, _, langHelperFactory, _ = descr
        assert name == language_name
        return parserFactory(language_name, debugMode)


_app = None  # note: there is only one app


def getApp():
    global _app
    if _app is None:
        _app = MockApp()
    return _app


class MockWikiData(object):
    def __init__(self, wikiDocument, wiki_content=None):
        self.wikiDocument = wikiDocument
        if wiki_content is not None:
            self.wiki_content = wiki_content  # {pageName: content}
        else:
            self.wiki_content = dict()

    def __str__(self):
        ans = ['=' * 80 + '\n']
        for page_name, content in self.wiki_content.items():
            lines = []
            header = '- ' + page_name + ' ' + '-' * 80
            lines.append(header[:80] + '\n')
            lines.append(content)
            lines.append('-' * 80 + '\n')
            ans.append(''.join(lines))
        ans.append('=' * 80 + '\n')
        return '\n'.join(ans)

    def getContent(self, word):
        try:
            return self.wiki_content[word]
        except KeyError:
            raise WikiWordNotFoundException

    def setContent(self, word, content):
        self.wiki_content[word] = content

    def isDefinedWikiPageName(self, word):
        return word in self.wiki_content

    def renameWord(self, word, toWord):
        assert self.isDefinedWikiPageName(word)
        self.wiki_content[toWord] = self.wiki_content[word]
        del self.wiki_content[word]

    def getAllDefinedWikiPageNames(self):
        return list(self.wiki_content.keys())


class MockWikiDocument(object):
    """
    a.k.a. WikiDocument
    """
    _TITLE_SPLIT_RE1 = re.compile(
        r"([" + UPPERCASE + r"]+)" +
        r"([" + UPPERCASE + r"][" + LOWERCASE + r"])")
    _TITLE_SPLIT_RE2 = re.compile(
        r"([" + LOWERCASE + r"])" + r"([" + UPPERCASE + r"])")

    def __init__(self, wiki_content=None, wiki_language_name=None):
        """
        wiki_content: {pageName: pageContent}
        """
        self.config = MockWikiConfiguration()
        if wiki_language_name is not None:
            self.config.set('main', 'wiki_language', wiki_language_name)
        self.wikiPageDict = dict()  # {pageName: page}
        self.baseWikiData = MockWikiData(self, wiki_content)

    def __str__(self):
        return str(self.baseWikiData)

    def getWikiConfig(self):
        return self.config

    def getCcWordBlacklist(self):
        return []

    def getNccWordBlacklist(self):
        return []

    def getWikiPage(self, word):
        try:
            page = self.wikiPageDict[word]
        except KeyError:  # not in cache
            if not self.baseWikiData.isDefinedWikiPageName(word):
                raise WikiWordNotFoundException
            page = MockWikiPage(self, word)
            self.wikiPageDict[word] = page
        return page

    def createWikiPage(self, pageName, content=''):
        assert not self.isDefinedWikiPageName(pageName)
        self.baseWikiData.setContent(pageName, content)
        page = MockWikiPage(self, pageName)
        self.wikiPageDict[pageName] = page
        return page

    def getWikiDefaultWikiLanguage(self):
        return self.config.get('main', 'wiki_language', DEFAULT_WIKI_LANGUAGE)

    def isDefinedWikiPageName(self, pageName):
        return self.baseWikiData.isDefinedWikiPageName(pageName)

    def getWikiWordSubpages(self, word):
        return [ww for ww in self.wikiPageDict if ww.startwith(word + '/')]

    def getWikiData(self):
        return self.baseWikiData

    @staticmethod
    def _updateWikiWordReferences(*args, **kwargs):
        return WikiDocument._updateWikiWordReferences(*args, **kwargs)

    @staticmethod
    def _searchAndReplaceWikiWordReferences(*args, **kwargs):
        return WikiDocument._searchAndReplaceWikiWordReferences(*args, **kwargs)

    def formatPageTitle(self, rawTitle, basePage=None):
        return '+ ' + rawTitle

    def getWikiPageTitle(self, word):
        creation_mode = self.getWikiConfig().getint(
            'main', 'wikiPageTitle_creationMode', 1)
        if creation_mode == 0:  # leave untouched
            return word
        elif creation_mode == 1:  # add spaces before uppercase letters
            title = self._TITLE_SPLIT_RE1.sub(r'\1 \2', word)
            title = self._TITLE_SPLIT_RE2.sub(r'\1 \2', title)
            return title
        else:  # no title at all
            return None

    def renameWikiWords(self, renameDict, modifyText):
        """Mimic WikiDocument.renameWikiWords.

        renameDict = {oldPageName: newPageName}
        """
        # 1. rename all pages
        for oldPageName, newPageName in renameDict.items():
            self.renameWikiWord(oldPageName, newPageName)

        if modifyText == ModifyText.off:
            return

        # 2. modify text of all affected pages, i.e., pages with links to
        #    old page names etc.

        # to simulate, simply run over *all* pages instead of figuring out
        # which pages need updating...
        to_update = self.getWikiData().getAllDefinedWikiPageNames()

        if modifyText == ModifyText.advanced:
            langHelper = getApp().createWikiLanguageHelper(
                self.getWikiDefaultWikiLanguage())
            for wikiword in to_update:
                page = self.getWikiPage(wikiword)
                text = MockWikiDocument._updateWikiWordReferences(
                    page, renameDict, langHelper)
                page.replaceLiveText(text)

        elif modifyText == ModifyText.simple:
            for wikiword in to_update:
                page = self.getWikiPage(wikiword)
                for oldPageName, newPageName in renameDict.items():
                    text = MockWikiDocument._searchAndReplaceWikiWordReferences(
                        page, oldPageName, newPageName)
                    if text is not None:
                        page.replaceLiveText(text)

    def renameWikiWord(self, oldPageName, newPageName):
        """Mimic WikiDocument.renameWikiWord."""

        print('renameWikiWord(%r, %r)' % (oldPageName, newPageName))

        page = self.getWikiPage(oldPageName)  # load in wikiPageDict

        oldPageTitle = self.getWikiPageTitle(oldPageName)
        if oldPageTitle is not None:
            oldPageTitle = self.formatPageTitle(oldPageTitle) + "\n"

        self.getWikiData().renameWord(oldPageName, newPageName)
        del self.wikiPageDict[oldPageName]

        # modify the page heading
        page = self.getWikiPage(newPageName)
        content = page.getLiveText()
        if oldPageTitle is not None and content.startswith(oldPageTitle):
            # replace previous title with new one
            new_title = self.formatPageTitle(self.getWikiPageTitle(newPageName))

            print('title: "%r" -> %r' % (oldPageTitle, new_title))

            content = new_title + "\n" + content[len(oldPageTitle):]
            page.replaceLiveText(content)




class MockAliasWikiPage(object):
    def __init__(self, wikiDocument, aliasPageName, realWikiPage):
        self.wikiDocument = wikiDocument
        self.aliasPageName = aliasPageName
        self.realWikiPage = realWikiPage

    def getWikiWord(self):
        return self.aliasPageName

    def getNonAliasPage(self):
        return self.realWikiPage

    def getContent(self):
        return self.realWikiPage.getContent()

    def getLivePageAst(self):
        return self.realWikiPage.getLivePageAst()

    def getWikiDocument(self):
        return self.wikiDocument

    def getFormatDetails(self):
        return self.realWikiPage.getFormatDetails()

    def replaceLiveText(self, text):
        self.realWikiPage.replaceLiveText(text)

    def setContent(self, content):
        self.realWikiPage.setContent(content)


class MockWikiPage(object):
    def __init__(self, wikiDocument, pageName):
        assert wikiDocument is not None
        self.wikiDocument = wikiDocument
        self.pageName = pageName

    def __str__(self):
        return self.getContent()

    def getFormatDetails(self):
        langHelper = getApp().createWikiLanguageHelper(
            self.wikiDocument.getWikiDefaultWikiLanguage())
        wikiLanguageDetails = langHelper.createWikiLanguageDetails(
            self.wikiDocument, self)
        format_details = WikiPageFormatDetails(
            wikiDocument=self.wikiDocument,
            basePage=self,
            wikiLanguageDetails=wikiLanguageDetails,
            noFormat=False,
            withCamelCase=True,  # camelCaseWordsEnabled
            autoLinkMode="off",
            paragraphMode=False,
        )
        return format_details

    def getWikiWord(self):
        return self.pageName

    def getWikiDocument(self):
        return self.wikiDocument

    def getLivePageAst(self):
        content = self.getContent()
        if content is None:
            return None
        language_name = self.wikiDocument.getWikiDefaultWikiLanguage()
        parser = getApp().createWikiParser(language_name)
        ast = parser.parse(language_name,
                           content,
                           self.getFormatDetails(),
                           DUMBTHREADSTOP)
        return ast

    def getContent(self):
        return self.wikiDocument.getWikiData().getContent(self.pageName)

    def setContent(self, content):
        self.wikiDocument.getWikiData().setContent(self.pageName, content)

    def getLiveText(self):
        return self.getContent()

    def getLiveTextNoTemplate(self):
        return self.getContent()

    def replaceLiveText(self, text):
        self.setContent(text)

    def getNonAliasPage(self):
        return self


_rank = {1: '1st', 2: '2nd', 3: '3rd'}


def rank(n):
    return _rank.get(n, '%dth' % n)


class NodeFinder(object):
    """Facade for AST navigation using attribute notation.

    To find the node of the 2nd heading, then find the node of the first
    wiki word after that, then get that node (via call) and then select
    the attribute wikiWord from that node::

        nf = NodeFinder(ast)
        nf.heading_2.wikiWord_1().wikiWord

    nf points to the root node. Get root node::

        nf()

    Get the 2nd heading node after the root node, i.e., the 2nd
    heading in the document::

        nf.heading_2()

    This is the same as finding the first one, and then the one after
    that::

        nf.heading.heading()

    Number of wikiWord nodes::

        nf.count('wikiWord')

    Print tree with node numbers and position in tree::

        print nf.heading

    Find node at postion node_pos::

        nf[node_pos]

    Nodes are numbered in depth-first order (their order thus matches
    their text order). The root node ('text') has number 0.
    """
    def __init__(self, ast, cur_node_nr=0, _nodes=None):
        self.ast = ast
        self.cur_node_nr = cur_node_nr
        if _nodes is None:
            self._nodes = dict()
            self._nodes['nodelist'] = []  # nodes in depth-first order, 0 = text
            self._nodes['count'] = Counter()  # {node.name: count}
            self._nodes['pos'] = {}  # {node.pos: node}
            nodes = chain([self.ast], self.ast.iterDeep())
            for node_nr, node in enumerate(nodes, 0):
                self._nodes['nodelist'].append(node)
                self._nodes['count'][node.name] += 1
                if node_nr > 0 and node.pos not in self._nodes['pos']:
                    self._nodes['pos'][node.pos] = node
        else:
            self._nodes = _nodes

    def __str__(self):
        lines = []
        for node_nr, node in enumerate(self._nodes['nodelist'], 0):
            line = '%d %s %d' % (node_nr, node.name, node.pos)
            if node_nr == self.cur_node_nr:
                line += ' <---'
            lines.append(line)
        return '\n'.join(lines)

    def __getattr__(self, node_name_n):
        """Go to the n-th named node *after* the current node."""
        try:
            node_name, n_str = node_name_n.split('_', 1)
        except ValueError:
            node_name, n = node_name_n, 1  # no postfix -> first/next node
        else:
            n = int(n_str)
        return self.find_nth_named_node_after_current_node(node_name, n)

    def __getitem__(self, node_pos):
        try:
            return self._nodes['pos'][node_pos]
        except KeyError:
            return KeyError('No node found at text position %d.' % node_pos)

    def __call__(self, *args, **kwargs):
        return self._nodes['nodelist'][self.cur_node_nr]

    def find_nth_named_node_after_current_node(self, node_name, n):
        msg = '%s node %r after node %d' % (
            rank(n), node_name, self.cur_node_nr)
        nodes = self._nodes['nodelist']
        i = 0
        for node_nr in range(self.cur_node_nr+1, len(nodes)):
            node = nodes[node_nr]
            if node.name == node_name:
                i += 1
                if i == n:
                    return NodeFinder(self.ast, node_nr, self._nodes)
        raise KeyError('%s node %r after node %d not found.' % (
            rank(n), node_name, self.cur_node_nr))

    def count(self, node_name):
        return self._nodes['count'][node_name]


def parse(text, page_name='_', language_name=DEFAULT_WIKI_LANGUAGE):
    """Return AST."""
    wikidoc = MockWikiDocument({page_name: text}, language_name)
    return wikidoc.getWikiPage(page_name).getLivePageAst()


def node_eq(node, node_):
    if any((node.name != node_.name,
            node.pos != node_.pos,
            node.strLength != node_.strLength,
            node.getString() != node_.getString())):
        return False
    else:
        return True


def ast_eq(ast, ast_):
    for node, node_ in zip(ast.iterDeep(), ast_.iterDeep()):
        if not node_eq(node, node_):
            return False
    return True


if __name__ == '__main__':
    text = """+ Heading

WikiWord

This is a line of text.

"""
    wiki_content = {'PageName': text}
    wikidoc = MockWikiDocument(wiki_content)
    page = wikidoc.getWikiPage('PageName')
    ast = page.getLivePageAst()
    # print u'AST of %s:' % page.getWikiWord()
    # print ast.pprint()
    # print wikidoc

    page = wikidoc.createWikiPage('NewPage')
    page.setContent('This is the first sentence on NewPage.\n')
    ast = page.getLivePageAst()
    # print u'AST of %s:' % page.getWikiWord()
    # print ast.pprint()
    # print wikidoc

    page = wikidoc.createWikiPage('TestPage')
    text = """+ Heading 1

TestPage

+ Heading 2

WikiWord

+ Heading 3

WikiWordBis

    """
    page.setContent(text)
    ast = page.getLivePageAst()

    nf = NodeFinder(ast)
    print(nf.heading_3().getString())
    print(nf.heading_3)
