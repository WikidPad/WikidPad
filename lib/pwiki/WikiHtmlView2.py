import io as StringIO
import urllib.request, urllib.parse, urllib.error, os, os.path, traceback

import wx, wx.html2


from .WikiExceptions import *
from .wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID, \
        wxKeyFunctionSink, appendToMenuByMenuDesc

from .MiscEvent import KeyFunctionSink

from .StringOps import utf8Enc, utf8Dec, pathEnc, urlFromPathname, \
        urlQuote, pathnameFromUrl, flexibleUrlUnquote, longPathEnc
from .Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE

from . import OsAbstract

from . import DocPages
from .TempFileSet import TempFileSet

from . import PluginManager

import threading
from .Utilities import DUMBTHREADSTOP, callInMainThread, ThreadHolder, between

from .ViHelper import ViHintDialog, ViHelper

# Import context menu strings
# Causes a circular import (which fails)
#from .WikiTxtCtrl import _CONTEXT_MENU_INTEXT_ACTIVATE as _CONTEXT_MENU_INTERNAL_JUMP
#from .WikiTxtCtrl import _CONTEXT_MENU_INTEXT_ACTIVATE_DIRECTION as _CONTEXT_MENU_INTERNAL_JUMP_DIRECTION

# used in search
from . import SystemInfo

from html.parser import HTMLParser


LOADING_JS = """

    $("head").append("<style type='text/css'>.circle { background-color: rgba(0,0,0,0); border: 5px solid rgba(0,183,229,0.9); opacity: .9; border-right: 5px solid rgba(0,0,0,0); border-left: 5px solid rgba(0,0,0,0); border-radius: 50px; box-shadow: 0 0 35px #2187e7; width: 50px; height: 50px; margin: 0 auto; -webkit-animation: spinPulse 1s infinite linear; } .circle1 { background-color: rgba(0,0,0,0); border: 5px solid rgba(0,183,229,0.9); opacity: .9; border-left: 5px solid rgba(0,0,0,0); border-right: 5px solid rgba(0,0,0,0); border-radius: 50px; box-shadow: 0 0 15px #2187e7; width: 30px; height: 30px; margin: 0 auto; position: relative; top: -50px; -webkit-animation: spinoffPulse 1s infinite linear; } @-webkit-keyframes spinPulse { 0% { -webkit-transform: rotate(160deg); opacity: 0; box-shadow: 0 0 1px #2187e7; } 50% { -webkit-transform: rotate(145deg); opacity: 1; } 100% { -webkit-transform: rotate(-320deg); opacity: 0; }; } @-webkit-keyframes spinoffPulse { 0% { -webkit-transform: rotate(0deg); } 100% { -webkit-transform: rotate(360deg); }; }</style>");


    $('body').prepend('<div style="position: fixed; margin-left: auto; margin-right: auto; left: 0; right: 0; width: 50px"><h1>Loading....</h1><div class="circle"></div><div class="circle1"></div><div>');
    
    
    """


if wx.Platform == '__WXMSW__':
    from .WindowsHacks import getLongPath
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

# Search
class WebviewSearchDialog(wx.Frame):
# Base on WikiTxtDialogs.IncrementalSearchDialog
# Would it be better to inherit?
    
    COLOR_YELLOW = wx.Colour(255, 255, 0);
    COLOR_GREEN = wx.Colour(0, 255, 0);
    
    def __init__(self, parent, id, webviewCtrl, rect, font, mainControl, searchInit=None):
        # Frame title is invisible but is helpful for workarounds with
        # third-party tools
        wx.Frame.__init__(self, parent, id, "WikidPad i-search",
                rect.GetPosition(), rect.GetSize(),
                wx.NO_BORDER | wx.FRAME_FLOAT_ON_PARENT)

        self.webviewCtrl = webviewCtrl
        self.mainControl = mainControl
        self.tfInput = wx.TextCtrl(self, GUI_ID.INC_SEARCH_TEXT_FIELD,
                _("Incremental search (ENTER/ESC to finish)"),
                style=wx.TE_PROCESS_ENTER | wx.TE_RICH)

        self.tfInput.SetFont(font)
        self.tfInput.SetBackgroundColour(WebviewSearchDialog.COLOR_YELLOW)
        mainsizer = wx.BoxSizer(wx.HORIZONTAL)
        mainsizer.Add(self.tfInput, 1, wx.ALL | wx.EXPAND, 0)

        self.SetSizer(mainsizer)
        self.Layout()
        self.tfInput.SelectAll()  #added for Mac compatibility
        self.tfInput.SetFocus()

        config = self.mainControl.getConfig()

        self.closeDelay = 1000 * config.getint("main", "incSearch_autoOffDelay",
                0)  # Milliseconds to close or 0 to deactivate

        self.Bind(wx.EVT_TEXT, self.OnText, id=GUI_ID.INC_SEARCH_TEXT_FIELD)
        self.tfInput.Bind(wx.EVT_KEY_DOWN, self.OnKeyDownInput)
        self.tfInput.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.Bind(wx.EVT_TIMER, self.OnTimerIncSearchClose, 
                id=GUI_ID.TIMER_INC_SEARCH_CLOSE)
        self.tfInput.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouseAnyInput)

        if searchInit:
            self.tfInput.SetValue(searchInit)
            self.tfInput.SetSelection(-1, -1)

        if self.closeDelay:
            self.closeTimer = wx.Timer(self, GUI_ID.TIMER_INC_SEARCH_CLOSE)
            self.closeTimer.Start(self.closeDelay, True)

#     def Close(self):
#         wx.Frame.Close(self)
#         self.txtCtrl.SetFocus()


    def OnKillFocus(self, evt):
        self.webviewCtrl.forgetIncrementalSearch()
        self.Close()

    def OnText(self, evt):
        self.webviewCtrl.searchStr = self.tfInput.GetValue()
        foundPos = self.webviewCtrl.executeIncrementalSearch(self.tfInput.GetValue())

        if foundPos == False:
            # Nothing found
            self.tfInput.SetBackgroundColour(WebviewSearchDialog.COLOR_YELLOW)
        else:
            # Found
            self.tfInput.SetBackgroundColour(WebviewSearchDialog.COLOR_GREEN)

    def OnMouseAnyInput(self, evt):
#         if evt.Button(wx.MOUSE_BTN_ANY) and self.closeDelay:

        # Workaround for name clash in wx.MouseEvent.Button:
        if wx._core_.MouseEvent_Button(evt, wx.MOUSE_BTN_ANY) and self.closeDelay:
            # If a mouse button was pressed/released, restart timer
            self.closeTimer.Start(self.closeDelay, True)

        evt.Skip()


    def OnKeyDownInput(self, evt):
        if self.closeDelay:
            self.closeTimer.Start(self.closeDelay, True)

        key = evt.GetKeyCode()
        accP = getAccelPairFromKeyDown(evt)
        matchesAccelPair = self.mainControl.keyBindings.matchesAccelPair

        searchString = self.tfInput.GetValue()

        foundPos = -2
        if accP in ((wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER),
                (wx.ACCEL_NORMAL, wx.WXK_RETURN)):
            # Return pressed
            self.webviewCtrl.endIncrementalSearch()
            self.Close()
        elif accP == (wx.ACCEL_NORMAL, wx.WXK_ESCAPE):
            # Esc -> Abort inc. search, go back to start
            self.webviewCtrl.resetIncrementalSearch()
            self.Close()
        elif matchesAccelPair("ContinueSearch", accP):
            foundPos = self.webviewCtrl.executeIncrementalSearch(searchString)
        # do the next search on another ctrl-f
        elif matchesAccelPair("StartIncrementalSearch", accP):
            foundPos = self.webviewCtrl.executeIncrementalSearch(searchString)
        elif accP in ((wx.ACCEL_NORMAL, wx.WXK_DOWN),
                (wx.ACCEL_NORMAL, wx.WXK_PAGEDOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_PAGEDOWN)):
            foundPos = self.webviewCtrl.executeIncrementalSearch(searchString)
        elif matchesAccelPair("BackwardSearch", accP):
            foundPos = self.webviewCtrl.executeIncrementalSearchBackward(searchString)
        elif accP in ((wx.ACCEL_NORMAL, wx.WXK_UP),
                (wx.ACCEL_NORMAL, wx.WXK_PAGEUP),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_UP),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_PAGEUP)):
            foundPos = self.webviewCtrl.executeIncrementalSearchBackward(searchString)
        elif matchesAccelPair("ActivateLink", accP) or \
                matchesAccelPair("ActivateLinkNewTab", accP) or \
                matchesAccelPair("ActivateLink2", accP) or \
                matchesAccelPair("ActivateLinkBackground", accP) or \
                matchesAccelPair("ActivateLinkNewWindow", accP):
            # ActivateLink is normally Ctrl-L
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            # ActivateLink2 is normally Ctrl-Return
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            self.webviewCtrl.endIncrementalSearch()
            self.Close()
            self.webviewCtrl.OnKeyDown(evt)
        # handle the other keys
        else:
            evt.Skip()

        if foundPos == False:
            # Nothing found
            self.tfInput.SetBackgroundColour(WebviewSearchDialog.COLOR_YELLOW)
        else:
            # Found
            self.tfInput.SetBackgroundColour(WebviewSearchDialog.COLOR_GREEN)

        # Else don't change

    if SystemInfo.isOSX():
        # Fix focus handling after close
        def Close(self):
            wx.Frame.Close(self)
            wx.CallAfter(self.webviewCtrl.SetFocus)

    def OnTimerIncSearchClose(self, evt):
        self.webviewCtrl.endIncrementalSearch()  # TODO forgetIncrementalSearch() instead?
        self.Close()



