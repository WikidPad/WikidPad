import cStringIO as StringIO
import urllib, os, os.path, traceback

import wx, wx.html


from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID, \
        wxKeyFunctionSink

from MiscEvent import KeyFunctionSink

from StringOps import uniToGui, utf8Enc, utf8Dec, pathEnc, urlFromPathname, \
        urlQuote, pathnameFromUrl, flexibleUrlUnquote
from .Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE

import DocPages
from TempFileSet import TempFileSet

from . import PluginManager

# Stuff for webkit
import gobject
gobject.threads_init()

import pygtk
pygtk.require('2.0')
import gtk, gtk.gdk

# pywebkitgtk (http://code.google.com/p/pywebkitgtk/)
import webkit

if wx.Platform == '__WXMSW__':
    from WindowsHacks import getLongPath
else:
    def getLongPath(s):
        """
        Dummy
        """
        return s


def wxToGtkLabel(s):
    """
    The message catalog for internationalization should only contain
    labels with wx style ('&' to tag shortcut character)
    """
    return s.replace("&", "_")


class LinkConverterForPreviewWk:
    """
    Faked link dictionary for HTML exporter
    """
    def __init__(self, wikiDocument):
        self.wikiDocument = wikiDocument
        
    def getLinkForWikiWord(self, word, default = None):
        if self.wikiDocument.isDefinedWikiLink(word):
            return urlQuote(u"http://internaljump/wikipage/%s" % word, u"/#:;@")
        else:
            return default
 
