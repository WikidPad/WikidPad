import sets

import wx
# from  wxPython.wx import *

from StringOps import escapeForIni, unescapeForIni


class WinLayoutException(Exception):
    pass

def getOverallDisplaysSize():
    """
    Estimate the width and height of the screen real estate with all
    available displays. This assumes that all displays have same
    resolution and are positioned in a rectangular shape.
    """
    width = 0
    height = 0

    for i in xrange(wx.Display.GetCount()):
        d = wx.Display(i)
        
        rect = d.GetGeometry()
        width = max(width, rect.x + rect.width)
        height = max(height, rect.y + rect.height)

    return (width, height)


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
        
#     screenX = wxSystemSettings_GetMetric(wxSYS_SCREEN_X)
#     screenY = wxSystemSettings_GetMetric(wxSYS_SCREEN_Y)

    screenX, screenY = getOverallDisplaysSize()
    
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



def setWindowSize(win, size):
    """
    Set size of a wx.Window, but ensure that the size is valid
    """
    sizeX, sizeY = size

#     screenX = wxSystemSettings_GetMetric(wxSYS_SCREEN_X)
#     screenY = wxSystemSettings_GetMetric(wxSYS_SCREEN_Y)

    screenX, screenY = getOverallDisplaysSize()    

    # don't let the window be > than the size of the screen
    if sizeX > screenX:
        sizeX = screenX-20
    if sizeY > screenY:
        sizeY = screenY-20

    # set the size
    win.SetSize((sizeX, sizeY))


class SmartSashLayoutWindow(wx.SashLayoutWindow):
    def __init__(self, *args, **kwargs):
#         from wxPython.wx import EVT_SASH_DRAGGED

        wx.SashLayoutWindow.__init__(self, *args, **kwargs)
        
        self.effectiveSashPos = 0
        self.minimalEffectiveSashPos = 0
        self.sashPos = 0
        self.centerWindow = None
        
        self.SetMinimumSizeX(1)
        self.SetMinimumSizeY(1)

        wx.EVT_SASH_DRAGGED(self, self.GetId(), self.OnSashDragged)


    def setInnerAutoLayout(self, centerWindow):
        if self.centerWindow is not None:
            return

        self.centerWindow = centerWindow
        wx.EVT_SIZE(self, self.OnSize)


    def align(self, al):
#         from wxPython.wx import wxLAYOUT_TOP, wxLAYOUT_BOTTOM, wxLAYOUT_LEFT, \
#                 wxLAYOUT_RIGHT, wxLAYOUT_HORIZONTAL, wxLAYOUT_VERTICAL, \
#                 wxSASH_TOP, wxSASH_BOTTOM, wxSASH_LEFT, wxSASH_RIGHT
        
        if al == wx.LAYOUT_TOP:
            self.SetOrientation(wx.LAYOUT_HORIZONTAL)
            self.SetAlignment(wx.LAYOUT_TOP)
            self.SetSashVisible(wx.SASH_BOTTOM, True)
        elif al == wx.LAYOUT_BOTTOM:
            self.SetOrientation(wx.LAYOUT_HORIZONTAL)
            self.SetAlignment(wx.LAYOUT_BOTTOM)
            self.SetSashVisible(wx.SASH_TOP, True)
        elif al == wx.LAYOUT_LEFT:
            self.SetOrientation(wx.LAYOUT_VERTICAL)
            self.SetAlignment(wx.LAYOUT_LEFT)
            self.SetSashVisible(wx.SASH_RIGHT, True)
        elif al == wx.LAYOUT_RIGHT:
            self.SetOrientation(wx.LAYOUT_VERTICAL)
            self.SetAlignment(wx.LAYOUT_RIGHT)
            self.SetSashVisible(wx.SASH_LEFT, True)


    def setSashPosition(self, pos):
