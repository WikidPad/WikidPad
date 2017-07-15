

import os, os.path, traceback, sys, re, importlib

from wx.xrc import XRCCTRL, XRCID, XmlResource, XmlSubclassFactory
import wx

from .WikiExceptions import *

from .Utilities import AttrContainer
from .MiscEvent import KeyFunctionSink
from . import SystemInfo, StringOps


# try:
#     import gtk, gobject
# except:
#     gtk = None
#     gobject = None


def _unescapeWithRe(text):
    """
    Unescape things like \n or \f. Throws exception if unescaping fails
    """
    return re.sub("", text, "", 1)



class wxSourceId:
    """
    Can be used either as id number or as source in wx.EvtHandler.Bind() calls
    """
    __slots__ = ("_value",)

    def __init__(self, value):
        self._value = value
    
    def __int__(self):
        return self._value
    
    GetId = __int__


class wxIdPool:
    def __init__(self):
        self._xrcPoolcache = {}
        self._poolmap = {}

    def __getattr__(self, name):
        """Returns a new wx-Id for each new string <name>.
 
        If the same name is given twice, the same id is returned.
        
        If the name is in the XRC id-table its value there will be returned
        """
        try:
            if name not in self._xrcPoolcache:
                self._xrcPoolcache[name] = wxSourceId(XRCID(name))
                
            return self._xrcPoolcache[name]
        except:
            try:
                return self._poolmap[name]
            except KeyError:
                id = wxSourceId(wx.NewId())
                self._poolmap[name] = id
                return id
                
    __getitem__ = __getattr__



GUI_ID = wxIdPool()
GUI_ID.__doc__="All purpose standard Gui-Id-Pool"



class _XrcControlsAssociation:
    """
    As Phoenix doesn't anymore return the same Python object when
    calling XRCCTRL or FindWindow multiple times searching  for the same
    C++ object associated data must be stored separately.

    That's what this class is for. It shouldn't be used directly but it
    is handled by XrcControls if needed.
    """
    
    def __init__(self, xrcCtrls):
        self.__xrcCtrls = xrcCtrls
        self.__idDataMap = {}
    
    def _get(self, name):
        if not name in self.__idDataMap:
            self.__idDataMap[name] = AttrContainer()
        
        return self.__idDataMap[name]

    
    def __getattr__(self, name):
        return self._get(name)


    def __getitem__(self, name):
        return self._get(name)
        



class XrcControls:
    """
    Convenience wrapper for XRCCTRL
    """
    def __init__(self, basepanel):
        self.__basepanel = basepanel
        
        self.__idAssociation = None
        

    def _get(self, name):
#         print ("--XrcControls.__getattr__1", repr((name, self.__basepanel)))
#         if name in self.__cache:
#             return self.__cache[name]

#         result = XRCCTRL(self.__basepanel, name)
#         if result is None:
#             raise InternalError("XML-ID '%s' not found in %s" %
#                     (name, repr(self.__basepanel)))
            
        wid = XRCID(name)    

        result = wx.FindWindowById(wid, self.__basepanel)

        if result is None:
            raise InternalError("XML-ID '%s' not found in %s" %
                    (name, repr(self.__basepanel)))
        
        return result


    def __getattr__(self, name):
        return self._get(name)


    def __getitem__(self, name):
        return self._get(name)


    @property
    def _assoc(self):
        if self.__idAssociation is None:
            self.__idAssociation = _XrcControlsAssociation(self)
        
        return self.__idAssociation


    def _byId(self, wid):
        return self.__basepanel.FindWindow(wid) # self.__basepanel.FindWindowById(wid)




class SimpleXmlSubclassFactory(XmlSubclassFactory):
    def Create(self, className):
        modName, plainClassName = className.rsplit(".", 1)
        module = importlib.import_module(modName)
        
        return getattr(module, plainClassName)()




class WindowUpdateLocker:
    """
    Python translation of wxWindowUpdateLocker.
    Usage:
    with WindowUpdateLocker(window):
        do this, do that...
    thawn again
    """
    def __init__(self, window):
        self.window = window
    
    def __enter__(self):
        if self.window is not None:
            self.window.Freeze()
        
        return self.window
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.window is not None:
            self.window.Thaw()



class _TopLevelLockerClass:
    """
    Provides context in which all top level windows are locked
    Usage:
    with TopLevelLocker:
        do this, do that...
    
    """
    def __enter__(self):
        wx.EnableTopLevelWindows(False)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        wx.EnableTopLevelWindows(True)

# The one and only instance
TopLevelLocker = _TopLevelLockerClass()


class IdRecycler:
    """
    You can get ids from it, associate them with a value, later clear the
    associations and reuse ids
    """
    def __init__(self):
        self.unusedSet = set()
        self.assoc = {}
    
    def assocGetId(self, value):
        """
        Get a new or unused id and associate it with value. Returns the id.
        """
        if len(self.unusedSet) == 0:
            id = wx.NewId()
        else:
            id = self.unusedSet.pop()
        
        self.assoc[id] = value
        return id
    
    def assocGetIdAndReused(self, value):
        """
        Get a new or unused id and associate it with value.
        Returns tuple (id, reused) where reused is True iff id is not new.
        """
        if len(self.unusedSet) == 0:
            id = wx.NewId()
            reused = False
        else:
            id = self.unusedSet.pop()
            reused = True

        self.assoc[id] = value
        return (id, reused)


    def get(self, id, default=None):
        """
        Get value for an id as for a dict object.
        """
        return self.assoc.get(id, default)
        
    def __getitem__(self, id):
        """
        Get value for an id as for a dict object.
        """
        return self.assoc[id]

    def iteritems(self):
        return iter(list(self.assoc.items()))

    def clearAssoc(self):
        """
        Clear the associations, but store all ids for later reuse.
        """
        self.unusedSet.update(iter(self.assoc.keys()))
        self.assoc.clear()



