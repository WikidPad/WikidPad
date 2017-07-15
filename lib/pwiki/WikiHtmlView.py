## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback, os, os.path, re

import wx, wx.html

from .WikiExceptions import *

from .SystemInfo import isWindows, isOSX

from . import wxHelper
from .wxHelper import getAccelPairFromKeyDown, GUI_ID, wxKeyFunctionSink, \
        appendToMenuByMenuDesc

from .MiscEvent import KeyFunctionSink

from . import StringOps
from .StringOps import utf8Enc, utf8Dec, pathEnc, urlFromPathname, \
        urlQuote, pathnameFromUrl, flexibleUrlUnquote
from .Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE

from . import OsAbstract

from . import DocPages
from .TempFileSet import TempFileSet

from . import PluginManager

# Try and load the html2 webview renderer
try:
    WikiHtmlViewWK = None
    if wx.version().startswith(("2.9", "3", "4")):
        from . import WikiHtmlView2
    else:
        WikiHtmlView2 = None

        try:
            from . import WikiHtmlViewWK
        except:
            WikiHtmlViewWK = None
            import ExceptionLogger
            ExceptionLogger.logOptionalComponentException("Initialize webkit HTML renderer")
            

except:
#         traceback.print_exc()
    WikiHtmlView2 = None
    import ExceptionLogger
    ExceptionLogger.logOptionalComponentException("Initialize webkit HTML2 renderer")



# Try and load Windows IE renderer
if isWindows():
    try:
        from . import WikiHtmlViewIE
    except:
        import ExceptionLogger
        ExceptionLogger.logOptionalComponentException("Initialize IE HTML renderer")
        WikiHtmlViewIE = None
else:
    WikiHtmlViewIE = None


class LinkConverterForPreview:
    """
    Faked link dictionary for HTML exporter
    """
    def __init__(self, wikiDocument):
        self.wikiDocument = wikiDocument
        
    def getLinkForWikiWord(self, word, default = None):
        if self.wikiDocument.isDefinedWikiLinkTerm(word):
            return "internaljump:wikipage/%s" % word
        else:
            return default


def createWikiHtmlView(presenter, parent, ID):
    pvRenderer = presenter.getConfig().getint("main", "html_preview_renderer", 0)

    if WikiHtmlViewIE and pvRenderer in (1, 2):
        # Set preview renderer to 0 = Internal
        config = presenter.getConfig()
        config.set("main", "html_preview_renderer", "0")
        config.saveGlobalConfig()
        hvIe = WikiHtmlViewIE.WikiHtmlViewIE(presenter, parent, ID,
                pvRenderer == 2)
        # If no error occurred, set back to previous value
        config.set("main", "html_preview_renderer", str(pvRenderer))
        config.saveGlobalConfig()
        return hvIe
        
    elif WikiHtmlViewWK and pvRenderer == 3:
        return WikiHtmlViewWK.WikiHtmlViewWK(presenter, parent, ID)

    elif WikiHtmlView2 and pvRenderer == 4:
        return WikiHtmlView2.WikiHtmlView2(presenter, parent, ID)

    # Internal preview if nothing else wanted or possible
    return WikiHtmlView(presenter, parent, ID)