class LinkConverterForPreviewWk:
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
 
class WikiHtmlView2(wx.Panel):
    def __init__(self, presenter, parent, ID):

        wx.Panel.__init__(self, parent, ID, style=wx.FRAME_NO_TASKBAR|wx.FRAME_FLOAT_ON_PARENT)

        self.html = wx.html2.WebView.New(self)

        self.box = wx.BoxSizer(wx.VERTICAL)
        self.box.Add(self.html, 1, wx.EXPAND)
        self.SetSizer(self.box)

        self.exportingThreadHolder = ThreadHolder()
        
        self.vi = None # Contains ViFunctions instance if vi key handling enabled
        self.keyEventConn = None

        self.page_loaded = False


        try:
            self.Bind(wx.html2.EVT_WEB_VIEW_NAVIGATING, self.OnPageNavigation, 
                    self.html)

            self.Bind(wx.html2.EVT_WEB_VIEW_LOADED, self.OnPageLoaded, 
                    self.html)
        # wxPython 2.9.5 renames the webview part
        except AttributeError:
            self.Bind(wx.html2.EVT_WEBVIEW_NAVIGATING, self.OnPageNavigation, 
                    self.html)

            self.Bind(wx.html2.EVT_WEBVIEW_LOADED, self.OnPageLoaded, 
                    self.html)

        # TODO: watch for mouseover event
        # NOT WORKING
        
        # NOTE: Scroll events are eaten by the ctrl and only fired when
        #       the ctrl is not scrolled, i.e. if at the top or bottom of
        #       the page.
        self.html.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheelScrollEvent)

        self.Bind(wx.EVT_CHILD_FOCUS, self.OnFocus)

        # We have to proxy middle clicks as well
        #self.html.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleDown)


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
        
        self.selectedText = ""
        self.selectedHTML = ""

        self.currentLoadedWikiWord = None
        self.currentLoadedUrl = None  # Contains the URL of the temporary HTML
                # file without anchors

        self.anchor = None  # Name of anchor to jump to when view gets visible
        self.lastAnchor = None  
        self.contextHref = None # Link overwhich the mouse currently resides
        self.passNavigate = 0
        self.freezeCount = 0

        # TODO Should be changed to presenter as controller
        self.exporterInstance = PluginManager.getExporterTypeDict(
                self.presenter.getMainControl(), False)["html_single"][0]\
                (self.presenter.getMainControl())

        self._DEFAULT_FONT_SIZES = self.presenter.getMainControl().presentationExt.INTHTML_FONTSIZES
        
        # TODO More elegantly
        self.exporterInstance.exportType = "html_previewWK"
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
                    "", ".html", relativeTo="")
        self.htpaths[1] = self.exporterInstance.tempFileSet.createTempFile(
                    "", ".html", relativeTo="")


        self.normHtpaths = [os.path.normcase(getLongPath(self.htpaths[0])),
                os.path.normcase(getLongPath(self.htpaths[1]))]

        self.currentHtpath = 0 # index into self.htpaths

        #wx.EVT_KEY_DOWN(self, self.OnKeyDown)
        #wx.EVT_KEY_UP(self, self.OnKeyUp)
        self.Bind(wx.EVT_SIZE, self.OnSize)

        self.Bind(wx.EVT_MENU, self.OnClipboardCopy, 
                id=GUI_ID.CMD_CLIPBOARD_COPY)
        self.Bind(wx.EVT_MENU, self.OnSelectAll, 
                id=GUI_ID.CMD_SELECT_ALL)
        self.Bind(wx.EVT_MENU, lambda evt: self.addZoom(1), 
                id=GUI_ID.CMD_ZOOM_IN)
        self.Bind(wx.EVT_MENU, lambda evt: self.addZoom(-1), 
                id=GUI_ID.CMD_ZOOM_OUT)

        self.Bind(wx.EVT_MENU, self.OnActivateThis, 
                id=GUI_ID.CMD_ACTIVATE_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewTabThis, 
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewTabBackgroundThis, 
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewWindowThis, 
                id=GUI_ID.CMD_ACTIVATE_NEW_WINDOW_THIS)

        # Passing the evt here is not strictly necessary, but it may be
        # used in the future
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "left"), 
                id=GUI_ID.CMD_ACTIVATE_THIS_LEFT)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, 
            "left"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_LEFT)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(
            evt, "left"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_LEFT)

        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "right"), 
                id=GUI_ID.CMD_ACTIVATE_THIS_RIGHT)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, 
            "right"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_RIGHT)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(
            evt, "right"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_RIGHT)

        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "above"), 
                id=GUI_ID.CMD_ACTIVATE_THIS_ABOVE)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, 
            "above"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_ABOVE)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(
            evt, "above"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_ABOVE)

        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "below"), 
                id=GUI_ID.CMD_ACTIVATE_THIS_BELOW)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, "below"), 
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_BELOW)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(evt, 
            "below"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_BELOW)



        self.Bind(wx.EVT_MENU, self.OnOpenContainingFolderThis, 
                id=GUI_ID.CMD_OPEN_CONTAINING_FOLDER_THIS)
        self.Bind(wx.EVT_MENU, self.OnGoBackInHistory, 
                id=GUI_ID.CMD_HISTORY_BACK)
        self.Bind(wx.EVT_MENU, self.OnGoForwardInHistory, 
                id=GUI_ID.CMD_HISTORY_FORWARD)

        #wx.EVT_LEFT_DCLICK(self, self.OnLeftDClick)
        #wx.EVT_MIDDLE_DOWN(self.html, self.OnMiddleDown)
        #wx.EVT_MOTION(self, self.OnMouseMotion)


        use_vi_navigation = self.presenter.getConfig().getboolean("main",
                "html_preview_webkitViKeys", False)


        if use_vi_navigation:

            self.vi = ViFunctions(self) 

            self.html.Bind(wx.EVT_KEY_DOWN, self.vi.OnViKeyDown)

            #wx.CallAfter(self.vi._enableMenuShortcuts, False)

        else:
            if self.vi is not None:
                self.vi._enableMenuShortcuts(True)
                self.vi = None

        self.passNavigate = 0
        
        # Set zoom factor
        zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
        
        # Restrict it to range -2...2
        zoom = between(-2, zoom, 2)
                
        # Adjust range to 0..4
        try:
            self.html.SetZoom(zoom + 2)
        except wx._core.wxAssertionError:
            # Fails for unknown reason with IE under Windows 7
            pass
        

        self.jquery = False

        # Only introduced in 2.9.5
        #self.html.EnableContextMenu(False)

        #self.javascript_includes = []
        #self.css_includes = []

        #self.js_dir = os.path.join(self.presenter.getMainControl().wikiAppDir, "lib", "js")
        
        #for f in os.listdir(self.js_dir):
        #    if f.endswith(".js"):
        #        self.javascript_includes.append(os.path.join(self.js_dir, f))
        #    elif f.endswith(".css"):
        #        self.css_includes.append(os.path.join(self.js_dir, f))



    def OnFocus(self, evt):
        """Refresh the page when it gains focus"""
        self.refresh()

    def OnShow(self, evt):
        self.realizeIfNeeded()
        evt.Skip()

    def FollowLinkIfSelected(self):
        """
        Follows any focused link
        """

        self.html.RunScript('''
            document.title = "None"
            if (document.activeElement.tagName == "A" || document.activeElement.tagName == "a") {
                document.title = document.activeElement.href
            }
            ''')
        link = self.html.GetCurrentTitle()

        if link != "None":
            self._activateLink(link, tabMode=0)

    def OnPageNavigation(self, evt):
        # TODO: make extendable - for plugins + VI mode
        uri = flexibleUrlUnquote(evt.GetURL())

        # Run script segfaults if WikidPad started with a page in preview
        # quick hack to prevent this
        if self.page_loaded:
            self.html.RunScript(r"""event_str = false;""")

        self.page_loaded = True

        # This can lead to an event being vetoed multiple times
        # (which should not be an issue)
        r = False
        for split_uri in uri.split("//PROXY_EVENT_SEPERATOR//"):
            event_return = self.HandleProxyEvent(evt, split_uri)
            if event_return:
                r = True

        if r:
            return 



        # TODO: add iframe support
        ## iframes have a parent
        ## let them load normally if set in options (otherwise they are 
        ## opened by the external launcher as the page is loaded)
        #if frame.get_parent() is not None and \
        #        self.presenter.getConfig().getboolean("main",
        #        "html_preview_ieShowIframes", True):
        #    # Yeah this is probably not the best way to do this...
        #    if str(action.get_reason()) == "<enum WEBKIT_WEB_NAVIGATION_REASON_OTHER of type WebKitWebNavigationReason>":
        #        return False
 
        if self._activateLink(uri, tabMode=0):
            evt.Veto()


    def HandleProxyEvent(self, evt, uri):
        """
        Helper to handle custom events

        @param evt: The wxPython navigation event
        @param uri: The PROXY_EVENT uri 

        @rtype: bool
        @return: True if the event has been vetoed and the link
                    should not be activated.
        """

        if uri.endswith("PROXY_EVENT//JQUERY_LOADED"):
            self.OnJqueryLoaded()
            evt.Veto()
            return True
        if "PROXY_EVENT//MOUSE_CLICK" in uri:
            if not uri.endswith("KEEP_FOCUS"):
                self.presenter.makeCurrent()
            evt.Veto()
            return True
        elif "PROXY_EVENT//MOUSE_RIGHT_CLICK" in uri:
            self.OnContextMenu()
            evt.Veto()
            return True
        elif "PROXY_EVENT//MOUSE_MIDDLE_CLICK" in uri:
            ctrl = uri.split("PROXY_EVENT//MOUSE_MIDDLE_CLICK/")[1]

            if ctrl == "TRUE":
                ctrlDown = True
            else:
                ctrlDown = False

            self.OnMiddleDown(controlDown=ctrlDown)
            evt.Veto()
            return True
        # Check if it is a link hover event
        elif "PROXY_EVENT//HOVER_START/" in uri:
            link = uri.split("PROXY_EVENT//HOVER_START/")[1]
            self.contextHref = link
            self.updateStatus(link)
            evt.Veto()
            return True
        elif "PROXY_EVENT//HOVER_END/" in uri:
            self.contextHref = None
            self.updateStatus(None)
            evt.Veto()
            return True
        elif "PROXY_EVENT//ANCHOR/" in uri:
            anchor = uri.split("PROXY_EVENT//ANCHOR/")[1]
            self.html.RunScript("""
                document.getElementsByName("{0}")[0].scrollIntoView()
                // We don't use location.href as we get into a
                // navigation loop hell
                //location.href = "#{0}";
                """.format(anchor))
            evt.Veto()
            return True
        # This breaks if not in VI mode
        elif self.vi is not None:
            if self.vi.OnViPageNavigation(evt, uri):
                return True
        # Run the event through the previewPageNavigation hook

        if self.presenter.getMainControl().hooks.previewPageNavigation(
                self, evt, uri) is True:
            return True
        elif "PROXY_EVENT" in uri:
            # unmanged event, veto it
            evt.Veto()
            return True

        return False


    def OnContextMenu(self):
        """
        Generates a context specific context menu

        TODO: Print button
        """
        menu = wx.Menu()

        if self.html.HasSelection():
            appendToMenuByMenuDesc(menu, "Copy;CMD_CLIPBOARD_COPY")

        appendToMenuByMenuDesc(menu, "Select All;CMD_SELECT_ALL")

        appendToMenuByMenuDesc(menu, "-")

        href = self.contextHref
        if href is not None:
            if href.startswith("http://internaljump/"):
                appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTERNAL_JUMP)

                # Check if their are any surrounding viewports that we can use
                viewports = self.presenter.getMainControl().\
                        getMainAreaPanel().getPossibleTabCtrlDirections(
                                self.presenter)
                for direction in viewports:
                    if viewports[direction] is not None:
                        appendToMenuByMenuDesc(menu, 
                                    _CONTEXT_MENU_INTERNAL_JUMP_DIRECTION[
                                            direction])
            else:
                appendToMenuByMenuDesc(menu, "Activate;CMD_ACTIVATE_THIS")
                
                if href.startswith("file:") or \
                        href.startswith("rel://"):

                    appendToMenuByMenuDesc(menu,
                            "Open Containing Folder;"
                            "CMD_OPEN_CONTAINING_FOLDER_THIS")

        appendToMenuByMenuDesc(menu, "-")

        # Add the Forward and Back items
        backMenuItem = appendToMenuByMenuDesc(menu, 
                "Back;CMD_HISTORY_BACK")[0]
        forwardMenuItem = appendToMenuByMenuDesc(menu, 
                "Forward;CMD_HISTORY_FORWARD")[0]

        # Disable Forward / Back items if there is no history
        pageHistDeepness = self.presenter.getPageHistory().getDeepness()

        if pageHistDeepness[0] == 0:
            backMenuItem.Enable(False)

        if pageHistDeepness[1] == 0:
            forwardMenuItem.Enable(False)
        #    forward_menu_item.set_sensitive(False)
        #self.PopupMenuXY(menu, evt.GetX(), evt.GetY())
        self.PopupMenu(menu)
        menu.Destroy()

    def OnJqueryLoaded(self):
        """
        This is only called if jQuery is present and loaded

        jQuery must be added to the page via the exporter
        """
        js_path = os.path.join(self.presenter.getMainControl().wikiAppDir, "lib", "js", "onload_jquery.js")

        if os.path.isfile(js_path):
            try:
                with open(js_path) as f:
                    self.html.RunScript(f.read())
                self.jquery = True
            except IOError as e:
                print("Unable to load '{0}'".format(js_path), e)

    def OnPageLoaded(self, evt):
        """
        Called when page is loaded
        """

        # As the html2 ctrl eats all mouse events we have to use a javascript
        # hack to check when the ctrl gains focus
        self.html.RunScript(r"""
        // TODO: function to handle multiple events
        var event_str = false;

        function triggerEvent(event) {
            if (event_str) {
                event_str = event_str + "//PROXY_EVENT_SEPERATOR//PROXY_EVENT//" + event;
            } else {
                event_str = "PROXY_EVENT//" + event;
            }
            window.location.href = event_str;
        }

        function onClick(e) {
            // First check for selection and fire an event if needed
            checkSelection();

            // Left click
            if(e.button == 0) {
                triggerEvent("MOUSE_CLICK");
            } else if (e.button == 1) {
                // Middle click
                ctrl = "/FALSE"
                if (e.ctrlKey) {
                    ctrl = "/TRUE"
                }
                triggerEvent("MOUSE_MIDDLE_CLICK" + ctrl);
                e.stopPropagation();
                e.preventDefault();
                e.stopImmediatePropagation();
                e.cancelBubble = true;
            }
        }

        function onContextMenu() {
            triggerEvent("MOUSE_RIGHT_CLICK");
        }

        // We disable the context menu (with the aim of creating our own)
        document.addEventListener('contextmenu', function(e) {
            onContextMenu();
            e.stopPropagation();
            e.preventDefault();
            e.stopImmediatePropagation();
            e.cancelBubble = true;
            return false;
        }, false);

        document.addEventListener('click', onClick, true); 

        ////////////////////////////////////
        // Detect and react to text selection
        ////////////////////////////////////
        
        // Function to retrieve the selected text
        function getSelectedText() {
            var text = "";
            if (typeof window.getSelection != "undefined") {
                text = window.getSelection().toString();
            } else if (typeof document.selection != "undefined" && document.selection.type == "Text") {
                text = document.selection.createRange().text;
            }
            return text;
        }

        // Create events so we can monitor if text is selected or not
        function checkSelection() {
            if (getSelectedText().length > 0) {
                triggerEvent("SELECTION_EXISTS");
            } else {
                triggerEvent("NO_SELECTION_EXISTS");
            }
        }

        // We could add a selectionchange event listener but it would
        // cause a lot of events to be fired.
        // Instead we just hook into click (handled above), blur and keyup events
        document.addEventListener('blur', checkSelection, true); 
        document.addEventListener('keyup', checkSelection, true); 

        //////////////////////////////

        // We also need to hack in a solution to detect when hovering over
        // links
        function hoverLink(link) { 
            triggerEvent("HOVER_START/" + link);
        }
        function hoverLinkEnd(link) { 
            triggerEvent("HOVER_END/" + link);
        }

        function setupHoverLinks(elem) { 
            elem.onmouseover = function() {
                hoverLink(elem.href);
            }
            elem.onmouseout = function() {
                hoverLinkEnd(elem.href);
            }
        }


        links = document.getElementsByTagName("a");

        for (var i = 0; i < links.length; i++) {
                link = links[i].href;
                setupHoverLinks(links[i]);
        }


// Attempt to load jQuery
if ((typeof jQuery !== 'undefined')) {
    $( document ).ready(function() {
        triggerEvent("JQUERY_LOADED");
    });
}

        """)


        #Scroll to last position if no anchor
        if self.lastAnchor is None:
            wikiPage = self.presenter.getDocPage()
            lx, ly = wikiPage.getPresentation()[3:5]

            self.scrollDeferred(lx, ly)
            
        # Run hooks
        self.presenter.getMainControl().hooks.previewPageLoaded(self)


    def OnMouseWheelScrollEvent(self, evt):
        if self.vi is not None and self.vi.hintDialog is not None:
            self.vi.clearHints()
            self.vi.hintDialog.Close()

        # If ctrl is pressed
        if evt.ControlDown():
            #if evt.direction == gtk.gdk.SCROLL_UP:
            #    self.addZoom(-1)
            #elif evt.direction == gtk.gdk.SCROLL_DOWN:
            #    self.addZoom(1)
            scrollUpZoom = evt.GetWheelRotation() // evt.GetWheelDelta()
            if self.presenter.getConfig().getboolean(
                    "main", "mouse_reverseWheelZoom", False):
                scrollUpZoom = -scrollUpZoom
            
            self.addZoom(scrollUpZoom)



    def Freeze(self):
        self.freezeCount += 1
        
    def Thaw(self):
        self.freezeCount = max(0, self.freezeCount - 1)
        if self.freezeCount == 0:
            self.Refresh(False)

    def OnOpenLinkInNewTab(self, evt):
        uri = self.contextHref
        self._activateLink(uri, tabMode=2)

        return False
        
    def OnOpenLinkInNewBackgroundTab(self, evt):
        uri = self.contextHref
        self._activateLink(uri, tabMode=3)

        return False

    def OnGoBackInHistory(self, evt):
        """
        using self.presenter.getMainControl().goBrowserBack()
        results in scrolling issues
        """
        self.presenter.getPageHistory().goInHistory(-1)

    def OnGoForwardInHistory(self, evt):
        self.presenter.getPageHistory().goInHistory(+1)

    def OnPrint(self, gtkEvent):
        # 2=Export to HTML (Webview)
        self.presenter.getMainControl().OnShowPrintMainDialog(exportTo=2)

    def updateStatus(self, status):
        # TODO: Handle visual mode
        if self.visible:

            # Status None is sent on mouse off
            if status is None:
                self.presenter.getMainControl().statusBar.SetStatusText(
                        "", 0)
                return

            internaljumpPrefix = "http://internaljump/"

            # It appears webkit urls sometimes need cleaning up
            if internaljumpPrefix in status:
                status = "{}{}".format(internaljumpPrefix, 
                        status.split(internaljumpPrefix)[1])

            wikiWord = None
            if status.startswith(internaljumpPrefix):
                # First check for an anchor. In URLs, anchors are always
                # separated by '#' regardless which character is used
                # in the wiki syntax (normally '!')
                try:
                    wikiWord, anchor = status[len(internaljumpPrefix):].split(
                            "#", 1)
                except ValueError:
                    wikiWord = status[len(internaljumpPrefix):]
                    anchor = None


                wikiDocument = self.presenter.getWikiDocument()
                if wikiDocument is None:
                    return
                
                # Add to internal jump prefix?
                pagePrefix = "wikipage/"
                wikiWord = wikiDocument.getWikiPageNameForLinkTerm(
                        wikiWord[len(pagePrefix):])


            # Webview uses the full url for links to anchors on the same page
            elif status[len("file://"):].startswith(
                    self.currentLoadedUrl[len("file:"):]):
                wikiWord = self.currentLoadedWikiWord
                try:
                    anchor = status.split("#", 1)[1]
                except IndexError:
                    anchor = None
    
            if wikiWord is not None:
                if anchor is not None:
                    anchor = "#{0}".format(anchor)
                else:
                    anchor = ""
                status = _("Link to page: {0}{1}".format(wikiWord, anchor))

            self.presenter.getMainControl().statusBar.SetStatusText(
                    status, 0)

    def GetScriptReturn(self, script, return_value):
        """
        Helper function to allow retrieval of a javascript value
        """
        self.html.RunScript('oldtitle=document.title;')

        self.html.RunScript(script)

        self.html.RunScript("document.title = {0}".format(return_value))

        r =  self.html.GetCurrentTitle()
            
        self.html.RunScript('document.title=oldtitle;')

        return r

    def GetViewStart(self):
        """
        """
        scriptRet = self.GetScriptReturn("a = window.scrollX + ',' + window.scrollY;", "a")
        
        if scriptRet == "" or scriptRet == "undefined,undefined":
            # Happens with IE
            return (0, 0)
            
        return tuple([int(i) for i in scriptRet.split(",")])

    def Scroll(self, x, y):
        """
        Scroll viewport to position.

        Uses javascript as widgets built in scrolling does not appear to work
        """
        self.html.RunScript("scrollTo({0}, {1})".format(x, y))


    def getIntendedViewStart(self):
        """
        If a deferred scrolling waits for process, this returns the deferred
        scroll values instead of real view start
        """
        if self.deferredScrollPos is not None:
            return self.deferredScrollPos
        else:
            return self.GetViewStart()


    def setLayerVisible(self, vis, scName=""):
        """
        Informs the widget if it is really visible on the screen or not
        """
        if not self.visible and vis:
            #self.outOfSync = True   # Just to be sure
            self.refresh()
            
        if not vis:
            self.exporterInstance.tempFileSet.clear()

        self.visible = vis


    def close(self):
        self.exportingThreadHolder.setThread(None)

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
        # TODO: Rewrite HtmlExporter in include a threadstop

        ## _prof.start()

        if self.currentLoadedWikiWord:
            try:
                prevPage = self.presenter.getWikiDocument().getWikiPage(
                        self.currentLoadedWikiWord)
                vs = self.getIntendedViewStart()
                if vs is not None:
                    prevPage.setPresentation(vs, 3)
            except WikiWordNotFoundException as e:
                pass

        wikiPage = self.presenter.getDocPage()

        if isinstance(wikiPage,
                (DocPages.DataCarryingPage, DocPages.AliasWikiPage)) and \
                not wikiPage.checkFileSignatureAndMarkDirty():
            # Valid wiki page and invalid signature -> rebuild HTML page
            self.outOfSync = True

        if self.outOfSync:
#             self.currentLoadedWikiWord = None
            # Exporting the page can be time consuming so we do it in another
            # thread so the UI is not locked

            # Quick temp? fix to show that a page is being load (as the
            # currently open page will stay responsive
            if self.jquery:
                self.html.RunScript(LOADING_JS)
                print("LOADING")

            eth = self.exportingThreadHolder

            old_thread = eth.getThread()

            if old_thread is not None:
                eth.setThread(None)

            t = threading.Thread(None, self.generateExportHtml, args =  (wikiPage, eth))

            eth.setThread(t)
            t.setDaemon(True)
            t.start()

        else:  # Not outOfSync
            if self.anchor is not None:
#                 self.passNavigate += 1
                #self.html.LoadURL(self.currentLoadedUrl + u"#" + self.anchor)
                wx.CallAfter(self.html.LoadURL, "PROXY_EVENT//ANCHOR/" + 
                        self.anchor)

                # Is this neccessary?
                wx.CallAfter(self.postRefresh, self.anchor)
                #self.lastAnchor = self.anchor
            #else:
            #    lx, ly = wikiPage.getPresentation()[3:5]
            #    self.scrollDeferred(lx, ly)


        #self.anchor = None
        self.outOfSync = False

    def generateExportHtml(self, wikiPage, threadstop=DUMBTHREADSTOP):
        try:
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

            self.presenter.setTabProgressThreadSafe(0, threadstop)
            
            # Remove previously used temporary files
            self.exporterInstance.tempFileSet.clear()
            self.exporterInstance.buildStyleSheetList()

            self.exporterInstance.setWikiDocument(   # ?
                    self.presenter.getWikiDocument())

            self.exporterInstance.setLinkConverter(
                    LinkConverterForPreviewWk(self.presenter.getWikiDocument()))   # /?
            
            threadstop.testValidThread()

            self.presenter.setTabProgressThreadSafe(20, threadstop)

            html = self.exporterInstance.exportWikiPageToHtmlString(wikiPage)

            threadstop.testValidThread()

            wx.GetApp().getInsertionPluginManager().taskEnd()

            self.presenter.setTabProgressThreadSafe(30, threadstop)
            
            if self.currentLoadedWikiWord == word and \
                    self.anchor is None:

                htpath = self.htpaths[self.currentHtpath]

                with open(htpath, "w", encoding="utf-8") as f:
                    f.write(html)

                url = "file:" + urlFromPathname(htpath)
                self.currentLoadedUrl = url
                self.passNavigate += 1

                # NOTE: html2 seems to be threadsafe (on linux at least)
                #       but this should probably be moved back to the main thread
                #       just to be sure
                callInMainThread(self.html.LoadURL,url)

                # If we are just reloading the page we can leave the scroll
                # at its last position
                #lx, ly = wikiPage.getPresentation()[3:5]
                #self.scrollDeferred(lx, ly)
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
                callInMainThread(self.html.LoadURL,url)
                self.lastAnchor = self.anchor
                
                #if self.anchor is None:
                #    lx, ly = wikiPage.getPresentation()[3:5]
                #    self.scrollDeferred(lx, ly)

            self.outOfSync = False
            #self.anchor = None

        except NotCurrentThreadException:
            return
        finally:
            self.presenter.setTabProgressThreadSafe(100, threadstop)


    def postRefresh(self, anchor):
        self.lastAnchor = anchor
        self.anchor = None
        self.outOfSync = False

    def gotoAnchor(self, anchor):
        self.anchor = anchor
        if self.visible:
            self.refresh()
            
    def getSelectedHTML(self):
        """
        Returns the HTML of the currently selected text

        __on_selection_received is called and sets self.selectedHTML
        """
        return self.html.GetSelectedSource()

    # NOTE: capitalized to maintain consistency with WikiTxtCtrl
    def GetSelectedText(self):
        """
        Returns the currently selected text (plain)
        """
        return self.html.GetSelectedText()


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
                vs = self.getIntendedViewStart()
                if vs is not None:
                    prevPage.setPresentation(vs, 3)
            except WikiWordNotFoundException as e:
                pass

    def onOptionsChanged(self, miscevt):
        self.outOfSync = True
        self._updateTempFilePrefPath()
        
        # To allow switching vi keys on and off without restart
        if self.keyEventConn is not None:
            self.html.ctrl.disconnect(self.keyEventConn)
            use_vi_navigation = self.presenter.getConfig().getboolean("main",
                    "html_preview_webkitViKeys", False)
            if use_vi_navigation:
    
                self.vi = ViFunctions(self) 
                self.html.Bind(wx.EVT_KEY_DOWN, self.vi.OnViKeyDown)
    
                self.keyEventConn = self.html.ctrl.connect("key-press-event",
                        self.__on_key_press_event_vi)
            else:
                self.vi = None
                self.html.Bind(wx.EVT_KEY_DOWN, None)
                

        if self.visible:
            self.refresh()

    def onUpdatedWikiPage(self, miscevt):
        """
        Called on when a page is saved

        If a page is updated we should refresh all open previews
        unless html_preview_reduceUpdateHandling is False
        """
        if self.presenter.getConfig().getboolean("main",
                "html_preview_reduceUpdateHandling", True):
            return
        self.outOfSync = True
        if self.visible:
            self.refresh()
            
    def onChangedLiveText(self, miscevt):
        self.outOfSync = True

    def scrollDeferred(self, lx, ly):
        if self.deferredScrollPos is not None:
            self.deferredScrollPos = (lx, ly)
        else:
            # Put new _scrollAndThaw into queue
            self.Freeze()
            self.deferredScrollPos = (lx, ly)
            wx.CallAfter(self._scrollAndThaw)
        
    def _scrollAndThaw(self):
        try:
            self.Scroll(self.deferredScrollPos[0], self.deferredScrollPos[1])
            self.Thaw()
            self.deferredScrollPos = None
            self.counterResizeIgnore = 0
        except RuntimeError:
            # There will be a better way to do this
            pass


    def OnSize(self, evt):
        lx, ly = self.getIntendedViewStart()
        self.scrollDeferred(lx, ly)

        evt.Skip()

    def OnClipboardCopy(self, evt):
        self.html.Copy()

    def OnSelectAll(self, evt):
        self.html.SelectAll();

    def addZoom(self, step):
        """
        Modify the zoom setting by step relative to current zoom in
        configuration.

        html2.SetZoom only has 5 different zoom levels (0-4)

        It may be worth using a javascript based zoom which would
        allow for finer control
        """
        zoom = self.presenter.getConfig().getint("main", "preview_zoom", 0)
        zoom += step
        
        # Restrict to allowed range.
        # In the internal configuration the value 0 means the default size
        # This should be kept consistent between different WikiHtmlView
        # implementations.
        # So it is restricted to range -2...2
        zoom = between(-2, zoom, 2)

        self.presenter.getConfig().set("main", "preview_zoom", str(zoom))
        self.outOfSync = True
        self.refresh()
        
        # The parameter must be in range 0...4 where 2 is default value
        try:
            self.html.SetZoom(zoom + 2)
        except wx._core.wxAssertionError:
            # Fails for unknown reason with IE under Windows 7
            pass


        
    def OnMiddleDown(self, controlDown=False):
        if self.contextHref is not None:
            if controlDown:
                middleConfig = self.presenter.getConfig().getint("main",
                    "mouse_middleButton_withoutCtrl", 2)
            else:
                middleConfig = self.presenter.getConfig().getint("main",
                    "mouse_middleButton_withCtrl", 3)

            tabMode = MIDDLE_MOUSE_CONFIG_TO_TABMODE[middleConfig]

            self._activateLink(self.contextHref, tabMode=tabMode)

        #return False

    def _activateLink(self, href, tabMode=0):
        """
        tabMode -- 0:Same tab; 2: new tab in foreground; 3: new tab in background
        Returns True if link was processed here and doesn't need further processing
        """

