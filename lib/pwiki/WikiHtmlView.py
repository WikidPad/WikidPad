## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback, os, os.path, re

import wx, wx.html

from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID, \
        wxKeyFunctionSink, appendToMenuByMenuDesc

from MiscEvent import KeyFunctionSink

from StringOps import uniToGui, pathnameFromUrl, flexibleUrlUnquote
from Configuration import isWindows, MIDDLE_MOUSE_CONFIG_TO_TABMODE, isOSX

import DocPages
from TempFileSet import TempFileSet

import Exporters

if isWindows():
    try:
        import WikiHtmlViewIE
    except:
#         traceback.print_exc()
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
        if self.wikiDocument.isDefinedWikiLink(word):
            return u"internaljump:wikipage/%s" % word
        else:
            return default


def createWikiHtmlView(presenter, parent, ID):
    pvRenderer = presenter.getConfig().getint("main", "html_preview_renderer", 0)

    if WikiHtmlViewIE and pvRenderer > 0:
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
    else:
        return WikiHtmlView(presenter, parent, ID)



# class TestFilter(wx.html.HtmlFilter):
#     def CanRead(self, fsfile):
#         print "--TestFilter", repr(fsfile.GetLocation())
#         return False
#     
#     def ReadFile(self, fsfile):
#         return u""
# 
# wx.html.HtmlWindow.AddFilter(TestFilter())






# class MyLocalFSHandler(wx.FileSystemHandler):
#     def CanOpen(self, location):
#         print "--CanOpen1", repr(location), repr(self.GetProtocol(location))
#         return self.GetProtocol(location) == u"file"
#         
#     def OpenFile(self, fs, location):
#         print "--OpenFile", repr(location)
#         
#         right = self.GetRightLocation(location);
#         fn = wx.FileSystem.URLToFileName(right);
#         fullpath = os.path.abspath(fn)
#     
#         if not os.path.exists(fullpath):
#             return None
# #     
# #         // we need to check whether we can really read from this file, otherwise
# #         // wxFSFile is not going to work
# #         wxFFileInputStream *is = new wxFFileInputStream(fullpath);
# #         if ( !is->Ok() )
# #         {
# #             delete is;
# #             return (wxFSFile*) NULL;
# #         }
# 
#         f = open(fullpath, "rb")
# 
#         return wx.FSFile(f,
#                             right,
#                             self.GetMimeTypeFromExt(location),
#                             self.GetAnchor(location), wx.DateTime())
# #                             ,wxDateTime(wxFileModificationTime(fullpath))
# #                             );
# 
# 
# 
# wx.FileSystem.CleanUpHandlers()
# wx.FileSystem.AddHandler(MyLocalFSHandler())





class WikiHtmlView(wx.html.HtmlWindow):
    def __init__(self, presenter, parent, ID):
        wx.html.HtmlWindow.__init__(self, parent, ID)
        self.presenter = presenter

        self.presenterListener = wxKeyFunctionSink((
                ("loaded current wiki page", self.onLoadedCurrentWikiPage),
                ("reloaded current doc page", self.onReloadedCurrentPage),
                ("opened wiki", self.onOpenedWiki),
                ("closing current wiki", self.onClosingCurrentWiki)
#                 ("changed options", self.onOptionsChanged),
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

        self.currentLoadedWikiWord = None

        self.anchor = None  # Name of anchor to jump to when view gets visible
        self.contextHref = None  # Link href on which context menu was opened
        
        # TODO Should be changed to presenter as controller
        self.exporterInstance = Exporters.HtmlExporter(
                self.presenter.getMainControl())
                
        self._DEFAULT_FONT_SIZES = self.presenter.getMainControl().presentationExt.INTHTML_FONTSIZES
        
        # TODO More elegantly
        self.exporterInstance.exportType = u"html_previewWX"
        self.exporterInstance.styleSheet = u""
        self.exporterInstance.tempFileSet = TempFileSet()
        self._updateTempFilePrefPath()

        self.exporterInstance.setWikiDocument(
                self.presenter.getWikiDocument())
        self.exporterInstance.setLinkConverter(
                LinkConverterForPreview(self.presenter.getWikiDocument()))

        wx.EVT_KEY_DOWN(self, self.OnKeyDown)
        wx.EVT_KEY_UP(self, self.OnKeyUp)

        wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY, self.OnClipboardCopy)
        wx.EVT_MENU(self, GUI_ID.CMD_SELECT_ALL, lambda evt: self.SelectAll())
        wx.EVT_MENU(self, GUI_ID.CMD_ZOOM_IN, lambda evt: self.addZoom(1))
        wx.EVT_MENU(self, GUI_ID.CMD_ZOOM_OUT, lambda evt: self.addZoom(-1))
        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_THIS, self.OnActivateThis)        
        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS,
                self.OnActivateNewTabThis)        
        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS,
                self.OnActivateNewTabBackgroundThis)        

        self.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
        wx.EVT_LEFT_DCLICK(self, self.OnLeftDClick)
        wx.EVT_MIDDLE_DOWN(self, self.OnMiddleDown)
        wx.EVT_MOUSEWHEEL(self, self.OnMouseWheel)
        wx.EVT_MOTION(self, self.OnMouseMotion)        


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
        _RE_RIGHT_FILE_URL = re.compile(u"file:/[a-zA-Z]:")
        
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
                prevPage.setPresentation(self.GetViewStart(), 3)
            except WikiWordNotFoundException, e:
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
            self.SetFonts("", "", [max(s + 2 * zoom, 1)
                    for s in self._DEFAULT_FONT_SIZES])
                    