class WikiHtmlViewWK(wx.Panel):
    def __init__(self, presenter, parent, ID):
        # Must be set before calling base class constructor
        self.loaded = False

        wx.Panel.__init__(self, parent, ID, style=wx.FRAME_NO_TASKBAR|wx.FRAME_FLOAT_ON_PARENT)

        self.html = WKHtmlWindow(self)
        self.scrolled_window = None

        self.box = wx.BoxSizer(wx.VERTICAL)
        self.box.Add(self.html, 1, wx.EXPAND)
        self.SetSizer(self.box)


        # Window must be shown for pizza stuff to work
        self.Bind(wx.EVT_WINDOW_CREATE, self.OnShow)

        # This is need it for wxPython2.8,
        # for 2.6 doesnt hurt
        self.SendSizeEvent()

        #parent.GetParent().Layout()


        # WikiHtml stuff
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
        
        self.selectedText = u""

        self.currentLoadedWikiWord = None
        self.currentLoadedUrl = None  # Contains the URL of the temporary HTML
                # file without anchors

        self.anchor = None  # Name of anchor to jump to when view gets visible
        self.lastAnchor = None  
        self.on_link = None # Link overwhich the mouse currently resides
        self.passNavigate = 0
        self.freezeCount = 0

        # TODO Should be changed to presenter as controller
        self.exporterInstance = PluginManager.getExporterTypeDict(
                self.presenter.getMainControl(), False)[u"html_single"][0]\
                (self.presenter.getMainControl())

        self._DEFAULT_FONT_SIZES = self.presenter.getMainControl().presentationExt.INTHTML_FONTSIZES
        
        # TODO More elegantly
        self.exporterInstance.exportType = u"html_previewWK"
        #self.exporterInstance.styleSheet = u""

        self.exporterInstance.tempFileSet = TempFileSet()
        self._updateTempFilePrefPath()

        self.exporterInstance.setWikiDocument(
                self.presenter.getWikiDocument())

        self.exporterInstance.setLinkConverter(
                LinkConverterForPreviewWk(self.presenter.getWikiDocument()))

        # Two files prevents a wierd bug that occurs when using anchors 
        # with a single file.

        # It should be possible with a single file (or maybe direct html
        # injection)
        self.htpaths = [None, None]
        self.htpaths[0] = self.exporterInstance.tempFileSet.createTempFile(
                    u"", ".html", relativeTo="").decode("latin-1")
        self.htpaths[1] = self.exporterInstance.tempFileSet.createTempFile(
                    u"", ".html", relativeTo="").decode("latin-1")

        self.normHtpaths = [os.path.normcase(getLongPath(self.htpaths[0])),
                os.path.normcase(getLongPath(self.htpaths[1]))]

        self.currentHtpath = 0 # index into self.htpaths

        self.normHtpaths = [os.path.normcase(getLongPath(self.htpaths[0])),
                os.path.normcase(getLongPath(self.htpaths[1]))]


        #wx.EVT_KEY_DOWN(self, self.OnKeyDown)
        #wx.EVT_KEY_UP(self, self.OnKeyUp)
        #wx.EVT_SIZE(self, self.OnSize)

        wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY, self.OnClipboardCopy)
        wx.EVT_MENU(self, GUI_ID.CMD_SELECT_ALL, self.OnSelectAll)
        wx.EVT_MENU(self, GUI_ID.CMD_ZOOM_IN, lambda evt: self.addZoom(1))
        wx.EVT_MENU(self, GUI_ID.CMD_ZOOM_OUT, lambda evt: self.addZoom(-1))
        #wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_THIS, self.OnActivateThis)        
        #wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS,
        #        self.OnActivateNewTabThis)
        #wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS,
        #        self.OnActivateNewTabBackgroundThis)        
        #wx.EVT_MENU(self, GUI_ID.CMD_OPEN_CONTAINING_FOLDER_THIS,
        #        self.OnOpenContainingFolderThis)

        #wx.EVT_LEFT_DCLICK(self, self.OnLeftDClick)
        #wx.EVT_MIDDLE_DOWN(self, self.OnMiddleDown)
        #wx.EVT_MOTION(self, self.OnMouseMotion)

    def OnShow(self, evt):
        self._realizeIfNeeded()
        evt.Skip()

    def _realizeIfNeeded(self):
        if self.loaded:
            return

        if self.html.PizzaMagic():
            self.scrolled_window = self.html.scrolled_window
            #self.html.ctrl.connect("load-started", self.__on_load_started)
            self.html.ctrl.connect("load-finished", self.__on_load_finished)
            self.html.ctrl.connect("navigation-policy-decision-requested",
                    self.__on_navigate)

            self.html.ctrl.connect("hovering-over-link", 
                    self.__on_hovering_over_link)

            #self.scrolled_window.set_events(gtk.gdk.BUTTON_PRESS_MASK)

            self.html.ctrl.connect("button_press_event", 
                    self.__on_button_press_event)

            self.html.ctrl.connect("scroll_event", self.__on_scroll_event)

            self.html.ctrl.connect("selection_received", 
                    self.__on_selection_received)
            self.html.ctrl.connect("populate-popup", self.__on_populate_popup)

            self.html.ctrl.connect("focus-in-event", self.__on_focus_in_event)
            self.html.ctrl.connect("expose-event", self.__on_expose_event)

            self.loaded = True
            self.passNavigate = 0
            
            # Set zoom factor
            zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
            zoomFact = max(0.1, zoom * 0.1 + 1.0)
            self.html.ctrl.set_zoom_level(zoomFact)
            
            # If scroll position was already set, scroll now
            if self.deferredScrollPos is not None:
                lx, ly = self.deferredScrollPos
                self.deferredScrollPos = None
                self.scrollDeferred(lx, ly)
            else:
                wikiPage = self.presenter.getDocPage()
                lx, ly = wikiPage.getPresentation()[3:5]
                self.scrollDeferred(lx, ly)



    def __on_button_press_event(self, view, gtkEvent):
        """
        Catch middle button events and pass them on OnMiddleDown
        """
        if gtkEvent.button == 2: # 2 is middle button
            return self.OnMiddleDown(gtkEvent)

    def __on_navigate(self, view, frame, request, action, decision):
        """
        Handles default (webkit) navigation requests
        """
        uri = flexibleUrlUnquote(request.get_uri())

        # iframes have a parent
        # let them load normally if set in options (otherwise they are 
        # opened by the external launcher as the page is loaded)
        if frame.get_parent() is not None and \
                self.presenter.getConfig().getboolean("main",
                "html_preview_ieShowIframes", True):
            return False

        # Return True to block navigation, i.e. launching a url
        return self._activateLink(uri, tabMode=0)


    def __on_hovering_over_link(self, view, title, status):
        """
        Called on link mouseover
        """
        
        if status is None:
            self.on_link = None
            self.updateStatus(u"")
        else:
            # flexibleUrlUnquote seems to fail on unicode links
            # unquote shouldn't happen here for self.on_link (MB 2011-04-15)
            self.on_link = status
            self.updateStatus(unicode(urllib.unquote(status)))


    def __on_selection_received(self, widget, selection_data, data):
        if str(selection_data.type) == "STRING" and widget.has_selection():
            self.selectedText = selection_data.get_text()
        else:
            self.selectedText = None

        return False