def getTextFromClipboard():
    """
    Retrieve text or unicode text from clipboard
    """
    from .StringOps import lineendToInternal, mbcsDec

    cb = wx.TheClipboard
    cb.Open()
    try:
        dataob = textToDataObject()
        if cb.GetData(dataob):
            if dataob.GetTextLength() > 0:
                return lineendToInternal(dataob.GetText())
            else:
                return ""
        return None
    finally:
        cb.Close()


if SystemInfo.isWindows():
    # Windows variant
    def getHasHtmlOnClipboard():
        """
        Returns tuple (hasHtml, hasUrl) where both items can be boolean
        or None (meaning unknown) to inform if HTML data and the source URL
        respectively are available on clipboard
        """
        cb = wx.TheClipboard
        df = wx.DataFormat("HTML Format")
        avail = cb.IsSupported(df)
#         avail = wx.IsClipboardFormatAvailable(df.GetType())
        
        return (avail, avail)


    def getHtmlFromClipboard():
        """
        Retrieve HTML source from clipboard. Returns a tuple (source, URL)
        where source is the HTML sourcecode and URL is the URL where it came
        from. Both or one of the items may be None.
        """
        from .StringOps import lineendToInternal, mbcsDec
    
        cb = wx.TheClipboard
        cb.Open()
        try:
            df = wx.DataFormat("HTML Format")
            dataob = wx.CustomDataObject(df)
    
            if cb.GetData(dataob):
                if dataob.GetSize() > 0:
                    raw = dataob.GetData()
                    
                    # Windows HTML clipboard format contains a header with additional
                    # information
                    start = None
                    end = None
                    sourceUrl = None
                    
                    canBreak = lambda : start is not None and end is not None \
                            and sourceUrl is not None

                    pos = 0
                    try:
                        for line in raw.split("\r\n"):
                            if line.startswith("StartFragment:"):
                                start = int(line[14:])
                                if canBreak():
                                    break
                            elif line.startswith("EndFragment:"):
                                end = int(line[14:])
                                if canBreak():
                                    break
                            elif line.startswith("SourceURL:"):
                                sourceUrl = line[10:]
                                if canBreak():
                                    break
                            pos += len(line) + 2
                            if start is not None and pos >= start:
                                break

                    except ValueError:
                        return (None, None)
                                
                    if start is None or end is None:
                        return (None, None)
                    
                    return (lineendToInternal(dataob.GetData()[start:end]).decode(
                            "utf-8", "replace"), sourceUrl)

            return (None, None)
        finally:
            cb.Close()

# elif gtk is not None and gobject is not None:
#     # GTK variant
#     def getHtmlFromClipboard():
#         """
#         Retrieve HTML source from clipboard. Returns a tuple (source, URL)
#         where source is the HTML sourcecode and URL is the URL where it came
#         from. Both or one of the items may be None. For GTK second item is always
#         None.
#         """
#         clipboard = gtk.Clipboard()
#         targets = clipboard.wait_for_targets()
#     
#         if "text/html" in targets:
#             contents = clipboard.wait_for_contents("text/html")
#             if contents:
#     
#                 # Firefox data needs to be formated first
#                 if "text/_moz_htmlinfo" in targets:
#                     d = contents.data.decode('utf_16').replace(u'\x00', u'').strip()
#                 else:
#                     d = contents.data.strip()
#     
#                 text = d  # getData(d)
#                 return (text, None)
#     
#         return (None, None)


else:
    # Default variant, works for GTK, probably also for other systems
    
    def getHasHtmlOnClipboard():
        """
        Returns tuple (hasHtml, hasUrl) where both items can be boolean
        or None (meaning unknown) to inform if HTML data and the source URL
        respectively are available on clipboard
        """
        cb = wx.TheClipboard
        df = wx.DataFormat("text/html")
        avail = cb.IsSupported(df)

        return (avail, False)


    def getHtmlFromClipboard():
        """
        Retrieve HTML source from clipboard. Returns a tuple (source, URL)
        where source is the HTML sourcecode and URL is the URL where it came
        from. Both or one of the items may be None. For GTK second item is always
        None.
        """
        from .StringOps import lineendToInternal, mbcsDec
    
        cb = wx.TheClipboard
        cb.Open()
        try:
            dataob = wx.CustomDataObject(wx.DataFormat("text/html"))
            if cb.GetData(dataob):
                if dataob.GetSize() > 0:
                    raw = dataob.GetData()
                    return (lineendToInternal(StringOps.fileContentToUnicode(
                            raw)), None)
        finally:
            cb.Close()

        return (None, None)

# else:
#     # Dummy variant
#     def getHtmlFromClipboard():
#         """
#         Retrieve HTML source from clipboard. Returns a tuple (source, URL)
#         where source is the HTML sourcecode and URL is the URL where it came
#         from. Both or one of the items may be None. For the dummy implementation
#         both are always None.
#         """
#         return (None, None)


# For testing
# getTextFromClipboard = lambda : getHtmlFromClipboard()[0]



def textToDataObject(text=None):
    """
    Create data object for an unicode string
    """
    from .StringOps import lineendToOs, mbcsEnc, utf8Enc
    
    if text is None:
        text = ""
    
    text = lineendToOs(text)

    return wx.TextDataObject(text)


def getBitmapFromClipboard():
    """
    Retrieve bitmap from clipboard if available
    """
    cb = wx.TheClipboard
    cb.Open()
    try:
        dataob = wx.BitmapDataObject()

        if cb.GetData(dataob):
            result = dataob.GetBitmap()
            if result is not wx.NullBitmap:
                return result
            else:
                return None
        return None
    finally:
        cb.Close()