class WikiHtmlView(wx.html.HtmlWindow):
    def __init__(self, presenter, parent, ID):
        wx.html.HtmlWindow.__init__(self, parent, ID)
        self.presenter = presenter

        self.presenterListener = wxKeyFunctionSink((
                ("loaded current wiki page", self.onLoadedCurrentWikiPage),
                ("reloaded current doc page", self.onReloadedCurrentPage),
                ("opened wiki", self.onOpenedWiki),
                ("closing current wiki", self.onClosingCurrentWiki)
        ), self.presenter.getMiscEvent())
        
        self.__sinkApp = wxKeyFunctionSink((
                ("options changed", self.onOptionsChanged),
        ), wx.GetApp().getMiscEvent())
        
        self.__sinkDocPage = wxKeyFunctionSink((
                ("updated wiki page", self.onUpdatedWikiPage),
                ("changed live text", self.onChangedLiveText)
        ), self.presenter.getCurrentDocPageProxyEvent())

        self.visible = False
        self.outOfSync = True   # HTML content is out of sync with live content
        self.counterResizeIgnore = 0  # How often to ignore a size event
        self.deferredScrollPos = None  # Used by scrollDeferred()

        self.currentLoadedWikiWord = None

        self.anchor = None  # Name of anchor to jump to when view gets visible
        self.contextHref = None  # Link href on which context menu was opened
        
        # TODO Should be changed to presenter as controller
        self.exporterInstance = PluginManager.getExporterTypeDict(
                self.presenter.getMainControl(), False)["html_single"][0]\
                (self.presenter.getMainControl())

        self._DEFAULT_FONT_SIZES = self.presenter.getMainControl().presentationExt.INTHTML_FONTSIZES
        
        # TODO More elegantly
        self.exporterInstance.exportType = "html_previewWX"
        self.exporterInstance.styleSheet = ""
        self.exporterInstance.tempFileSet = TempFileSet()
        self._updateTempFilePrefPath()

        self.exporterInstance.setWikiDocument(
                self.presenter.getWikiDocument())
        self.exporterInstance.setLinkConverter(
                LinkConverterForPreview(self.presenter.getWikiDocument()))

        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyUp)
        self.Bind(wx.EVT_SIZE, self.OnSize)

        self.Bind(wx.EVT_MENU, self.OnClipboardCopy, id=GUI_ID.CMD_CLIPBOARD_COPY)
        self.Bind(wx.EVT_MENU, lambda evt: self.SelectAll(), id=GUI_ID.CMD_SELECT_ALL)
        self.Bind(wx.EVT_MENU, lambda evt: self.addZoom(1), id=GUI_ID.CMD_ZOOM_IN)
        self.Bind(wx.EVT_MENU, lambda evt: self.addZoom(-1), id=GUI_ID.CMD_ZOOM_OUT)
        self.Bind(wx.EVT_MENU, self.OnActivateThis, id=GUI_ID.CMD_ACTIVATE_THIS)        
        self.Bind(wx.EVT_MENU, self.OnActivateNewTabThis,
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewTabBackgroundThis,
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewWindowThis,
                id=GUI_ID.CMD_ACTIVATE_NEW_WINDOW_THIS)

        self.Bind(wx.EVT_MENU, self.OnOpenContainingFolderThis,
                id=GUI_ID.CMD_OPEN_CONTAINING_FOLDER_THIS)

        self.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDClick)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleDown)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)


    def setLayerVisible(self, vis, scName=""):
        """
        Informs the widget if it is really visible on the screen or not
        """
        if not self.visible and vis:
            self.outOfSync = True   # Just to be sure
            self.refresh()
            
        if not vis:
            self.exporterInstance.tempFileSet.clear()

        self.visible = vis



    if isWindows():
        _RE_RIGHT_FILE_URL = re.compile("file:/[a-zA-Z]:")
        
        def OnOpeningURL(self, typ, url):
            if url.startswith("file:"):
                if self._RE_RIGHT_FILE_URL.match(url):
                    return wx.html.HTML_OPEN
                # At least under Windows, wxWidgets has another
                # opinion how a local file URL should look like
                # than Python.
                # The same processing is done already by the exporter
                # for WikidPad URL but not for URLs in HTML tags. 
                p = pathnameFromUrl(url)
                url = wx.FileSystem.FileNameToURL(p)
                return url
    
            return wx.html.HTML_OPEN


    def close(self):
        self.Unbind(wx.EVT_SET_FOCUS)
        self.setLayerVisible(False)
        self.presenterListener.disconnect()
        self.__sinkApp.disconnect()
        self.__sinkDocPage.disconnect()


