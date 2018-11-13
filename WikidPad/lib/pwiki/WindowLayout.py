import traceback

import wx, wx.adv

from .MiscEvent import MiscEventSourceMixin
from .StringOps import escapeForIni, unescapeForIni

from .SystemInfo import isLinux

from .wxHelper import LayerSizer, ProxyPanel


class WinLayoutException(Exception):
    pass


_INITIAL_DISPLAY_CLIENT_SIZE = None

def initiateAfterWxApp():
    """
    Called after wx.App was created to do some intialization
    """
    global _INITIAL_DISPLAY_CLIENT_SIZE

    _INITIAL_DISPLAY_CLIENT_SIZE = getOverallDisplaysClientRect()
    
    if _INITIAL_DISPLAY_CLIENT_SIZE.width < 10 or \
            _INITIAL_DISPLAY_CLIENT_SIZE.height < 10:
        
        _INITIAL_DISPLAY_CLIENT_SIZE = wx.Rect(0, 0, 800, 600)


def getOverallDisplaysClientSize():
    """
    Estimate the rectangle of the screen real estate with all
    available displays. This assumes that all displays have same
    resolution and are positioned in a rectangular shape.
    """
    global _INITIAL_DISPLAY_CLIENT_SIZE

    # TODO: Find solution for multiple displays with taskbar always visible

    if wx.Display.GetCount() == 1:
        return wx.GetClientDisplayRect()

    # The following may be wrong if taskbar is always visible
    width = 0
    height = 0

    for i in range(wx.Display.GetCount()):
        d = wx.Display(i)
        
        rect = d.GetGeometry()
        width = max(width, rect.x + rect.width)
        height = max(height, rect.y + rect.height)

    # May workaround a bug
    if (width < 10 or height < 10) and (_INITIAL_DISPLAY_CLIENT_SIZE is not None):
        return _INITIAL_DISPLAY_CLIENT_SIZE

    return wx.Rect(0, 0, width, height)



def getOverallDisplaysClientRect():
    """
    Estimate the rectangle of the screen real estate with all
    available displays. This assumes that all displays have same
    resolution and are positioned in a rectangular shape.
    """
    global _INITIAL_DISPLAY_CLIENT_SIZE

    # TODO: Find solution for multiple displays with taskbar always visible

    if wx.Display.GetCount() == 1:
        return wx.GetClientDisplayRect()

    left = 0
    top = 0
    right = 0 # Actually first position outside of screen to the right
    bottom = 0 # First pos. outside downwards

    for i in range(wx.Display.GetCount()):
        d = wx.Display(i)
        
        rect = d.GetGeometry()
        
        dright = rect.x + rect.width
        dbottom = rect.y + rect.height
        
        left = min(left, rect.x)
        top = min(top, rect.y)
        right = max(right, dright)
        bottom = max(bottom, dbottom)


    width = right - left
    height = bottom - top

    # May workaround a bug
    if (width < 10 or height < 10) and (_INITIAL_DISPLAY_CLIENT_SIZE is not None):
        return _INITIAL_DISPLAY_CLIENT_SIZE

    return wx.Rect(left, top, width, height)





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
        currentX, currentY = win.GetPosition()
        
#     screenX, screenY = getOverallDisplaysSize()
    clRect = getOverallDisplaysClientRect()
    
    clRectRight = clRect.x + clRect.width
    clRectBottom = clRect.y + clRect.height
    
    # fix any crazy screen positions
    if currentX < clRect.x:
        currentX = clRect.x + 10
    if currentY < clRect.y:
        currentY = clRect.y + 10
    if currentX >= clRectRight:
        currentX = clRectRight - 100
    if currentY >= clRectBottom:
        currentY = clRectBottom - 100

    if fullVisible:
        sizeX, sizeY = win.GetSize()
        if currentX + sizeX > clRectRight:
            currentX = clRectRight - sizeX
        if currentY + sizeY > clRectBottom:
            currentY = clRectBottom - sizeY

    win.SetPosition((currentX, currentY))