def getFilesFromClipboard():
    """
    Retrieve bitmap from clipboard if available
    """
    from .StringOps import utf8Dec
    cb = wx.TheClipboard
    cb.Open()
    try:
        dataob = wx.FileDataObject()

        if cb.GetData(dataob):
            filenames = dataob.GetFilenames()
            if filenames:
                if SystemInfo.isLinux():
                    # On Linux, at least Ubuntu, fn may be a UTF-8 encoded unicode(!?)
                    # string
                    try:
                        filenames = [utf8Dec(fn.encode("latin-1"))[0]
                                for fn in filenames]
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass

                return filenames
            else:
                return None
        return None
    finally:
        cb.Close()



if SystemInfo.isWindows():
#     def getMetafileFromClipboard():
#         """
#         Retrieve metafile from clipboard if available
#         """
#         cb = wx.TheClipboard
#         cb.Open()
#         try:
#             dataob = wx.CustomDataObject(wx.DataFormat(wx.DF_METAFILE))
#             dataob.SetData("")
#     
#             if cb.GetData(dataob):
#                 result = dataob.GetData()
# #                 if result is not wx.NullBitmap:
#                 return result
# #                 else:
# #                     return None
#             return None
#         finally:
#             cb.Close()


    def getMetafileFromClipboard():
        """
        Retrieve metafile from clipboard if available
        """
        cb = wx.TheClipboard
        cb.Open()
        try:
            dataob = wx.MetafileDataObject()
    
            if cb.GetData(dataob):
                result = dataob.GetMetafile()
#                 if result is not wx.NullBitmap:
                return result
#                 else:
#                     return None
            return None
        finally:
            cb.Close()
else:
    def getMetafileFromClipboard():
        return None



# if SystemInfo.isLinux():   # TODO Mac?
#     
#     def copyTextToClipboard(text): 
#         dataob = textToDataObject(text)
#     
#         cb = wx.TheClipboard
#         
#         cb.Open()
#         try:
#             cb.SetData(dataob)
#         finally:
#             cb.Close()
#     
#         dataob = textToDataObject(text)
#         cb.UsePrimarySelection(True)
#         cb.Open()
#         try:
#             cb.SetData(dataob)
#         finally:
#             cb.Close()
#             cb.UsePrimarySelection(False)
# 
# else:


def copyTextToClipboard(text): 
    dataob = textToDataObject(text)

    cb = wx.TheClipboard
    
    cb.Open()
    try:
        cb.SetData(dataob)
    finally:
        cb.Close()




def getAccelPairFromKeyDown(evt):
    """
    evt -- wx KeyEvent received from a key down event
    return: tuple (modifier, keycode) suitable e.g. as AcceleratorEntry
            (without event handling function)
    """
    keyCode = evt.GetKeyCode()
    
    modif = wx.ACCEL_NORMAL

    if evt.ShiftDown():
        modif |= wx.ACCEL_SHIFT
    if evt.ControlDown():
        modif |= wx.ACCEL_CTRL
    if evt.AltDown():
        modif |= wx.ACCEL_ALT
    
    return (modif, keyCode)


def getAccelPairFromString(s):
    ae = wx.AcceleratorEntry()
    if not ae.FromString(s):
        return (None, None)

    return ae.GetFlags(), ae.GetKeyCode()


def setHotKeyByString(win, hotKeyId, keyString):
    # Search for Windows key
    winMatch = re.search("(?<![^\+\-])win[\+\-]", keyString, re.IGNORECASE)
    winKey = False
    if winMatch:
        winKey = True
        keyString = keyString[:winMatch.start(0)] + \
                keyString[winMatch.end(0):]

    accFlags, vkCode = getAccelPairFromString("\t" + keyString)

#     win.RegisterHotKey(hotKeyId, 0, 0)
    win.UnregisterHotKey(hotKeyId)
    if accFlags is not None:
        modFlags = 0
        if accFlags & wx.ACCEL_SHIFT:
            modFlags |= wx.MOD_SHIFT
        if accFlags & wx.ACCEL_CTRL:
            modFlags |= wx.MOD_CONTROL
        if accFlags & wx.ACCEL_ALT:
            modFlags |= wx.MOD_ALT
        if winKey:
            modFlags |= wx.MOD_WIN
            
#         print "setHotKeyByString7", hotKeyId
        return win.RegisterHotKey(hotKeyId, modFlags, vkCode)

    return False


if SystemInfo.isLinux():
    def isAllModKeysReleased(keyEvent):
        # For Linux the test must be done this way.
        # Meta is always reported as pressed (at least for PC), so ignore it
        mstate = wx.GetMouseState()
        return not (mstate.ControlDown() or mstate.ShiftDown() or 
                mstate.AltDown() or mstate.CmdDown())

else:
    def isAllModKeysReleased(keyEvent):
        if keyEvent is None:
            # No key event available
            mstate = wx.GetMouseState()
            return not (mstate.ControlDown() or mstate.ShiftDown() or 
                    mstate.AltDown() or mstate.CmdDown() or mstate.MetaDown())
        else:
            return not (keyEvent.GetModifiers() & \
                    (wx.MOD_ALT | wx.MOD_CONTROL | wx.MOD_ALTGR | wx.MOD_META | wx.MOD_CMD))


def cloneFont(font):
    return wx.Font(font.GetPointSize(), font.GetFamily(), font.GetStyle(),
                font.GetWeight(), font.GetUnderlined(), font.GetFaceName(),
                font.GetDefaultEncoding())


