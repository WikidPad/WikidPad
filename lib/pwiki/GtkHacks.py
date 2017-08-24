"""
This is a specific file for handling some operations not provided
by the OS-independent wxPython library.
"""

import ctypes, os, os.path, traceback
from ctypes import c_int, c_uint, c_long, c_ulong, c_ushort, c_char, c_char_p, \
        c_wchar_p, c_byte, byref, create_string_buffer, create_unicode_buffer, \
        c_void_p, string_at, sizeof   # , WindowsError

import wx

# Some development infos regarding the gtk2/wxGTK3 issue /freeze) on newer systems:
#
# First hints:  http://sourceforge.net/p/taskcoach/bugs/1593/
#                   #1593 Taskcoach won't launch with wxPython GTK3 and pygtk2 installed
#               http://askubuntu.com/questions/215068/gtk-problem-in-ubuntu-12-04
# And then:     http://www.pygtk.org/
#                   "Note: New users are encouraged to use GTK+3 through the PyGObject bindings
#                          instead of using PyGTK with GTK+2. Windows users may still want to keep
#                          using PyGTK until more convenient installers are published."
# The new:      https://wiki.gnome.org/action/show/Projects/PyGObject
#               http://python-gtk-3-tutorial.readthedocs.org/en/latest/
#               http://lazka.github.io/pgi-docs/   Python GObject Introspection API Reference
#
# Porting info: https://wiki.gnome.org/Projects/PyGObject/IntrospectionPorting
#
# Clipboard example providing the solution used below:
#               https://git.gnome.org/browse/pygobject/tree/demos/gtk-demo/demos/clipboard.py
#
#------------
#
# Fedora packaging:
#
# On Fedora 21 (a bit shortened list):
#
#    # dnf list installed *pygo* python*gob* pygtk* wx* gtk* python
#
#      gtk2.x86_64                     2.24.28-1.fc21
#      gtk2-devel.x86_64               2.24.28-1.fc21
#      gtk3.x86_64                     3.14.15-1.fc21
#      gtkhtml3.x86_64                 4.8.5-1.fc21
#      pygobject2.x86_64               2.28.6-13.fc21
#      pygobject3.x86_64               3.14.0-1.fc21
#      pygobject3-base.x86_64          3.14.0-1.fc21
#      pygtk2.x86_64                   2.24.0-11.fc21
#      pygtk2-libglade.x86_64          2.24.0-11.fc21
#      python.x86_64                   2.7.8-15.fc21
#      python3-gobject.x86_64          3.14.0-1.fc21
#      wxBase.x86_64                   2.8.12-13.fc21
#      wxBase3.x86_64                  3.0.2-9.fc21
#      wxGTK.x86_64                    2.8.12-13.fc21
#      wxGTK-gl.x86_64                 2.8.12-13.fc21
#      wxGTK-media.x86_64              2.8.12-13.fc21
#      wxGTK3.x86_64                   3.0.2-9.fc21
#      wxPython.x86_64                 2.8.12.0-8.fc21
#
# On Fedora 23:
#
#    # dnf list installed *pygo* python*gob* pygtk* wx* gtk* python
#
#      gtk-update-icon-cache.x86_64    3.18.2-1.fc23
#      gtk2.x86_64                     2.24.28-2.fc23
#      gtk3.x86_64                     3.18.2-1.fc23
#      gtkmm24.x86_64                  2.24.4-7.fc23
#      pygobject2.x86_64               2.28.6-14.fc23
#      pygtk2.x86_64                   2.24.0-12.fc23
#      python.x86_64                   2.7.10-8.fc23
#      python-gobject.x86_64           3.18.0-2.fc23
#      python-gobject-base.x86_64      3.18.0-2.fc23
#      python3-gobject.x86_64          3.18.0-2.fc23
#      python3-gobject-base.x86_64     3.18.0-2.fc23
#      wxBase3.x86_64                  3.0.2-11.fc23
#      wxGTK3.x86_64                   3.0.2-11.fc23
#      wxGTK3-gl.x86_64                3.0.2-11.fc23
#      wxGTK3-media.x86_64             3.0.2-11.fc23
#      wxPython.x86_64                 3.0.2.0-7.fc23
#------------


