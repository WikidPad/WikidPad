import io as StringIO
import urllib.request, urllib.parse, urllib.error, os, os.path, traceback

import wx, wx.html


from .WikiExceptions import *
from .wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID, \
        wxKeyFunctionSink

from .MiscEvent import KeyFunctionSink

from .StringOps import utf8Enc, utf8Dec, pathEnc, urlFromPathname, \
        urlQuote, pathnameFromUrl, flexibleUrlUnquote
from .Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE

from . import DocPages
from .TempFileSet import TempFileSet

from . import PluginManager

# Stuff for webkit
import gobject
gobject.threads_init()

import pygtk
pygtk.require('2.0')
import gtk, gtk.gdk

# pywebkitgtk (http://code.google.com/p/pywebkitgtk/)
import webkit

from .ViHelper import ViHintDialog, ViHelper

# used in search
from . import SystemInfo

from html.parser import HTMLParser

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
class WebkitSearchDialog(wx.Frame):
# Base on WikiTxtDialogs.IncrementalSearchDialog
# Would it be better to inherit?
    
    COLOR_YELLOW = wx.Colour(255, 255, 0);
    COLOR_GREEN = wx.Colour(0, 255, 0);
    
    def __init__(self, parent, id, webkitCtrl, rect, font, mainControl, searchInit=None):
        # Frame title is invisible but is helpful for workarounds with
        # third-party tools
        wx.Frame.__init__(self, parent, id, "WikidPad i-search",
                rect.GetPosition(), rect.GetSize(),
                wx.NO_BORDER | wx.FRAME_FLOAT_ON_PARENT)

        self.webkitCtrl = webkitCtrl
        self.mainControl = mainControl
        self.tfInput = wx.TextCtrl(self, GUI_ID.INC_SEARCH_TEXT_FIELD,
                _("Incremental search (ENTER/ESC to finish)"),
                style=wx.TE_PROCESS_ENTER | wx.TE_RICH)

        self.tfInput.SetFont(font)
        self.tfInput.SetBackgroundColour(WebkitSearchDialog.COLOR_YELLOW)
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
        self.webkitCtrl.forgetIncrementalSearch()
        self.Close()

    def OnText(self, evt):
        self.webkitCtrl.searchStr = self.tfInput.GetValue()
        foundPos = self.webkitCtrl.executeIncrementalSearch(self.tfInput.GetValue())

        if foundPos == False:
            # Nothing found
            self.tfInput.SetBackgroundColour(WebkitSearchDialog.COLOR_YELLOW)
        else:
            # Found
            self.tfInput.SetBackgroundColour(WebkitSearchDialog.COLOR_GREEN)

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
            self.webkitCtrl.endIncrementalSearch()
            self.Close()
        elif accP == (wx.ACCEL_NORMAL, wx.WXK_ESCAPE):
            # Esc -> Abort inc. search, go back to start
            self.webkitCtrl.resetIncrementalSearch()
            self.Close()
        elif matchesAccelPair("ContinueSearch", accP):
            foundPos = self.webkitCtrl.executeIncrementalSearch(searchString)
        # do the next search on another ctrl-f
        elif matchesAccelPair("StartIncrementalSearch", accP):
            foundPos = self.webkitCtrl.executeIncrementalSearch(searchString)
        elif accP in ((wx.ACCEL_NORMAL, wx.WXK_DOWN),
                (wx.ACCEL_NORMAL, wx.WXK_PAGEDOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_PAGEDOWN)):
            foundPos = self.webkitCtrl.executeIncrementalSearch(searchString)
        elif matchesAccelPair("BackwardSearch", accP):
            foundPos = self.webkitCtrl.executeIncrementalSearchBackward(searchString)
        elif accP in ((wx.ACCEL_NORMAL, wx.WXK_UP),
                (wx.ACCEL_NORMAL, wx.WXK_PAGEUP),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_UP),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_PAGEUP)):
            foundPos = self.webkitCtrl.executeIncrementalSearchBackward(searchString)
        elif matchesAccelPair("ActivateLink", accP) or \
                matchesAccelPair("ActivateLinkNewTab", accP) or \
                matchesAccelPair("ActivateLink2", accP) or \
                matchesAccelPair("ActivateLinkBackground", accP) or \
                matchesAccelPair("ActivateLinkNewWindow", accP):
            # ActivateLink is normally Ctrl-L
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            # ActivateLink2 is normally Ctrl-Return
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            self.webkitCtrl.endIncrementalSearch()
            self.Close()
            self.webkitCtrl.OnKeyDown(evt)
        # handle the other keys
        else:
            evt.Skip()

        if foundPos == False:
            # Nothing found
            self.tfInput.SetBackgroundColour(WebkitSearchDialog.COLOR_YELLOW)
        else:
            # Found
            self.tfInput.SetBackgroundColour(WebkitSearchDialog.COLOR_GREEN)

        # Else don't change

    if SystemInfo.isOSX():
        # Fix focus handling after close
        def Close(self):
            wx.Frame.Close(self)
            wx.CallAfter(self.webkitCtrl.SetFocus)

    def OnTimerIncSearchClose(self, evt):
        self.webkitCtrl.endIncrementalSearch()  # TODO forgetIncrementalSearch() instead?
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
 