# This doesn't work for wxPython 2.8 and newer, constants are missing
#     _DEFAULT_FONT_SIZES = (wx.html.HTML_FONT_SIZE_1, wx.html.HTML_FONT_SIZE_2, 
#             wx.html.HTML_FONT_SIZE_3, wx.html.HTML_FONT_SIZE_4,
#             wx.html.HTML_FONT_SIZE_5, wx.html.HTML_FONT_SIZE_6,
#             wx.html.HTML_FONT_SIZE_7)

    # These are the Windows sizes
#     if isWindows():
#         _DEFAULT_FONT_SIZES = (7, 8, 10, 12, 16, 22, 30)
#     elif isOSX():
#         _DEFAULT_FONT_SIZES = (9, 12, 14, 18, 24, 30, 36)
#     else:
#         _DEFAULT_FONT_SIZES = (10, 12, 14, 16, 19, 24, 32)




    # For __WXGPE__ (?)
    # _DEFAULT_FONT_SIZES = (6, 7, 8, 9, 10, 12, 14)
    # For others
    # _DEFAULT_FONT_SIZES = (10, 12, 14, 16, 19, 24, 32)


    def refresh(self):
        ## _prof.start()
        
        # Store position of currently displayed page, if any
        if self.currentLoadedWikiWord:
            try:
                prevPage = self.presenter.getWikiDocument().getWikiPage(
                        self.currentLoadedWikiWord)
                prevPage.setPresentation(self.getIntendedViewStart(), 3)
            except WikiWordNotFoundException as e:
                pass

        wikiPage = self.presenter.getDocPage()
        if isinstance(wikiPage,
                (DocPages.DataCarryingPage, DocPages.AliasWikiPage)) and \
                not wikiPage.checkFileSignatureAndMarkDirty():
            # Valid wiki page and invalid signature -> rebuild HTML page
            self.outOfSync = True

        if self.outOfSync:
            self.currentLoadedWikiWord = None
    
            if wikiPage is None:
                return  # TODO Do anything else here?
                
            word = wikiPage.getWikiWord()
            if word is None:
                return  # TODO Do anything else here?

            # Remove previously used temporary files
            self.exporterInstance.tempFileSet.clear()
            self.exporterInstance.buildStyleSheetList()

            self.currentLoadedWikiWord = word
#             content = self.presenter.getLiveText()

            html = self.exporterInstance.exportWikiPageToHtmlString(wikiPage)

            wx.GetApp().getInsertionPluginManager().taskEnd()

    
            # TODO Reset after open wiki
            zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
            lx, ly = self.getIntendedViewStart()
            self.SetFonts("", "", [max(s + 2 * zoom, 1)
                    for s in self._DEFAULT_FONT_SIZES])
                    
#             print "-- refresh8", html.encode("mbcs", "ignore")
            self.SetPage(html)
            self.scrollDeferred(lx, ly)

#         traceback.print_stack()
        if self.anchor:   #  and self.HasAnchor(self.anchor):
            if self.HasAnchor(self.anchor):
                self.ScrollToAnchor(self.anchor)
                # Workaround because ScrollToAnchor scrolls too far
                # Here the real scroll position is needed so
                # getIntendedViewStart() is not called
                lx, ly = self.GetViewStart()
                self.scrollDeferred(lx, ly-1)
            else:
                self.scrollDeferred(0, 0)
        elif self.outOfSync:
            lx, ly = wikiPage.getPresentation()[3:5]
            self.scrollDeferred(lx, ly)

        self.anchor = None
        self.outOfSync = False

        ## _prof.stop()


    def gotoAnchor(self, anchor):
        self.anchor = anchor
        if self.visible:
            self.refresh()
            
    
    def GetSelectedText(self):
        return self.SelectionToText()


    def _updateTempFilePrefPath(self):
        wikiDocument = self.presenter.getWikiDocument()

        if wikiDocument is not None:
            self.exporterInstance.tempFileSet.setPreferredPath(
                    wikiDocument.getWikiTempDir())
        else:
            self.exporterInstance.tempFileSet.setPreferredPath(None)


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
            self.gotoAnchor(anchor)
