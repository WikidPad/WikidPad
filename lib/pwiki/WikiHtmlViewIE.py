## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import cStringIO as StringIO
import urllib, os.path

from wxPython.wx import *
from wxPython.html import *

import wx


if wx.Platform == '__WXMSW__':
    import wx.activex
    import wx.lib.iewin as iewin
else:
    iewin = None


from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID

from MiscEvent import KeyFunctionSink

from StringOps import uniToGui, utf8Enc

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
            return urllib.quote(u"internaljump:%s" % word, "/#:;@")
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
            return urllib.quote(u"file://internaljump/%s" % word, "/#:;@")
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

        self.presenter.getMiscEvent().addListener(KeyFunctionSink((
                ("loaded current page", self.onLoadedCurrentWikiPage),
                ("reloaded current page", self.onReloadedCurrentPage),
                ("opened wiki", self.onOpenedWiki),
                ("closing current wiki", self.onClosingCurrentWiki),
                ("options changed", self.onOptionsChanged),
                ("updated wiki page", self.onUpdatedWikiPage),
                ("changed live text", self.onChangedLiveText)
        )), False)

        self.visible = False
        self.outOfSync = True   # HTML content is out of sync with live content

        self.currentLoadedWikiWord = None

        self.anchor = None  # Name of anchor to jump to when view gets visible
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
        self.exporterInstance.styleSheet = "file:" + urllib.pathname2url(
                os.path.join(wxGetApp().globalConfigSubDir,
                'wikipreview.css'))
# 
#         EVT_KEY_DOWN(self, self.OnKeyDown)
#         EVT_KEY_UP(self, self.OnKeyUp)
#         EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY, self.OnClipboardCopy)
#         EVT_MENU(self, GUI_ID.CMD_ZOOM_IN, lambda evt: self.addZoom(1))
#         EVT_MENU(self, GUI_ID.CMD_ZOOM_OUT, lambda evt: self.addZoom(-1))
        iewin.EVT_BeforeNavigate2(self, self.GetId(), self.OnBeforeNavigate)

        EVT_SET_FOCUS(self, self.OnSetFocus)
#         EVT_MOUSEWHEEL(self, self.OnMouseWheel) 


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


    def refresh(self):
        ## _prof.start()

        # Store position of currently displaayed page, if any
        if self.currentLoadedWikiWord:
            try:
                pass
#                 prevPage = self.presenter.getWikiDocument().getWikiPage(
#                         self.currentLoadedWikiWord)
#                 prevPage.setPresentation(self.GetViewStart(), 3)
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
                    self.LinkCreatorForPreview(
                        self.presenter.getWikiDocument().getWikiData()))
                    
            htpath = self.exporterInstance.tempFileSet.createTempFile(
                    utf8Enc(uniToGui(html))[0], ".html", relativeTo="")
                    
            url = "file:" + urllib.pathname2url(htpath)
            
            # wxFileSystem.FileNameToURL
                    
            # wxFileSystem.FileNameToURL(p)

            wxGetApp().getInsertionPluginManager().taskEnd()
            
            if self.anchor:
                url += "#" + self.anchor

    
            # TODO Reset after open wiki
#             zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
#             self.SetFonts("", "", [max(s + 2 * zoom, 1)
#                     for s in self._DEFAULT_FONT_SIZES])
                    
#             sf = StringIO.StringIO(utf8Enc(uniToGui(html))[0])
#             self.LoadStream(sf)
#             sf.close()

            self.passNavigate += 1
            self.LoadUrl(url)


#         if self.anchor and self.HasAnchor(self.anchor):
#             self.ScrollToAnchor(self.anchor)
#             # Workaround because ScrollToAnchor scrolls too far
#             lx, ly = self.GetViewStart()
#             self.Scroll(lx, ly-1)
#         elif self.outOfSync:
#             pass
            
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
                pass
#                 prevPage = self.presenter.getWikiDocument().getWikiPage(
#                         self.currentLoadedWikiWord)
#                 prevPage.setPresentation(self.GetViewStart(), 3)
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

#     def OnClipboardCopy(self, evt):
#         copyTextToClipboard(self.SelectionToText())


    def OnBeforeNavigate(self, evt):
#         print "OnBeforeNavigate", repr(evt.URL)
        if self.passNavigate:
            self.passNavigate -= 1
            return

        href = evt.URL
        if self.drivingMoz:
            internaljumpPrefix = u"file://internaljump/"
        else:
            internaljumpPrefix = u"internaljump:"

        if href.startswith(internaljumpPrefix):
            evt.Cancel = True
            # Jump to another wiki page
            
            # First check for an anchor. In URLs, anchors are always
            # separated by '#' regardless which character is used
            # in the wiki syntax (normally '!')
            try:
                word, anchor = href[len(internaljumpPrefix):].split(u"#", 1)
            except ValueError:
                word = href[len(internaljumpPrefix):]
                anchor = None
                
#             if self.drivingMoz:
            # unescape word
            word = urllib.unquote(word)
            if anchor:
                anchor = urllib.unquote(anchor)

            # Now open wiki
            self.presenter.getMainControl().openWikiPage(
                    word, motionType="child", anchor=anchor)
        elif href.startswith(u"file:"):
            pass
        else:
            evt.Cancel = True
            self.presenter.getMainControl().launchUrl(href)


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