class WikiHtmlViewWK(wx.Panel):
    def __init__(self, presenter, parent, ID):
        # Must be set before calling base class constructor
        self.webkitCtrlLoaded = False

        wx.Panel.__init__(self, parent, ID, style=wx.FRAME_NO_TASKBAR|wx.FRAME_FLOAT_ON_PARENT)

        self.html = WKHtmlWindow(self)
        self.scrolled_window = None
        self.keyProcessWxWindow = KeyProcessWxWindow(self, self)

        self.box = wx.BoxSizer(wx.VERTICAL)
        self.box.Add(self.html, 1, wx.EXPAND)
        self.box.Add(self.keyProcessWxWindow, 0, wx.EXPAND)
        self.SetSizer(self.box)
        
        self.vi = None # Contains ViFunctions instance if vi key handling enabled
        self.keyEventConn = None # GTK key press event connection
        self.focusEventConn = None # GTK focus-in-event event connection

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
        
        self.selectedText = ""
        self.selectedHTML = ""

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
        #wx.EVT_SIZE(self, self.OnSize)

        self.Bind(wx.EVT_MENU, self.OnClipboardCopy, id=GUI_ID.CMD_CLIPBOARD_COPY)
        self.Bind(wx.EVT_MENU, self.OnSelectAll, id=GUI_ID.CMD_SELECT_ALL)
        self.Bind(wx.EVT_MENU, lambda evt: self.addZoom(1), id=GUI_ID.CMD_ZOOM_IN)
        self.Bind(wx.EVT_MENU, lambda evt: self.addZoom(-1), id=GUI_ID.CMD_ZOOM_OUT)
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
        self.realizeIfNeeded()
        evt.Skip()

    def realizeIfNeeded(self):
        if not self.webkitCtrlLoaded and self.html.PizzaMagic():
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

            use_vi_navigation = self.presenter.getConfig().getboolean("main",
                    "html_preview_webkitViKeys", False)

            if use_vi_navigation:

                self.vi = ViFunctions(self) 

                self.keyEventConn = self.html.ctrl.connect("key-press-event",
                        self.__on_key_press_event_vi)

                wx.CallAfter(self.vi._enableMenuShortcuts, False)

            else:
                if self.vi is not None:
                    self.vi._enableMenuShortcuts(True)
                    self.vi = None
                    
                    self.keyEventConn = self.html.ctrl.connect("key-press-event",
                            self.__on_key_press_event)


            self.html.ctrl.connect("scroll_event", self.__on_scroll_event)

            self.html.ctrl.connect("selection_received", 
                    self.__on_selection_received)
            self.html.ctrl.connect("populate-popup", self.__on_populate_popup)

            self.focusEventConn = self.html.ctrl.connect("focus-in-event",
                    self.__on_focus_in_event)
            self.html.ctrl.connect("expose-event", self.__on_expose_event)

            #self.html.ctrl.connect("set-scroll-adjustments", self.__on_scroll_adjustment)

            self.webkitCtrlLoaded = True
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

            self.keyProcessWxWindow.realize()
            self.html.ctrl.grab_focus()


    def __on_button_press_event(self, view, gtkEvent):
        """
        Catch middle button events and pass them on OnMiddleDown
        """
        if gtkEvent.button == 2: # 2 is middle button
            return self.OnMiddleDown(gtkEvent)

    def __on_key_press_event(self, view, gtkEvent):
        key = gtkEvent.keyval

        # Pass modifier keys on
        if key in (65505, 65507, 65513):
            return False

        control_mask = False
        if gtkEvent.state & gtk.gdk.CONTROL_MASK: # Ctrl
            control_mask = True