def setWindowSize(win, size=None):
    """
    Set size of a wx.Window, but ensure that the size is valid
    """
    if size is not None:
        sizeX, sizeY = size
    else:
        sizeX, sizeY = win.GetSize()

#     screenX, screenY = getOverallDisplaysSize()    
    clRect = getOverallDisplaysClientRect()

    # don't let the window be > than the size of the screen
    if sizeX > clRect.width:
        sizeX = clRect.width - 20
    if sizeY > clRect.height:
        sizeY = clRect.height - 20

    # set the size
    win.SetSize((sizeX, sizeY))


def setWindowClientSize(win, size):
    """
    Similar to setWindowSize(), but sets the client size of the window
    """
    sizeX, sizeY = size

#     screenX, screenY = getOverallDisplaysSize()    
    clRect = getOverallDisplaysClientRect()

    # don't let the window be > than the size of the screen
    if sizeX > clRect.width:
        sizeX = clRect.width - 20
    if sizeY > clRect.height:
        sizeY = clRect.height - 20

    # set the size
    win.SetClientSize((sizeX, sizeY))



def getRelativePositionTupleToAncestor(win, ancestor):
    """
    Calculates relative pixel position of win to ancestor where ancestor
    is either parent, grandparent, grandgrandparent ... or None for
    absolute position.
    Returns a tuple with the position.
    """
    resultx = 0
    resulty = 0
    while win is not None and win is not ancestor:
        x, y = win.GetPosition()
        resultx += x
        resulty += y
        
        win = win.GetParent()

    return (resultx, resulty)



#     m_sashCursorWE = new wxCursor(wxCURSOR_SIZEWE);
#     m_sashCursorNS = new wxCursor(wxCURSOR_SIZENS);

SASH_TOP = 0
SASH_RIGHT = 1
SASH_BOTTOM = 2
SASH_LEFT = 3
SASH_NONE = 100