def drawTextRight(dc, text, startX, startY, width):
    """
    Draw text on a device context right aligned.
    startX, startY -- Upper left corner of box in which to align
    width -- Width of the box in which text should be aligned
    """
    # Calc offset to right align text
    offsetX = width - dc.GetTextExtent(text)[0]
    if offsetX < 0:
        offsetX = 0
    
    dc.DrawText(text, startX + offsetX, startY)


def drawTextCenter(dc, text, startX, startY, width):
    """
    Draw text on a device context center aligned.
    startX, startY -- Upper left corner of box in which to align
    width -- Width of the box in which text should be aligned
    """
    # Calc offset to center align text
    offsetX = (width - dc.GetTextExtent(text)[0]) // 2
    if offsetX < 0:
        offsetX = 0
    
    dc.DrawText(text, startX + offsetX, startY)


def clearMenu(menu):
    """
    Remove all items from a menu.
    """
    for item in menu.GetMenuItems():
        menu.DestroyItem(item)


def appendToMenuByMenuDesc(menu, desc, keyBindings=None):
    """
    Appends the menu items described in unistring desc to menu.
    keyBindings -- a KeyBindingsCache object or None
     
    menu -- already created wx-menu where items should be appended
    desc consists of lines, each line represents an item. A line only
    containing '-' is a separator. Other lines consist of multiple
    parts separated by ';'. The first part is the display name of the
    item, it may be preceded by '*' for a radio item or '+' for a checkbox
    item.
    
    The second part is the command id as it can be retrieved by GUI_ID,
    third part (optional) is the long help text for status line.
    
    Fourth part (optional) is the shortcut, either written as e.g.
    "Ctrl-A" or preceded with '*' and followed by a key to lookup
    in the KeyBindings, e.g. "*ShowFolding". If keyBindings
    parameter is None, all shortcuts (with or without *) are ignored.
    """
    menuItems = []
    for line in desc.split("\n"):
        if line.strip() == "":
            continue

        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 4:
            parts += [""] * (4 - len(parts))

        if parts[0] == "-":
            ic = menu.GetMenuItemCount()
            if ic > 0 and not menu.FindItemByPosition(ic - 1).IsSeparator():
                # Separator
                menu.AppendSeparator()
        else:
            # First check for radio or checkbox items
            kind = wx.ITEM_NORMAL
            title = _unescapeWithRe(parts[0])
            if title[0] == "*":
                # Radio item
                title = title[1:]
                kind = wx.ITEM_RADIO
            elif title[0] == "+":
                # Checkbox item
                title = title[1:]
                kind = wx.ITEM_CHECK

            # Check for shortcut
            if parts[3] != "" and keyBindings is not None:
                if parts[3][0] == "*":
                    parts[3] = getattr(keyBindings, parts[3][1:], "")
                
                if parts[3] != "":
                    title += "\t" + parts[3]
                
            menuID = getattr(GUI_ID, parts[1], -1)
            if menuID == -1:
                continue
            parts[2] = _unescapeWithRe(parts[2])


            # Check and see if we want a submenu
            submenu = None
            # TODO: this should be recursive to allow for nested submenus
            if "|" in title:
                submenu_name, title, = title.split("|")

                # Menu ID's are always negative. -1 is returned if not found
                submenu_id = menu.FindItem(submenu_name)
                if submenu_id != -1:
                    submenu = menu.FindItemById(submenu_id).SubMenu
                # If we can't find the submenu create it
                else:
                    submenu = wx.Menu()
                    menu.Append(wx.ID_ANY, submenu_name, submenu)

            if submenu is not None:
                menuItem = submenu.Append(menuID, _(title), _(parts[2]), kind)
            else:
                menuItem = menu.Append(menuID, _(title), _(parts[2]), kind)
            
            menuItems.append(menuItem)

    return menuItems



# TODO: 2.4: Remove
def runDialogModalFactory(clazz):
    def runModal(*args, **kwargs):
        dlg = clazz(*args, **kwargs)
        try:
            dlg.CenterOnParent(wx.BOTH)
            if dlg.ShowModal() == wx.ID_OK:
                return dlg.GetValue()
            else:
                return None
    
        finally:
            dlg.Destroy()
    
    return runModal


class ModalDialogMixin:
    @classmethod
    def runModal(clazz, *args, **kwargs):
        dlg = clazz(*args, **kwargs)
        try:
            dlg.CenterOnParent(wx.BOTH)
            if dlg.ShowModal() == wx.ID_OK:
                return dlg.GetValue()
            else:
                return dlg.GetCancelValue()
    
        finally:
            dlg.Destroy()


    def GetValue(self):
        return None

    def GetCancelValue(self):
        return self.GetValue()   # TODO: Good idea?




def getWindowParentsUpTo(childWindow, stopWindow):
    result = [childWindow]
    currentWindow = childWindow

    while True:
        currentWindow = currentWindow.GetParent()
        if currentWindow is None:
            return None   # Error
        result.append(currentWindow)
        if currentWindow is stopWindow:
            return result


def isDeepChildOf(childWindow, parentWindow):
    if parentWindow is None or childWindow is None:
        return False

    while True:
        childWindow = childWindow.GetParent()
        if childWindow is None:
            return False
        if childWindow is parentWindow:
            return True


def getAllChildWindows(win):
    winSet = set()
    winSet.add(win)
    _getAllChildWindowsRecurs(win, winSet)
    
    return winSet


def _getAllChildWindowsRecurs(win, winSet):
    for c in win.GetChildren():
        winSet.add(c)
        _getAllChildWindowsRecurs(c, winSet)


def debugListChildWindows(win):

    def _recurs(win, deep):
        print(" " * deep + repr(win), "id=" + repr(win.GetId()), "name=" + repr(win.GetName()), "RTTI=" + repr(win.GetClassName()))
        for c in win.GetChildren():
            _recurs(c, deep+2)
    
    _recurs(win, 0)