#             self.anchor = anchor
#             if self.visible:
#                 self.refresh()

    def onOpenedWiki(self, miscevt):
        self.currentLoadedWikiWord = None

        self._updateTempFilePrefPath()
        self.exporterInstance.setWikiDocument(
                self.presenter.getWikiDocument())
        self.exporterInstance.setLinkConverter(
                LinkConverterForPreview(self.presenter.getWikiDocument()))

    def onClosingCurrentWiki(self, miscevt):
        if self.currentLoadedWikiWord:
            try:
                prevPage = self.presenter.getWikiDocument().getWikiPage(
                        self.currentLoadedWikiWord)
                prevPage.setPresentation(self.getIntendedViewStart(), 3)
            except WikiWordNotFoundException as e:
                pass

    def onOptionsChanged(self, miscevt):
        self.outOfSync = True
        self._updateTempFilePrefPath()
        if self.visible:
            self.refresh()

    def onUpdatedWikiPage(self, miscevt):
        if self.presenter.getConfig().getboolean("main",
                "html_preview_reduceUpdateHandling", False):
            return

        self.outOfSync = True
        if self.visible:
            self.refresh()
            
    def onChangedLiveText(self, miscevt):
        self.outOfSync = True


    def scrollDeferred(self, lx, ly):
        if self.deferredScrollPos is not None:
            # An unprocessed _scrollAndThaw is in the message queue yet ->
            # just change scrollPos
            self.deferredScrollPos = (lx, ly)
        else:
            # Put new _scrollAndThaw into queue
            self.Freeze()
            self.deferredScrollPos = (lx, ly)
            wx.CallAfter(self._scrollAndThaw)
        
    def _scrollAndThaw(self):
        if wxHelper.isDead(self):
            return
            
        self.Scroll(self.deferredScrollPos[0], self.deferredScrollPos[1])
        self.Thaw()
        self.deferredScrollPos = None
        self.counterResizeIgnore = 0


    def OnSize(self, evt):
        lx, ly = self.getIntendedViewStart()
        self.scrollDeferred(lx, ly)

        evt.Skip()


    def OnSetFocus(self, evt):
        if self.visible:
            self.refresh()

    def OnClipboardCopy(self, evt):
        text = self.SelectionToText()
        if len(text) == 0:
            return

        wxHelper.copyTextToClipboard(text)


    def OnLeftDClick(self, evt):
        pos = self.CalcUnscrolledPosition(evt.GetPosition())
        cell = self.GetInternalRepresentation().FindCellByPos(pos.x, pos.y)
        if cell is not None:
            linkInfo = cell.GetLink()
            if linkInfo is not None:
                evt.Skip()
                return
                
        pres = self.presenter
        mc = pres.getMainControl()
                
        paramDict = {"page": pres.getDocPage(), "presenter": pres,
                "main control": mc}
                
        mc.getUserActionCoord().reactOnUserEvent(
                "mouse/leftdoubleclick/preview/body", paramDict)

