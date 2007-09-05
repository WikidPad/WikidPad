import os, os.path, traceback, sys, re

from wx.xrc import XRCCTRL, XRCID
import wx

from MiscEvent import KeyFunctionSink
import Configuration


def _unescapeWithRe(text):
    """
    Unescape things like \n or \f. Throws exception if unescaping fails
    """
    return re.sub(u"", text, u"", 1)


class wxIdPool:
    def __init__(self):
        self.poolmap={}

    def __getattr__(self, name):
        """Returns a new wx-Id for each new string <name>.
 
        If the same name is given twice, the same id is returned.
        
        If the name is in the XRC id-table its value there will be returned
        """
        try:
            return XRCID(name)
        except:
            try:
                return self.poolmap[name]
            except KeyError:
                id=wx.NewId()
                self.poolmap[name]=id
                return id


GUI_ID = wxIdPool()
GUI_ID.__doc__="All purpose standard Gui-Id-Pool"

 
class XrcControls:
    """
    Convenience wrapper for XRCCTRL
    """
    def __init__(self, basepanel):
        self.__basepanel = basepanel

    def __getattr__(self, name):
        return XRCCTRL(self.__basepanel, name)
        
    def __getitem__(self, name):
        return XRCCTRL(self.__basepanel, name)
    


if Configuration.isWin9x():
    def getTextFromClipboard():
        """
        Retrieve text or unicode text from clipboard
        """
        from StringOps import lineendToInternal, mbcsDec
        import array
    
        cb = wx.TheClipboard
        cb.Open()
        try:
            dataob = wx.DataObjectComposite()
            cdataob = wx.CustomDataObject(wx.DataFormat(wx.DF_TEXT))
            udataob = wx.CustomDataObject(wx.DataFormat(wx.DF_UNICODETEXT))
            cdataob.SetData("")
            udataob.SetData("")
            dataob.Add(udataob)
            dataob.Add(cdataob)
    
            if cb.GetData(dataob):
                if udataob.GetDataSize() > 0 and (udataob.GetDataSize() % 2) == 0:
                    # We have unicode data
                    # This might not work for all platforms:   # TODO Better impl.
                    rawuni = udataob.GetData()
                    arruni = array.array("u")
                    arruni.fromstring(rawuni)
                    realuni = lineendToInternal(arruni.tounicode())
                    return realuni
                elif cdataob.GetDataSize() > 0:
                    realuni = lineendToInternal(
                            mbcsDec(cdataob.GetData(), "replace")[0])
                    return realuni
                else:
                    return u""
            return None
        finally:
            cb.Close()


    def textToDataObject(text=None):
        """
        Create data object for an unicode string
        """
        from StringOps import lineendToOs, mbcsEnc, utf8Enc
        import array
        
        cdataob = wx.CustomDataObject(wx.DataFormat(wx.DF_TEXT))
        udataob = wx.CustomDataObject(wx.DataFormat(wx.DF_UNICODETEXT))
    
        if text is not None:
            realuni = lineendToOs(text)
            arruni = array.array("u")
            arruni.fromunicode(realuni+u"\x00")
            rawuni = arruni.tostring()
            udataob.SetData(rawuni)
            cdataob.SetData(mbcsEnc(realuni)[0]+"\x00")
        else:
            cdataob.SetData("")
            udataob.SetData("")
    
        dataob = wx.DataObjectComposite()
        dataob.Add(udataob, True)
        dataob.Add(cdataob)
    
        return dataob

else:    # Non-Windows 9x versions

    def getTextFromClipboard():
        """
        Retrieve text or unicode text from clipboard
        """
        from StringOps import lineendToInternal, mbcsDec
    
        cb = wx.TheClipboard
        cb.Open()
        try:
            dataob = textToDataObject()

            if cb.GetData(dataob):
                if dataob.GetTextLength() > 0:
                    return lineendToInternal(dataob.GetText())
                else:
                    return u""
            return None
        finally:
            cb.Close()


    def textToDataObject(text=None):
        """
        Create data object for an unicode string
        """
        from StringOps import lineendToOs, mbcsEnc, utf8Enc
        
        if text is None:
            text = u""
        
        text = lineendToOs(text)

        return wx.TextDataObject(text)


# bmp.ConvertToImage()
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
    ae = wx.GetAccelFromString(s)
    if ae is None:
        return (None, None)

    return ae.GetFlags(), ae.GetKeyCode()


def setHotKeyByString(win, hotKeyId, keyString):
    # Search for Windows key
    winMatch = re.search(u"(?<![^\+\-])win[\+\-]", keyString, re.IGNORECASE)
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




def appendToMenuByMenuDesc(menu, desc, keyBindings=None):
    """
    Appends the menu items described in unistring desc to
    menu.
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
    parameter is None, all shortcuts are ignored.
    """
    for line in desc.split(u"\n"):
        if line.strip() == u"":
            continue
        
        parts = [p.strip() for p in line.split(u";")]
        if len(parts) < 4:
            parts += [u""] * (4 - len(parts))
        
        if parts[0] == u"-":
            # Separator
            menu.AppendSeparator()
        else:
            # First check for radio or checkbox items
            kind = wx.ITEM_NORMAL
            title = _unescapeWithRe(parts[0])
            if title[0] == u"*":
                # Radio item
                title = title[1:]
                kind = wx.ITEM_RADIO
            elif title[0] == u"+":
                # Checkbox item
                title = title[1:]
                kind = wx.ITEM_CHECK

            # Check for shortcut
            if parts[3] != u"" and keyBindings is not None:
                if parts[3][0] == u"*":
                    parts[3] = getattr(keyBindings, parts[3][1:], u"")
                
                if parts[3] != u"":
                    title += u"\t" + parts[3]
                
            menuID = getattr(GUI_ID, parts[1], -1)
            if menuID == -1:
                continue
            parts[2] = _unescapeWithRe(parts[2])
            menu.Append(menuID, title, parts[2], kind)