#         from wxPython.wx import wxSizeEvent, wxLAYOUT_VERTICAL

        if self.GetOrientation() == wx.LAYOUT_VERTICAL:
            self.SetDefaultSize((pos, 1000))
        else:
            self.SetDefaultSize((1000, pos))
            
        self.sashPos = pos
        if pos >= self.minimalEffectiveSashPos:
            self.effectiveSashPos = pos
            
        parent = self.GetParent()
        sevent = wx.SizeEvent(parent.GetSize())
        parent.ProcessEvent(sevent)

    def getSashPosition(self):
        return self.sashPos


    def setMinimalEffectiveSashPosition(self, minPos):
        self.minimalEffectiveSashPos = minPos

    def getMinimalEffectiveSashPosition(self):
        return self.minimalEffectiveSashPos

    def setEffectiveSashPosition(self, ePos):
        # TODO Check bounds
        self.effectiveSashPos = ePos

    def getEffectiveSashPosition(self):
        return self.effectiveSashPos


    def isCollapsed(self):
        return self.getSashPosition() < self.minimalEffectiveSashPos

    def collapseWindow(self):
        if not self.isCollapsed():
            self.setSashPosition(1)

    def uncollapseWindow(self):
        if self.isCollapsed():
            self.setSashPosition(self.effectiveSashPos)


    def OnSashDragged(self, evt):
#         from wxPython.wx import wxLAYOUT_VERTICAL

        # print "OnSashDragged", repr((evt.GetDragRect().width, evt.GetDragRect().height))

        if self.GetOrientation() == wx.LAYOUT_VERTICAL:
            self.setSashPosition(evt.GetDragRect().width)
        else:
            self.setSashPosition(evt.GetDragRect().height)

        evt.Skip()
        
    def OnSize(self, evt):
#         evt.Skip()
        if self.centerWindow is None:
            return
            
        wx.LayoutAlgorithm().LayoutWindow(self, self.centerWindow)


class WindowLayouter:
    """
    Helps layouting a couple of (SmartSashLayout)Window's in a main window
    """
    
    _RELATION_TO_ALIGNMENT = {
            "above": wx.LAYOUT_TOP,
            "below": wx.LAYOUT_BOTTOM,
            "left": wx.LAYOUT_LEFT,
            "right": wx.LAYOUT_RIGHT
    }

    def __init__(self, mainWindow, createWindowFunc):
        """
        mainWindow -- normally a frame in which the other winodws
            should be layouted
        createWindowFunc -- a function taking a dictionary of properties
            (especially with a "name" property describing the name/type
            of window) and a parent wx.Window object to create a new window
            of requested type with requested properties
        """
        self.mainWindow = mainWindow
        self.createWindowFunc = createWindowFunc
#         self.centerWindowProps = None
        self.windowPropsList = []  # List of window properties, first window is
                # center window. List is filled during lay. definition
                
                
        # The following 4 are filled during layout realization

        self.directMainChildren = []  # List of window objects which are
                # direct children of the mainWindow. Destroying the windows
                # in this list resets the mainWindow for a new layout
                
        self.winNameToObject = {}  # Map from window name to wx.Window object
        self.winNameToSashWindow = {}  # Map from window name to enclosing
                # sash window object
        self.winNameToWinProps = {}

#         self.toRelayout = Set()  # Set of window objects for which the
#                 # wx.LayoutAlgorithm.LayoutWindow() must be called


    def realize(self):
        """
        Called after a new layout is defined to realize it.
        """
        # TODO Allow calling realize() multiple times

        if len(self.windowPropsList) == 0:
            return  # TODO Error?
            
        centerWindowProps = self.windowPropsList[0]
        centerWindowName = centerWindowProps["name"]
        
        for pr in self.windowPropsList[1:]:
            winName = pr["name"]
            
            relTo = pr["layout relative to"]
            if relTo == centerWindowName:
                enclWin = self.mainWindow
            else:
                enclWin = self.winNameToSashWindow[relTo]
                
            sashWin = SmartSashLayoutWindow(enclWin, -1,
                wx.DefaultPosition, (30, 30), wx.SW_3DSASH)
            objWin = self.createWindowFunc(pr, sashWin)
            
            if objWin is None:
                sashWin.Destroy()
                continue

            relation = pr["layout relation"]
            
            sashPos = int(pr.get("layout sash position", "60"))
            sashEffPos = int(pr.get("layout sash effective position", "60"))

            sashWin.align(self._RELATION_TO_ALIGNMENT[relation])
            sashWin.setMinimalEffectiveSashPosition(5)  # TODO Configurable?
#             pos = self.getConfig().getint("main", "splitter_pos", 170)
#     
#             self.treeSashWindow.setSashPosition(pos)
            sashWin.setSashPosition(sashPos)
            sashWin.setEffectiveSashPosition(sashEffPos)

            self.winNameToObject[winName] = objWin
            self.winNameToSashWindow[winName] = sashWin
            self.winNameToWinProps[winName] = pr

            if enclWin is self.mainWindow:
                self.directMainChildren.append(sashWin)
            else:
                enclWin.setInnerAutoLayout(self.winNameToObject[relTo])
