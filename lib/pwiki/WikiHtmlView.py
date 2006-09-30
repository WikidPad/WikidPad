## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

from wxPython.wx import *
from wxPython.html import *


from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID

from MiscEvent import KeyFunctionSink

from StringOps import uniToGui

import Exporters



class LinkCreatorForPreview:
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
                ("reloaded current page", self.onReloadedCurrentPage),
                ("opened wiki", self.onOpenedWiki),
                ("options changed", self.onOptionsChanged),
                ("updated wiki page", self.onUpdatedWikiPage)

#                 ("updated current page cache", self.updatedCurrentPageCache),
#                 ("renamed wiki page", self.renamedWikiPage)
        )), False)

        self.visible = False

        self.currentLoadedWikiWord = None

        self.anchor = None  # Name of anchor to jump to when view gets visible

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


    # TODO Called too often and at wrong time, e.g. when switching from
    # preview to edit.

    def refresh(self):
        ## _prof.start()
        # Store position of previous page, if any
        if self.currentLoadedWikiWord:
            try:
                prevPage = self.pWiki.getWikiDocument().getWikiPage(
                        self.currentLoadedWikiWord)
                prevPage.setPresentation(self.GetViewStart(), 3)
            except WikiWordNotFoundException, e:
                pass

        self.currentLoadedWikiWord = None

        self.exporterInstance.wikiData = self.pWiki.getWikiData()

        wikiPage = self.pWiki.getCurrentDocPage()
        if wikiPage is None:
            return  # TODO Do anything else here?

        word = wikiPage.getWikiWord()
        self.currentLoadedWikiWord = word
        content = self.pWiki.getCurrentText()

        html = self.exporterInstance.exportContentToHtmlString(word, content,
                wikiPage.getFormatDetails(),
                LinkCreatorForPreview(self.pWiki.getWikiData()),
                asHtmlPreview=True)

        # TODO Reset after open wiki
        zoom = self.pWiki.getConfig().getint("main", "preview_zoom", 0)
        self.SetFonts("", "", [max(s + 2 * zoom, 1)
                for s in self._DEFAULT_FONT_SIZES])
        self.SetPage(uniToGui(html))
        
        if self.anchor and self.HasAnchor(self.anchor):
            self.ScrollToAnchor(self.anchor)
            # Workaround because ScrollToAnchor scrolls too far
            lx, ly = self.GetViewStart()
            self.Scroll(lx, ly-1)
        else:
            lx, ly = wikiPage.getPresentation()[3:5]
            self.Scroll(lx, ly)
            
        self.anchor = None

        ## _prof.stop()


    def onLoadedCurrentWikiPage(self, miscevt):
        self.anchor = miscevt.get("anchor")
        if self.visible:
            self.refresh()
            
    def onReloadedCurrentPage(self, miscevt):
        """
        Called when already loaded page should be loaded again, mainly
        interesting if a link with anchor is activated
        """
        anchor = miscevt.get("anchor")
        if anchor:
            self.anchor = anchor
            if self.visible:
                self.refresh()

    def onOpenedWiki(self, miscevt):
        self.currentLoadedWikiWord = None

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
            
            # First check for an anchor. In URLs, anchors are always
            # separated by '#' regardless which character is used
            # in the wiki syntax (normally '!')
            try:
                word, anchor = href[13:].split(u"#", 1)
            except ValueError:
                word = href[13:]
                anchor = None
                
            # Now open wiki
            self.pWiki.openWikiPage(word, motionType="child", anchor=anchor)
        else:
            self.pWiki.launchUrl(href)


    def OnKeyUp(self, evt):
        acc = getAccelPairFromKeyDown(evt)
        if acc == (wxACCEL_CTRL, ord('C')): 
            # Consume original clipboard copy function
            pass
        else:
            evt.Skip()


    def OnKeyDown(self, evt):
        acc = getAccelPairFromKeyDown(evt)
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