class wxKeyFunctionSink(wx.EvtHandler, KeyFunctionSink):
    """
    A MiscEvent sink which dispatches events further to other functions.
    If the wxWindow ifdestroyed receives a destroy message, the sink
    automatically disconnects from evtSource.
    """
    __slots__ = ("eventSource", "ifdestroyed")


    def __init__(self, activationTable, eventSource=None, ifdestroyed=None):
        wx.EvtHandler.__init__(self)
        KeyFunctionSink.__init__(self, activationTable)

        self.eventSource = eventSource
        self.ifdestroyed = ifdestroyed
        
        if self.eventSource is not None:
            self.eventSource.addListener(self, False)
        
        if self.ifdestroyed is not None:
            wx.EVT_WINDOW_DESTROY(self.ifdestroyed, self.OnDestroy)


    def OnDestroy(self, evt):
        # Event may be sent for child windows. Ignore them
        if not self.ifdestroyed is evt.GetEventObject():
            evt.Skip()
            return

        self.disconnect()
        evt.Skip()


    def setEventSource(self, eventSource):
        self.disconnect()
        self.eventSource = eventSource
        if eventSource is not None:
            self.eventSource.addListener(self)

    def disconnect(self):
        """
        Disconnect from eventSource.
        """
        if self.eventSource is None:
            return
        self.eventSource.removeListener(self)
        self.eventSource = None




class IconCache:
    def __init__(self, iconDir, lowResources):
        self.iconDir = iconDir
        self.lowResources = lowResources
        
        # add the gif handler for gif icon support
#         wxImage_AddHandler(wxGIFHandler())
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
        If createIconImageList is true, self.iconImageList is also
        built
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

                if self.lowResources:   # and not icon.startswith("tb_"):
                    bitmap = None

                iconname = icon.replace('.gif', '')
                if id == -1:
                    id = self.iconLookupCache[iconname][0]

                self.iconLookupCache[iconname] = (id, bitmap)
            except Exception, e:
                traceback.print_exc()
                sys.stderr.write("couldn't load icon %s\n" % iconFile)


    # TODO !  Do not remove bitmaps which are in use
    def clearIconBitmaps(self):
        """
        Remove all bitmaps stored in the cache, needed by
        PersonalWiki.resourceSleep.
        """
        for k in self.iconLookupCache.keys():
            self.iconLookupCache[k] = (self.iconLookupCache[k][0], None)


    def lookupIcon(self, iconname):
        """
        Returns the bitmap object for the given iconname.
        If the bitmap wasn't cached already, it is loaded and created.
        If icon is unknown, None is returned.
        """
        try:
            bitmap = self.iconLookupCache[iconname][1]
            if bitmap is not None:
                return bitmap
                
            # Bitmap not yet available -> create it and store in the cache
            iconFile = os.path.join(self.iconDir, iconname+".gif")
            bitmap = wx.Bitmap(iconFile, wx.BITMAP_TYPE_GIF)
            
            self.iconLookupCache[iconname] = (self.iconLookupCache[iconname][0],
                    bitmap)
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
        elif isinstance(desc, basestring):
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



class LayerSizer(wx.PySizer):
    def __init__(self):
        wx.PySizer.__init__(self)
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
             wx.PySizer.Add(self, item)


    def RecalcSizes(self):
        pos = self.GetPosition()
        size = self.GetSize()
        size = wx.Size(size.GetWidth(), size.GetHeight())
        for item in self.GetChildren():
            win = item.GetWindow()
            if win is None:
                item.SetDimension(pos, size)
            else:
                # Bad hack
                # Needed because some ctrls like e.g. ListCtrl do not support
                # to overwrite virtual methods like DoSetSize
                win.SetDimensions(pos.x, pos.y, size.GetWidth(), size.GetHeight())



class DummyWindow(wx.Window):
    def __init__(self, parent, id=-1):
        wx.Window.__init__(self, parent, id, size=(0,0))


class EnhancedListControl(wx.ListCtrl):
    def __init__(*args, **kwargs):
        wx.ListCtrl.__init__(*args, **kwargs)
        
    def GetAllSelected(self):
        result = []
        sel = -1
        while True:
            sel = self.GetNextItem(sel, state=wx.LIST_STATE_SELECTED)
            if sel == -1:
                break
            result.append(sel)

        return result


    if Configuration.isWindows():
        _SETSSI_ITEMMASK = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
    else:
        # TODO Check for MacOS
        _SETSSI_ITEMMASK = wx.LIST_STATE_SELECTED


    def SelectSingle(self, idx):
        # Unselect all selected
        for prev in self.GetAllSelected():
            self.SetItemState(prev, 0, self._SETSSI_ITEMMASK)

        if idx > -1:
            self.SetItemState(idx, self._SETSSI_ITEMMASK, self._SETSSI_ITEMMASK)





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
        