#                 self.toRelayout.add((enclWin, self.winNameToObject[relTo]))


        # Create center window
        winName = centerWindowProps["name"]
        objWin = self.createWindowFunc(centerWindowProps, self.mainWindow)
        if not objWin is None:
            self.winNameToObject[winName] = objWin
            self.directMainChildren.append(objWin)


    def getWindowForName(self, winName):
        """
        Return window object for name. Call this only after realize().
        Returns None if window not in layouter
        """
        return self.winNameToObject.get(winName)


    def isWindowCollapsed(self, winName):
        sashWin = self.winNameToSashWindow.get(winName)
        if sashWin is None:
            return False

        return sashWin.isCollapsed()

    def collapseWindow(self, winName):
        sashWin = self.winNameToSashWindow.get(winName)
        if sashWin is None:
            return
            
        return sashWin.collapseWindow()

    def uncollapseWindow(self, winName):
        sashWin = self.winNameToSashWindow.get(winName)
        if sashWin is None:
            return
            
        return sashWin.uncollapseWindow()


    def updateWindowProps(self, winProps):
        """
        Update window properties, esp. layout information
        """
#         if winProps is None:
#             return

        sashWindow = self.winNameToSashWindow.get(winProps["name"])
        if sashWindow is None:
            # Delete any sash window positions
            winProps.pop("layout sash position", None)
            winProps.pop("layout sash effective position", None)
        else:
            winProps["layout sash position"] = str(sashWindow.getSashPosition())
            winProps["layout sash effective position"] = \
                    str(sashWindow.getEffectiveSashPosition())


    def cleanMainWindow(self, excluded=()):
        """
        Destroy all direct children of mainWindow which were created here
        to allow a new layout.
        
        excluded -- Sequence or set of window objects which shoudl be preserved
        """
        for w in self.directMainChildren:
            if (w not in excluded) and (w.GetParent() is self.mainWindow):
                w.Destroy()


    def layout(self):
        """
        Called after a resize of the main or one of the subwindows if necessary
        """
        if len(self.windowPropsList) == 0:
            return

        wx.LayoutAlgorithm().LayoutWindow(self.mainWindow,
                self.winNameToObject[self.windowPropsList[0]["name"]])


#     def setCenterWindowProps(self, winProps):
#         """
#         Set window (its properties) which occupies the remaining space
#         in the main window
#         """
#         self.centerWindowProps = winProps

    def addWindowProps(self, winProps):
        """
        Add window props of new window which should be layed out.
        winProps is then owned by addWindowProps, do not reuse it.
        """
        relTo = winProps.get("layout relative to")
        if relTo is None:
            if len(self.windowPropsList) > 0:
                raise WinLayoutException(u"All except first window must relate "
                        u"to another window. %s is not first window" %
                        winProps["name"])
            
            self.windowPropsList.append(winProps)
        else:
            relation = winProps.get("layout relation")
            if relation not in ("above", "below", "left", "right"):
                raise WinLayoutException((u"Window %s must relate to previously "
                            u"entered window") % winProps["name"])
            # Check if relTo relates to already entered window
            for pr in self.windowPropsList:
                if pr["name"] == relTo:
                    # Valid
                    self.windowPropsList.append(winProps)
                    break
            else:
                raise WinLayoutException((u"Window %s must relate to previously "
                            u"entered window") % winProps["name"])
        

    def getWinPropsForConfig(self):
        """
        Return a string from the winProps to write to configuration
        """
        result = []
        for pr in self.windowPropsList:
            self.updateWindowProps(pr)
            result.append(winPropsToString(pr))
        
        return ";".join(result)
        
    def setWinPropsByConfig(self, cfstr):
        """
        Create window properties by a string cfstr as returned
        by getWinPropsForConfig(). This method is an alternative to
        addWindowProps().
        """
        for ps in cfstr.split(";"):
            winProps = stringToWinprops(ps)
            self.addWindowProps(winProps)




def winPropsToString(winProps):
    return "&".join([escapeForIni(k, ";:&") + ":" + escapeForIni(v, ";:&")
            for k, v in winProps.iteritems()])


def stringToWinprops(s):
    if type(s) is unicode:
        s = str(s)

    items = [(unescapeForIni(item.split(":", 1)[0]),
            unescapeForIni(item.split(":", 1)[1])) for item in s.split("&")]
    
    result = {}
    for k, v in items:
        result[k] = v
        
    return result


            