#    def __on_load_started(self, view, frame):
#        pass

    def __on_load_finished(self, view, frame):
        """
        Called when page is loaded
        """

        #Scroll to last position if no anchor
        if self.lastAnchor is None:
            wikiPage = self.presenter.getDocPage()
            lx, ly = wikiPage.getPresentation()[3:5]

            self.scrollDeferred(lx, ly)

    def __on_populate_popup(self, view, menu):
        """
        Modify popup menu

        There is probably a better way to do this as opposed to at runtime 
        but i'm not sure how
        """

        internaljumpPrefix = u"http://internaljump/"
        link = self.on_link

        for i in menu.get_children():
            # Fix for some webkitgtk?? versions
            try:
                action = i.get_children()[0].get_label()
            except:
                continue

            if action == u"_Back":
                menu.remove(i)
            elif action == u"_Forward":
                menu.remove(i)
            elif action == u"_Stop":
                menu.remove(i)
            elif action == u"_Reload":
                menu.remove(i)
            elif action == u"_Copy":
                pass
            elif action == u"Cop_y Image":
                pass
            elif action == u"Copy Link Loc_ation":
                # No point in copying internal links
                if link and link.startswith(internaljumpPrefix):
                    menu.remove(i)

                # Doesn't work as selection get lost if a link is
                # is rightclicked on

                ## Add item to copy selection (doesn't normally exist in
                ## webkit apparently)
                #if self.getSelectedText() is not None:
                #    copy_menu_item = gtk.ImageMenuItem(gtk.STOCK_COPY)
                #    copy_menu_item.get_children()[0].set_label(
                #            wxToGtkLabel(_('Copy &Selected Text')))
                #    copy_menu_item.connect("activate", self.OnClipboardCopy)
                #    menu.append(copy_menu_item)
            elif action == u"Open _Image in New Window":
                menu.remove(i)
            elif action == u"Sa_ve Image As":
                menu.remove(i)
            elif action == u"_Download Linked File":
                menu.remove(i)
            elif action == u"_Open Link":
                if link:
                    if not link.startswith(internaljumpPrefix):
                        i.get_children()[0].set_label(
                                wxToGtkLabel(_("Open Link (External)")))
                    else:
                        i.get_children()[0].set_label(
                                wxToGtkLabel(_("Follow &Link")))
                else:
                    menu.remove(i)

            elif action == u"Open Link in New _Window":
                menu.remove(i)

                # Only show for internal jumps
                if link and link.startswith(internaljumpPrefix):
                    # New tab (forground)
                    open_new_tab_menu_item = gtk.ImageMenuItem(gtk.STOCK_OPEN)
                    open_new_tab_menu_item.get_children()[0].set_label(
                            wxToGtkLabel(_('Follow Link in New &Tab')))
                    open_new_tab_menu_item.connect("activate", self.OnOpenLinkInNewTab)
                    menu.append(open_new_tab_menu_item)

                    # New tab (background)
                    open_new_tab_background_menu_item = gtk.ImageMenuItem(gtk.STOCK_OPEN)
                    open_new_tab_background_menu_item.get_children()[0].set_label(
                            wxToGtkLabel(_('Follow Link in New Back&ground Tab')))
                    open_new_tab_background_menu_item.connect("activate", self.OnOpenLinkInNewBackgroundTab)
                    menu.append(open_new_tab_background_menu_item)
            elif action == u"_Download Linked File":
                menu.remove(i)
            else:
                # Remove unknown menu items
                menu.remove(i)

        back_menu_item = gtk.ImageMenuItem(gtk.STOCK_GO_BACK)
        back_menu_item.connect("activate", self.OnGoBackInHistory)
        menu.append(back_menu_item)

            
        forward_menu_item = gtk.ImageMenuItem(gtk.STOCK_GO_FORWARD)
        forward_menu_item.connect("activate", self.OnGoForwardInHistory)
        menu.append(forward_menu_item)

        # Disable forward/back buttons if no history
        # but leave visible (so as to give feedback)
        pageHistDeepness = self.presenter.getPageHistory().getDeepness()

        if pageHistDeepness[0] == 0:
            back_menu_item.set_sensitive(False)

        if pageHistDeepness[1] == 0:
            forward_menu_item.set_sensitive(False)

        menu.show_all()

    def __on_scroll_event(self, widget, evt):
        # If ctrl is pressed
        if evt.state & gtk.gdk.CONTROL_MASK:
            if evt.direction == gtk.gdk.SCROLL_UP:
                self.addZoom(-1)
            elif evt.direction == gtk.gdk.SCROLL_DOWN:
                self.addZoom(1)

            return True # Return true so we don't scroll

    def __on_focus_in_event(self, widget, evt):
        if self.visible:
            self.refresh()

    def Freeze(self):
        self.freezeCount += 1
        
    def Thaw(self):
        self.freezeCount = max(0, self.freezeCount - 1)
        if self.freezeCount == 0:
            self.Refresh(False)

    def __on_expose_event(self, view, *params):
        return self.freezeCount > 0


    def OnOpenLinkInNewTab(self, gtkEvent):
        uri = self.on_link
        self._activateLink(uri, tabMode=2)

        return False
        
    def OnOpenLinkInNewBackgroundTab(self, gtkEvent):
        uri = self.on_link
        self._activateLink(uri, tabMode=3)

        return False

    def OnGoBackInHistory(self, gtkEvent):
        self.presenter.getMainControl().goBrowserBack()

    def OnGoForwardInHistory(self, gtkEvent):
        self.presenter.getMainControl().goBrowserForward()

    def updateStatus(self, status):
        if self.visible:

            # Status None is sent on mouse off
            if status is None:
                self.presenter.getMainControl().statusBar.SetStatusText(
                        uniToGui(""), 0)
                return

            internaljumpPrefix = u"http://internaljump/"

            if status.startswith(internaljumpPrefix):
                # First check for an anchor. In URLs, anchors are always
                # separated by '#' regardless which character is used
                # in the wiki syntax (normally '!')
                try:
                    wikiWord, anchor = status[len(internaljumpPrefix):].split(
                            u"#", 1)
                except ValueError:
                    wikiWord = status[len(internaljumpPrefix):]
                    anchor = None


                wikiDocument = self.presenter.getWikiDocument()
                if wikiDocument is None:
                    return
                
                # Add to internal jump prefix?
                pagePrefix = u"wikipage/"
                wikiWord = wikiDocument.getUnAliasedWikiWord(wikiWord[len(pagePrefix):])

                if wikiWord is not None:
                    status = _(u"Link to page: %s") % wikiWord

            self.presenter.getMainControl().statusBar.SetStatusText(
                    uniToGui(status), 0)

    # GTK wx mapping
    def GetViewStart(self):
        """
        Bridge gtk to wx's ScrolledWindow.
        May return None if underlying webkit window isn't realized yet.
        """
        if not self.loaded:
            return None

        x = self.scrolled_window.get_hadjustment().value
        y = self.scrolled_window.get_vadjustment().value

        return (x, y)

    def Scroll(self, x, y):
        """
        Bridge gtk to wx's ScrolledWindow
        """
        
        # I don't know how to create a gtk adjustment so just modify one
        hAdjustment = self.scrolled_window.get_hadjustment()
        hAdjustment.set_all(x)

        vAdjustment = self.scrolled_window.get_vadjustment()
        vAdjustment.set_all(y)

        self.scrolled_window.set_hadjustment(hAdjustment)
        self.scrolled_window.set_vadjustment(vAdjustment)


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


        if self.currentLoadedWikiWord:
            try:
                prevPage = self.presenter.getWikiDocument().getWikiPage(
                        self.currentLoadedWikiWord)
                vs = self.GetViewStart()
                if vs is not None:
                    prevPage.setPresentation(vs, 3)
            except WikiWordNotFoundException, e:
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

            self.exporterInstance.setWikiDocument(   # ?
                    self.presenter.getWikiDocument())

            self.exporterInstance.setLinkConverter(
                    LinkConverterForPreviewWk(self.presenter.getWikiDocument()))   # /?

            html = self.exporterInstance.exportWikiPageToHtmlString(wikiPage)

            wx.GetApp().getInsertionPluginManager().taskEnd()
            
            if self.currentLoadedWikiWord == word and \
                    self.anchor is None:

                htpath = self.htpaths[self.currentHtpath]

                with open(htpath, "w") as f:
                    f.write(utf8Enc(html)[0])

                url = "file:" + urlFromPathname(htpath)
                self.currentLoadedUrl = url
                self.passNavigate += 1
                self.html.LoadUrl(url)

                #lx, ly = wikiPage.getPresentation()[3:5]
                #self.scrollDeferred(lx, ly)
            else:                        
                self.currentLoadedWikiWord = word

                self.currentHtpath = 1 - self.currentHtpath
                htpath = self.htpaths[self.currentHtpath]
                
                with open(htpath, "w") as f:
                    f.write(utf8Enc(html)[0])

                url = "file:" + urlFromPathname(htpath)
                self.currentLoadedUrl = url
    
                if self.anchor is not None:
                    url += "#" + self.anchor

                self.passNavigate += 1
                self.html.LoadUrl(url)
                self.lastAnchor = self.anchor
                
                #if self.anchor is None:
                #    lx, ly = wikiPage.getPresentation()[3:5]
                #    self.scrollDeferred(lx, ly)


        else:  # Not outOfSync
            if self.anchor is not None:
                # Webkit seems not to send "navigation-policy-decision-requested"
                # if only anchor changes
