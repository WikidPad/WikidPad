

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import io as StringIO
import urllib.request, urllib.parse, urllib.error, os, os.path, traceback

import wx, wx.html

if wx.Platform == '__WXMSW__':
#     import wx.activex
    import wx.lib.iewin as iewin
    from .WindowsHacks import getLongPath
else:
    iewin = None


# if wx.Platform == '__WXMSW__':
#     try:
#         # Generate dependencies for py2exe
#         import comtypes.gen._99AB80C4_5E19_4FD5_B3CA_5EF62FC3F765_0_1_0 as _dummy
#         import comtypes.gen.myole4ax as _dummy
#         import comtypes.gen._3050F1C5_98B5_11CF_BB82_00AA00BDCE0B_0_4_0 as _dummy
#         import comtypes.gen.MSHTML as _dummy
#         del _dummy
#     except:
#         pass

if not True:
    # Generate dependencies for py2exe
    import comtypes.gen._99AB80C4_5E19_4FD5_B3CA_5EF62FC3F765_0_1_0 as _dummy
    import comtypes.gen.myole4ax as _dummy
    import comtypes.gen._3050F1C5_98B5_11CF_BB82_00AA00BDCE0B_0_4_0 as _dummy
    import comtypes.gen.MSHTML as _dummy



from .WikiExceptions import *
from .wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID, \
        wxKeyFunctionSink

from .MiscEvent import KeyFunctionSink

from .StringOps import utf8Enc, utf8Dec, pathEnc, urlFromPathname, \
        urlQuote, pathnameFromUrl, flexibleUrlUnquote

from . import DocPages
from .TempFileSet import TempFileSet

from . import PluginManager



class LinkConverterForPreviewIe:
    """
    Faked link dictionary for HTML exporter
    """
    def __init__(self, wikiDocument):
        self.wikiDocument = wikiDocument

    def getLinkForWikiWord(self, word, default = None):
        if self.wikiDocument.isDefinedWikiLinkTerm(word):
            return urlQuote("http://internaljump/wikipage/%s" % word, "/#:;@")
        else:
            return default

class LinkConverterForPreviewMoz:
    """
    Faked link dictionary for HTML exporter
    """
    def __init__(self, wikiDocument):
        self.wikiDocument = wikiDocument

    def getLinkForWikiWord(self, word, default = None):
        if self.wikiDocument.isDefinedWikiLinkTerm(word):
            return urlQuote("file://internaljump/wikipage/%s" % word, "/#:;@")
        else:
            return default


class WikiHtmlViewIE(iewin.IEHtmlWindow):
    def __init__(self, presenter, parent, ID, drivingMoz):
        self.drivingMoz = drivingMoz

        if self.drivingMoz:
#             wx.activex.IEHtmlWindowBase.__init__(self, parent,    # wx.activex.CLSID(
            wx.lib.activex.ActiveXCtrl.__init__(self, parent,
                '{1339B54C-3453-11D2-93B9-000000000000}',
                ID, pos=wx.DefaultPosition, size=wx.DefaultSize, style=0,
                name='MozHtmlWindow')
            self.LinkConverterForPreview = LinkConverterForPreviewMoz
        else:
#             wx.activex.IEHtmlWindowBase.__init__(self, parent,
            wx.lib.activex.ActiveXCtrl.__init__(self, parent,
#                 '{8856F961-340A-11D0-A96B-00C04FD705A2}',
                'Shell.Explorer.2', 
                ID, pos=wx.DefaultPosition, size=wx.DefaultSize, style=0,
                name='IEHtmlWindow')
            self.LinkConverterForPreview = LinkConverterForPreviewIe


        self._canGoBack = False
        self._canGoForward = False


        self.presenter = presenter

        self.presenterListener = wxKeyFunctionSink((
                ("loaded current wiki page", self.onLoadedCurrentWikiPage),
                ("reloaded current doc page", self.onReloadedCurrentPage),
                ("opened wiki", self.onOpenedWiki),
                ("closing current wiki", self.onClosingCurrentWiki)
#                 ("options changed", self.onOptionsChanged),
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
        self.deferredScrollPos = None  # Used by scrollDeferred()

        self.currentLoadedWikiWord = None
        self.currentLoadedUrl = None  # Contains the URL of the temporary HTML
                # file without anchors

        self.anchor = None  # Name of anchor to jump to when view gets visible
        self.lastAnchor = None
        self.passNavigate = 0


        # TODO Should be changed to presenter as controller
        self.exporterInstance = PluginManager.getExporterTypeDict(
                self.presenter.getMainControl(), False)["html_single"][0]\
                (self.presenter.getMainControl())

        # TODO More elegantly
        if self.drivingMoz:
            self.exporterInstance.exportType = "html_previewMOZ"
        else:
            self.exporterInstance.exportType = "html_previewIE"

        self.exporterInstance.tempFileSet = TempFileSet()
        self._updateTempFilePrefPath()

        self.exporterInstance.setWikiDocument(
                self.presenter.getWikiDocument())
        self.exporterInstance.setLinkConverter(
                self.LinkConverterForPreview(self.presenter.getWikiDocument()))

        # Create two temporary html files (IE 7 needs two to work)
        self.htpaths = [None, None]
        self.htpaths[0] = self.exporterInstance.tempFileSet.createTempFile(
                    "", ".html", relativeTo="")
        self.htpaths[1] = self.exporterInstance.tempFileSet.createTempFile(
                    "", ".html", relativeTo="")

        self.normHtpaths = [os.path.normcase(getLongPath(self.htpaths[0])),
                os.path.normcase(getLongPath(self.htpaths[1]))]
                
        self.currentHtpath = 0 # index into self.htpaths

#         iewin.EVT_BeforeNavigate2(self, self.GetId(), self.OnBeforeNavigate)

        self.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
#         EVT_MOUSEWHEEL(self, self.OnMouseWheel)


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


    def close(self):
        self.setLayerVisible(False)
        try:
            os.remove(pathEnc(self.htpaths[0]))
        except:
            pass

        try:
            os.remove(pathEnc(self.htpaths[1]))
        except:
            pass
            # TODO: Option to show also these exceptions
            # traceback.print_exc()

        self.presenterListener.disconnect()
        self.__sinkApp.disconnect()
        self.__sinkDocPage.disconnect()


    def refresh(self):
        ## _prof.start()
        
        # Store position of currently displayed page, if any
        if self.currentLoadedWikiWord:
            try:
                prevPage = self.presenter.getWikiDocument().getWikiPage(
                        self.currentLoadedWikiWord)
                prevPage.setPresentation(self.GetViewStart(), 3)
            except WikiWordNotFoundException as e:
                pass
            except AttributeError:
                pass

        wikiPage = self.presenter.getDocPage()
        if isinstance(wikiPage,
                (DocPages.DataCarryingPage, DocPages.AliasWikiPage)) and \
                not wikiPage.checkFileSignatureAndMarkDirty():
            # Valid wiki page and invalid signature -> rebuild HTML page
            self.outOfSync = True

        if self.outOfSync:
#             self.currentLoadedWikiWord = None

            wikiDocument = self.presenter.getWikiDocument()
            if wikiDocument is None:
                self.currentLoadedWikiWord = None
                return

            if wikiPage is None:
                self.currentLoadedWikiWord = None
                return  # TODO Do anything else here?

            word = wikiPage.getWikiWord()
            if word is None:
                self.currentLoadedWikiWord = None
                return  # TODO Do anything else here?
            
            # Remove previously used temporary files
            self.exporterInstance.tempFileSet.clear()
            self.exporterInstance.buildStyleSheetList()

            content = self.presenter.getLiveText()

            html = self.exporterInstance.exportWikiPageToHtmlString(wikiPage)

            wx.GetApp().getInsertionPluginManager().taskEnd()
            
            if self.currentLoadedWikiWord == word and \
                    self.anchor is None:

                htpath = self.htpaths[self.currentHtpath]

                with open(htpath, "w", encoding="utf-8") as f:
                    f.write(html)

                url = "file:" + urlFromPathname(htpath)
                self.currentLoadedUrl = url
                self.passNavigate += 1
#                 self.RefreshPage(iewin.REFRESH_COMPLETELY)

                lx, ly = self.GetViewStart()

                self.LoadUrl(url, iewin.NAV_NoReadFromCache | iewin.NAV_NoWriteToCache)
                self.scrollDeferred(lx, ly)
            else:                        
                self.currentLoadedWikiWord = word

                self.currentHtpath = 1 - self.currentHtpath
                htpath = self.htpaths[self.currentHtpath]
                
                with open(htpath, "w", encoding="utf-8") as f:
                    f.write(html)

                url = "file:" + urlFromPathname(htpath)
                self.currentLoadedUrl = url
    
                if self.anchor is not None:
                    url += "#" + self.anchor
    
                self.passNavigate += 1
                self.LoadUrl(url, iewin.NAV_NoReadFromCache | iewin.NAV_NoWriteToCache)
                self.lastAnchor = self.anchor
                
                if self.anchor is None:
                    lx, ly = wikiPage.getPresentation()[3:5]
                    self.scrollDeferred(lx, ly)

        else:  # Not outOfSync
            if self.anchor is not None:
                self.passNavigate += 1
                self.LoadUrl(self.currentLoadedUrl + "#" + self.anchor)
                self.lastAnchor = self.anchor

        self.anchor = None
        self.outOfSync = False

        ## _prof.stop()



    # IE ActiveX wx mapping
    def GetViewStart(self):
        """
        Bridge IE ActiveX object to wx's ScrolledWindow.
        """
        body = self.ctrl.Document.body
        return (body.scrollLeft, body.scrollTop)

    def Scroll(self, x, y):
        """
        Bridge IE ActiveX object to wx's ScrolledWindow
        """
        body = self.ctrl.Document.body
        body.scrollLeft = x
        body.scrollTop = y



    def gotoAnchor(self, anchor):
        self.anchor = anchor
        if self.visible:
#             self.outOfSync = True
            self.refresh()

    def GetSelectedText(self):
        return self.GetStringSelection(False)


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
                self.LinkConverterForPreview(self.presenter.getWikiDocument()))

    def onClosingCurrentWiki(self, miscevt):
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
        self.deferredScrollPos = (lx, ly)


    def DownloadComplete(self, this):
        if self.deferredScrollPos is not None:
            self.Scroll(self.deferredScrollPos[0], self.deferredScrollPos[1])


    def OnSetFocus(self, evt):
        try:
            if self.visible:
                self.refresh()
        except:
            traceback.print_exc()
            

#     def OnClipboardCopy(self, evt):
#         copyTextToClipboard(self.SelectionToText())



    def BeforeNavigate2(self, this, pDisp, URL, Flags, TargetFrameName,
                        PostData, Headers, Cancel):
                            
        Cancel[0] = False
        if self.passNavigate:
            self.passNavigate -= 1
            return
            
        if (not (Flags[0] and iewin.NAV_Hyperlink)) and \
                self.presenter.getConfig().getboolean("main",
                "html_preview_ieShowIframes", False):
            return

        href = URL[0]


        if self.drivingMoz:
            internaljumpPrefix = "file://internaljump/"
        else:
            internaljumpPrefix = "http://internaljump/"
            
        if href.startswith(internaljumpPrefix + "wikipage/"):

            if self.drivingMoz:
                # Unlike stated, the Mozilla ActiveX control has some
                # differences to the IE control. For instance, it returns
                # here an UTF-8 URL-quoted string, while IE returns the
                # unicode as it is.
                href = utf8Dec(urllib.parse.unquote(href.encode("ascii", "replace")))[0]

            Cancel[0] = True
            # Jump to another wiki page

            # First check for an anchor. In URLs, anchors are always
            # separated by '#' regardless which character is used
            # in the wiki syntax (normally '!')
            try:
                word, anchor = href[len(internaljumpPrefix) + 9:].split("#", 1)
            except ValueError:
                word = href[len(internaljumpPrefix) + 9:]
                anchor = None
            
            # unescape word
            word = urllib.parse.unquote(word) # utf8Dec(urllib.unquote(word))[0]
            if anchor:
                anchor = urllib.parse.unquote(anchor)  # utf8Dec(urllib.unquote(anchor))[0]

            # Now open wiki
            self.presenter.getMainControl().openWikiPage(
                    word, motionType="child", anchor=anchor)

#         elif href.startswith(internaljumpPrefix + u"action/scroll/selfanchor/"):
#             anchorFragment = href[len(internaljumpPrefix + u"action/scroll/selfanchor/"):]
#             self.gotoAnchor(anchorFragment)
#             evt.Cancel = True

        elif href == (internaljumpPrefix + "action/history/back"):
            # Go back in history
            self.presenter.getMainControl().goBrowserBack()
            Cancel[0] = True

        elif href == (internaljumpPrefix + "mouse/leftdoubleclick/preview/body"):
            pres = self.presenter
            mc = pres.getMainControl()

            paramDict = {"page": pres.getDocPage(), "presenter": pres,
                    "main control": mc}

            mc.getUserActionCoord().reactOnUserEvent(
                    "mouse/leftdoubleclick/preview/body", paramDict)
            Cancel[0] = True

        elif href.startswith("file:"):
            hrefSplit = href.split("#", 1)
            hrefNoFragment = hrefSplit[0]
            normedPath = os.path.normcase(getLongPath(pathnameFromUrl(hrefNoFragment)))
            if len(hrefSplit) == 2 and normedPath in self.normHtpaths:
                self.gotoAnchor(hrefSplit[1])
                Cancel[0] = True
            else:
                self.presenter.getMainControl().launchUrl(href)
                Cancel[0] = True
        else:
            self.presenter.getMainControl().launchUrl(href)
            Cancel[0] = True


    def StatusTextChange(self, status):
        if self.visible:
            if self.drivingMoz:
                internaljumpPrefix = "file://internaljump/wikipage/"
            else:
                internaljumpPrefix = "http://internaljump/wikipage/"

            if status.startswith(internaljumpPrefix):
                # First check for an anchor. In URLs, anchors are always
                # separated by '#' regardless which character is used
                # in the wiki syntax (normally '!')
                try:
                    wikiWord, anchor = status[len(internaljumpPrefix):].split(
                            "#", 1)
                    anchor = flexibleUrlUnquote(anchor)
                except ValueError:
                    wikiWord = status[len(internaljumpPrefix):]
                    anchor = None
                    
                wikiWord = flexibleUrlUnquote(wikiWord)

                wikiDocument = self.presenter.getWikiDocument()
                if wikiDocument is None:
                    return
                    
                wikiWord = wikiDocument.getWikiPageNameForLinkTerm(wikiWord)

                if wikiWord is not None:
                    status = _("Link to page: %s") % wikiWord

            self.presenter.getMainControl().statusBar.SetStatusText(
                    status, 0)


#     def OnKeyUp(self, evt):
#         acc = getAccelPairFromKeyDown(evt)
#         if acc == (wxACCEL_CTRL, ord('C')):
#             # Consume original clipboard copy function
#             pass
#         else:
#             evt.Skip()
#
#     def addZoom(self, step):
#         """
#         Modify the zoom setting by step relative to current zoom in
#         configuration.
#         """
#         zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
#         zoom += step
#
#         self.presenter.getConfig().set("main", "preview_zoom", str(zoom))
#         self.outOfSync = True
#         self.refresh()
#
#
#
#     def OnKeyDown(self, evt):
#         print "OnKeyDown1"
#         acc = getAccelPairFromKeyDown(evt)
#         if acc == (wxACCEL_CTRL, ord('+')) or \
#                 acc == (wxACCEL_CTRL, WXK_NUMPAD_ADD):
#             self.addZoom(1)
#         elif acc == (wxACCEL_CTRL, ord('-')) or \
#                 acc == (wxACCEL_CTRL, WXK_NUMPAD_SUBTRACT):
#             self.addZoom(-1)
#         else:
#             evt.Skip()
#
#     def OnMouseWheel(self, evt):
#         if evt.ControlDown():
#             self.addZoom( -(evt.GetWheelRotation() // evt.GetWheelDelta()) )
#         else:
#             evt.Skip()