#         decision.use()
        if self.passNavigate:
            self.passNavigate -= 1
            return False

        internaljumpPrefix = "http://internaljump/"

        # It appears webkit urls sometimes need cleaning up
        if internaljumpPrefix in href:
            href = "{}{}".format(internaljumpPrefix, 
                    href.split(internaljumpPrefix)[1])


        ## Webview uses the full url for links to anchors on the same page
        #elif href[len("file://"):].startswith(
        #        self.currentLoadedUrl[len("file:"):]):
        #    wikiWord = self.currentLoadedWikiWord
        #    print(self.currentLoadedUrl, wikiWord)
        #    wikiWord = self.currentLoadedWikiWord
        #    try:
        #        href = "{}{}{}".format(internaljumpPrefix, wikiWord, 
        #                href.split("#", 1)[1])
        #    except IndexError:
        #        anchor = None

        if href.startswith(internaljumpPrefix + "wikipage/"):  # len("wikipage/") == 9

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

            # Now open wiki
            presenter.openWikiPage(word, motionType="child", anchor=anchor)

            if not tabMode & 1:
                # Show in foreground
                presenter.getMainControl().getMainAreaPanel().\
                        showPresenter(presenter)
                presenter.SetFocus()


            #decision.ignore()
            return True

        elif href == (internaljumpPrefix + "action/history/back"):
            # Go back in history
            self.presenter.getMainControl().goBrowserBack()
            #decision.ignore()
            return True

        elif href == (internaljumpPrefix + "mouse/leftdoubleclick/preview/body"):
            # None affect current tab so return false
            pres = self.presenter
            mc = pres.getMainControl()

            paramDict = {"page": pres.getDocPage(), "presenter": pres,
                    "main control": mc}

            mc.getUserActionCoord().reactOnUserEvent(
                    "mouse/leftdoubleclick/preview/body", paramDict)
            ##decision.ignore()

            self.html.RunScript("checkSelection();")
            return True

        elif href == (internaljumpPrefix + "event/pageBuilt"):
            # Should we be doing anything here?
            return True

        elif href.startswith("file:"):
            hrefSplit = href.split("#", 1)
            hrefNoFragment = hrefSplit[0]
            normedPath = os.path.normcase(getLongPath(pathnameFromUrl(hrefNoFragment)))
            if len(hrefSplit) == 2 and normedPath.encode() in self.normHtpaths:
            #if len(hrefSplit) == 2 and normedPath in self.normHtpath:
                self.gotoAnchor(hrefSplit[1])
                #decision.ignore()
            else:
                # To lauch external urls we need to remove webviews preceeding
                # "file:///", quote the url and add "file:/"
                self.presenter.getMainControl().launchUrl(
                        "file:/{0}".format(urlQuote(href[len("file:///"):])))
                #decision.ignore()
            return True
        else:
            self.presenter.getMainControl().launchUrl(href)
            #decision.ignore()
            return True

        # Should never be reached
        return False

    def FocusSelection(self):
        # Focus selected elements
        # Might this fail is some cases?
        self.html.RunScript('''
            var selectionRange = window.getSelection ();

            if (selectionRange.rangeCount > 0) {
                var range = selectionRange.getRangeAt (0);
                container = range.commonAncestorContainer;
                container.parentNode.focus();
            }

            ''')

    def GetScrollAndCaretPosition(self):
        x, y = self.getIntendedViewStart()
        return None, x, y

    def SetScrollAndCaretPosition(self, pos, x, y):
        self.scrollDeferred(x, y)

    #def SetFocus(self):
    #    self.html.ctrl.grab_focus()

    def ViewSource(self, arg=None):
        #self.html.set_view_source_mode(
        #        not self.html.get_view_source_mode())
        self.html.LoadURL("view-source:"+self.currentLoadedUrl)

    def GetHtmlViewToActivate(self, direction, makePresenterCurrent=False):
        """
        Helper for OnActive* functions.

        Returns the htmlview to activate the link on (based on the direction
        parameter)
        """
        if direction is not None:
            presenter = self.presenter.getMainControl().getMainAreaPanel().\
                            getActivePresenterTo(direction, self.presenter)
            if makePresenterCurrent:
                presenter.makeCurrent()
            html = presenter.getSubControl("preview")
        else:
            html = self

        return html


    def OnActivateThis(self, evt, direction=None):
        html = self.GetHtmlViewToActivate(direction, True)
        html._activateLink(self.contextHref, tabMode=0)

    def OnActivateNewTabThis(self, evt, direction=None):
        html = self.GetHtmlViewToActivate(direction, True)
        html._activateLink(self.contextHref, tabMode=2)

    def OnActivateNewTabBackgroundThis(self, evt, direction=None):
        # If we are opening a background tab assume we want the current
        # tabCtrl to remain active
        presenter = self.presenter

        html = self.GetHtmlViewToActivate(direction, True)
        html._activateLink(self.contextHref, tabMode=3)

        wx.CallAfter(presenter.makeCurrent)

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
                path = os.path.dirname(pathnameFromUrl(link))
                if not os.path.exists(longPathEnc(path)):
                    self.presenter.displayErrorMessage(
                            _("Folder does not exist"))
                    return

                OsAbstract.startFile(self.presenter.getMainControl(),
                        path)
            except IOError:
                pass   # Error message?