#         # Search is started on Ctrl + f
#         if control_mask:
#             if key == 102: # f
#                 self.startIncrementalSearch()
#             elif key == 108: # l
#                 self.FollowLinkIfSelected()

        if key == 65307: # Escape
            self.html.ClearSelection()

        # Now send to  self.keyProcessWxWindow  to let wxPython translate
        # and process the key event
        if self.scrolled_window:
            gtkEvent = gtkEvent.copy()
            self.html.ctrl.handler_block(self.focusEventConn)
            try:
                self.keyProcessWxWindow.gtkMyself.grab_focus()
                self.keyProcessWxWindow.gtkMyself.emit("key-press-event", gtkEvent)
                self.html.ctrl.grab_focus()
            finally:
                self.html.ctrl.handler_unblock(self.focusEventConn)
            # Return False if not handled otherwise no default gtk
            # bindings (such as arrow keys) will word
            return False 


    def __on_key_press_event_vi(self, view, gtkEvent):
        """
        Allows navigation with vi like commands (as used by
        pentadactyl/vimperator). Statusbar field zero is used
        to display counts / primary key.

        Counts are limited to 10000. 
        Default count value is 1. 
        Counts must preceed command.

        Some commands have been implemented but don't work as 
        there shortcuts are currently used by wikipad (e.g. 
        Ctrl+o, Ctrl+d, etc...). Reassigning (or removing) the
        shortcuts will allow them to function.


        Current implemented commands:
        NOTE: this list is not upto date

                key(s)  :       action  
        --------------------------------------------------------
        (count) j       : scroll down (same as down arrow)
        (count) k       : scroll up (same as up arrow)
        (count) h       : scroll left (same as left arrow)
        (count) l       : scroll right (same as right arrow)
                
        (count) G       : scroll to (count)% of page
                            defaults to bottom of page
        (count) gg      : scroll to (count)% of page
                            defaults to top of page
        {count} %       : scroll to {count}% of page

                0       : scrolls to absolute left of document
        (count) ^       : scrolls to (count)% of document
                          horizontally. Defaults to 0% (same as
                          0)
        (count) $       : scrolls to (count)% of document
                          horizontally. Defaults to 100%

                gh      : goto home page
                gH      : open home in new forground tab

        (count) gt      : cycles to next tab
                          if (count) goes to (count) next tab
        (count) gT      : cycles to previous tab
                          if (count) goes to (count) previous tab

        (count) H       : go back in history count times
        (count) L       : go forward in history count times

                gu      : display parents dialog (Ctrl + Up)
        (count) gU      : same as gu but if only one parent defined
                          skip the dialog and open it directly. If
                          count keep going until no or more than one
                          parent reached (intervening pages are not
                          recorded in history).

                o       : open wikipage (Ctrl + o)

                /       : start incremental search (Ctrl + f)

                dd      : close current tab (as opposed to single 
                          "d" in pentadactyl)

                Return  : follow link (if selected)

        Ctrl+[ or Esc   : clear selection (and/or count/modifier)
        
                y       : copy selected wikiword to clipboard (not implemented)
                Y       : copy selected text to clipboard

        """
        self.realizeIfNeeded()

        vi = self.vi
        key = gtkEvent.keyval

        # Pass modifier keys on
        if key in (65505, 65507, 65513):
            return False

        if gtkEvent.state & gtk.gdk.CONTROL_MASK: # Ctrl
            key = ("Ctrl", key)

        if key == 65307 or key == ("Ctrl", 91): # Escape
            self.html.ClearSelection()
            vi.FlushBuffers()
        
        m = vi.mode

        if vi._acceptable_keys is None or \
                                "*" not in vi._acceptable_keys:
            if 48 <= key <= 57: # Normal
                if self.vi.SetNumber(key-48):
                    return True
            elif 65456 <= key <= 65465: # Numpad
                if self.vi.SetNumber(key-65456):
                    return True

        # Set count to be used
        vi.SetCount()

        if vi._motion and vi._acceptable_keys is None:
            #vi._acceptable_keys = None
            vi._motion.append(key)

            temp = vi._motion[:-1]
            temp.append("*")
            if tuple(vi._motion) in vi.motion_keys[m]:
                vi.RunKeyChain(tuple(vi.key_inputs), m)
                return True
                #vi._motion = []
            elif tuple(temp) in vi.motion_keys[m]:
                vi._motion[-1] = "*"
                vi._motion_wildcard.append(key)
                vi.RunKeyChain(tuple(vi.key_inputs), m)
                #vi._motion = []
                return True
                
            elif tuple(vi._motion) in vi.motion_key_mods[m]:
                #vi._acceptable_keys = vi.motion_key_mods[m][tuple(vi._motion)]
                return True

            vi.FlushBuffers()
            return True


        if vi._acceptable_keys is not None:
            if key in vi._acceptable_keys:
                vi._acceptable_keys = None
                pass
            elif "*" in vi._acceptable_keys:
                vi._wildcard.append(key)
                vi.key_inputs.append("*")
                vi._acceptable_keys = None
                vi.RunKeyChain(tuple(vi.key_inputs), m)

                return True
            elif "motion" in vi._acceptable_keys:
                vi._acceptable_keys = None
                vi._motion.append(key)
                if (key,) in vi.motion_keys[m]:
                    vi.key_inputs.append("motion")
                    vi.RunKeyChain(tuple(vi.key_inputs), m)
                    return True
                if (key,) in vi.motion_key_mods[m]:
                    vi.key_inputs.append("motion")
                    return True


        vi.key_inputs.append(key)
        vi.updateViStatus()

        key_chain = tuple(vi.key_inputs)

        if vi.RunKeyChain(key_chain, m):
            return True

        vi.FlushBuffers()
        
        # Now send to  self.keyProcessWxWindow  to let wxPython translate
        # and process the key event
        if self.scrolled_window:
#             #
#             # NOTE: The following code causes the webkit ctrl to loose focus
#             #       and I can't work out how to gain it again
#             #
#             gtkEvent = gtkEvent.copy()
#             self.html.ctrl.handler_block(self.focusEventConn)
#             try:
#                 self.keyProcessWxWindow.gtkMyself.grab_focus()
#                 self.keyProcessWxWindow.gtkMyself.emit("key-press-event", gtkEvent)
#                 # Seems to work but doesn't always according to Ross (MB):
#                 self.html.ctrl.grab_focus()
#             finally:
#                 self.html.ctrl.handler_unblock(self.focusEventConn)
            return False

    def FollowLinkIfSelected(self):
        """
        Follows any focused link
        """

        self.html.getWebkitWebView().execute_script('''
            document.title = "None"
            if (document.activeElement.tagName == "A" || document.activeElement.tagName == "a") {
                document.title = document.activeElement.href
            }
            ''')
        link = self.html.getWebkitWebView().get_main_frame().get_title()

        if link != "None":
            self._activateLink(link, tabMode=0)

        #html = self.getSelectedHTML()

        #if len(html) > 0:

        #    parser = ExtractUrlFromHTML()
        #    parser.feed(html)
        #    urls = parser.GetUrls()
        #    if len(urls) > 0:
        #        self._activateLink(urls[0], tabMode=0)


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
            # Yeah this is probably not the best way to do this...
            if str(action.get_reason()) == "<enum WEBKIT_WEB_NAVIGATION_REASON_OTHER of type WebKitWebNavigationReason>":
                return False
 
        # Return True to block navigation, i.e. launching a url
        return self._activateLink(uri, tabMode=0)


    def __on_hovering_over_link(self, view, title, status):
        """
        Called on link mouseover
        """

        if status is None:
            self.on_link = None

            # Prevent problem if we pass over 2 links quickly
            if self.old_status.startswith("Link to page:"):
                self.old_status = ""
            self.updateStatus(self.old_status)
        else:
            self.old_status = self.presenter.getMainControl().statusBar.GetStatusText()
            # flexibleUrlUnquote seems to fail on unicode links
            # unquote shouldn't happen here for self.on_link (MB 2011-04-15)
            self.on_link = status
            self.updateStatus(str(urllib.parse.unquote(status)))


    def __on_selection_received(self, widget, selection_data, data):
        if widget.has_selection():
            if str(selection_data.type) == "STRING":
                self.selectedText = selection_data.get_text()
            else:
                self.selectedText = ""

            if str(selection_data.type) == "text/html":
                self.selectedHTML = selection_data.data
            else:
                self.selectedHTML = ""

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

        internaljumpPrefix = "http://internaljump/"
        link = self.on_link

        for i in menu.get_children():
            # Fix for some webkitgtk?? versions
            try:
                action = i.get_children()[0].get_label()
            except:
                continue

            if action == "_Back":
                menu.remove(i)
            elif action == "_Forward":
                menu.remove(i)
            elif action == "_Stop":
                menu.remove(i)
            elif action == "_Reload":
                menu.remove(i)
            elif action == "_Copy":
                pass
            elif action == "Cop_y Image":
                pass
            elif action == "Copy Link Loc_ation":
                # No point in copying internal links
                if link and link.startswith(internaljumpPrefix):
                    menu.remove(i)

                # Doesn't work as selection get lost if a link is
                # is rightclicked on

                ## Add item to copy selection (doesn't normally exist in
                ## webkit apparently)
                #if self.GetSelectedText() is not None:
                #    copy_menu_item = gtk.ImageMenuItem(gtk.STOCK_COPY)
                #    copy_menu_item.get_children()[0].set_label(
                #            wxToGtkLabel(_('Copy &Selected Text')))
                #    copy_menu_item.connect("activate", self.OnClipboardCopy)
                #    menu.append(copy_menu_item)
            elif action == "Open _Image in New Window":
                menu.remove(i)
            elif action == "Sa_ve Image As":
                menu.remove(i)
            elif action == "_Download Linked File":
                menu.remove(i)
            elif action == "_Open Link":
                if link:
                    if not link.startswith(internaljumpPrefix):
                        i.get_children()[0].set_label(
                                wxToGtkLabel(_("Open Link (External)")))
                    else:
                        i.get_children()[0].set_label(
                                wxToGtkLabel(_("Follow &Link")))
                else:
                    menu.remove(i)

            elif action == "Open Link in New _Window":
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
            elif action == "_Download Linked File":
                menu.remove(i)
            else:
                # Remove unknown menu items
                menu.remove(i)

        print_menu_item = gtk.ImageMenuItem(gtk.STOCK_PRINT)
        print_menu_item.connect("activate", self.OnPrint)
        menu.append(print_menu_item)

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
        
        if self.vi is not None and self.vi.hintDialog is not None:
            self.vi.clearHints()
            self.vi.hintDialog.Close()

        # If ctrl is pressed
        if evt.state & gtk.gdk.CONTROL_MASK:
            if self.presenter.getConfig().getboolean(
                    "main", "mouse_reverseWheelZoom", False):
                scrollUpZoom = -1
            else:
                scrollUpZoom = 1
            
            if evt.direction == gtk.gdk.SCROLL_UP:
                self.addZoom(scrollUpZoom)
            elif evt.direction == gtk.gdk.SCROLL_DOWN:
                self.addZoom(-scrollUpZoom)

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