class SmartSashLayoutWindow(wx.adv.SashLayoutWindow):
    def __init__(self, *args, **kwargs):
        wx.adv.SashLayoutWindow.__init__(self, *args, **kwargs)
        
        self.effectiveSashPos = 0
        self.minimalEffectiveSashPos = 0
        self.sashPos = 0
        self.centerWindow = None
        self.layoutWorkSize = None
        
        self.SetMinimumSizeX(1)
        self.SetMinimumSizeY(1)

        self.Bind(wx.adv.EVT_SASH_DRAGGED, self.OnSashDragged) #self.GetId(), )

        if isLinux():
            self._CURSOR_SIZEWE = wx.Cursor(wx.CURSOR_SIZEWE)
            self._CURSOR_SIZENS = wx.Cursor(wx.CURSOR_SIZENS)
            self.Bind(wx.EVT_MOTION, self.MouseMotion)
            self.Bind(wx.EVT_LEAVE_WINDOW, self.OnMouseLeave)
        
    if isLinux():

        def MouseMotion(self, evt):
            if evt.Moving():
                x, y = evt.GetPosition()
                sashHit = self.SashHitTest(x, y)
                
                if sashHit == SASH_NONE:
                    self.SetCursor(wx.NullCursor)
                elif sashHit == SASH_LEFT or sashHit == SASH_RIGHT:
                    self.SetCursor(self._CURSOR_SIZEWE)
                elif sashHit == SASH_TOP or sashHit == SASH_BOTTOM:
                    self.SetCursor(self._CURSOR_SIZENS)
                    
            evt.Skip()
    
        def OnMouseLeave(self, evt):
            self.SetCursor(wx.NullCursor)
            evt.Skip()


    def setInnerAutoLayout(self, centerWindow):
        if self.centerWindow is not None:
            return

        self.centerWindow = centerWindow
        self.Bind(wx.EVT_SIZE, self.OnSize)


    def align(self, al):
        if al == wx.adv.LAYOUT_TOP:
            self.SetOrientation(wx.adv.LAYOUT_HORIZONTAL)
            self.SetAlignment(wx.adv.LAYOUT_TOP)
            self.SetSashVisible(wx.adv.SASH_BOTTOM, True)
        elif al == wx.adv.LAYOUT_BOTTOM:
            self.SetOrientation(wx.adv.LAYOUT_HORIZONTAL)
            self.SetAlignment(wx.adv.LAYOUT_BOTTOM)
            self.SetSashVisible(wx.adv.SASH_TOP, True)
        elif al == wx.adv.LAYOUT_LEFT:
            self.SetOrientation(wx.adv.LAYOUT_VERTICAL)
            self.SetAlignment(wx.adv.LAYOUT_LEFT)
            self.SetSashVisible(wx.adv.SASH_RIGHT, True)
        elif al == wx.adv.LAYOUT_RIGHT:
            self.SetOrientation(wx.adv.LAYOUT_VERTICAL)
            self.SetAlignment(wx.adv.LAYOUT_RIGHT)
            self.SetSashVisible(wx.adv.SASH_LEFT, True)


    def setSashPosition(self, pos):
        parent = self.GetParent()
        if isinstance(parent, SmartSashLayoutWindow):
            ws = parent.layoutWorkSize
            if ws is None:
                cwidth, cheight = parent.GetClientSize()
            else:
                cwidth, cheight = ws
        else:
            cwidth, cheight = parent.GetClientSize()

        if self.GetOrientation() == wx.adv.LAYOUT_VERTICAL:
            if cwidth > 10:
                pos = min(pos, cwidth - 5)
        else:
            if cheight > 10:
                pos = min(pos, cheight - 5)

        if self.GetOrientation() == wx.adv.LAYOUT_VERTICAL:
            self.SetDefaultSize((pos, 1000))
            self.layoutWorkSize = (pos, cheight)
        else:
            self.SetDefaultSize((1000, pos))
            self.layoutWorkSize = (cwidth, pos)

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

    def expandWindow(self, flag=True):
        if flag and self.isCollapsed():
            self.setSashPosition(self.effectiveSashPos)
        elif not flag and not self.isCollapsed():
            self.setSashPosition(1)

    def collapseWindow(self):
        if not self.isCollapsed():
            self.setSashPosition(1)


    def OnSashDragged(self, evt):
        # print "OnSashDragged", repr((evt.GetDragRect().width, evt.GetDragRect().height))

        if self.GetOrientation() == wx.adv.LAYOUT_VERTICAL:
            self.setSashPosition(evt.GetDragRect().width)
        else:
            self.setSashPosition(evt.GetDragRect().height)

        evt.Skip()
        
    def OnSize(self, evt):
        self.layoutWorkSize = None
        if self.centerWindow is None:
            return
            
        wx.adv.LayoutAlgorithm().LayoutWindow(self, self.centerWindow)


class WindowSashLayouter:
    """
    Helps layouting a couple of (SmartSashLayout)Window's in a main window
    """
    
    _RELATION_TO_ALIGNMENT = {
            "above": wx.adv.LAYOUT_TOP,
            "below": wx.adv.LAYOUT_BOTTOM,
            "left": wx.adv.LAYOUT_LEFT,
            "right": wx.adv.LAYOUT_RIGHT
    }

    def __init__(self, mainWindow, createWindowFunc):
        """
        mainWindow -- normally a frame in which the other windows
            should be layouted
        createWindowFunc -- a function taking a dictionary of properties
            (especially with a "name" property describing the name/type
            of window) and a parent wxWindow object to create a new window
            of requested type with requested properties
        """
        self.mainWindow = mainWindow
        self.createWindowFunc = createWindowFunc
#         self.centerWindowProps = None
        self.windowPropsList = []  # List of window properties, first window is
                # center window. List is filled during lay. definition

        self._resetWinStructure()

