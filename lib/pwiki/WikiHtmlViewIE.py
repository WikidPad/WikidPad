## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import cStringIO as StringIO
import urllib, os, os.path, traceback

import wx, wx.html

if wx.Platform == '__WXMSW__':
    import wx.activex
    import wx.lib.iewin as iewin
else:
    iewin = None


from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID, \
        wxKeyFunctionSink

from MiscEvent import KeyFunctionSink

from StringOps import uniToGui, utf8Enc, utf8Dec, urlFromPathname, urlQuote, \
        writeEntireTxtFile

from TempFileSet import TempFileSet

import Exporters



class LinkCreatorForPreviewIe:
    """
    Faked link dictionary for HTML exporter
    """
    def __init__(self, wikiData):
        self.wikiData = wikiData

    def get(self, word, default = None):
        if self.wikiData.isDefinedWikiWord(word):
            return urlQuote(u"internaljump:wikipage/%s" % word, u"/#:;@")
        else:
            return default

class LinkCreatorForPreviewMoz:
    """
    Faked link dictionary for HTML exporter
    """
    def __init__(self, wikiData):
        self.wikiData = wikiData

    def get(self, word, default = None):
        if self.wikiData.isDefinedWikiWord(word):
            return urlQuote(u"file://internaljump/wikipage/%s" % word, u"/#:;@")
        else:
            return default


class WikiHtmlViewIE(iewin.IEHtmlWindow):
    def __init__(self, presenter, parent, ID, drivingMoz):
        self.drivingMoz = drivingMoz

        if self.drivingMoz:
            wx.activex.IEHtmlWindowBase.__init__(self, parent,
                wx.activex.CLSID('{1339B54C-3453-11D2-93B9-000000000000}'),
                ID, pos=wx.DefaultPosition, size=wx.DefaultSize, style=0,
                name='MozHtmlWindow')
            self.LinkCreatorForPreview = LinkCreatorForPreviewMoz
        else:
            wx.activex.IEHtmlWindowBase.__init__(self, parent,
                wx.activex.CLSID('{8856F961-340A-11D0-A96B-00C04FD705A2}'),
                ID, pos=wx.DefaultPosition, size=wx.DefaultSize, style=0,
                name='IEHtmlWindow')
            self.LinkCreatorForPreview = LinkCreatorForPreviewIe

        self.presenter = presenter

        self.presenterListener = wxKeyFunctionSink((
                ("loaded current wiki page", self.onLoadedCurrentWikiPage),
                ("reloaded current doc page", self.onReloadedCurrentPage),
                ("opened wiki", self.onOpenedWiki),
                ("closing current wiki", self.onClosingCurrentWiki),
#                 ("options changed", self.onOptionsChanged),
                ("changed live text", self.onChangedLiveText)
        ), self.presenter.getMiscEvent())

        self.__sinkApp = wxKeyFunctionSink((
                ("options changed", self.onOptionsChanged),
        ), wx.GetApp().getMiscEvent())

        self.__sinkDocPage = wxKeyFunctionSink((
                ("updated wiki page", self.onUpdatedWikiPage),
        ), self.presenter.getCurrentDocPageProxyEvent())

        self.visible = False
        self.outOfSync = True   # HTML content is out of sync with live content

        self.currentLoadedWikiWord = None
        self.currentLoadedUrl = None  # Contains the URL of the temporary HTML
                # file without anchors

        self.anchor = None  # Name of anchor to jump to when view gets visible
        self.lastAnchor = None
        self.passNavigate = 0


        # TODO Should be changed to presenter as controller
        self.exporterInstance = Exporters.HtmlXmlExporter(
                self.presenter.getMainControl())

        # TODO More elegantly
        if self.drivingMoz:
            self.exporterInstance.exportType = u"html_previewMOZ"
        else:
            self.exporterInstance.exportType = u"html_previewIE"

        self.exporterInstance.tempFileSet = TempFileSet()
        self._updateTempFilePrefPath()
        self.exporterInstance.styleSheet = "file:" + urlFromPathname(
                os.path.join(wx.GetApp().globalConfigSubDir,
                'wikipreview.css'))

        self.exporterInstance.setWikiDataManager(self.presenter.getWikiDocument())

        # Create temporary html file
        self.htpath = self.exporterInstance.tempFileSet.createTempFile(
                    u"", ".html", relativeTo="")

        iewin.EVT_BeforeNavigate2(self, self.GetId(), self.OnBeforeNavigate)

        wx.EVT_SET_FOCUS(self, self.OnSetFocus)
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
            os.remove(pathEnc(self.htpath))
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
                pass
#                 prevPage = self.presenter.getWikiDocument().getWikiPage(
#                         self.currentLoadedWikiWord)
#                 prevPage.setPresentation(self.GetViewStart(), 3)
            except WikiWordNotFoundException, e:
                pass
        if self.outOfSync:
#             self.currentLoadedWikiWord = None

            wikiDoc = self.presenter.getWikiDocument()
            if wikiDoc is None:
                self.currentLoadedWikiWord = None
                return

            self.exporterInstance.wikiData = wikiDoc.getWikiData()

            wikiPage = self.presenter.getDocPage()
            if wikiPage is None:
                self.currentLoadedWikiWord = None
                return  # TODO Do anything else here?

            word = wikiPage.getWikiWord()
            if word is None:
                self.currentLoadedWikiWord = None
                return  # TODO Do anything else here?

            # Remove previously used temporary files
            self.exporterInstance.tempFileSet.clear()

            content = self.presenter.getLiveText()

            html = self.exporterInstance.exportContentToHtmlString(word, content,
                    wikiPage.getFormatDetails(),
                    self.LinkCreatorForPreview(
                        self.presenter.getWikiDocument().getWikiData()))
                        
#             htpath = self.exporterInstance.tempFileSet.createTempFile(
#                     utf8Enc(html)[0], ".html", relativeTo="")

            writeEntireTxtFile(self.htpath, utf8Enc(html)[0])

            url = "file:" + urlFromPathname(self.htpath)

            wx.GetApp().getInsertionPluginManager().taskEnd()
            
            self.currentLoadedUrl = url
            if self.currentLoadedWikiWord == word and \
                    self.anchor is None:
                self.RefreshPage()

            else:                        
                self.currentLoadedWikiWord = word 
    
                if self.anchor:
                    url += "#" + self.anchor
    
    
                self.passNavigate += 1
                self.LoadUrl(url)
                self.lastAnchor = self.anchor

        else:  # Not outOfSync
            if self.anchor:
                self.passNavigate += 1
                self.LoadUrl(self.currentLoadedUrl + u"#" + self.anchor)
                self.lastAnchor = self.anchor

        self.anchor = None
        self.outOfSync = False

        ## _prof.stop()


    def gotoAnchor(self, anchor):
        self.anchor = anchor
        if self.visible:
#             self.outOfSync = True
            self.refresh()


    def _updateTempFilePrefPath(self):
        wikiDoc = self.presenter.getWikiDocument()

        if wikiDoc is not None:
            self.exporterInstance.tempFileSet.setPreferredPath(
                    wikiDoc.getWikiTempDir())
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
        self.exporterInstance.setWikiDataManager(self.presenter.getWikiDocument())

    def onClosingCurrentWiki(self, miscevt):
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
        # Trying to fix mysterious crashes (but doesn't help)
        try:
            if self.visible:
                self.refresh()
        except:
            traceback.print_exc()
            

#     def OnClipboardCopy(self, evt):
#         copyTextToClipboard(self.SelectionToText())


    def OnBeforeNavigate(self, evt):
        if self.passNavigate:
            self.passNavigate -= 1
            return

        href = evt.URL
        if self.drivingMoz:
            internaljumpPrefix = u"file://internaljump/"
        else:
            internaljumpPrefix = u"internaljump:"

        if href.startswith(internaljumpPrefix + u"wikipage/"):

            if self.drivingMoz:
                # Unlike stated, the Mozilla ActiveX control has some
                # differences to the IE control. For instance, it returns
                # here an UTF-8 URL-quoted string, while IE returns the
                # unicode as it is.
                href = utf8Dec(urllib.unquote(href.encode("ascii", "replace")))[0]

            evt.Cancel = True
            # Jump to another wiki page

            # First check for an anchor. In URLs, anchors are always
            # separated by '#' regardless which character is used
            # in the wiki syntax (normally '!')
            try:
                word, anchor = href[len(internaljumpPrefix) + 9:].split("#", 1)
            except ValueError:
                word = href[len(internaljumpPrefix) + 9:]
                anchor = None

#             if self.drivingMoz:

            # unescape word
            word = urllib.unquote(word) # utf8Dec(urllib.unquote(word))[0]
            if anchor:
                anchor = urllib.unquote(anchor)  # utf8Dec(urllib.unquote(anchor))[0]

            # Now open wiki
            self.presenter.getMainControl().openWikiPage(
                    word, motionType="child", anchor=anchor)

        elif href.startswith(internaljumpPrefix + u"action/scroll/selfanchor/"):
            anchorFragment = href[len(internaljumpPrefix + u"action/scroll/selfanchor/"):]
            self.gotoAnchor(anchorFragment)
            evt.Cancel = True

        elif href == (internaljumpPrefix + u"action/history/back"):
            # Go back in history
            self.presenter.getMainControl().goBrowserBack()
            evt.Cancel = True

        elif href == (internaljumpPrefix + u"mouse/leftdoubleclick/preview/body"):
            pres = self.presenter
            mc = pres.getMainControl()

            paramDict = {"page": pres.getDocPage(), "presenter": pres,
                    "main control": mc}
                    
            mc.getUserActionCoord().reactOnUserEvent(
                    u"mouse/leftdoubleclick/preview/body", paramDict)
            evt.Cancel = True

#         elif href.startswith(u"file:"):
#             pass
        else:
            self.presenter.getMainControl().launchUrl(href)
            evt.Cancel = True


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