#                 self.passNavigate += 1
                self.html.LoadUrl(self.currentLoadedUrl + u"#" + self.anchor)
                self.lastAnchor = self.anchor
            else:
                lx, ly = wikiPage.getPresentation()[3:5]
                self.scrollDeferred(lx, ly)

        self.anchor = None
        self.outOfSync = False


        ## _prof.stop()


    def gotoAnchor(self, anchor):
        self.anchor = anchor
        if self.visible:
            self.refresh()
            
    
    def getSelectedText(self):
        """
        Works but probably not the best solution

        __on_selection_received is called and sets self.selectedText
        """
        ret = self.html.getWebkitWebView().selection_convert("PRIMARY", "STRING")
        return self.selectedText


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

    def onOpenedWiki(self, miscevt):
        self.currentLoadedWikiWord = None

        self._updateTempFilePrefPath()
        self.exporterInstance.setWikiDocument(
                self.presenter.getWikiDocument())
        self.exporterInstance.setLinkConverter(
                LinkConverterForPreviewWk(self.presenter.getWikiDocument()))

    def onClosingCurrentWiki(self, miscevt):
        if self.currentLoadedWikiWord:
            try:
                prevPage = self.presenter.getWikiDocument().getWikiPage(
                        self.currentLoadedWikiWord)
                vs = self.GetViewStart()
                if vs is not None:
                    prevPage.setPresentation(vs, 3)
            except WikiWordNotFoundException, e:
                pass

    def onOptionsChanged(self, miscevt):
        self.outOfSync = True
        self._updateTempFilePrefPath()
        if self.visible:
            self.refresh()

    def onUpdatedWikiPage(self, miscevt):
        #self.outOfSync = True
        #if self.visible:
        #    self.refresh()
        pass
            
    def onChangedLiveText(self, miscevt):
        self.outOfSync = True


    def scrollDeferred(self, lx, ly):
        
        if not self.loaded or self.deferredScrollPos is not None:
            # WebkitWebView not realized yet or
            # an unprocessed _scrollAndThaw is in the message queue yet ->
            # just change scrollPos
            self.deferredScrollPos = (lx, ly)