class wxKeyFunctionSink(wx.EvtHandler, KeyFunctionSink):
    """
    A MiscEvent sink which dispatches events further to other functions.
    If the wxWindow ifdestroyed receives a destroy message, the sink
    automatically disconnects from evtSource.
    """
    __slots__ = ("eventSource", "ifdestroyed", "disabledSource")


    def __init__(self, activationTable, eventSource=None, ifdestroyed=None):
        wx.EvtHandler.__init__(self)
        KeyFunctionSink.__init__(self, activationTable)

        self.eventSource = eventSource
        self.ifdestroyed = ifdestroyed
        self.disabledSource = None
        
        if self.eventSource is not None:
            self.eventSource.addListener(self, self.ifdestroyed is None)

        if self.ifdestroyed is not None:
            self.ifdestroyed.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)


    def OnDestroy(self, evt):
        # Event may be sent for child windows. Ignore them
        if not self.ifdestroyed is evt.GetEventObject():
            evt.Skip()
            return

        self.disconnect()
        evt.Skip()


    def enable(self, val=True):
        if val:
            if self.eventSource is not None or self.disabledSource is None:
                return

            self.eventSource = self.disabledSource
            self.disabledSource = None
            self.eventSource.addListener(self)
        else:
            if self.eventSource is None or self.disabledSource is not None:
                return
            
            self.disabledSource = self.eventSource
            self.eventSource.removeListener(self)
            self.eventSource = None

    def disable(self):
        return self.enable(False)


    def setEventSource(self, eventSource):
        if self.eventSource is eventSource:
            return

        self.disconnect()
        self.eventSource = eventSource
        self.disabledSource = None
        if self.eventSource is not None:
            self.eventSource.addListener(self)

    def disconnect(self):
        """
        Disconnect from eventSource.
        """
        self.disabledSource = None
        if self.eventSource is None:
            return
        self.eventSource.removeListener(self)
        self.eventSource = None

    def __repr__(self):
        return "<wxHelper.wxKeyFunctionSink " + hex(id(self)) + " ifdstr: " + \
                repr(self.ifdestroyed) + ">"


def isDead(wxWnd):
    """
    Check if C++ part of a wx-object is dead already
    """
    return not wxWnd  # wxObj.__class__ is wx._core._wxPyDeadObject


class IconCache:
    def __init__(self, iconDir):
        self.iconDir = iconDir
#         self.lowResources = lowResources
        
        # default icon is page.gif
        icons = ['page.gif']
        # add the rest of the icons
        icons.extend([fn for fn in os.listdir(self.iconDir)
                if fn.endswith('.gif') and fn != 'page.gif'])

        self.iconFileList = icons
        self.fillIconCache()


    def fillIconCache(self):
        """
        Fills or refills the self.iconLookupCache (if createIconImageList is
        false, self.iconImageList must exist already)
        """

        # create the image icon list
        self.iconImageList = wx.ImageList(16, 16)
        self.iconLookupCache = {}

        for icon in self.iconFileList:
#             iconFile = os.path.join(self.wikiAppDir, "icons", icon)
            iconFile = os.path.join(self.iconDir, icon)
            bitmap = wx.Bitmap(iconFile, wx.BITMAP_TYPE_GIF)
            try:
                id = self.iconImageList.Add(bitmap, wx.NullBitmap)

#                 if self.lowResources:   # and not icon.startswith("tb_"):
#                     bitmap = None

                iconname = icon.replace('.gif', '')
                if id == -1:
                    id = self.iconLookupCache[iconname][0]

                self.iconLookupCache[iconname] = (id, iconFile, bitmap)
            except Exception as e:
                traceback.print_exc()
                sys.stderr.write("couldn't load icon %s\n" % iconFile)


#     # TODO !  Do not remove bitmaps which are in use
#     def clearIconBitmaps(self):
#         """
#         Remove all bitmaps stored in the cache, needed by
#         PersonalWiki.resourceSleep.
#         """
#         for k in self.iconLookupCache.keys():
#             self.iconLookupCache[k] = self.iconLookupCache[k][0:2] + (None,)


    def lookupIcon(self, iconname):
        """
        Returns the bitmap object for the given iconname.
        If the bitmap wasn't cached already, it is loaded and created.
        If icon is unknown, None is returned.
        """
        try:
            bitmap = self.iconLookupCache[iconname][2]
            if bitmap is not None:
                return bitmap
                
            # Bitmap not yet available -> create it and store in the cache
            iconFile = os.path.join(self.iconDir, iconname+".gif")
            bitmap = wx.Bitmap(iconFile, wx.BITMAP_TYPE_GIF)
            
            self.iconLookupCache[iconname] = self.iconLookupCache[iconname][0:2] + \
                    (bitmap,)

            return bitmap

        except KeyError:
            return None


    def lookupIconIndex(self, iconname):
        """
        Returns the id number into self.iconImageList of the requested icon.
        If icon is unknown, -1 is returned.
        """
        try:
            return self.iconLookupCache[iconname][0]
        except KeyError:
            return -1


    def lookupIconPath(self, iconname):
        """
        Returns the path to icon file of the requested icon.
        If icon is unknown, -1 is returned.
        """
        try:
            return self.iconLookupCache[iconname][1]
        except KeyError:
            return None

    def resolveIconDescriptor(self, desc, default=None):
        """
        Used for plugins of type "MenuFunctions" or "ToolbarFunctions".
        Tries to find and return an appropriate wxBitmap object.
        
        An icon descriptor can be one of the following:
            - None
            - a wxBitmap object
            - the filename of a bitmap
            - a tuple of filenames, first existing file is used
        
        If no bitmap can be found, default is returned instead.
        """
        if desc is None:
            return default            
        elif isinstance(desc, wx.Bitmap):
            return desc
        elif isinstance(desc, str):
            result = self.lookupIcon(desc)
            if result is not None:
                return result
            
            return default
        else:    # A sequence of possible names
            for n in desc:
                result = self.lookupIcon(n)
                if result is not None:
                    return result

            return default
            
            