if wx.version() < "2.9" or "gtk2" in wx.version():
    import gtk
else:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk

from .wxHelper import getTextFromClipboard

from .StringOps import strftimeUB, pathEnc, mbcsEnc, mbcsDec   # unescapeWithRe
from . import DocPages


if wx.version() < "2.9":
    pass
    #import gobject
    #gobject.threads_init()    # TODO: is it really needed? Doesn't seem so.

# gnome.program_init('glipper', '1.0', properties= { gnome.PARAM_APP_DATADIR : glipper.DATA_DIR })


class BaseFakeInterceptor:
    def __init__(self):
        pass

    def addInterceptCollection(self, interceptCollection):
        """
        Called automatically if interceptor is added to an
        intercept collection
        """
        pass

    def removeInterceptCollection(self, interceptCollection):
        """
        Called automatically if interceptor is removed from an
        intercept collection.
        """
        pass


    def startBeforeIntercept(self, interceptCollection):
        """
        Called for each interceptor of a collection before the actual
        intercept happens. If one interceptor returns anything but True,
        interception doesn't happen.
        """
        return True

    def startAfterIntercept(self, interceptCollection):
        """
        Called for each interceptor of a collection after the actual
        intercept happened.
        """
        pass


    def stopBeforeUnintercept(self, interceptCollection):
        """
        Called for each interceptor of a collection before the actual
        unintercept happens. If one interceptor returns anything but True,
        uninterception doesn't happen (this may be dangerous).
        """
        return True

    def stopAfterUnintercept(self, interceptCollection):
        """
        Called for each interceptor of a collection after the actual
        unintercept happened.
        """
        pass


#     def interceptWinProc(self, interceptCollection, params):
#         """
#         Called for each Windows message to the intercepted window. This is
#         the ANSI-style method, wide-char is not supported.
#
#         params -- WinProcParams object containing parameters the function can
#                 modify and a returnValue which can be set to prevent
#                 from calling interceptWinProc functions
#         """
#         pass



class FakeInterceptCollection:
    """
    Class holding a list of interceptor objects which can do different
    operations.
    """
    def __init__(self, interceptors=None):
        self.interceptors = []

        self.hWnd = None  # Stored, but unused

        if interceptors is not None:
            for icept in interceptors:
                self.addInterceptor(icept)


    # TODO Test if already started!
    def addInterceptor(self, icept):
        if icept in self.interceptors:
            return

        icept.addInterceptCollection(self)
        self.interceptors.append(icept)


    def clear(self):
        self.stop()

        for icept in self.interceptors:
            icept.removeInterceptCollection(self)

        self.interceptors = []


    def close(self):
        self.clear()


    def start(self, callingWindow):
        if self.isIntercepting():
            return False

        for icept in self.interceptors:
            if not icept.startBeforeIntercept(self):
                return False

        self.intercept(callingWindow)

        for icept in self.interceptors:
            try:
                icept.startAfterIntercept(self)
            except:
                traceback.print_exc()

        return True


    def stop(self):
        if not self.isIntercepting():
            return False

        for icept in self.interceptors:
            try:
                if not icept.stopBeforeUnintercept(self):
                    return False
            except:
                traceback.print_exc()

        self.unintercept()

        for icept in self.interceptors:
            try:
                icept.stopAfterUnintercept(self)
            except:
                traceback.print_exc()



    def intercept(self, callingWindow):
        if self.isIntercepting():
            return

        self.hWnd = 1

#         # The stub must be saved because ctypes doesn't hold an own reference
#         # to it.
#         self.ctWinProcStub = WindowProcType(self.winProc)
#         self.oldWndProc = SetWindowLong(c_int(self.hWnd), c_int(GWL_WNDPROC),
#                 self.ctWinProcStub)


    def unintercept(self):
        if not self.isIntercepting():
            return