#_CONTEXT_MENU_INTERNAL_JUMP = \
#u"""
#Activate;CMD_ACTIVATE_THIS
#Activate New Tab;CMD_ACTIVATE_NEW_TAB_THIS
#Activate New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
#Activate New Window.;CMD_ACTIVATE_NEW_WINDOW_THIS
#"""


# Entries to support i18n of context menus
if not True:
    N_("Activate")
    N_("Activate New Tab")
    N_("Activate New Tab Backgrd.")

class ExtractUrlFromHTML(HTMLParser):
    """HTML Parser designed to extract urls from html"""
    def __init__(self):
        HTMLParser.__init__(self)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)

        if tag == "a" and "href" in attributes:
            self.urls.append(attributes['href'])

    def GetUrls(self):
        return self.urls


class ViFunctions(ViHelper):
    # TODO: Insert mode (as per vimperator/pentadactyl)
    def __init__(self, view):
        ViHelper.__init__(self, view)

        self.mode = ViHelper.NORMAL

        k = ViHelper.KEY_BINDINGS
        # Currently we only have one mode whilst in preview
        self.keys = { 0 : {
#(k["g"], k["u"]) : (0, (self.ViewParents, False), 0, 0), # gu
#(k["g"], k["U"]) : (0, (self.ViewParents, True), 0, 0), # gU
(k["\\"], k["u"]) : (0, (self.ViewParents, False), 0, 0), # \u
(k["\\"], k["U"]) : (0, (self.ViewParents, True), 0, 0), # \U
(k["g"], k["t"]) : (0, (self.SwitchTabs, None), 0, 0), # gt
(k["g"], k["T"])  : (0, (self.SwitchTabs, True), 0, 0), # gT
(k["g"], k["r"]) : (0, (self.OpenHomePage, False), 0, 0), # gr
(k["g"], k["R"]) : (0, (self.OpenHomePage, True), 0, 0), # gR

(k["\\"], k["o"]) : (0, (self.ctrl.presenter.getMainControl(). \
                                showWikiWordOpenDialog, None), 0, 0), # \o
# TODO: rewrite open dialog so it can be opened with new tab as default
(k["\\"], k["O"]): (0, (self.ctrl.presenter.getMainControl(). \
                                showWikiWordOpenDialog, None), 0, 0), # \O
(k["g"], k["o"]) : (0, (self.ctrl.presenter.getMainControl(). \
                                showWikiWordOpenDialog, None), 0, 0), # go
# TODO: rewrite open dialog so it can be opened with new tab as default
(k["g"], k["O"]): (0, (self.ctrl.presenter.getMainControl(). \
                                showWikiWordOpenDialog, None), 0, 0), # gO

(k["d"], k["d"]) : (0, (self.CloseCurrentTab, None), 0, 0), # dd

(k["Z"], k["Z"]) : (0, (self.ctrl.presenter.getMainControl().exitWiki, None), 0, 0), # ZZ

# ctrl +

(("Ctrl", k["["]),) : (0, (self.ctrl.html.ClearSelection, None), 0, 0), # Ctrl + [
(("Ctrl", k["d"]),) : (0, (self.HalfPageJumpDown, None), 0, 0), # Ctrl + d
(("Ctrl", k["u"]),) : (0, (self.HalfPageJumpUp, None), 0, 0), # Ctrl + u
(("Ctrl", k["l"]),) : (0, (self.ctrl.FollowLinkIfSelected, None), 0, 0), # Ctrl + l

(k["/"],)  : (0, (self.StartForwardSearch, None), 0, 0), # /
(k["?"],)  : (0, (self.StartReverseSearch, None), 0, 0), # ?

(k[":"],)  : (0, (self.StartCmdInput, None), 0, 0), # :

(k["\\"], k["o"]) : (0, (self.StartCmdInput, "open "), 0, 0), # \o
(k["\\"], k["t"]) : (0, (self.StartCmdInput, "tabopen "), 0, 0), # \t

(k["n"],) : (1, (self.Repeat, self.ContinueLastSearchSameDirection), 0, 0), # n
(k["N"],) : (1, (self.Repeat, self.ContinueLastSearchReverseDirection), 0, 0), # N

(k["["],)  : (0, (self.GoBackwardInHistory, None), 0, 0), # [
(k["]"],)  : (0, (self.GoForwardInHistory, None), 0, 0), # ]
# H and L are equivelent to gh and gl in preview mode
(k["H"],)  : (0, (self.GoBackwardInHistory, None), 0, 0), # H
(k["L"],)  : (0, (self.GoForwardInHistory, None), 0, 0), # L
(k["g"], k["H"])  : (0, (self.GoBackwardInHistory, None), 0, 0), # gH
(k["g"], k["L"])  : (0, (self.GoForwardInHistory, None), 0, 0), # gL
(k["g"], k["h"])  : (0, (self.GoBackwardInHistory, None), 0, 0), # gh
(k["g"], k["l"])  : (0, (self.GoForwardInHistory, None), 0, 0), # gl

(k["H"],)  : (0, (self.GoBackwardInHistory, None), 0, 0), # H
(k["L"],)  : (0, (self.GoForwardInHistory, None), 0, 0), # L
(k["o"],) : (0, (self.ctrl.presenter.getMainControl(). \
                        showWikiWordOpenDialog, None), 0, 0), # o
(k["O"],) : (0, (self.ctrl.presenter.getMainControl(). \
                        showWikiWordOpenDialog, None), 0, 0), # O
(k["j"],) : (0, (self.DocumentNavigation, k["j"]), 0, 0), # j
(k["k"],) : (0, (self.DocumentNavigation, k["k"]), 0, 0), # k
(k["h"],) : (0, (self.DocumentNavigation, k["h"]), 0, 0), # h
(k["l"],) : (0, (self.DocumentNavigation, k["l"]), 0, 0), # l
(k["g"], k["g"]) : (0, (self.DocumentNavigation, (k["g"], k["g"])), 0, 0), # gg
(k["G"],)  : (0, (self.DocumentNavigation, k["G"]), 0, 0), # G
(k["%"],)  : (0, (self.DocumentNavigation, k["%"]), 0, 0), # %
(k["$"],)  : (0, (self.DocumentNavigation, k["$"]), 0, 0), # $
(k["^"],)  : (0, (self.DocumentNavigation, k["^"]), 0, 0), # ^
(k["0"],)  : (0, (self.DocumentNavigation, k["0"]), 0, 0), # 0

(k["}"],) : (0, (self.JumpToNextHeading, None), 0, 0), # }
(k["{"],) : (0, (self.JumpToPreviousHeading, None), 0, 0), # {

(k["f"],) : (0, (self.startFollowHint, 0), 0, 0), # f
(k["F"],) : (0, (self.startFollowHint, 2), 0, 0), # F
(k["Y"],)  : (0, (self.ctrl.OnClipboardCopy, None), 0, 0), # Y
(k["y"],) : (0, (self.CopyWikiWord, None), 0, 0), # y
#652k["]"]  : (self.ctrl.FollowLinkIfSelected, None), # return


(("Alt", k["g"]),)    : (0, (self.GoogleSelection, None), 1, 0), # <a-g>

(("Ctrl", k["w"]), k["l"])  : (0, (self.ctrl.presenter.getMainControl().getMainAreaPanel().switchPresenterByPosition, "right"), 0, 0), # <c-w>l
(("Ctrl", k["w"]), k["h"])  : (0, (self.ctrl.presenter.getMainControl().getMainAreaPanel().switchPresenterByPosition, "left"), 0, 0), # <c-w>l
(("Ctrl", k["w"]), k["j"])  : (0, (self.ctrl.presenter.getMainControl().getMainAreaPanel().switchPresenterByPosition, "below"), 0, 0), # <c-w>l
(("Ctrl", k["w"]), k["k"])  : (0, (self.ctrl.presenter.getMainControl().getMainAreaPanel().switchPresenterByPosition, "above"), 0, 0), # <c-w>l

(k["g"], k["s"])  : (0, (self.SwitchEditorPreview, None), 0, 0), # gs
(k["g"], k["."])  : (0, (self.SwitchEditorPreview, "textedit"), 0, 0), # ge
(k["g"], k["p"])  : (0, (self.SwitchEditorPreview, "preview"), 0, 0), # gp

# F3 and F4 switch directly to editor / preview mode
(wx.WXK_F3,)     : (0, (self.SwitchEditorPreview, "textedit"), 0, 0), # F3
(wx.WXK_F4,)     : (0, (self.SwitchEditorPreview, "preview"), 0, 0), # F4
# F5 refreshes the current page
(wx.WXK_F5,)     : (0, (self.RefreshPage, None), 0, 0), # F5
(k["R"],)     : (0, (self.RefreshPage, None), 0, 0), # R
    
        }
        }


        # VISUAL MODE
        self.keys[2] = self.keys[0].copy()
        self.keys[2].update({
            # TODO: implement
        })

        self.LoadPlugins("preview_wk")

        # Generate possible key modifiers
        self.key_mods = self.GenerateKeyModifiers(self.keys)
        self.motion_keys = self.GenerateMotionKeys(self.keys)
        self.motion_key_mods = self.GenerateKeyModifiers(self.motion_keys)

        # Used for rewriting menu shortcuts
        self.GenerateKeyAccelerators(self.keys)

    def OnViPageNavigation(self, evt, uri):
        if "PROXY_EVENT//SELECTION_EXISTS" in uri:
            self.SetMode(ViHelper.VISUAL)
            evt.Veto()
            return True
        elif "PROXY_EVENT//NO_SELECTION_EXISTS" in uri:
            self.SetMode(ViHelper.NORMAL)
            evt.Veto()
            return True

        return False

    # Vi Helper functions
    def SetMode(self, mode):
        """
        """
        
        if mode is None:
            mode = self.mode
        else:
            self.mode = mode

        if mode == ViHelper.NORMAL:
            self.RemoveSelection()
        elif mode == ViHelper.VISUAL:
            pass



    def RefreshPage(self):
        self.outOfSync = True
        self.ctrl.refresh()

    # Document navigation
    def HalfPageJumpDown(self):
        self.ctrl.html.RunScript("window.scrollBy(0,window.innerHeight/2);")
            
    def HalfPageJumpUp(self):
        self.ctrl.html.RunScript("window.scrollBy(0,-window.innerHeight/2);")

    def DocumentNavigation(self, key):
        """
        function to handle most navigation commonds

        currently handles: j, k, h, l, G, gg, 0, $
        """
        step_incr = "25"

        c = self.count

        if key == 106: # j
            self.ctrl.html.RunScript("window.scrollBy(0,{0});".format(
                    c * step_incr))

        elif key == 107: # k
            self.ctrl.html.RunScript("window.scrollBy(0,-{0});".format(
                    c * step_incr))

        elif key == 104: # h
            self.ctrl.html.RunScript("window.scrollBy({0},0);".format(
                    c * step_incr))

        elif key == 108: # l
            self.ctrl.html.RunScript("window.scrollBy(-{0},0);".format(
                    c * step_incr))

        # If count is specified go to (count)% of page
        elif (key == 71 or key == (103, 103) or key == 37) and self.true_count: # gg or G
            if c > 100: c == 100 # 100% is the max
            self.ctrl.html.RunScript("window.scrollTo(window.scrollX,(document.documentElement.scrollHeight/100*{0}))".format(c))

        # G defaults to 100%
        elif key == 71: # G
            self.ScrollToPageBottom()

        # gg to 0%
        elif key == (103, 103): # gg
            self.ScrollToPageTop()

        elif (key == 48 or key == 94) and self.true_count: # count + $ or ^
            if c > 100: c == 100 # 100% is the max
            self.ctrl.html.RunScript("window.scrollTo((document.documentElement.scrollWidth/100*{0}),window.scrollY)".format(c))

        elif key == 36: # $
            self.ScrollToPageRight()

        elif key == 94: # ^
            self.ScrollToPageLeft()

        elif key == 48: # 0
            self.ScrollToPageLeft()

    def ScrollToPageTop(self):
        self.ctrl.html.RunScript("window.scrollTo(window.scrollX,0);")

    def ScrollToPageBottom(self):
        self.ctrl.html.RunScript("window.scrollTo(window.scrollX,document.body.scrollHeight);")

    def ScrollToPageLeft(self):
        self.ctrl.html.RunScript("window.scrollTo(0,window.scrollY);")

    def ScrollToPageRight(self):
        self.ctrl.html.RunScript("window.scrollTo(0,window.scrollY);")

    def JumpToNextHeading(self):
        self._JumpHeading(True)

    def JumpToPreviousHeading(self):
        self._JumpHeading(False)

    def _JumpHeading(self, forward=True):
        # TODO: optimise

        if forward:
            f = "true" 
        else:
            f = "false"

        self.ctrl.html.RunScript(
        """

var forward = {0}

function getOffset( el ) {{
    var _x = 0;
    var _y = 0;
    while( el && !isNaN( el.offsetLeft ) && !isNaN( el.offsetTop ) ) {{
        _x += el.offsetLeft - el.scrollLeft;
        _y += el.offsetTop - el.scrollTop;
        el = el.offsetParent;
    }}
    return {{ top: _y, left: _x }};
}}


//Get all headings
var headings = new Array();

for( i = 1; i<= 6; i++ ) {{ 
    var tag = 'h' + i;
    var heads = document.getElementsByTagName( tag );
    for ( j = 0; j < heads.length; j++ ) {{ 
        headings.push(heads[j])
    }}
}}

doc_height = document.body.scrollHeight

scroll_height = window.pageYOffset

// We start by scrolling to the end of the document
if (forward) {{
    var to_scroll = doc_height - scroll_height
    }} else {{
    var to_scroll = - scroll_height
    }}


//distances = new Array();

for (var i=0; i<headings.length; i++) {{
    //heading_pos = getOffset(headings[i]).top
    x = getOffset(headings[i]).top
    if (forward) {{
        if (0 < x && x < to_scroll) {{
            to_scroll = x
            }}
        }} else {{
        if (x < 0 && x > to_scroll) {{
            to_scroll = x
            }}
        }}
    }}


window.scrollTo(0, scroll_height + to_scroll)
""".format(f))

    # Numbers
    def SetNumber(self, n):

        # If 0 is first modifier it is a command
        if len(self.key_number_modifier) < 1 and n == 0:
            return False
        self.key_number_modifier.append(n)
        self.key_modifier = []
        self.updateViStatus(True)
        return True

    def clearHints(self):
        """
        Loop through all links and remove any custom formating

        Currently if a background was previously set it will be lost
        """

        self.ctrl.html.RunScript(
        '''
        //START JAVASCRIPT CODE
        var all_links = document.links;

        for (var i=0; i<all_links.length; i++) {
            if (all_links[i].style.backgroundColor == "rgb(253, 255, 71)" || all_links[i].style.backgroundColor == "rgb(0, 255, 0)") {
        all_links[i].style.backgroundColor = "";
            }
        }

        hints = document.getElementsByName("quick-hints");


        var arr = Array.prototype.slice.call( hints )
        

        for (var i=0; i<hints.length; i++) {
            hints[i].innerHTML = "";
        }
        //END JAVASCRIPT CODE
        ''')

    def highlightLinks(self, string="", number=""):
        # TODO: Text based link selection
        self.clearHints()

        # Label hints
        if string is None: string = ""
        if number is None: number = ""


        # Hack to retrieve selected url from title
        self.ctrl.html.RunScript('oldtitle=document.title;')

        # The javascript code to handle link highlighting
        self.ctrl.html.RunScript('''
//START JAVASCRIPT CODE
// double {{'s are needed as we are using string.format() to insert formating
var string = "{0}";
var number = "{1}";

function checkInputString(element) {{
    link_text = element.text.toLowerCase()
    if (string.length == 0) {{
        return true;
    }} else if (link_text.indexOf(string) != -1) {{
        return true;
    }}
    return false;
}}

function checkInput(i, element) {{
    if (number.length == 0) {{
        return true;
    }} else if (i.toString().substr(0, number.length) === number) {{
        return true;
    }}
    return false;
}}


function isElementInViewport(element) {{
    var top = element.offsetTop;
    var left = element.offsetLeft;
    var width = element.offsetWidth;
    var height = element.offsetHeight;

    while(element.offsetParent) {{
        element = element.offsetParent;
        top += element.offsetTop;
        left += element.offsetLeft;
        }}

    return (
        top < (window.pageYOffset + window.innerHeight) &&
        left < (window.pageXOffset + window.innerWidth) &&
        (top + height) > window.pageYOffset &&
        (left + width) > window.pageXOffset
        );
    }}

var all_links = document.links;

var string_test=new Array();
var visible_links=new Array();
var links_selected=new Array();

// First test for input string
for (var i=0; i<all_links.length; i++) {{

    if (isElementInViewport(all_links[i])) {{
        string_test.push(all_links[i]);
        }}

    }}

// Then number
for (var i=0; i<string_test.length; i++) {{
    if (checkInputString(string_test[i])) {{
        visible_links.push(string_test[i]);
        }}
    }}

primary = false;
for (var i=0; i<visible_links.length; i++) {{
    visible_links[i].style.backgroundColor = "";
    if (checkInput(i, visible_links[i])) {{
        links_selected.push(visible_links[i]);
        visible_links[i].innerHTML = "<span name='quick-hints'>["+i+"]</span>" + visible_links[i].innerHTML;

        if (!primary) {{
            visible_links[i].style.backgroundColor = "rgb(0,255,0)";
            primary = true;
        }} else {{
            visible_links[i].style.backgroundColor = "#FDFF47";
        }}

        }}
    }}

hints = document.getElementsByName("quick-hints")

//Format the hints
for (var i=0; i<hints.length; i++) {{
    hints[i].style.backgroundColor = "gray";
    hints[i].style.color = "black";
    hints[i].style.fontWeight = "bold";
    hints[i].style.fontSize = "x-small";
    hints[i].style.zIndex = 1;
    hints[i].style.position = "absolute";
    }}

document.title = links_selected.length;
//END JAVASCRIPT CODE
        '''.format(string.lower(), number))

        link_number = int(self.ctrl.html.GetCurrentTitle())

        self.ctrl.html.RunScript('document.title=links_selected[0];')

        if link_number > 0:
            primary_link = urllib.parse.unquote(
                    self.ctrl.html.GetCurrentTitle())
        else:
            primary_link = None
            
        self.ctrl.html.RunScript('document.title=oldtitle;')

        return link_number, primary_link

    def startFollowHint(self, tabMode=0):
        """
        Called to start hint mode.

        Creates the hint dialog and calls highlightLinks() to format
        the links.

        If not links are present in the viewport the dialog is not opened, 
        if a single is present it is activated automatically
        """

        link_number, link = self.highlightLinks()
        # If only a single link is present we can launch that and finish
        if link_number == 1:
            self.ctrl._activateLink(link, tabMode=tabMode)
            self.clearHints()
            return
        # Or if no links visible on page
        elif link_number < 1:
            self.visualBell()
            return

        sb = self.ctrl.presenter.getMainControl().GetStatusBar()

        rect = sb.GetFieldRect(0)
        if SystemInfo.isOSX():
            # needed on Mac OSX to avoid cropped text
            rect = wx._core.Rect(rect.x, rect.y - 2, rect.width, rect.height + 4)

        rect.SetPosition(sb.ClientToScreen(rect.GetPosition()))

        self.hintDialog = ViHintDialog(self.ctrl, -1, self, rect,
                sb.GetFont(), self.ctrl.presenter.getMainControl(), tabMode, link)
        self.hintDialog.Show()


    def executeFollowHint(self, text):
        """
        Processes input text
        """
        # Seperate string into numerical component
        n = []
        s = []
        for i in text[::-1]:
            if i.isdigit():
                n.append(i)
            else:
                s.append(i)

        s.reverse()
        n.reverse()

        return self.highlightLinks("".join(s), "".join(n))

    def forgetFollowHint(self):
        """
        Called if user just leaves the hint field.
        """
        self.clearHints()
        self.hintDialog = None

    def resetFollowHint(self):
        """
        Called by WebviewSearchDialog before aborting an inc. search.
        Called when search was explicitly aborted by user (with escape key)
        TODO: Make vi keybinding "Ctrl + [" call this as well
        """
        #self.ctrl.html.ClearSelection()
        self.clearHints()
        self.hintDialog = None

    def endFollowHint(self):
        """
        Called if incremental search ended successfully.
        """
        self.clearHints()
        self.hintDialog = None

    def _SearchText(self, text, forward=True, match_case=False, wrap=True, 
            whole_word=False, regex=True, word_start=False, select_text=True, 
                                                    repeat_search=False):
        """
        Run incremental search

        search_text arguments:
            (string to search for, case_sensitive, forward, wrap)

        Focuses selected elements
        """
        # TODO: check functionality in wxPython > 3.0.0.0

        # WEBVIEW_FIND_DEFAULT is needed to focus results
        find_flags = wx.html2.WEBVIEW_FIND_DEFAULT

        # Not implemented
        #if highlight:
        #    find_flags = find_flags | wx.html2.WEBVIEW_FIND_HIGHLIGHT_RESULT

        if match_case:
            find_flags = find_flags | wx.html2.WEBVIEW_FIND_MATCH_CASE

        if wrap:
            find_flags = find_flags | wx.html2.WEBVIEW_FIND_WRAP

        if whole_word:
            find_flags = find_flags | wx.html2.WEBVIEW_FIND_ENTIRE_WORD

        if not forward:
            find_flags = find_flags | wx.html2.WEBVIEW_FIND_BACKWARDS

        if len(text) > 0:
            result = self.ctrl.html.Find(text, flags=find_flags)

            self.ctrl.FocusSelection()

            if not select_text:
                self.ctrl.html.ClearSelection()

            return result
        else:
            self.ctrl.html.ClearSelection()
            
        return False

    def RemoveSelection(self):
        self.ctrl.html.ClearSelection()