#     def getNewImageList(self):
#         """
#         Return a new (cloned) image list
#         """
#         return cloneImageList(self.iconImageList)
        
        
    def getImageList(self):
        """
        Return the internal image list. The returned object should be given
        wx components only with SetImageList, not AssignImageList
        """
        return self.iconImageList




class LayerSizer(wx.Sizer):
    def __init__(self):
        wx.Sizer.__init__(self)
        self.addedItemIds = set()

    def CalcMin(self):
        minw = 0
        minh = 0
        for item in self.GetChildren():
            mins = item.GetMinSize()
            minw = max(minw, mins.width)
            minh = max(minh, mins.height)

        return wx.Size(minw, minh)
        
    
    def Add(self, item):
        pId = id(item)
        if pId not in self.addedItemIds:
             self.addedItemIds.add(pId)
             wx.Sizer.Add(self, item)


    def RecalcSizes(self):
        pos = self.GetPosition()
        size = self.GetSize()
        size = wx.Size(size.GetWidth(), size.GetHeight())
        for item in self.GetChildren():
            win = item.GetWindow()
            if win is None:
                item.SetSize(pos.x, pos.y, size.GetWidth(), size.GetHeight())
            else:
                # Bad hack
                # Needed because some ctrls like e.g. ListCtrl do not support
                # to overwrite virtual methods like DoSetSize
                win.SetSize(pos.x, pos.y, size.GetWidth(), size.GetHeight())



class DummyWindow(wx.Window):
    """
    Used to catch hotkeys because there seems to be a bug which prevents
    deleting them so instead the whole window is deleted and recreated.
    """
    def __init__(self, parent, id=-1):
        wx.Window.__init__(self, parent, id, size=(0,0))



class ProxyPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        
        self.subWindow = None
        
        self.Bind(wx.EVT_SIZE, self.OnSize)

    def __repr__(self):
        return "<ProxyPanel " + str(id(self)) + " for " + repr(self.subWindow) + ">"


    def setSubWindow(self, subWindow):
        self.subWindow = subWindow

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(subWindow, 1, wx.EXPAND, 0)

        self.SetSizer(sizer)


    def getSubWindow(self):
        return self.subWindow


    def close(self):
        if self.subWindow is not None:
            self.subWindow.close()


    def OnSize(self, evt):
        evt.Skip()
        size = evt.GetSize()


class ProgressHandler:
    """
    Implementation of a GuiProgressListener to
    show a progress dialog
    """
    def __init__(self, title, msg, addsteps, parent, flags=wx.PD_APP_MODAL,
            yieldsteps=5):
        self.title = title
        self.msg = msg
        self.addsteps = addsteps
        self.parent = parent
        self.flags = flags
        self.progDlg = None
        self.yieldsteps = yieldsteps
        self.currYieldStep = 1

    def setTitle(self, title):
        self.title = title
        if self.progDlg is not None:
            # Set title in open dialog
            self.progDlg.SetTitle(self.title)
    
    def setMessage(self, msg):
        self.msg = msg
        if self.progDlg is not None:
            # Set message in open dialog
            self.progDlg.ctrls.text.SetLabel(msg)


    def open(self, sum):
        """
        Start progress handler, set the number of steps, the operation will
        take in sum. Will be called once before update()
        is called several times
        """
        if self.progDlg is None:
            res = XmlResource.Get()
            self.progDlg = res.LoadDialog(self.parent, "ProgressDialog")
            self.progDlg.ctrls = XrcControls(self.progDlg)
            self.progDlg.SetTitle(self.title)

        self.currYieldStep = 1

        self.progDlg.ctrls.text.SetLabel(self.msg)
        self.progDlg.ctrls.gauge.SetRange(sum + self.addsteps)
        self.progDlg.ctrls.gauge.SetValue(0)
        self.progDlg.Show()

    def update(self, step, msg):
        """
        Called after a step is finished to trigger update
        of GUI.
        step -- Number of done steps
        msg -- Human readable description what is currently done
        returns: True to continue, False to stop operation
        """
        self.msg = msg

        self.progDlg.ctrls.text.SetLabel(msg)
        self.progDlg.ctrls.gauge.SetValue(step)
        
        self.currYieldStep -= 1
        if self.currYieldStep <= 0:
            self.currYieldStep = self.yieldsteps
            wx.SafeYield(onlyIfNeeded = True)

        return True

    def close(self):
        """
        Called after finishing operation or after abort to 
        do clean-up if necessary
        """
        self.progDlg.Destroy()
        self.progDlg = None


