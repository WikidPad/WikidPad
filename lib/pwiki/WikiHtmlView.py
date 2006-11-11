## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

from wxPython.wx import *
from wxPython.html import *


from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID

from MiscEvent import KeyFunctionSink

from StringOps import uniToGui

from TempFileSet import TempFileSet

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
    def __init__(self, presenter, parent, ID):
        wxHtmlWindow.__init__(self, parent, ID)
        self.presenter = presenter

        self.presenter.getMiscEvent().addListener(KeyFunctionSink((
                ("loaded current page", self.onLoadedCurrentWikiPage),
                ("reloaded current page", self.onReloadedCurrentPage),
                ("opened wiki", self.onOpenedWiki),
                ("closing current wiki", self.onClosingCurrentWiki),
                ("options changed", self.onOptionsChanged),
                ("updated wiki page", self.onUpdatedWikiPage),
                ("changed live text", self.onChangedLiveText)

#                 ("updated current page cache", self.updatedCurrentPageCache),
#                 ("renamed wiki page", self.renamedWikiPage)
        )), False)

        self.visible = False
        self.outOfSync = True   # HTML content is out of sync with live content

        self.currentLoadedWikiWord = None

        self.anchor = None  # Name of anchor to jump to when view gets visible

        
        # TODO Should be changed to presenter as controller
        self.exporterInstance = Exporters.HtmlXmlExporter(
                self.presenter.getMainControl())
        
        # TODO More elegantly
        self.exporterInstance.exportType = u"html_preview"
        self.exporterInstance.tempFileSet = TempFileSet()

        
        EVT_KEY_DOWN(self, self.OnKeyDown)
        EVT_KEY_UP(self, self.OnKeyUp)
        EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY, self.OnClipboardCopy)
        EVT_MENU(self, GUI_ID.CMD_ZOOM_IN, lambda evt: self.addZoom(1))
        EVT_MENU(self, GUI_ID.CMD_ZOOM_OUT, lambda evt: self.addZoom(-1))

        EVT_SET_FOCUS(self, self.OnSetFocus)
        EVT_MOUSEWHEEL(self, self.OnMouseWheel) 


    def setVisible(self, vis):
        """
        Informs the widget if it is really visible on the screen or not
        """
        if not self.visible and vis:
            self.outOfSync = True   # Just to be sure
            self.refresh()
            
        if not vis:
            self.exporterInstance.tempFileSet.clear()

        self.visible = vis


    def close(self):
        self.setVisible(False)


    _DEFAULT_FONT_SIZES = (wxHTML_FONT_SIZE_1, wxHTML_FONT_SIZE_2, 
            wxHTML_FONT_SIZE_3, wxHTML_FONT_SIZE_4, wxHTML_FONT_SIZE_5, 
            wxHTML_FONT_SIZE_6, wxHTML_FONT_SIZE_7)


    # TODO Called too often and at wrong time, e.g. when switching from
    # preview to edit.

    def refresh(self):
        ## _prof.start()

        # Store position of currently displaayed page, if any
        if self.currentLoadedWikiWord:
            try:
                prevPage = self.presenter.getWikiDocument().getWikiPage(
                        self.currentLoadedWikiWord)
                prevPage.setPresentation(self.GetViewStart(), 3)
            except WikiWordNotFoundException, e:
                pass

        if self.outOfSync:
            self.currentLoadedWikiWord = None
    
            self.exporterInstance.wikiData = self.presenter.getWikiDocument().\
                    getWikiData()
    
            wikiPage = self.presenter.getDocPage()
            if wikiPage is None:
                return  # TODO Do anything else here?
                
            word = wikiPage.getWikiWord()
            if word is None:
                return  # TODO Do anything else here?

            # Remove previously used temporary files
            self.exporterInstance.tempFileSet.clear()

            self.currentLoadedWikiWord = word
            content = self.presenter.getLiveText()
    
            html = self.exporterInstance.exportContentToHtmlString(word, content,
                    wikiPage.getFormatDetails(),
                    LinkCreatorForPreview(
                        self.presenter.getWikiDocument().getWikiData()),
                    asHtmlPreview=True)
    
            # TODO Reset after open wiki
            zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
            self.SetFonts("", "", [max(s + 2 * zoom, 1)
                    for s in self._DEFAULT_FONT_SIZES])
                    
#             print "refresh8", repr(html)
            self.SetPage(uniToGui(html))


        if self.anchor and self.HasAnchor(self.anchor):
            self.ScrollToAnchor(self.anchor)
            # Workaround because ScrollToAnchor scrolls too far
            lx, ly = self.GetViewStart()
            self.Scroll(lx, ly-1)
        elif self.outOfSync:
            lx, ly = wikiPage.getPresentation()[3:5]
            self.Scroll(lx, ly)
            
        self.anchor = None
        self.outOfSync = False

        ## _prof.stop()


    def onLoadedCurrentWikiPage(self, miscevt):
        self.anchor = miscevt.get("anchor")
        self.outOfSync = True
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

        self.exporterInstance.setWikiDataManager(self.presenter.getWikiDocument())

    def onClosingCurrentWiki(self, miscevt):
        if self.currentLoadedWikiWord:
            try:
                prevPage = self.presenter.getWikiDocument().getWikiPage(
                        self.currentLoadedWikiWord)
                prevPage.setPresentation(self.GetViewStart(), 3)
            except WikiWordNotFoundException, e:
                pass

    def onOptionsChanged(self, miscevt):
        self.outOfSync = True
        if self.visible:
            self.refresh()

    def onUpdatedWikiPage(self, miscevt):
        self.outOfSync = True
        if self.visible:
            self.refresh()
            
    def onChangedLiveText(self, miscevt):
        self.outOfSync = True


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
            self.presenter.getMainControl().openWikiPage(
                    word, motionType="child", anchor=anchor)
        else:
            self.presenter.getMainControl().launchUrl(href)


    def OnKeyUp(self, evt):
        acc = getAccelPairFromKeyDown(evt)
        if acc == (wxACCEL_CTRL, ord('C')): 
            # Consume original clipboard copy function
            pass
        else:
            evt.Skip()

    def addZoom(self, step):
        """
        Modify the zoom setting by step relative to current zoom in
        configuration.
        """
        zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
        zoom += step

        self.presenter.getConfig().set("main", "preview_zoom", str(zoom))
        self.outOfSync = True
        self.refresh()



    def OnKeyDown(self, evt):
        acc = getAccelPairFromKeyDown(evt)
        if acc == (wxACCEL_CTRL, ord('+')) or \
                acc == (wxACCEL_CTRL, WXK_NUMPAD_ADD):
            self.addZoom(1)
#             zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
#             self.presenter.getConfig().set("main", "preview_zoom", str(zoom + 1))
#             self.outOfSync = True
#             self.refresh()
        elif acc == (wxACCEL_CTRL, ord('-')) or \
                acc == (wxACCEL_CTRL, WXK_NUMPAD_SUBTRACT):
            self.addZoom(-1)
#             zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
#             self.presenter.getConfig().set("main", "preview_zoom", str(zoom - 1))
#             self.outOfSync = True
#             self.refresh()
        else:
            evt.Skip()

    def OnMouseWheel(self, evt):
        if evt.ControlDown():
            self.addZoom( -(evt.GetWheelRotation() // evt.GetWheelDelta()) )
#             zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
#             zoom -= evt.GetWheelRotation() // evt.GetWheelDelta()
#             self.presenter.getConfig().set("main", "preview_zoom", str(zoom))
#             self.outOfSync = True
#             self.refresh()
        else:
            evt.Skip()