#         self.toRelayout = Set()  # Set of window objects for which the
#                 # wxLayoutAlgorithm.LayoutWindow() must be called


    def _resetWinStructure(self):
        # The following 4 are filled during layout realization

        self.directMainChildren = []  # List of window objects which are
                # direct children of the mainWindow. Destroying the windows
                # in this list resets the mainWindow for a new layout

        self.winNameToProxy = {}
        self.winNameToObject = {}  # Map from window name to wxWindow object
        self.winNameToSashWindow = {}  # Map from window name to enclosing
                # sash window object
        self.winNameToWinProps = {}
        

    def realize(self, proxiedCachedWindows=None):
        """
        Called after a new layout is defined to realize it.
        """
        # TODO Allow calling realize() multiple times

        if len(self.windowPropsList) == 0:
            return  # TODO Error?
            
        if proxiedCachedWindows is None:
            proxiedCachedWindows = {}
            
        self._resetWinStructure()

        centerWindowProps = self.windowPropsList[0]
        centerWindowName = centerWindowProps["name"]

        for pr in self.windowPropsList[1:]:
            winName = pr["name"]
            
            relTo = pr["layout relative to"]
            if relTo == centerWindowName:
                enclWin = self.mainWindow
            else:
                try:
                    enclWin = self.winNameToSashWindow[relTo]
                except KeyError:
                    enclWin = self.mainWindow

            sashWin = SmartSashLayoutWindow(enclWin, -1,
                wx.DefaultPosition, (30, 30), wx.adv.SW_3DSASH)
            
            proxyWin = proxiedCachedWindows.get(winName)
            if proxyWin is not None:
                proxyWin.Reparent(sashWin)    # TODO Reparent not available for all OS'
                objWin = proxyWin.getSubWindow()
                del proxiedCachedWindows[winName]
            else:
                proxyWin = ProxyPanel(sashWin)
                objWin = self.createWindowFunc(pr, proxyWin)
    
                if objWin is None:
                    proxyWin.Destroy()
                    sashWin.Destroy()
                    continue
    
                proxyWin.setSubWindow(objWin)

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

            self.winNameToProxy[winName] = proxyWin
            self.winNameToObject[winName] = objWin
            self.winNameToSashWindow[winName] = sashWin
            self.winNameToWinProps[winName] = pr

            if enclWin is self.mainWindow:
                self.directMainChildren.append(sashWin)
            else:
#                 enclWin.setInnerAutoLayout(self.winNameToObject[relTo])
                enclWin.setInnerAutoLayout(self.winNameToProxy[relTo])


        # Create center window
        winName = centerWindowProps["name"]
        
        proxyWin = proxiedCachedWindows.get(winName)
        
        if proxyWin is not None:
            proxyWin.Reparent(self.mainWindow)    # TODO Reparent not available for all OS'
            objWin = proxyWin.getSubWindow()
            del proxiedCachedWindows[winName]
        else:
            proxyWin = ProxyPanel(self.mainWindow)
            objWin = self.createWindowFunc(centerWindowProps, proxyWin)

            if objWin is None:
                proxyWin.Destroy()
                return

            proxyWin.setSubWindow(objWin)

#         objWin = self.createWindowFunc(centerWindowProps, self.mainWindow)
        
        if not objWin is None:
#             proxyWin.setSubWindow(objWin)
            self.winNameToProxy[winName] = proxyWin
            self.winNameToObject[winName] = objWin
            self.directMainChildren.append(proxyWin)



    def realizeNewLayoutByCf(self, layoutCfStr):
        """
        Create a new window layouter according to the
        layout configuration string layoutCfStr. Try to reuse and reparent
        existing windows.
        BUG: Reparenting seems to disturb event handling for tree events and
            isn't available for all OS'
        """
        # Reparent reusable windows so they aren't destroyed when
        #   cleaning main window
        # TODO Reparent not available for all OS'
        self.setWinPropsByConfig(layoutCfStr)
        self.preserveSashPositions()       

        proxiedCachedWindows = {}
        for n, w in self.winNameToProxy.items():
            proxiedCachedWindows[n] = w
            w.Reparent(self.mainWindow)    # TODO Reparent not available for all OS'

        self.cleanMainWindow(list(proxiedCachedWindows.values()))


        self.realize(proxiedCachedWindows)

        # Destroy windows which weren't reused
        # TODO Call close method of object window if present
        for n, w in proxiedCachedWindows.items():
            w.close()
            w.Destroy()


    def close(self):
        for w in self.winNameToObject.values():
            w.close()


    def getWindowByName(self, winName):
        """
        Return window object for name. Call this only after realize().
        Returns None if window not in layouter
        """
        return self.winNameToObject.get(winName)
        
    def focusWindow(self, winName):
        """
        Set focus to window named winName
        """
        w = self.getWindowByName(winName)
        
        if w is None:
            return
        
        w.SetFocus()


    def isWindowCollapsed(self, winName):
        sashWin = self.winNameToSashWindow.get(winName)
        if sashWin is None:
            return True

        return sashWin.isCollapsed()


    def containsWindow(self, winName):
        return winName in self.winNameToSashWindow


    def expandWindow(self, winName, flag=True):
        sashWin = self.winNameToSashWindow.get(winName)
        if sashWin is None:
            return
            
        return sashWin.expandWindow(flag)

    def collapseWindow(self, winName):
        sashWin = self.winNameToSashWindow.get(winName)
        if sashWin is None:
            return
            
        return sashWin.collapseWindow()


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
            if (w not in excluded):    # ???  and (w.GetParent() is self.mainWindow):
                w.Destroy()


    def layout(self):
        """
        Called after a resize of the main or one of the subwindows if necessary
        """
        if len(self.windowPropsList) == 0:
            return
            
        wx.adv.LayoutAlgorithm().LayoutWindow(self.mainWindow,
                self.winNameToProxy[self.windowPropsList[0]["name"]])


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
                raise WinLayoutException("All except first window must relate "
                        "to another window. %s is not first window" %
                        winProps["name"])

            self.windowPropsList.append(winProps)
        else:
            relation = winProps.get("layout relation")
            if relation not in ("above", "below", "left", "right"):
                raise WinLayoutException(("Window %s must relate to previously "
                            "entered window") % winProps["name"])
            # Check if relTo relates to already entered window
            for pr in self.windowPropsList:
                if pr["name"] == relTo:
                    # Valid
                    self.windowPropsList.append(winProps)
                    break
            else:
                raise WinLayoutException(("Window %s must relate to previously "
                            "entered window") % winProps["name"])
        

    def preserveSashPositions(self):
        """
        Must be called after setWinPropsByConfig() or addWindowProps() to
        modify the added window sash sizes before realize is called.
        It uses self.winNameToWinProps to fill in sash sizes of current
        layout if existing.
        """
        for newProps in self.windowPropsList:
            winName = newProps.get("name")
            currProps = self.winNameToWinProps.get(winName)
            if currProps is None:
                continue

            self.updateWindowProps(currProps)
        
            if "layout sash position" in currProps and \
                    "layout sash position" in newProps:
                newProps["layout sash position"] = \
                        currProps["layout sash position"]

            if "layout sash effective position" in currProps and \
                    "layout sash effective position" in newProps:
                newProps["layout sash effective position"] = \
                        currProps["layout sash effective position"]


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
        self.windowPropsList = []
        for ps in cfstr.split(";"):
            winProps = stringToWinprops(ps)
            self.addWindowProps(winProps)



def winPropsToString(winProps):
    return "&".join([escapeForIni(k, ";:&") + ":" + escapeForIni(v, ";:&")
            for k, v in winProps.items()])


def stringToWinprops(s):
    if type(s) is str:
        s = str(s)

    items = [(unescapeForIni(item.split(":", 1)[0]),
            unescapeForIni(item.split(":", 1)[1])) for item in s.split("&")]
    
    result = {}
    for k, v in items:
        result[k] = v
        
    return result


