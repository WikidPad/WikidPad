## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

from wxPython.wx import *
from wxPython.html import *

from wxHelper import keyDownToAccel, copyTextToClipboard, GUI_ID

from MiscEvent import KeyFunctionSink

from StringOps import uniToGui

import Exporters



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
                ("options changed", self.onOptionsChanged),
                ("updated wiki page", self.onUpdatedWikiPage)

#                 ("updated current page cache", self.updatedCurrentPageCache),
#                 ("renamed wiki page", self.renamedWikiPage)
        )), False)

        self.visible = False

        self.currentLoadedWikiWord = None
        self.scrollPosCache = {}
        
        self.exporterInstance = Exporters.HtmlXmlExporter(self.pWiki)
        
        # TODO More elegant
        self.exporterInstance.pWiki = self.pWiki
        
        EVT_KEY_DOWN(self, self.OnKeyDown)
        EVT_KEY_UP(self, self.OnKeyUp)
        EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY, self.OnClipboardCopy)
        
        EVT_SET_FOCUS(self, self.OnSetFocus)
        EVT_MOUSEWHEEL(self, self.OnMouseWheel) 


    def setVisible(self, vis):
        """
        Informs the widget if it is really visible on the screen or not
        """
        if not self.visible and vis:
            self.refresh()

        self.visible = vis


    _DEFAULT_FONT_SIZES = (wxHTML_FONT_SIZE_1, wxHTML_FONT_SIZE_2, 
            wxHTML_FONT_SIZE_3, wxHTML_FONT_SIZE_4, wxHTML_FONT_SIZE_5, 
            wxHTML_FONT_SIZE_6, wxHTML_FONT_SIZE_7)


    def refresh(self):
        ## _prof.start()
        # Store position of previous word, if any
        if self.currentLoadedWikiWord:
            self.scrollPosCache[self.currentLoadedWikiWord] = self.GetViewStart()
        
        self.exporterInstance.wikiData = self.pWiki.getWikiData()
        
        wikiPage = self.pWiki.getCurrentDocPage()
        if wikiPage is None:
            return  # TODO Do anything else here?

        word = wikiPage.getWikiWord()
        self.currentLoadedWikiWord = word
        content = self.pWiki.getCurrentText()
        
        html = self.exporterInstance.exportContentToHtmlString(word, content,
                wikiPage.getFormatDetails(),
#                 wikiPage.getLinkCreator(self.pWiki.getWikiData()), asHtmlPreview=True)
                LinkCreator(self.pWiki.getWikiData()), asHtmlPreview=True)

        # TODO Reset after open wiki
#         lx, ly = self.GetViewStart()
        zoom = self.pWiki.getConfig().getint("main", "preview_zoom", 0)
        self.SetFonts("", "", [max(s + 2 * zoom, 1)
                for s in self._DEFAULT_FONT_SIZES])
        self.SetPage(uniToGui(html))
        
        lx, ly = self.scrollPosCache.get(self.currentLoadedWikiWord, (0, 0))
        self.Scroll(lx, ly)
        ## _prof.stop()


    def onLoadedCurrentWikiPage(self, miscevt):
        if self.visible:
            self.refresh()
            
    def onOpenedWiki(self, miscevt):
        self.currentLoadedWikiWord = None
        self.scrollPosCache = {}

        self.exporterInstance.setWikiDataManager(self.pWiki.getWikiDataManager())

    def onOptionsChanged(self, miscevt):
        if self.visible:
            self.refresh()

    def onUpdatedWikiPage(self, miscevt):
        if self.visible:
            self.refresh()


    def OnSetFocus(self, evt):
        if self.visible:
            self.refresh()

    def OnClipboardCopy(self, evt):
        copyTextToClipboard(self.SelectionToText())


    def OnLinkClicked(self, linkinfo):
        href = linkinfo.GetHref()
        if href.startswith(u"internaljump:"):
            # Jump to another wiki page
            self.pWiki.openWikiPage(href[13:], motionType="child")
        else:
            self.pWiki.launchUrl(href)


    def OnKeyUp(self, evt):
        acc = keyDownToAccel(evt)
        if acc == (wxACCEL_CTRL, ord('C')):
            # Consume original clipboard copy function
            pass
        else:
            evt.Skip()


    def OnKeyDown(self, evt):
        acc = keyDownToAccel(evt)
        if acc == (wxACCEL_CTRL, ord('+')) or \
                acc == (wxACCEL_CTRL, WXK_NUMPAD_ADD):
            zoom = self.pWiki.getConfig().getint("main", "preview_zoom", 0)
            self.pWiki.getConfig().set("main", "preview_zoom", str(zoom + 1))
            self.refresh()
        elif acc == (wxACCEL_CTRL, ord('-')) or \
                acc == (wxACCEL_CTRL, WXK_NUMPAD_SUBTRACT):
            zoom = self.pWiki.getConfig().getint("main", "preview_zoom", 0)
            self.pWiki.getConfig().set("main", "preview_zoom", str(zoom - 1))
            self.refresh()
        else:
            evt.Skip()

    def OnMouseWheel(self, evt):
        if evt.ControlDown():
            zoom = self.pWiki.getConfig().getint("main", "preview_zoom", 0)
            zoom -= evt.GetWheelRotation() // evt.GetWheelDelta()
            self.pWiki.getConfig().set("main", "preview_zoom", str(zoom))
            self.refresh()
        else:
            evt.Skip()