#         SetWindowLong(c_int(self.hWnd), c_int(GWL_WNDPROC),
#                 c_int(self.oldWndProc))
#
#         self.oldWinProc = None
#         self.ctWinProcStub = None
        self.hWnd = None


    def isIntercepting(self):
        return self.hWnd is not None


#     def _lastWinProc(self, params):
#         """
#         This default function reacts only on a WM_DESTROY message and
#         stops interception. All messages are sent to the original WinProc
#         """
#
#         if params.uMsg == WM_DESTROY and params.hWnd == self.hWnd:
#             self.stop()
#
#         params.returnValue = CallWindowProc(c_int(self.oldWndProc),
#                 c_int(params.hWnd), c_uint(params.uMsg),
#                 c_uint(params.wParam), c_ulong(params.lParam))


#     def winProc(self, hWnd, uMsg, wParam, lParam):
#         params = self.winParams
#         params.set(hWnd, uMsg, wParam, lParam)
#
#         for icept in self.interceptors:
#             try:
#                 icept.interceptWinProc(self, params)
#             except:
#                 traceback.print_exc()
#
#             if params.returnValue is not None:
#                 return params.returnValue
#
#         self._lastWinProc(params)
#         return params.returnValue





class ClipboardCatchFakeIceptor(BaseFakeInterceptor):
    """
    Interceptor module to catch clipboard changes.
    """
    MODE_OFF = 0
    MODE_AT_PAGE = 1
    MODE_AT_CURSOR = 2

    def __init__(self, mainControl):
        BaseFakeInterceptor.__init__(self)

#         self.hWnd = None
        self.gtkDefClipboard = None
        self.gtkConnHandle = None

        self.ignoreCCMessage = 0

        self.mainControl = mainControl
        self.wikiPage = None
        self.mode = ClipboardCatchFakeIceptor.MODE_OFF
        self.lastText = None


    def getMode(self):
        return self.mode

    def _cbViewerChainIn(self):
        """
        Hook into clipboard.
        """
        if self.gtkDefClipboard is not None:
            return


        if wx.version() < "2.9":
            self.gtkDefClipboard = gtk.clipboard_get()
        else:
            self.gtkDefClipboard = Gtk.Clipboard.get(Gdk.atom_intern('CLIPBOARD', True))

        self.gtkConnHandle = self.gtkDefClipboard.connect("owner-change",
                lambda clp, evt: self.handleClipboardChange())