def calculateMainWindowLayoutCfString(config):
    newLayoutMainTreePosition = config.getint("main",
        "mainTree_position", 0)
    newLayoutViewsTreePosition = config.getint("main",
        "viewsTree_position", 0)
    newLayoutDocStructurePosition = config.getint("main",
        "docStructure_position", 0)
    newLayoutTimeViewPosition = config.getint("main",
        "timeView_position", 0)    

    mainPos = {0:"left", 1:"right", 2:"above", 3:"below"}\
            [newLayoutMainTreePosition]

    # Set layout for main tree
    layoutCfStr = "name:main area panel;"\
            "layout relation:%s&layout relative to:main area panel&name:maintree&"\
            "layout sash position:170&layout sash effective position:170" % \
            mainPos

    # Add layout for Views tree
    if newLayoutViewsTreePosition > 0:
        viewsPos = {1:"above", 2:"below", 3:"left", 4:"right"}\
                [newLayoutViewsTreePosition]
        layoutCfStr += (";layout relation:%s&layout relative to:maintree&name:viewstree&"
                "layout sash position:60&layout sash effective position:60") % \
                viewsPos

    if newLayoutTimeViewPosition > 0:
        timeViewPos = {1:"left", 2:"right", 3:"above", 4:"below"}\
            [newLayoutTimeViewPosition]
        layoutCfStr += ";layout relation:%s&layout relative to:main area panel&name:time view&"\
                    "layout sash position:120&layout sash effective position:120" % \
                    timeViewPos

    # Layout for doc structure window
    if newLayoutDocStructurePosition > 0:
        docStructPos = {1:"left", 2:"right", 3:"above", 4:"below"}\
            [newLayoutDocStructurePosition]
        layoutCfStr += ";layout relation:%s&layout relative to:main area panel&name:doc structure&"\
                    "layout sash position:120&layout sash effective position:120" % \
                    docStructPos

    # Layout for log window
    layoutCfStr += ";layout relation:below&layout relative to:main area panel&name:log&"\
                "layout sash position:1&layout sash effective position:120"
                

    # It may be better to load this only when vi mode is started
    layoutCfStr += ";layout relation:below&layout relative to:main area panel&name:vi input&"\
                "layout sash position:0&layout sash effective position:120"

    return layoutCfStr





class LayeredControlPresenter(MiscEventSourceMixin):
    """
    Controls appearance of multiple controls laying over each other in
    one panel or notebook.
    """
    def __init__(self):
        self.subControls = {}
        self.lastVisibleCtrlName = None
        self.visible = False
        self.shortTitle = ""
        self.longTitle = ""

    def setSubControl(self, scName, sc):
        self.subControls[scName] = sc
        if sc is None:
            del self.subControls[scName]

    def getSubControl(self, scName):
        return self.subControls.get(scName)


    def switchSubControl(self, scName):
        """
        Make the chosen subcontrol visible, all other invisible
        """
        try:
            subControl = self.subControls[scName]
        except KeyError:
            traceback.print_exc()
            return

        
        if self.visible and self.lastVisibleCtrlName != scName:
            # First show subControl scName, then hide the others
            # to avoid flicker
            self.subControls[scName].setLayerVisible(True, scName)
            for n, c in self.subControls.items():
#                 if n != scName:
                if c is not subControl:
                    c.setLayerVisible(False, n)

        self.lastVisibleCtrlName = scName
        self.setTitle(self.shortTitle)


    def getCurrentSubControlName(self):
        return self.lastVisibleCtrlName
        
    def getCurrentSubControl(self):
        return self.subControls.get(self.lastVisibleCtrlName)
        
    def hasSubControl(self, scName):
        return scName in self.subControls

    def setLayerVisible(self, vis, scName=""):
        if self.visible == vis:
            return

        if vis:
            for n, c in self.subControls.items():
                c.setLayerVisible(n == self.lastVisibleCtrlName, n)
        else:
            for n, c in self.subControls.items():
                c.setLayerVisible(False, n)

        self.visible = vis
        
    def getLayerVisible(self):
        return self.visible
        
    def close(self):
        for c in frozenset(list(self.subControls.values())): # Same control may appear
                            # multiple times
            c.close()

        
    def SetFocus(self):
        self.subControls[self.lastVisibleCtrlName].SetFocus()
        
    def setTitle(self, shortTitle):
        self.shortTitle = shortTitle
        self.longTitle = shortTitle

    def getShortTitle(self):
        return self.shortTitle

    def getLongTitle(self):
        return self.longTitle