class ReorderableListBox(wx.ListBox):
    """
    Additional functionality: Move selected item one step upward/downward
    """
    def __init__(self, *args, **kwargs):
        if len(args) == 0 and len(kwargs) == 0:
            wx.ListBox.__init__(self)
            self.Bind(wx.EVT_WINDOW_CREATE, self.OnCreate)
        else:
            wx.ListBox.__init__(self, *args, **kwargs)
            wx.CallAfter(self.__PostInit)

    def OnCreate(self,evt):
        self.Unbind(wx.EVT_WINDOW_CREATE)
        wx.CallAfter(self.__PostInit)
        evt.Skip()
        return True

    def __PostInit(self):
        pass

    def MoveSelectedUp(self):
        """
        Move currently selected item one up in the list (including associated
        data if any). Fails silently if not possible.
        """
        sel = self.GetSelection()
        if sel == wx.NOT_FOUND or sel == 0:
            return
            
        data = self.GetClientData(sel)
        label = self.GetString(sel)
        self.Delete(sel)
        
        self.Insert(label, sel - 1)
        
        if data is not None:
            self.SetClientData(sel - 1, data)
        
        self.SetSelection(sel - 1)


    def MoveSelectedDown(self):
        """
        Move currently selected item one down in the list (including associated
        data if any). Fails silently if not possible.
        """

        sel = self.GetSelection()
        if sel == wx.NOT_FOUND or sel == self.GetCount() - 1:
            return

        data = self.GetClientData(sel)
        label = self.GetString(sel)
        self.Delete(sel)

        self.Insert(label, sel + 1)
        
        if data is not None:
            self.SetClientData(sel + 1, data)
        
        self.SetSelection(sel + 1)


    def GetClientDatas(self):
        """
        Get list of all item data.
        """
        return [self.GetClientData(i) for i in range(self.GetCount())]


    def SetLabelsAndClientDatas(self, labels, datas):
        with WindowUpdateLocker(self):
            self.Clear()
            self.Append(labels)
            
            for i, d in enumerate(datas):
                self.SetClientData(i, d)




class EnhancedListControl(wx.ListCtrl):
    def __init__(self, *args, **kwargs):
        wx.ListCtrl.__init__(self, *args, **kwargs)

    def GetAllSelected(self):
        result = []
        sel = -1
        while True:
            sel = self.GetNextItem(sel, state=wx.LIST_STATE_SELECTED)
            if sel == -1:
                break
            result.append(sel)

        return result

    def GetFirstSelected(self):
        return self.GetNextItem(-1, state=wx.LIST_STATE_SELECTED)

    def GetIsSelected(self, idx):
        if idx < 0 or idx >= self.GetItemCount():
            return False

        return bool(self.GetItemState(idx, wx.LIST_STATE_SELECTED))


    if SystemInfo.isWindows():
        _SETSSI_ITEMMASK = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
    else:
        # TODO Check for MacOS
        _SETSSI_ITEMMASK = wx.LIST_STATE_SELECTED


    def SelectSingle(self, idx, scrollVisible=False):
        # Unselect all selected
        for prev in self.GetAllSelected():
            self.SetItemState(prev, 0, self._SETSSI_ITEMMASK)

        if idx > -1:
            self.SetItemState(idx, self._SETSSI_ITEMMASK, self._SETSSI_ITEMMASK)
            if scrollVisible:
                self.EnsureVisible(idx)


    def autosizeColumn(self, col):
        # Call function below
        autosizeColumn(self, col)
        
    def getConfigStringForColWidths(self):
        result = []
        for i in range(self.GetColumnCount()):
            result.append(str(self.GetColumnWidth(i)))
        
        return ",".join(result)
    
    def setColWidthsByConfigString(self, cfgString):
        if cfgString is None:
            return

        cfgParts = cfgString.split(",")
        if len(cfgParts) != self.GetColumnCount():
            return
            
        try:
            cfgParts = [int(p) for p in cfgParts]
        except ValueError:
            return

        with WindowUpdateLocker(self):
            for i in range(self.GetColumnCount()):
                self.SetColumnWidth(i, cfgParts[i])




if SystemInfo.isWindows():   # Maybe necessary for other OS' as well
    def autosizeColumn(listCtrl, col):
        """
        Workaround for some bug in wxPython 2.8.10
        """
        with WindowUpdateLocker(listCtrl):
            listCtrl.SetColumnWidth(col, wx.LIST_AUTOSIZE)
            listCtrl.SetColumnWidth(col, listCtrl.GetColumnWidth(col) + 10)
else:
    def autosizeColumn(listCtrl, col):
        listCtrl.SetColumnWidth(col, wx.LIST_AUTOSIZE)



def registerPluginGuiId(idText):
    """
    Takes a string id and returns an id number suitable for GUI operations.
    If given  idText  wasn't used in a previous call, a new id is returned
    otherwise the same id as for the first call with same idText is returned.
    """
    return GUI_ID[idText]



class EnhancedPlgSuppMenu(wx.Menu):
    """
    A plugin supported context menu provides functionality for plugins to add
    additional menu items and react on them
    """
    def __init__(self, owningWindow, title="", style=0):
        wx.Menu.__init__(self, title, style)

        self.contextName = None
        self.contextDict = None
        self.listenedIds = set()
        self.owningWindow = owningWindow

    def close(self):
        self.clearListeners()

    def setContext(self, contextName, contextDict):
        self.contextName = contextName
        self.contextDict = contextDict

    def setContextName(self, contextName):
        self.contextName = contextName
        
    def getContextName(self):
        return self.contextName

    def setContextDict(self, contextDict):
        self.contextDict = contextDict
        
    def getContextDict(self):
        return self.contextDict
        
    def getOwningWindow(self):
        return self.owningWindow

        
    @staticmethod
    def convertId(id):
        if isinstance(id, str):
            id = registerPluginGuiId(id)
        elif id == -1:
            id = wx.NewId()

        return id
    
    def appendNecessarySeparator(self):
        """
        Similar to AppendSeparator, but ensures that no separator appears
        at the beginning of the menu or two separators consecutively.
        """
        if self.GetMenuItemCount() == 0:
            return
        
        # Python's  "list[-1]"  syntax doesn't work here
        if self.GetMenuItems()[self.GetMenuItemCount() - 1].IsSeparator():
            return
        
        self.AppendSeparator()


    def preparePlgMenuItem(self, label, hint, evtfct=None, iconBitmap=None,
            menuID=None, updatefct=None, kind=wx.ITEM_NORMAL):
        """
        Prepare a menu item for a plugin. Mainly called by "provideMenuItemV01"
        of a "MenuItemProvider" plugin.
        label -- Label of menu item
        hint -- Short help text for status bar
        evtfct -- function to call when item is clicked, function takes
            the following parameters:
            
            menuItemUnifName -- unified name string identifying provided menu item
            contextName -- string to identify the basic type of menu, e.g.
                "contextMenu/editor/textArea" for the context menu in
                the text area of the editor.
            
            contextDict -- a dictionary with string keys and arbitrary objects
                as values. These give more information about the situation
                in which the menu was created. The content depends on
                the context name.
                Detailed information is given in
                "docs/MenuHandling_contextInfo.txt".
            
            menu -- this menu object

        iconBitmap -- icon as wx.Bitmap object
        menuID -- string or number to identify item uniquely in the scope of
            this menu
        updatefct -- function to call when item needs UI update (before it is
            shown). Function takes same parameters as  evtfct.
        kind -- One of wx.ITEM_NORMAL, wx.ITEM_CHECK, wx.ITEM_RADIO
        
        Returns: Newly created wx.MenuItem object
        """
        # Similar to (but not copy of) PersonalWikiFrame.addMenuItem

        menuIDNo = self.convertId(menuID)
        
        if menuIDNo is None:
            menuIDNo = wx.NewId()
            
        if kind is None:
            kind = wx.ITEM_NORMAL