#             wx.CallAfter(self._scrollAndThaw)
        else:
            # Put new _scrollAndThaw into queue
            self.Freeze()
            self.deferredScrollPos = (lx, ly)
            wx.CallAfter(self._scrollAndThaw)
        
    def _scrollAndThaw(self):
        if self.scrolled_window != None:
            self.Scroll(self.deferredScrollPos[0], self.deferredScrollPos[1])
            self.Thaw()
            self.deferredScrollPos = None
            self.counterResizeIgnore = 0


    def OnSize(self, evt):
        if self.counterResizeIgnore > 0:
            self.counterResizeIgnore -= 1
            return

        vs = self.GetViewStart()
        if vs is not None:
            self.counterResizeIgnore = 1
            evt.Skip()
            self.scrollDeferred(vs[0], vs[1])


    def OnClipboardCopy(self, evt):
        self.html.getWebkitWebView().copy_clipboard()

    def OnSelectAll(self, evt):
        self.html.getWebkitWebView().select_all()

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
        
        zoomFact = max(0.1, zoom * 0.1 + 1.0)
        self.html.getWebkitWebView().set_zoom_level(zoomFact)

        
    def OnMiddleDown(self, gtkEvent):
        if self.on_link is not None:
            if not gtkEvent.state & gtk.gdk.CONTROL_MASK:
                middleConfig = self.presenter.getConfig().getint("main",
                    "mouse_middleButton_withoutCtrl", 2)
            else:
                middleConfig = self.presenter.getConfig().getint("main",
                    "mouse_middleButton_withCtrl", 3)

            tabMode = MIDDLE_MOUSE_CONFIG_TO_TABMODE[middleConfig]

            self._activateLink(self.on_link, tabMode=tabMode)
            return True
        return False

    def _activateLink(self, href, tabMode=0):
        """
        tabMode -- 0:Same tab; 2: new tab in foreground; 3: new tab in background
        Returns True if link was processed here and doesn't need further processing
        """