class LayeredControlPanel(wx.Panel, LayeredControlPresenter):
    """
    A layered presenter which is itself a wx.Panel and contains
    the subcontrols.
    """
    def __init__(self, parent, id=-1):
        wx.Panel.__init__(self, parent, id, style=wx.NO_BORDER)
        LayeredControlPresenter.__init__(self)

        self.SetSizer(LayerSizer())


    def setSubControl(self, scName, sc):
        oldSc = self.getSubControl(scName)
        if oldSc is not None:
            self.GetSizer().Detach(oldSc)
            oldSc.close()

        LayeredControlPresenter.setSubControl(self, scName, sc)
        if sc is not None:
            self.GetSizer().Add(sc)


    def switchSubControl(self, scName, gainFocus=False):
        """
        Make the chosen subcontrol visible, all other invisible
        """
        try:
            subControl = self.subControls[scName]
        except KeyError:
            traceback.print_exc()
            return

        # First show subControl scName, then hide the others
        # to avoid flicker
        if self.visible and self.lastVisibleCtrlName != scName:
            self.subControls[scName].setLayerVisible(True, scName)

        self.subControls[scName].Show(True)

        for n, c in self.subControls.items():
#             if n != scName:
            if c is not subControl:
                if self.visible:
                    c.setLayerVisible(False, n)
                c.Show(False)

        if gainFocus:
            self.subControls[scName].SetFocus()

        self.lastVisibleCtrlName = scName
        self.setTitle(self.shortTitle)   #?

    def getTabContextMenu(self):
        sc = self.getCurrentSubControl()
        if sc is None:
            return None
        
        return sc.getTabContextMenu()


    def SetFocus(self):
        try:
            self.subControls[self.lastVisibleCtrlName].SetFocus()
        except KeyError:
            wx.Panel.SetFocus(self)

    def setTitle(self, shortTitle):
        LayeredControlPresenter.setTitle(self, shortTitle)
        self.fireMiscEventProps({"changed presenter title": True,
                "title": shortTitle})


class StorablePerspective:
    """
    Interface for window objects which can save and restore their state
    """
    
    def getPerspectiveType(self):
        """
        Returns a unistring which identifies the basic type of window.
        Currently this is always empty, later versions may have different
        types. The idea is to create a central registry which calls
        appropriate factory function based on this type
        """
        raise NotImplementedError
        
    def getStoredPerspective(self):
        """
        Returns a unistring describing the contents of the window for
        later recreation or None if this window can't be stored.
        If a window doesn't need to store additional perspective data,
        return empty unistring
        """
        raise NotImplementedError
        
    def setByStoredPerspective(self, perspectType, data, typeFactory):
        """
        Modify this window from the unistring  data  which was previously returned
        by a call to getStoredPerspective() and return it. May raise
        NotImplementedError if in-place change is not supported.
        
        perspectType -- Unistring identifier previously returned by
            getPerspectiveType()
        data -- Unistring with data for reconstruction
        typeFactory -- Factory function to create subwindows or None
            (see below)
        
        If the window contains child windows with own perspective data,
        the type factory is used.  typeFactory  is a function:

            typeFactory(parent, perspectType, data, typeFactory)
            
        where:
                
            parent -- Designated parent window for newly created window
            perspectType -- Unistring type of desired child window
            data -- Unistring perspective data
            typeFactory -- Normally the same factory function, may be
                another one or None in special cases
                
        
        typeFactory is allowed to be None if it is sure that no child windows
        need to be created from perspective data.
        """
        raise NotImplementedError
        
    def deleteForNewPerspective(self):
        """
        When a new perspective is set for a parent window it has to remove existing
        children. It does that by detaching this window and later calling this method.
        By default the method just destroys this window. Overridden methods
        should call this base method
        """
        self.Destroy()



#     @staticmethod
#     def createFromStoredPerspective(parent, perspectType, data, typeFactory):
#         """
#         Create a window from the unistring  data  which was previously returned
#         by a call to getStoredPerspective() and return it. May return None
#         in case of an error, otherwise the returned window has parent  parent.
#         
#         If the window contains child windows with own perspective data,
#         the type factory is used.  typeFactory  is a function which takes
#         a perspective type identifier as single parameter and returns either
#         a class or an object implementing StorablePerspective interface
#         or None if the requested perspective type is unknown.
#         
#         typeFactory  is allowed to be None if it is sure that no child windows
#         need to be created from perspective data.
#         """
#         raise NotImplementedError