#         lcut = label.split(u"\t", 1)
#         if len(lcut) > 1:
#             lcut[1] = self.translateMenuAccelerator(lcut[1])
#             label = lcut[0] + u" \t" + lcut[1]

        menuitem = wx.MenuItem(self, menuIDNo, label, hint, kind)
        if iconBitmap:
            menuitem.SetBitmap(iconBitmap)

        # self.AppendItem(menuitem)
        if evtfct is not None:
            self.addCmdListener(menuIDNo, evtfct, menuID)

        if updatefct is not None:
# TODO:
#             if isinstance(updatefct, tuple):
#                 updatefct = _buildChainedUpdateEventFct(updatefct)
            self.addUpdListener(menuIDNo, updatefct, menuID)

        return menuitem


#     def addPlgMenuItem(self, label, hint, evtfct=None, iconBitmap=None,
#             menuID=None, updatefct=None, kind=wx.ITEM_NORMAL):
#         # Similar to (but not copy of) PersonalWikiFrame.addMenuItem
#         
#         menuitem = self.preparePlgMenuItem(label, hint, evtfct, iconBitmap,
#             menuID, updatefct, kind)
#         self.AppendItem(menuitem)
#         return menuitem


    def insertProvidedItem(self, insertIdx, unifName):
        wx.GetApp().getProvideMenuItemDispatcher().dispatch(unifName,
                self.contextName, self.contextDict, self, insertIdx)
    
    def appendProvidedItem(self, unifName):
        return self.insertProvidedItem(self.GetMenuItemCount(), unifName)

    def addCmdListener(self, id, handler, origId=None):
        id = self.convertId(id)
        self.owningWindow.Bind(wx.EVT_MENU, lambda evt: handler(evt, origId,
                self.contextName, self.contextDict, self), id=id)
        self.listenedIds.add(id)
    
    def removeCmdListener(self, id):
        id = self.convertId(id)
        self.owningWindow.Unbind(wx.EVT_MENU, id=id)
        self.listenedIds.discard(id)


    def addUpdListener(self, id, handler, origId=None):
        id = self.convertId(id)
#         self.Bind(wx.EVT_UPDATE_UI, handler, id=id)
        self.owningWindow.Bind(wx.EVT_UPDATE_UI, lambda evt: handler(evt, origId,
                self.contextName, self.contextDict, self), id=id)
        self.listenedIds.add(id)
    
    def removeUpdListener(self, id):
        id = self.convertId(id)
        self.owningWindow.Unbind(wx.EVT_UPDATE_UI, id=id)
        self.listenedIds.discard(id)


    def clearListeners(self):
        for id in self.listenedIds:
            self.owningWindow.Unbind(wx.EVT_MENU, id=id)
            self.owningWindow.Unbind(wx.EVT_UPDATE_UI, id=id)

        self.listenedIds.clear()







# class ColoredStatusBar(wx.StatusBar):
#     def __init__(self, *args, **kwargs):
#         wx.StatusBar.__init__(self, *args, **kwargs)
#         self.bgColors = [None]
#         self.Bind(wx.EVT_PAINT, self.OnPaint)
# 
#     def SetFieldsCount(self, number=1):
#         wx.StatusBar.SetFieldsCount(self, number)
#         self.bgColors = [None] * number
#         
#     def SetFieldBgColor(self, idx, color):
#         self.bgColors[idx] = color
#         
#     def OnPaint(self, evt):
# #         wx.StatusBar.Update(self)
#         dc = wx.WindowDC(self)
# 
#         for i, color in enumerate(self.bgColors):
#             if color is None:
#                 continue
# 
#             rect = self.GetFieldRect(i)
#             
#             
#             dc.SetBrush(wx.RED_BRUSH)
#             dc.SetPen(wx.RED_PEN)
#             dc.DrawRectangle(rect.x + 1, rect.y + 1, rect.width - 2,
#                     rect.height - 2)
#             dc.SetPen(wx.BLACK_PEN)
#             dc.SetFont(self.GetFont())
#             dc.SetClippingRect(rect)
#             dc.DrawText(self.GetStatusText(i), rect.x + 2, rect.y + 2)
#             dc.SetFont(wx.NullFont)
#             dc.SetBrush(wx.NullBrush)
#             dc.SetPen(wx.NullPen)
# 
#         evt.Skip()
        