#         self.presenter.switchSubControl("textedit")

        
    def OnMiddleDown(self, evt):
        pos = self.CalcUnscrolledPosition(evt.GetPosition())
        cell = self.GetInternalRepresentation().FindCellByPos(pos.x, pos.y)
        if cell is not None:
            linkInfo = cell.GetLink()
            if linkInfo is not None:
                if not evt.ControlDown():
                    middleConfig = self.presenter.getConfig().getint("main",
                            "mouse_middleButton_withoutCtrl", 2)
                else:
                    middleConfig = self.presenter.getConfig().getint("main",
                            "mouse_middleButton_withCtrl", 3)

                tabMode = MIDDLE_MOUSE_CONFIG_TO_TABMODE[middleConfig]

                self._activateLink(cell.GetLink().GetHref(), tabMode=tabMode)
                return

        evt.Skip()


    def OnLinkClicked(self, linkinfo):
        href = linkinfo.GetHref()
        evt = linkinfo.GetEvent()

        if evt.RightUp():
            self.contextHref = linkinfo.GetHref()
            menu = wx.Menu()
            if href.startswith("internaljump:wikipage/"):
                appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTERNAL_JUMP)
            else:
                appendToMenuByMenuDesc(menu, "Activate;CMD_ACTIVATE_THIS")
                
                if href.startswith("file:") or \
                        href.startswith("rel://"):

                    appendToMenuByMenuDesc(menu,
                            "Open Containing Folder;"
                            "CMD_OPEN_CONTAINING_FOLDER_THIS")

            self.PopupMenuXY(menu, evt.GetX(), evt.GetY())
        else:
            # Jump to another wiki page
            
            # First check for an anchor. In URLs, anchors are always
            # separated by '#' regardless which character is used
            # in the wiki syntax (normally '!')
            # Now open wiki
            self._activateLink(href, tabMode=0)


    if isOSX():
        def GetViewStart(self):
            result = wx.html.HtmlWindow.GetViewStart(self)
            if isinstance(result, wx.Point):
                return (result.x, result.y)
            else:
                return result


    def getIntendedViewStart(self):
        """
        If a deferred scrolling waits for process, this returns the deferred
        scroll values instead of real view start
        """
        if self.deferredScrollPos is not None:
            return self.deferredScrollPos
        else:
            return tuple(self.GetViewStart())


    def _activateLink(self, href, tabMode=0):
        """
        Called if link was activated by clicking in the context menu, 
        therefore only links starting with "internaljump:wikipage/" can be
        handled.
        tabMode -- 0:Same tab; 2: new tab in foreground; 3: new tab in background
        """
        if href.startswith("internaljump:wikipage/"):
            # Jump to another wiki page
            
            # First check for an anchor. In URLs, anchors are always
            # separated by '#' regardless which character is used
            # in the wiki syntax (normally '!')
            try:
                word, anchor = href[22:].split("#", 1)
            except ValueError:
                word = href[22:]
                anchor = None

            # open the wiki page
            if tabMode & 2:
                if tabMode == 6:
                    # New Window
                    presenter = self.presenter.getMainControl().\
                            createNewDocPagePresenterTabInNewFrame()
                else:
                    # New tab
                    presenter = self.presenter.getMainControl().\
                            createNewDocPagePresenterTab()
                    presenter.switchSubControl("preview", False)
            else:
                # Same tab
                presenter = self.presenter

            presenter.openWikiPage(word, motionType="child", anchor=anchor)

            if not tabMode & 1:
                # Show in foreground
#                 presenter.switchSubControl("preview", True)
                presenter.getMainControl().getMainAreaPanel().\
                        showPresenter(presenter)
                presenter.SetFocus()
