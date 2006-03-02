# import os, traceback, codecs, array
# from cStringIO import StringIO
# import urllib_red as urllib
# import string, re
# import threading
# 
# from os.path import exists
# 
# from time import time, strftime
# 

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

from wxPython.wx import *
from wxPython.html import *

from MiscEvent import KeyFunctionSink

import Exporters

# from wxPython.stc import *
# import wxPython.xrc as xrc
# 
# from wxHelper import GUI_ID, XrcControls, XRCID
# 
# import WikiFormatting
# from WikiExceptions import WikiWordNotFoundException, WikiFileNotFoundException
# from textwrap import fill
# 
# from StringOps import utf8Enc, utf8Dec, mbcsEnc, mbcsDec, uniToGui, guiToUni, \
#         Tokenizer, revStr
# from Configuration import isUnicode



class LinkCreator:
    """
    Faked link dictionary for HTML exporter
    """
    def __init__(self, wikiData):
        self.wikiData = wikiData
        
    def get(self, word, default = None):
        if self.wikiData.isDefinedWikiWord(word):
            return u"internaljump:%s" % word
        else:
            return default


class WikiHtmlView(wxHtmlWindow):
    def __init__(self, pWiki, parent, ID):
        wxHtmlWindow.__init__(self, parent, ID)
        self.pWiki = pWiki
        
        self.pWiki.getMiscEvent().addListener(KeyFunctionSink((
                ("loaded current page", self.onLoadedCurrentWikiPage),
                ("opened wiki", self.onOpenedWiki),
                ("options changed", self.onOptionsChanged)
                
#                 ("updated current page cache", self.updatedCurrentPageCache),
#                 ("renamed page", self.renamedWikiPage)
        )))
        
        self.visible = False
        
        self.currentLoadedWikiWord = None
        self.scrollPosCache = {}
        
        self.exporterInstance = Exporters.HtmlXmlExporter(self.pWiki)
        
        # TODO More elegant
        self.exporterInstance.pWiki = self.pWiki


    def setVisible(self, vis):
        """
        Informs the widget if it is really visible on the screen or not
        """
        if not self.visible and vis:
            self.refresh()

        self.visible = vis


        # TODO More elegant
    def refresh(self):
        ## _prof.start()
        # Store position of previous word, if any
        if self.currentLoadedWikiWord:
            self.scrollPosCache[self.currentLoadedWikiWord] = self.GetViewStart()
        
        self.exporterInstance.wikiData = self.pWiki.wikiData
        
        wikiPage = self.pWiki.getCurrentDocPage()
        if wikiPage is None:
            return  # TODO Do anything else here?

        word = wikiPage.getWikiWord()
        self.currentLoadedWikiWord = word
        content = self.pWiki.getCurrentText()
        
        html = self.exporterInstance.exportContentToHtmlString(word, content,
                wikiPage.getFormatDetails(),
#                 wikiPage.getLinkCreator(self.pWiki.wikiData), asHtmlPreview=True)
                LinkCreator(self.pWiki.wikiData), asHtmlPreview=True)
        
        # TODO Reset after open wiki
#         lx, ly = self.GetViewStart()
        self.SetPage(html)
        
        lx, ly = self.scrollPosCache.get(self.currentLoadedWikiWord, (0, 0))
        self.Scroll(lx, ly)
        ## _prof.stop()


    def onLoadedCurrentWikiPage(self, miscevt):
        if self.visible:
            self.refresh()
            
    def onOpenedWiki(self, miscevt):
        self.currentLoadedWikiWord = None
        self.scrollPosCache = {}

    def onOptionsChanged(self, miscevt):
        if self.visible:
            self.refresh()


    def OnLinkClicked(self, linkinfo):
        href = linkinfo.GetHref()
        if href.startswith(u"internaljump:"):
            # Jump to another wiki page
            self.pWiki.openWikiPage(href[13:], motionType="child")
        else:
            self.pWiki.launchUrl(href)