# NOTE: duplicated from wikitxtctrl
_CONTEXT_MENU_INTERNAL_JUMP = \
"""
-
Follow Link;CMD_ACTIVATE_THIS
Follow Link New Tab;CMD_ACTIVATE_NEW_TAB_THIS
Follow Link New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
Follow Link New Window;CMD_ACTIVATE_NEW_WINDOW_THIS
"""

_CONTEXT_MENU_INTERNAL_JUMP_DIRECTION = {
    "left" : """
-
Follow Link in pane|Left;CMD_ACTIVATE_THIS_LEFT
Follow Link in pane|Left New Tab;CMD_ACTIVATE_NEW_TAB_THIS_LEFT
Follow Link in pane|Left New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_LEFT
""",
    "right" : """
-
Follow Link in pane|Right;CMD_ACTIVATE_THIS_RIGHT
Follow Link in pane|Right New Tab;CMD_ACTIVATE_NEW_TAB_THIS_RIGHT
Follow Link in pane|Right New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_RIGHT
""",
    "above" : """
-
Follow Link in pane|Above;CMD_ACTIVATE_THIS_ABOVE
Follow Link in pane|Above New Tab;CMD_ACTIVATE_NEW_TAB_THIS_ABOVE
Follow Link in pane|Above New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_ABOVE
""",
    "below" : """
-
Follow Link in pane|Below;CMD_ACTIVATE_THIS_BELOW
Follow Link in pane|Below New Tab;CMD_ACTIVATE_NEW_TAB_THIS_BELOW
Follow Link in pane|Below New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_BELOW
""",
    }