#    def startIncrementalSearch(self, initSearch=None):
#
#        sb = self.presenter.getMainControl().GetStatusBar()
#
#        # Save scroll position
#        x, y = self.getIntendedViewStart()
#        
#        self.searchStartScrollPosition = x, y
#
#        rect = sb.GetFieldRect(0)
#        if SystemInfo.isOSX():
#            # needed on Mac OSX to avoid cropped text
#            rect = wx._core.Rect(rect.x, rect.y - 2, rect.width, rect.height + 4)
#
#        rect.SetPosition(sb.ClientToScreen(rect.GetPosition()))
#
#        dlg = WebkitSearchDialog(self, -1, self, rect,
#                sb.GetFont(), self.presenter.getMainControl(), initSearch)
#        dlg.Show()
#
#
#    def executeIncrementalSearch(self, text):
#        """
#        Run incremental search
#
#        search_text arguments:
#            (string to search for, case_sensitive, forward, wrap)
#
#        Focuses selected elements
#        """
#
#        if len(text) > 0:
#            result = self.html.getWebkitWebView().search_text(text, False, True, True)
#
#            self.FocusSelection()
#
#            return result
#        else:
#            self.html.ClearSelection()
#            
#        return False
#
#
#    def executeIncrementalSearchBackward(self, text):
#        """
#        Run incremental search backwards
#        """
#        if len(text) > 0:
#            return self.html.getWebkitWebView().search_text(text, False, False, True)
#        else:
#            self.html.ClearSelection()
#
#        return False
#
#    def forgetIncrementalSearch(self):
#        """
#        Called if user just leaves the inc. search field.
#        """
#        pass
#
#    def resetIncrementalSearch(self):
#        """
#        Called by WebkitSearchDialog before aborting an inc. search.
#        Called when search was explicitly aborted by user (with escape key)
#        TODO: Make vi keybinding "Ctrl + [" call this as well
#        """
#        self.html.ClearSelection()
#
#        # To remain consitent with the textctrl incremental search we scroll
#        # back to where the search was started 
#        x, y = self.searchStartScrollPosition
#        self.Scroll(x, y)
#
#    def endIncrementalSearch(self):
#        """
#        Called if incremental search ended successfully.
#        """
#        pass


    def OnOpenLinkInNewTab(self, gtkEvent):
        uri = self.on_link
        self._activateLink(uri, tabMode=2)

        return False
        
    def OnOpenLinkInNewBackgroundTab(self, gtkEvent):
        uri = self.on_link
        self._activateLink(uri, tabMode=3)

        return False

    def OnGoBackInHistory(self, gtkEvent):
        """
        using self.presenter.getMainControl().goBrowserBack()
        results in scrolling issues
        """
        self.presenter.getPageHistory().goInHistory(-1)

    def OnGoForwardInHistory(self, gtkEvent):
        self.presenter.getPageHistory().goInHistory(+1)

    def OnPrint(self, gtkEvent):
        # 2=Export to HTML (Webkit)
        self.presenter.getMainControl().OnShowPrintMainDialog(exportTo=2)

    def updateStatus(self, status):
        if self.visible:

            # Status None is sent on mouse off
            if status is None:
                self.presenter.getMainControl().statusBar.SetStatusText(
                        "", 0)
                return

            internaljumpPrefix = "http://internaljump/"

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

                if wikiWord is not None:
                    status = _("Link to page: %s") % wikiWord

            self.presenter.getMainControl().statusBar.SetStatusText(
                    status, 0)


    # GTK wx mapping
    def GetViewStart(self):
        """
        Bridge gtk to wx's ScrolledWindow.
        May return None if underlying webkit window isn't realized yet.
        """
        if not self.webkitCtrlLoaded:
            return None

        x = self.scrolled_window.get_hadjustment().value
        y = self.scrolled_window.get_vadjustment().value

        return (x, y)

    def Scroll(self, x, y):
        """
        Bridge gtk to wx's ScrolledWindow
        """
        self.scrolled_window.get_hadjustment().set_value(x)
        self.scrolled_window.get_vadjustment().set_value(y)


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
                self.html.LoadUrl(self.currentLoadedUrl + "#" + self.anchor)
                self.lastAnchor = self.anchor
            #else:
            #    lx, ly = wikiPage.getPresentation()[3:5]
            #    self.scrollDeferred(lx, ly)

        self.anchor = None
        self.outOfSync = False

        if self.scrolled_window != None and not self.html.ctrl.is_focus():
            self.SetFocus()
            self.html.ctrl.grab_focus()


        ## _prof.stop()


    def gotoAnchor(self, anchor):
        self.anchor = anchor
        if self.visible:
            self.refresh()
            
    def getSelectedHTML(self):
        """
        Returns the HTML of the currently selected text

        __on_selection_received is called and sets self.selectedHTML
        """
        ret = self.html.getWebkitWebView().selection_convert("PRIMARY", "text/html")
        return self.selectedHTML

    # NOTE: capitalized to maintain consistency with WikiTxtCtrl
    def GetSelectedText(self):
        """
        Returns the currently selected text (plain)

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
    
                self.keyEventConn = self.html.ctrl.connect("key-press-event",
                        self.__on_key_press_event_vi)
            else:
                self.vi = None
                
                self.keyEventConn = self.html.ctrl.connect("key-press-event",
                        self.__on_key_press_event)

        if self.visible:
            self.refresh()

    def onUpdatedWikiPage(self, miscevt):
#         if self.presenter.getConfig().getboolean("main",
#                 "html_preview_reduceUpdateHandling", False):
#             return
        #self.outOfSync = True
        #if self.visible:
        #    self.refresh()
        pass
            
    def onChangedLiveText(self, miscevt):
        self.outOfSync = True


    def scrollDeferred(self, lx, ly):
        if not self.webkitCtrlLoaded or self.deferredScrollPos is not None:
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
        lx, ly = self.getIntendedViewStart()
        self.scrollDeferred(lx, ly)

        evt.Skip()


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

            # TODO: Fix for aliased wikiwords (will try and create a new page)
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

        internaljumpPrefix = "http://internaljump/"

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
            return True

        elif href == (internaljumpPrefix + "event/pageBuilt"):
            # Should we be doing anything here?
            return True

        elif href.startswith("file:"):
            hrefSplit = href.split("#", 1)
            hrefNoFragment = hrefSplit[0]
            normedPath = os.path.normcase(getLongPath(pathnameFromUrl(hrefNoFragment)))
            if len(hrefSplit) == 2 and normedPath in self.normHtpaths:
            #if len(hrefSplit) == 2 and normedPath in self.normHtpath:
                self.gotoAnchor(hrefSplit[1])
                #decision.ignore()
            else:
                # To lauch external urls we need to remove webkits preceeding
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
        self.html.getWebkitWebView().execute_script('''
            var selectionRange = window.getSelection ();

            if (selectionRange.rangeCount > 0) {
                var range = selectionRange.getRangeAt (0);
                container = range.commonAncestorContainer;
            }

            container.parentNode.focus();
            ''')

    def GetScrollAndCaretPosition(self):
        x, y = self.getIntendedViewStart()
        return None, x, y

    def SetScrollAndCaretPosition(self, pos, x, y):
        self.Scroll(x, y)


    def SetFocus(self):
        self.html.ctrl.grab_focus()

    def ViewSource(self, arg=None):
        self.html.getWebkitWebView().set_view_source_mode(
                not self.html.getWebkitWebView().get_view_source_mode())

        self.outOfSync = True
        self.refresh()


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
    def LoadHtmlString(self, html):
        self.ctrl.load_string(html, "text/html", "UTF-8", "file://")

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

    def ClearSelection(self):
        """
        Webkit API is currently missing a way to clear the selection
        directly so we have to use some javascript
        """
        self.ctrl.execute_script('window.getSelection().removeAllRanges()')

#     def Print(self, evt=None):
#         print_op = gtk.PrintOperation()
#         page_setup = gtk.PageSetup()
#         # TODO: Dialog to change margins
#         page_setup.set_top_margin(20, gtk.UNIT_MM)
#         page_setup.set_left_margin(20, gtk.UNIT_MM)
#         page_setup.set_right_margin(20, gtk.UNIT_MM)
#         page_setup.set_bottom_margin(20, gtk.UNIT_MM)
#         print_op.set_default_page_setup(page_setup)
#         self.ctrl.get_main_frame().print_full(print_op, gtk.PRINT_OPERATION_ACTION_PRINT_DIALOG)


class ViFunctions(ViHelper):
    def __init__(self, view):
        ViHelper.__init__(self, view)

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

("Ctrl", k["["]) : (0, (self.ctrl.html.ClearSelection, None), 0, 0), # Ctrl + [
("Ctrl", k["d"]) : (0, (self.HalfPageJumpDown, None), 0, 0), # Ctrl + d
("Ctrl", k["y"]) : (0, (self.HalfPageJumpUp, None), 0, 0), # Ctrl + u
("Ctrl", k["l"]) : (0, (self.ctrl.FollowLinkIfSelected, None), 0, 0), # Ctrl + l

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

(k["g"], k["s"])  : (0, (self.SwitchEditorPreview, None), 0, 0), # gs
(k["g"], k["."])  : (0, (self.SwitchEditorPreview, "textedit"), 0, 0), # ge
(k["g"], k["p"])  : (0, (self.SwitchEditorPreview, "preview"), 0, 0), # gp

# F3 and F4 switch directly to editor / preview mode
(65472,)     : (0, (self.SwitchEditorPreview, "textedit"), 0, 0), # F3
(65473,)     : (0, (self.SwitchEditorPreview, "preview"), 0, 0), # F4
# F5 refreshes the current page
(65475,)     : (0, (self.SwitchEditorPreview, "preview"), 0, 0), # F5
    
        }
        }

        self.LoadPlugins("preview_wk")

        # Generate possible key modifiers
        self.key_mods = self.GenerateKeyModifiers(self.keys)
        self.motion_keys = self.GenerateMotionKeys(self.keys)
        self.motion_key_mods = self.GenerateKeyModifiers(self.motion_keys)

        # Used for rewriting menu shortcuts
        self.GenerateKeyAccelerators(self.keys)

    # Vi Helper functions
    def SetMode(self, mode):
        """
        Dummy function for now

        May be used in the future
        """

    def RefreshPage(self):
        self.ctrl.refresh()

    # Document navigation
    def HalfPageJumpDown(self):
        adj = self.ctrl.scrolled_window.get_vadjustment()
        y = adj.get_value()

        jump = self.count*adj.get_page_size()/2

        if y+jump < adj.get_upper():
            adj.set_value(y+jump)
        else:
            adj.set_value(adj.get_upper()-adj.get_page_size())
            
    def HalfPageJumpUp(self):
        adj = self.ctrl.scrolled_window.get_vadjustment()
        y = adj.get_value()

        jump = self.count*adj.get_page_size()/2

        if y-jump > adj.get_lower():
            adj.set_value(y-jump)
        else:
            adj.set_value(adj.get_lower())

    def DocumentNavigation(self, key):
        """
        function to handle most navigation commonds

        currently handles: j, k, h, l, G, gg, 0, $
        """
        step_incr = self.ctrl.scrolled_window.get_vadjustment().get_step_increment()
        page_incr = self.ctrl.scrolled_window.get_vadjustment().get_page_increment()

        vadj = self.ctrl.scrolled_window.get_vadjustment()
        hadj = self.ctrl.scrolled_window.get_hadjustment()

        y = vadj.get_value()
        x = hadj.get_value()

        y_upper = vadj.get_upper()
        x_upper = hadj.get_upper()

        y_lower = vadj.get_lower()
        x_lower = hadj.get_lower()

        y_page_size = vadj.get_page_size()
        x_page_size = hadj.get_page_size()

        c = self.count


        if key == 106: # j
            if y+c*step_incr < y_upper-y_page_size:   mod = y+c*step_incr
            else:                                     mod = y_upper-y_page_size
            vadj.set_value(mod)

        elif key == 107: # k
            if y-c*step_incr > y_lower:               mod = y-c*step_incr
            else:                                     mod = y_lower
            vadj.set_value(mod)

        elif key == 104: # h
            if x-c*step_incr > x_lower:               mod = x-c*step_incr
            else:                                     mod = x_lower
            hadj.set_value(mod)

        elif key == 108: # l
            if x+c*step_incr < x_upper-x_page_size:   mod = x+c*step_incr
            else:                                     mod = x_upper-x_page_size
            hadj.set_value(mod)

        # If count is specified go to (count)% of page
        elif (key == 71 or key == (103, 103) or key == 37) and self.true_count: # gg or G
            if c > 100: c == 100 # 100% is the max
            vadj.set_value(int((y_upper-y_page_size)/100*c))

        # G defaults to 100%
        elif key == 71: # G
            vadj.set_value(y_upper-y_page_size)

        # gg to 0%
        elif key == (103, 103): # gg
            vadj.set_value(y_lower)

        elif (key == 48 or key == 94) and self.true_count: # count + $ or ^
            if c > 100: c == 100 # 100% is the max
            hadj.set_value(int((x_upper-x_page_size)/100*c))

        elif key == 36: # $
            hadj.set_value(x_upper-x_page_size)

        elif key == 94: # ^
            hadj.set_value(x_lower)

        elif key == 48: # 0
            hadj.set_value(x_lower)

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

        self.ctrl.html.getWebkitWebView().execute_script(
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

        self.ctrl.html.getWebkitWebView().execute_script(
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
        self.ctrl.html.getWebkitWebView().execute_script('oldtitle=document.title;')

        # The javascript code to handle link highlighting
        self.ctrl.html.getWebkitWebView().execute_script('''
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

        link_number = int(self.ctrl.html.getWebkitWebView(). \
                                get_main_frame().get_title())

        self.ctrl.html.getWebkitWebView(). \
                    execute_script('document.title=links_selected[0];')

        if link_number > 0:
            primary_link = self.ctrl.html.getWebkitWebView().get_main_frame().get_title()
        else:
            primary_link = None
            
        self.ctrl.html.getWebkitWebView().execute_script('document.title=oldtitle;')

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
        Called by WebkitSearchDialog before aborting an inc. search.
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
        if len(text) > 0:
            result = self.ctrl.html.getWebkitWebView().search_text(text, case_sensitive=match_case, forward=forward, wrap=wrap)

            self.ctrl.FocusSelection()

            if not select_text:
                self.ctrl.html.ClearSelection()

            return result
        else:
            self.ctrl.html.ClearSelection()
            
        return False

    def RemoveSelection(self):
        self.ctrl.html.ClearSelection()


class KeyProcessWxWindow(wx.Panel):
    def __init__(self, parent, htmlView, id=-1):
        wx.Panel.__init__(self, parent, id, size=(0,0))
        
        self.htmlView = htmlView

        self.Show()
        
        self.realized = False

    def realize(self):
        if self.realized:
            return

        whdl = self.GetHandle()

        # break if window not shown
        if whdl == 0:
            return False

        window = gtk.gdk.window_lookup(whdl)

        # We must keep a reference of "pizza". Otherwise we get a crash.
        self.pizza = pizza = window.get_user_data()

        self.gtkMyself = self.pizza   # .get_children()[0]
        
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        
        self.realized = True


    def OnKeyDown(self, evt):
#         evt.Skip()
        key = evt.GetKeyCode()

        accP = getAccelPairFromKeyDown(evt)
        matchesAccelPair = self.htmlView.presenter.getMainControl().keyBindings.\
                matchesAccelPair

        if matchesAccelPair("ActivateLink", accP):
            # ActivateLink is normally Ctrl-L
            # There is also a shortcut for it. This can only happen
            # if OnKeyDown is called indirectly
            # from IncrementalSearchDialog.OnKeyDownInput
            self.htmlView.FollowLinkIfSelected()

        elif matchesAccelPair("ActivateLink2", accP):
            # ActivateLink2 is normally Ctrl-Return
            self.htmlView.FollowLinkIfSelected()

#         elif matchesAccelPair("ActivateLinkBackground", accP):
#             # ActivateLink2 is normally Ctrl-Return
#             self.htmlView.activateLink(tabMode=3)
# 
#         elif matchesAccelPair("ContinueSearch", accP):
#             # ContinueSearch is normally F3
#             self.htmlView.startIncrementalSearch()  # self.htmlView.searchStr)
# #             evt.Skip()

        elif matchesAccelPair("StartIncrementalSearch", accP) or \
                matchesAccelPair("ContinueSearch", accP):
            # StartIncrementalSearch is normally Ctrl-F
            # ContinueSearch is normally F3
            # Start incremental search
            # First get selected text and prepare it as default value
            text = self.htmlView.GetSelectedText()
            text = text.split("\n", 1)[0]
#             text = re.escape(text[:30])
            text = text[:30]
            self.htmlView.startIncrementalSearch(text)
        else:
            evt.Skip()