#             print "-- refresh8", html.encode("mbcs", "ignore")
            self.SetPage(uniToGui(html))


        if self.anchor:   #  and self.HasAnchor(self.anchor):
            if self.HasAnchor(self.anchor):
                self.ScrollToAnchor(self.anchor)
                # Workaround because ScrollToAnchor scrolls too far
                lx, ly = self.GetViewStart()
                self.Scroll(lx, ly-1)
            else:
                self.Scroll(0, 0)
        elif self.outOfSync:
            lx, ly = wikiPage.getPresentation()[3:5]
            self.Scroll(lx, ly)

        self.anchor = None
        self.outOfSync = False

        ## _prof.stop()


    def gotoAnchor(self, anchor):
        self.anchor = anchor
        if self.visible:
            self.refresh()
            
    
    def getSelectedText(self):
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
                prevPage.setPresentation(self.GetViewStart(), 3)
            except WikiWordNotFoundException, e:
                pass

    def onOptionsChanged(self, miscevt):
        self.outOfSync = True
        self._updateTempFilePrefPath()
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
                u"mouse/leftdoubleclick/preview/body", paramDict)

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
            if href.startswith(u"internaljump:wikipage/"):
                appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTERNAL_JUMP)
            else:
                appendToMenuByMenuDesc(menu, u"Activate;CMD_ACTIVATE_THIS")

            self.PopupMenuXY(menu, evt.GetX(), evt.GetY())
        else:
            # Jump to another wiki page
            
            # First check for an anchor. In URLs, anchors are always
            # separated by '#' regardless which character is used
            # in the wiki syntax (normally '!')
            # Now open wiki
            self._activateLink(href, tabMode=0)


    def _activateLink(self, href, tabMode=0):
        """
        Called if link was activated by clicking in the context menu, 
        therefore only links starting with "internaljump:wikipage/" can be
        handled.
        tabMode -- 0:Same tab; 2: new tab in foreground; 3: new tab in background
        """
        if href.startswith(u"internaljump:wikipage/"):
            # Jump to another wiki page
            
            # First check for an anchor. In URLs, anchors are always
            # separated by '#' regardless which character is used
            # in the wiki syntax (normally '!')
            try:
                word, anchor = href[22:].split(u"#", 1)
            except ValueError:
                word = href[22:]
                anchor = None

            # open the wiki page
            if tabMode & 2:
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

        elif href == u"internaljump:action/history/back":
            # Go back in history
            self.presenter.getMainControl().goBrowserBack()

        elif href.startswith(u"#"):
            anchor = href[1:]
            if self.HasAnchor(anchor):
                self.ScrollToAnchor(anchor)
                # Workaround because ScrollToAnchor scrolls too far
                lx, ly = self.GetViewStart()
                self.Scroll(lx, ly-1)
            else:
                self.Scroll(0, 0)
        else:
            self.presenter.getMainControl().launchUrl(href)


    def OnActivateThis(self, evt):
        self._activateLink(self.contextHref, tabMode=0)

    def OnActivateNewTabThis(self, evt):
        self._activateLink(self.contextHref, tabMode=2)

    def OnActivateNewTabBackgroundThis(self, evt):
        self._activateLink(self.contextHref, tabMode=3)
        

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
            self.addZoom( -(evt.GetWheelRotation() // evt.GetWheelDelta()) )
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
        callTip = u""
        status = u""

        if cell is not None:
            linkInfo = cell.GetLink()
            if linkInfo is not None:
                href = linkInfo.GetHref()
                if href.startswith(u"internaljump:wikipage/"):
                    # Jump to another wiki page
                    
                    # First check for an anchor. In URLs, anchors are always
                    # separated by '#' regardless which character is used
                    # in the wiki syntax (normally '!')
                    try:
                        wikiWord, anchor = href[22:].split(u"#", 1)
                        anchor = flexibleUrlUnquote(anchor)
                    except ValueError:
                        wikiWord = href[22:]
                        anchor = None

                    wikiWord = flexibleUrlUnquote(wikiWord)
                    
                    wikiDocument = self.presenter.getWikiDocument()
                    if wikiDocument is None:
                        return
                    wikiWord = wikiDocument.getUnAliasedWikiWord(wikiWord)

                    if wikiWord is not None:
                        propList = wikiDocument.getPropertyTriples(wikiWord,
                                u"short_hint", None)

                        if len(propList) > 0:
                            callTip = propList[-1][2]
                        
                        status = _(u"Link to page: %s") % wikiWord
                else:
                    status = href

        self.presenter.getMainControl().statusBar.SetStatusText(
                        uniToGui(status), 0)

        self.SetToolTipString(callTip)



_CONTEXT_MENU_INTERNAL_JUMP = \
u"""
Activate;CMD_ACTIVATE_THIS
Activate New Tab;CMD_ACTIVATE_NEW_TAB_THIS
Activate New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
"""


# Entries to support i18n of context menus

N_(u"Activate")
N_(u"Activate New Tab")
N_(u"Activate New Tab Backgrd.")