#             else:
#                 presenter.switchSubControl("preview", False)

        elif href == "internaljump:action/history/back":
            # Go back in history
            self.presenter.getMainControl().goBrowserBack()

        elif href.startswith("#"):
            anchor = href[1:]
            if self.HasAnchor(anchor):
                self.ScrollToAnchor(anchor)
                # Workaround because ScrollToAnchor scrolls too far
                # Here the real scroll position is needed so
                # getIntendedViewStart() is not called
                lx, ly = self.GetViewStart()
                self.scrollDeferred(lx, ly-1)
            else:
                self.scrollDeferred(0, 0)
        else:
            self.presenter.getMainControl().launchUrl(href)


    def OnActivateThis(self, evt):
        self._activateLink(self.contextHref, tabMode=0)

    def OnActivateNewTabThis(self, evt):
        self._activateLink(self.contextHref, tabMode=2)

    def OnActivateNewTabBackgroundThis(self, evt):
        self._activateLink(self.contextHref, tabMode=3)

    def OnActivateNewWindowThis(self, evt):
        self._activateLink(self.contextHref, tabMode=6)


    def OnOpenContainingFolderThis(self, evt):
        if not self.contextHref:
            return

        link = self.contextHref

        if link.startswith("rel://"):
            link = self.presenter.getWikiDocument().makeRelUrlAbsolute(link)

        if link.startswith("file:"):
            try:
                path = os.path.dirname(StringOps.pathnameFromUrl(link))
                if not os.path.exists(StringOps.longPathEnc(path)):
                    self.presenter.displayErrorMessage(
                            _("Folder does not exist"))
                    return

                OsAbstract.startFile(self.presenter.getMainControl(),
                        path)
            except IOError:
                pass   # Error message?


    def OnKeyUp(self, evt):
        acc = getAccelPairFromKeyDown(evt)
        if acc == (wx.ACCEL_CTRL, ord('C')): 
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
        if acc == (wx.ACCEL_CTRL, ord('+')) or \
                acc == (wx.ACCEL_CTRL, wx.WXK_NUMPAD_ADD):
            self.addZoom(1)
        elif acc == (wx.ACCEL_CTRL, ord('-')) or \
                acc == (wx.ACCEL_CTRL, wx.WXK_NUMPAD_SUBTRACT):
            self.addZoom(-1)
        else:
            evt.Skip()


    def OnMouseWheel(self, evt):
        if evt.ControlDown():
            if self.presenter.getConfig().getboolean(
                    "main", "mouse_reverseWheelZoom", False):
                self.addZoom( -(evt.GetWheelRotation() // evt.GetWheelDelta()) )
            else:
                self.addZoom( evt.GetWheelRotation() // evt.GetWheelDelta() )
        else:
            evt.Skip()


    def OnMouseMotion(self, evt):
        evt.Skip()

        pos = self.CalcUnscrolledPosition(evt.GetPosition())
        irep = self.GetInternalRepresentation()
        if irep is None:
            cell = None
        else:
            cell = irep.FindCellByPos(pos.x, pos.y)
        callTip = ""
        status = ""

        if cell is not None:
            linkInfo = cell.GetLink()
            if linkInfo is not None:
                href = linkInfo.GetHref()
                if href.startswith("internaljump:wikipage/"):
                    # Jump to another wiki page
                    
                    # First check for an anchor. In URLs, anchors are always
                    # separated by '#' regardless which character is used
                    # in the wiki syntax (normally '!')
                    try:
                        wikiWord, anchor = href[22:].split("#", 1)
                        anchor = flexibleUrlUnquote(anchor)
                    except ValueError:
                        wikiWord = href[22:]
                        anchor = None

                    wikiWord = flexibleUrlUnquote(wikiWord)
                    
                    wikiDocument = self.presenter.getWikiDocument()
                    if wikiDocument is None:
                        return
                    wikiWord = wikiDocument.getWikiPageNameForLinkTerm(wikiWord)

                    if wikiWord is not None:
                        propList = wikiDocument.getAttributeTriples(wikiWord,
                                "short_hint", None)

                        if len(propList) > 0:
                            callTip = propList[-1][2]
                        
                        status = _("Link to page: %s") % wikiWord
                else:
                    status = href

        self.presenter.getMainControl().statusBar.SetStatusText(status, 0)

        self.SetToolTip(callTip)



_CONTEXT_MENU_INTERNAL_JUMP = \
"""
Activate;CMD_ACTIVATE_THIS
Activate New Tab;CMD_ACTIVATE_NEW_TAB_THIS
Activate New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
Activate New Window;CMD_ACTIVATE_NEW_WINDOW_THIS
"""


# Entries to support i18n of context menus
if False:
    N_("Activate")
    N_("Activate New Tab")
    N_("Activate New Tab Backgrd.")
    N_("Activate New Window")

