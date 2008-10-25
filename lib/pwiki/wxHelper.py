import os, os.path, traceback, sys

import wx
# from   wxPython.wx import wxNewId, wxSystemSettings_GetMetric, wxSYS_SCREEN_X, \
#         wxSYS_SCREEN_Y, wxSplitterWindow, wxSashLayoutWindow, \
#         EVT_WINDOW_DESTROY, wxEvtHandler, wxBitmap, wxBITMAP_TYPE_GIF, \
#         wxNullBitmap, wxImageList

from wx.xrc import XRCCTRL, XRCID


from MiscEvent import KeyFunctionSink


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
    

# DEPRECATED: Use same function in WindowLayout.py
def setWindowPos(win, pos=None, fullVisible=False):
    """
    Set position of a wx.Window, but ensure that the position is valid.
    If fullVisible is True, the window is moved to be full visible
    according to its current size. It is recommended to call
    setWindowSize first.
    """
    if pos is not None:
        currentX, currentY = pos
    else:
        currentX, currentY = win.GetPositionTuple()
        
    screenX = wx.SystemSettings_GetMetric(wx.SYS_SCREEN_X)
    screenY = wx.SystemSettings_GetMetric(wx.SYS_SCREEN_Y)
    
    # fix any crazy screen positions
    if currentX < 0:
        currentX = 10
    if currentY < 0:
        currentY = 10
    if currentX > screenX:
        currentX = screenX-100
    if currentY > screenY:
        currentY = screenY-100
        
    if fullVisible:
        sizeX, sizeY = win.GetSizeTuple()
        if currentX + sizeX > screenX:
            currentX = screenX - sizeX
        if currentY + sizeY > screenY:
            currentY = screenY - sizeY

    win.SetPosition((currentX, currentY))


# DEPRECATED: Use same function in WindowLayout.py
def setWindowSize(win, size):
    """
    Set size of a wx.Window, but ensure that the size is valid
    """
    sizeX, sizeY = size
    screenX = wx.SystemSettings_GetMetric(wx.SYS_SCREEN_X)
    screenY = wx.SystemSettings_GetMetric(wx.SYS_SCREEN_Y)

    # don't let the window be > than the size of the screen
    if sizeX > screenX:
        sizeX = screenX-20
    if sizeY > screenY:
        currentY = screenY-20

    # set the size
    win.SetSize((sizeX, sizeY))


def getTextFromClipboard():
    """
    Retrieve text or unicode text from clipboard
    """
#     from wxPython.wx import wxTheClipboard, wxDataObjectComposite, wxDataFormat, \
#             wxCustomDataObject, wxDF_TEXT, wxDF_UNICODETEXT
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
                return ""
        return None
    finally:
        cb.Close()


def textToDataObject(text):
#     from wxPython.wx import wxDataObjectComposite, wxDataFormat, \
#             wxCustomDataObject, wxDF_TEXT, wxDF_UNICODETEXT
    from StringOps import lineendToOs, mbcsEnc, utf8Enc
    import array
    
    cdataob = wx.CustomDataObject(wx.DataFormat(wx.DF_TEXT))
    udataob = wx.CustomDataObject(wx.DataFormat(wx.DF_UNICODETEXT))

    realuni = lineendToOs(text)
    arruni = array.array("u")
    arruni.fromunicode(realuni+u"\x00")
    rawuni = arruni.tostring()
    udataob.SetData(rawuni)
    cdataob.SetData(mbcsEnc(realuni)[0]+"\x00")

    dataob = wx.DataObjectComposite()
    dataob.Add(udataob, True)
    dataob.Add(cdataob)

    return dataob


def copyTextToClipboard(text): 
#     from wxPython.wx import wxTheClipboard
#     from StringOps import lineendToOs, mbcsEnc
#     import array
# 
#     cdataob = wxCustomDataObject(wxDataFormat(wxDF_TEXT))
#     udataob = wxCustomDataObject(wxDataFormat(wxDF_UNICODETEXT))
#     realuni = lineendToOs(text)
#     arruni = array.array("u")
#     arruni.fromunicode(realuni+u"\x00")
#     rawuni = arruni.tostring()
#     # print "Copy", repr(realuni), repr(rawuni), repr(mbcsenc(realuni)[0])
#     udataob.SetData(rawuni)
#     cdataob.SetData(mbcsEnc(realuni)[0]+"\x00")
# 
#     dataob = wxDataObjectComposite()
#     dataob.Add(udataob)
#     dataob.Add(cdataob)

    dataob = textToDataObject(text)

    cb = wx.TheClipboard
    cb.Open()
    try:
        cb.SetData(dataob)
    finally:
        cb.Close()


def getAccelPairFromKeyDown(evt):
#     from wxPython.wx import wxACCEL_ALT, wxACCEL_SHIFT, wxACCEL_CTRL, \
#             wxACCEL_NORMAL
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
#     from   wxPython.wx import wxGetAccelFromString
    ae = wx.GetAccelFromString(s)
    if ae is None:
        return (None, None)

    return ae.GetFlags(), ae.GetKeyCode()



def cloneImageList(imgList):
    """
    Create a copy of an wx.ImageList
    """
#     from wxPython.wx import wxImageList

    sz = imgList.GetSize(0)
    lng = imgList.GetImageCount()
    result = wx.ImageList(sz[0], sz[1], True, lng)
    
    try:
        for i in xrange(lng):
            result.AddIcon(imgList.GetIcon(i))
    except wx.PyAssertionError:
        # Alternative way
        result = wx.ImageList(sz[0], sz[1], True, lng)
        for i in xrange(lng):
            result.Add(imgList.GetBitmap(i))


    return result


class wxKeyFunctionSink(wx.EvtHandler, KeyFunctionSink):
    """
    A MiscEvent sink which dispatches events further to other functions.
    If the wx.Window ifdestroyed receives a destroy message, the sink
    automatically disconnects from evtSource.
    """
    __slots__ = ("evtSource", "ifdestroyed")


    def __init__(self, evtSource, ifdestroyed, activationTable):
        wx.EvtHandler.__init__(self)
        KeyFunctionSink.__init__(self, activationTable)

        self.evtSource = evtSource
        self.ifdestroyed = ifdestroyed
        
        if self.evtSource is not None:
            self.evtSource.addListener(self, False)
        
        if self.ifdestroyed is not None:
            wx.EVT_WINDOW_DESTROY(self.ifdestroyed, self.OnDestroy)


    def OnDestroy(self, evt):
        self.disconnect()
        evt.Skip()


    def addAsListenerTo(self, evtSource):
        self.disconnect()
        self.evtSource = evtSource
        self.evtSource.addListener(self)

    def disconnect(self):
        """
        Disconnect from evtSource.
        """
        if self.evtSource is None:
            return
        self.evtSource.removeListener(self)
        self.evtSource = None




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
        Tries to find and return an appropriate wx.Bitmap object.
        
        An icon descriptor can be one of the following:
            - None
            - a wx.Bitmap object
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
            
            
    def getNewImageList(self):
        """
        Return a new (cloned) image list
        """
        return cloneImageList(self.iconImageList)


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
        