#         # SetClipboardViewer sends automatically an initial clipboard changed (CC)
#         # message which should be ignored
#         self.ignoreNextCCMessage = True


    def _cbViewerChainOut(self):
        """
        Remove hook to clipboard.
        """
        if self.gtkDefClipboard is None:
            return

        self.gtkDefClipboard.disconnect(self.gtkConnHandle)
        self.gtkConnHandle = None
        self.gtkDefClipboard = None


    def catchAtPage(self, wikiPage):
        """
        wikiPage -- page to write clipboard content to
        """
        if not isinstance(wikiPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            self.mainControl.displayErrorMessage(
                    _("Only a real wiki page can be a clipboard catcher"))
            return

        self.lastText = None
        self.wikiPage = wikiPage
        self.mode = ClipboardCatchFakeIceptor.MODE_AT_PAGE
        self._cbViewerChainIn()


    def catchAtCursor(self):
        """
        Write clipboard content to cursor position
        """
        self.lastText = None
        self.mode = ClipboardCatchFakeIceptor.MODE_AT_CURSOR
        self._cbViewerChainIn()


    def catchOff(self):
        self.mode = ClipboardCatchFakeIceptor.MODE_OFF
        self._cbViewerChainOut()


    def informCopyInWikidPadStart(self, text=None):
        """
        Informs the interceptor, that currently something is copied in the
        editor in WikidPad itself. If mode is MODE_AT_CURSOR this
        clipboard content is then not copied back into the editor.
        """
        if self.mode == ClipboardCatchFakeIceptor.MODE_AT_CURSOR:
            self.ignoreCCMessage = 1
            if self.mainControl.getConfig().getboolean("main",
                    "clipboardCatcher_filterDouble", True):
                self.lastText = text
            else:
                self.lastText = None


    def informCopyInWikidPadStop(self):
        pass
#         print "--informCopyInWikidPadStop1"
#         self.ignoreCCMessage = 0


    def startAfterIntercept(self, interceptCollection):
        """
        Called for each interceptor of a collection after the actual
        intercept happened.
        """
#         self.hWnd = interceptCollection.getHWnd()


    def stopAfterUnintercept(self, interceptCollection):
        """
        Called for each interceptor of a collection after the actual
        unintercept happened.
        """
        self._cbViewerChainOut()
#         self.hWnd = None


#     def interceptWinProc(self, interceptCollection, params):
#         """
#         Called for each Windows message to the intercepted window. This is
#         the ANSI-style method, wide-char is not supported.
#
#         params -- WinProcParams object containing parameters the function can
#                 modify and a returnValue which can be set to prevent
#                 from calling interceptWinProc functions
#         """
#         if params.uMsg == WM_CHANGECBCHAIN:
#             if self.nextWnd == params.wParam:
#                 # repair the chain
#                 self.nextWnd = params.lParam
#
#             if self.nextWnd:  # Neither None nor 0
#                 # pass the message to the next window in chain
#                 SendMessage(c_int(self.nextWnd), c_int(params.uMsg),
#                         c_uint(params.wParam), c_ulong(params.lParam))
#
#         elif params.uMsg == WM_DRAWCLIPBOARD:
#             if self.ignoreNextCCMessage:
#                 self.ignoreNextCCMessage = False
#             else:
#                 self.handleClipboardChange()
#
#             if self.nextWnd:  # Neither None nor 0
#                 # pass the message to the next window in chain
#                 SendMessage(c_int(self.nextWnd), c_int(params.uMsg),
#                         c_uint(params.wParam), c_ulong(params.lParam))



    def notifyUserOnClipboardChange(self):
        config = self.mainControl.getConfig()
        notifMode = config.getint("main", "clipboardCatcher_userNotification", 0)
        if notifMode == 1:
            soundPath = config.get("main", "clipboardCatcher_soundFile", "")
            if soundPath == "":
                wx.Bell()
            else:
                try:
                    sound = wx.Sound(soundPath)
                    if sound.IsOk():
                        sound.Play(wx.SOUND_ASYNC)
                        self.clipCatchNotifySound = sound  # save a reference
                                # (This shouldn't be needed, but there seems to be a bug...)
                    else:
                        wx.Bell()
                except NotImplementedError as v:
                    wx.Bell()


    def handleClipboardChange(self):
        if self.ignoreCCMessage > 0:
            self.ignoreCCMessage -= 1
            return

        text = getTextFromClipboard()
        if text is None or len(text) == 0:
            return
        try:
            prefix = strftimeUB(self.mainControl.getConfig().get(
                    "main", "clipboardCatcher_prefix", r""))
        except:
            traceback.print_exc()
            prefix = ""   # TODO Error message?

        try:
            suffix = strftimeUB(self.mainControl.getConfig().get(
                    "main", "clipboardCatcher_suffix", r"\n"))
        except:
            traceback.print_exc()
            suffix = "\n"   # TODO Error message?

        if self.mode == ClipboardCatchFakeIceptor.MODE_OFF:
            return

        if self.mainControl.getConfig().getboolean("main",
                "clipboardCatcher_filterDouble", True) and self.lastText == text:
            # Same text shall be inserted again
            return

        if self.mode == ClipboardCatchFakeIceptor.MODE_AT_PAGE:
            if self.wikiPage is None:
                return
            self.wikiPage.appendLiveText(prefix + text + suffix)
            self.notifyUserOnClipboardChange()

        elif self.mode == ClipboardCatchFakeIceptor.MODE_AT_CURSOR:
            self.mainControl.getActiveEditor().ReplaceSelection(prefix + text + suffix)
            self.notifyUserOnClipboardChange()

        self.lastText = text


    def getWikiWord(self):
        if self.wikiPage is None:
            return None
        else:
            return self.wikiPage.getWikiWord()