#         decision.use()
        if self.passNavigate:
            self.passNavigate -= 1
            return False

        internaljumpPrefix = u"http://internaljump/"

        if href.startswith(internaljumpPrefix + u"wikipage/"):  # len("wikipage/") == 9


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
            word = urllib.unquote(word) # utf8Dec(urllib.unquote(word))[0]
            if anchor:
                anchor = urllib.unquote(anchor)  # utf8Dec(urllib.unquote(anchor))[0]

            if tabMode & 2:
                # New tab
                presenter = self.presenter.getMainControl().\
                        createNewDocPagePresenterTab()
                presenter.switchSubControl("preview", False)
            else:
                # Same tab
                presenter = self.presenter

            # Now open wiki
            presenter.openWikiPage(word, motionType="child", anchor=anchor)

            if not tabMode & 1:
                # Show in foreground
                presenter.getMainControl().getMainAreaPanel().\
                        showPresenter(presenter)
                presenter.SetFocus()


            #decision.ignore()
            return True

        elif href == (internaljumpPrefix + u"action/history/back"):
            # Go back in history
            self.presenter.getMainControl().goBrowserBack()
            #decision.ignore()
            return True

        elif href == (internaljumpPrefix + u"mouse/leftdoubleclick/preview/body"):
            # None affect current tab so return false
            pres = self.presenter
            mc = pres.getMainControl()

            paramDict = {"page": pres.getDocPage(), "presenter": pres,
                    "main control": mc}

            mc.getUserActionCoord().reactOnUserEvent(
                    u"mouse/leftdoubleclick/preview/body", paramDict)
            ##decision.ignore()
            return True

        elif href.startswith(u"file:"):
            hrefSplit = href.split("#", 1)
            hrefNoFragment = hrefSplit[0]
            normedPath = os.path.normcase(getLongPath(pathnameFromUrl(hrefNoFragment)))
            if len(hrefSplit) == 2 and normedPath in self.normHtpaths:
            #if len(hrefSplit) == 2 and normedPath in self.normHtpath:
                self.gotoAnchor(hrefSplit[1])
                #decision.ignore()
            else:
                self.presenter.getMainControl().launchUrl(href)
                #decision.ignore()
            return True
        else:
            self.presenter.getMainControl().launchUrl(href)
            #decision.ignore()
            return True

        # Should never be reached
        return False





#_CONTEXT_MENU_INTERNAL_JUMP = \
#u"""
#Activate;CMD_ACTIVATE_THIS
#Activate New Tab;CMD_ACTIVATE_NEW_TAB_THIS
#Activate New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
#"""
#
#
## Entries to support i18n of context menus
#if False:
#    N_(u"Activate")
#    N_(u"Activate New Tab")
#    N_(u"Activate New Tab Backgrd.")

class WKHtmlWindow(wx.Window):
    def __init__(self, *args, **kwargs):
        wx.Window.__init__(self, *args, **kwargs)


        self.ctrl = ctrl = webkit.WebView()
        self.Show()

    def PizzaMagic(self):

        whdl = self.GetHandle()

        # break if window not shown
        if whdl == 0:
            return False


        window = gtk.gdk.window_lookup(whdl)

        # We must keep a reference of "pizza". Otherwise we get a crash.
        self.pizza = pizza = window.get_user_data()

        self.scrolled_window = scrolled_window = pizza.parent

        # Removing pizza to put a webview in it's place
        scrolled_window.remove(pizza)

        scrolled_window.add(self.ctrl)

        self.ctrl.show()
        #parent.SendSizeEvent()
        return True

    def GetScrolledWindow(self):
        return self.scrolled_window

    def getWebkitWebView(self):
        return self.ctrl
        

    # Some basic usefull methods
#     def SetEditable(self, editable=True):
#         self.ctrl.set_editable(editable)

    def LoadUrl(self, url):
        try:
            self.ctrl.load_uri(url)
        except:
            self.ctrl.open(url)

#     def HistoryBack(self):
#         self.ctrl.go_back()
# 
#     def HistoryForward(self):
#         self.ctrl.go_forward()

    def StopLoading(self):
        self.ctrl.stop_loading() 

