import wx, wx.stc
import SystemInfo
from wxHelper import GUI_ID, getAccelPairFromKeyDown 
from collections import defaultdict

#TODO:  Multiple registers
#       Page marks
#       Alt-combinations

class ViHelper():
    """
    Base class for ViHandlers to inherit from.

    Contains code and functions that are relevent to VI emulation in
    both editor and preview mode.
    """
    # Modes
    # Current these are only (partly) implemented for the editor
    NORMAL, INSERT, VISUAL, REPLACE = range(4)

    MODE_TEXT = { 0 : u"", 1 : u"--INSERT--", 2 : u"--VISUAL--", 3 : u"REPLACE" }

    def __init__(self, ctrl):
        # ctrl is WikiTxtCtrl in the case of the editor,
        # WikiHtmlViewWk for the preview mode.
        self.ctrl = ctrl

        self.mode = 0

        self.pre_motion_key = None
        self.pre_key = None

        # When true pre_keys are ignored, as happens if a non pre modifier
        # is active
        self.block_pre_keys = False

        self.key_modifier = []
        self.key_number_modifier = [] # holds the count

        self.count = 1
        self.true_count = False

        self.hintDialog = None

        self.marks = defaultdict(dict)
        
        self.last_forward_find_cmd = None
        self.last_backward_find_cmd = None

        self.last_search_cmd = None
        self.search_start_position = []
        self.search_start_position_future = None

        self.last_cmd = None
        self.insert_action = []

        self.selection_mode = "NORMAL"

    def SetCount(self):
        self.count = 1
        self.true_count = False # True if count is specified
        if len(self.key_number_modifier) > 0:
            self.count = int("".join(map(str, self.key_number_modifier)))

            # Set a max count
            if self.count > 10000:
                self.count = 10000
            self.true_count = True

    def GetCharFromCode(self, keycode):
        """
        Converts keykeycode to unikeycode character. If no keykeycode is specified
        returns an empty string

        @param keycode: raw keycode value
        @return:        unicode character or empty string
        """
        if keycode is not None:
            return unichr(keycode)
        else:
            return u""

    def Mark(self, code):
        """
        Set marks can be any alpha charcter (a-zA-Z)

        @param code: keycode of mark to be set

        # TODO: save marks across sessions?
        """
        char = self.GetCharFromCode(code)
        if char is not None and char.isalpha():
            self._SetMark(code)
            self.visualBell("BLUE")
        else:
            self.visualBell("RED")
        self.updateViStatus()

    def _SetMark():
        """
        Dummy function to be overridden
        """

    def SetDefaultCaretColour(self):
        self.default_caret_colour = self.ctrl.GetCaretForeground()

    def GenerateKeyModifiers(self, keys):
        """
        Takes dictionary of key combinations and returns those that
        can be used to start a two key sequences

        @param keys: see self.keys in derived classes
        """
        key_mods = defaultdict(dict)
        for j in keys:
            key_mods[j] = {}
            key_mods[j] = set([i[0] for i in keys[j] if isinstance(i, tuple)])
        return key_mods

    def Repeat(self, func, count=None, arg=None):
        """
        Base function called if a command needs to be repeated
        a number of times.

        @param func: function to be run
        @param count: number of times to run the function, if not specified
                        manually will use the input count (which defaults to 1)
        @param arg: argument to run function with, can be single or multiple
                        arguments in the form of a dict
        """
        if count is None:
            count = self.count
        for i in range(count):
            if arg is not None:
                if type(arg) == dict:
                    func(**arg)
                else:
                    func(arg)
            else:
                func()

    def RunFunction(self, key, pre_motion_key=None):
        """
        Called when a key command is run

        keys is a dictionary which holds the "key" and its
        respective function.

        """
        keys = self.keys[self.mode]

        com_type, command, repeatable = keys[key]
        func, args = command

        # If a "pre motion" key has been pressed it must be followed by a motion.
        if pre_motion_key is not None:
            if com_type != 1: # Not a motion
                return False
            # Is it repeatable?
            repeatable = self.pre_keys[self.mode][pre_motion_key][2]

            # If in visual mode we don't want to change the selection start point
            if self.mode != ViHelper.VISUAL:
                # Otherwise the "pre motion" commands work by setting a start point
                # at the current positions, running the motion command and
                # finishing with a "post motion" command, i.e. deleting the
                # text that was selected.
                self.StartSelection()

        # Run the actual function
        if type(args) == dict:
            ret = func(**args)
        elif args is not None:
            ret = func(args)
        else:
            ret = func()
            
        # If "pre motion" key set run the "post motion" command
        if pre_motion_key is not None:
            # post motion function
            self.pre_keys[self.mode][pre_motion_key][1]()

        # If the command is repeatable save its type and any other settings
        if repeatable > 0:
            self.last_cmd = repeatable, key, self.count, pre_motion_key

        # Some commands should cause the mode to revert back to normal if run
        # from visual mode, others shouldn't.
        if self.mode == ViHelper.VISUAL:
            if com_type not in [1, 2]:
                self.SetMode(ViHelper.NORMAL)
            else:
                self.SelectSelection()
                if self.selection_mode == "LINE":
                    self.SelectFullLines()
 
        # Is this ever used?
        if ret is True:
            return True

        self.FlushBuffers()

    def FlushBuffers(self):
        """
        Clear modifiers and start keys so next input will be fresh

        Should be called after (most?) successful inputs and all failed
        ones.
        """
        self.pre_motion_key = None
        self.pre_key = None
        self.block_pre_keys = False
        self.key_modifier = []
        self.key_number_modifier = []
        self.updateViStatus()

    def SetSelMode(self, mode):
        self.selection_mode = mode

    def GetSelMode(self):
        return self.selection_mode

    def minmax(self, a, b):
        return min(a, b), max(a, b)

    def updateViStatus(self, force=False):
        # can this be right aligned?
        mode = self.mode
        text = u""
        if mode in self.keys:
            if (len(self.key_modifier) == 1 and \
            self.key_modifier[0] in self.key_mods[mode]) or \
                tuple(self.key_modifier) in self.keys[mode] or force:
                    mode = ViHelper.MODE_TEXT[self.mode]
                    count = u"".join(map(str, self.key_number_modifier))
                    pre_motion_key = self.GetCharFromCode(self.pre_motion_key)
                    pre_key = self.GetCharFromCode(self.pre_key)
                    key_modifier = u"".join(self.GetCharFromCode(i) \
                                                for i in self.key_modifier)

                    text = u"{0}{1}{2}{3}{4}".format( 
                            mode, count, pre_motion_key, pre_key, key_modifier)

        self.ctrl.presenter.getMainControl().statusBar.SetStatusText(text , 0)

#-----------------------------------------------------------------------------
# The following functions are common to both preview and editor mode
# -----------------------------------------------------------------------------
    def AddSearchPosition(self, pos):
        self.search_start_position.append(pos)

    def SwitchEditorPreview(self, scName=None):
        mainControl = self.ctrl.presenter.getMainControl()
        mainControl.setDocPagePresenterSubControl(scName)

    def StartSearch(self):
        # TODO: customise the search to make it more vim-like
        text = self.ctrl.GetSelectedText()
        text = text.split("\n", 1)[0]
        text = text[:30]
        self.ctrl.startIncrementalSearch(text)

    def GoForwardInHistory(self):
        pageHistDeepness = self.ctrl.presenter.getPageHistory().getDeepness()[1]
        if pageHistDeepness == 0:
            self.visualBell()
            return
        self.ctrl.presenter.getPageHistory().goInHistory(self.count)

    def GoBackwardInHistory(self):
        pageHistDeepness = self.ctrl.presenter.getPageHistory().getDeepness()[0]
        if pageHistDeepness == 0:
            self.visualBell()
            return
        self.ctrl.presenter.getPageHistory().goInHistory(-self.count)

    def ViewParents(self, direct=False):
        """
        Note: the way this works may change in the future
        """
        presenter = self.ctrl.presenter
        word = self.ctrl.presenter.getWikiWord()
 
        # If no parents give a notification and exit
        if len(presenter.getMainControl().getWikiData(). \
                    getParentRelationships(word)) == 0:
            
            self.visualBell()
            return

        path = []
        if direct:
            # Is it better to open each page? (slower but history recorded)
            for n in range(self.count):
                parents = presenter.getMainControl().getWikiData().getParentRelationships(word)
                    
                if len(parents) == 1:

                    # No need to loop if two pages are each others parents
                    # Loop will end as soon as we are about to go back to
                    # a page we were just on (3+ page loops can still occur)
                    if n > 0 and path[n-1] == word:
                        n = self.count-1
                    else:
                        word = parents[0]
                        path.append(word)

                    if n == self.count-1:
                        presenter.openWikiPage(word, forceTreeSyncFromRoot=True)
                        presenter.getMainControl().getMainAreaPanel().\
                                    showPresenter(presenter)
                        presenter.SetFocus()
                        return
                else:
                    presenter.openWikiPage(word, forceTreeSyncFromRoot=True)
                    presenter.getMainControl().getMainAreaPanel().\
                                showPresenter(presenter)
                    presenter.SetFocus()
                    break
                
        presenter.getMainControl().viewParents(word)

    def CopyWikiWord(self):
        """
        Copy current wikiword to clipboard
        """

    def SwitchTabs(self, left=False):
        """
        Switch to n(th) tab.
        Positive numbers go right, negative left.

        If tab end is reached will wrap around
        """
        n = self.count

        if left: n = -n

        mainAreaPanel = self.ctrl.presenter.getMainControl().getMainAreaPanel()
        pageCount = mainAreaPanel.GetPageCount()
        currentTabNum = mainAreaPanel.GetSelection() + 1

        if currentTabNum + n > pageCount:
            newTabNum = currentTabNum + n % pageCount
            if newTabNum > pageCount:
                newTabNum -= pageCount
        elif currentTabNum + n < 1:
            newTabNum = currentTabNum - (pageCount - n % pageCount)
            if newTabNum < 1:
                newTabNum += pageCount
        else:
            newTabNum = currentTabNum + n

        # Switch tab
        mainAreaPanel.SetSelection(newTabNum-1)
        mainAreaPanel.presenters[mainAreaPanel.GetSelection()].SetFocus()

    def CloseCurrentTab(self):
        """
        Closes currently focused tab
        """
        mainAreaPanel = self.ctrl.presenter.getMainControl().getMainAreaPanel()
        mainAreaPanel.closePresenterTab(mainAreaPanel.getCurrentPresenter())
        return True

    def OpenHomePage(self, inNewTab=False):
        """
        Opens home page.

        If inNewTab=True opens in a new forground tab
        """
        presenter = self.ctrl.presenter
        
        wikiword = presenter.getMainControl().getWikiDocument().getWikiName()

        if inNewTab:
            presenter = self.ctrl.presenter.getMainControl().\
                    createNewDocPagePresenterTab()
            presenter.switchSubControl("preview", False)


        # Now open wiki
        presenter.openWikiPage(wikiword, forceTreeSyncFromRoot=True)
        presenter.getMainControl().getMainAreaPanel().\
                    showPresenter(presenter)
        presenter.SetFocus()

#--------------------------------------------------------------------
# Misc commands
#--------------------------------------------------------------------
    def visualBell(self, colour="RED"):
        """
        Display a visual sign to alert user input has been
        recieved
        """
        sb = self.ctrl.presenter.getMainControl().GetStatusBar()

        rect = sb.GetFieldRect(0)
        if SystemInfo.isOSX():
            # needed on Mac OSX to avoid cropped text
            rect = wx._core.Rect(rect.x, rect.y - 2, rect.width, rect.height + 4)

        rect.SetPosition(sb.ClientToScreen(rect.GetPosition()))

        bell = ViVisualBell(self.ctrl, -1, rect, colour)


# I will move this to wxHelper later (MB)
try:
    class wxPopupOrFrame(wx.PopupWindow):
        def __init__(self, parent, id=-1, style=None):
            wx.PopupWindow.__init__(self, parent)

except AttributeError:
    class wxPopupOrFrame(wx.Frame):
        def __init__(self, parent, id=-1,
                style=wx.NO_BORDER|wx.FRAME_NO_TASKBAR|wx.FRAME_FLOAT_ON_PARENT):
            wx.Frame.__init__(self, parent, id, style=style)


# NOTE: is popup window available on macs yet?
class ViVisualBell(wxPopupOrFrame):
    """
    Popupwindow designed to cover the status bar. 
    
    Its intention is to give visual feedback that a command has 
    been received in cases where no other visual change is observed
    """
    
    COLOURS = {
        "RED" : wx.Colour(255, 0, 0), 
        "GREEN" : wx.Colour(0, 255, 0),
        "YELLOW" : wx.Colour(255, 255, 0),
        "BLUE" : wx.Colour(0, 0, 255),
            }
              
    
    def __init__(self, parent, id, rect, colour="RED", close_delay=100):
        wxPopupOrFrame.__init__(self, parent)
        self.SetPosition(rect.GetPosition())
        self.SetSize(rect.GetSize())
        self.SetBackgroundColour(ViVisualBell.COLOURS[colour])
        self.Show()

        wx.EVT_TIMER(self, GUI_ID.TIMER_VISUAL_BELL_CLOSE,
                self.OnClose)

        self.closeTimer = wx.Timer(self, GUI_ID.TIMER_VISUAL_BELL_CLOSE)
        self.closeTimer.Start(close_delay, True)


    def OnClose(self, evt):
        #self.timer.Stop()
        self.Destroy()
        


class ViHintDialog(wx.Frame):
    
    COLOR_YELLOW = wx.Colour(255, 255, 0);
    COLOR_GREEN = wx.Colour(0, 255, 0);
    COLOR_DARK_GREEN = wx.Colour(0, 100, 0);
    COLOR_RED = wx.Colour(255, 0, 0);
    
    def __init__(self, parent, id, viCtrl, rect, font, \
                    mainControl, tabMode=0, primary_link=None):
        # Frame title is invisible but is helpful for workarounds with
        # third-party tools
        wx.Frame.__init__(self, parent, id, u"WikidPad Hints",
                rect.GetPosition(), rect.GetSize(),
                wx.NO_BORDER | wx.FRAME_FLOAT_ON_PARENT)

        self.tabMode = tabMode

        self.parent = parent

        self.primary_link = primary_link

        self.viCtrl = viCtrl
        self.mainControl = mainControl
        self.tfInput = wx.TextCtrl(self, GUI_ID.INC_SEARCH_TEXT_FIELD,
                _(u"Follow Hint:"), style=wx.TE_PROCESS_ENTER | wx.TE_RICH)

        self.tfInput.SetFont(font)

        # Use a different colour if links are being opened in a different tab
        if tabMode == 0:
            self.colour = ViHintDialog.COLOR_GREEN
        else:
            self.colour = ViHintDialog.COLOR_DARK_GREEN

        self.tfInput.SetBackgroundColour(self.colour)
        mainsizer = wx.BoxSizer(wx.HORIZONTAL)
        mainsizer.Add(self.tfInput, 1, wx.ALL | wx.EXPAND, 0)

        self.SetSizer(mainsizer)
        self.Layout()
        self.tfInput.SelectAll()  #added for Mac compatibility
        self.tfInput.SetFocus()

        config = self.mainControl.getConfig()

        # Just use the same delays as incSearch
        self.closeDelay = 1000 * config.getint("main", "incSearch_autoOffDelay",
                0)  # Milliseconds to close or 0 to deactivate

        wx.EVT_TEXT(self, GUI_ID.INC_SEARCH_TEXT_FIELD, self.OnText)
        wx.EVT_KEY_DOWN(self.tfInput, self.OnKeyDownInput)
        wx.EVT_KILL_FOCUS(self.tfInput, self.OnKillFocus)
        wx.EVT_TIMER(self, GUI_ID.TIMER_INC_SEARCH_CLOSE,
                self.OnTimerIncSearchClose)
        wx.EVT_MOUSE_EVENTS(self.tfInput, self.OnMouseAnyInput)

        if self.closeDelay:
            self.closeTimer = wx.Timer(self, GUI_ID.TIMER_INC_SEARCH_CLOSE)
            self.closeTimer.Start(self.closeDelay, True)

#     def Close(self):
#         wx.Frame.Close(self)
#         self.txtCtrl.SetFocus()


    def OnKillFocus(self, evt):
        self.viCtrl.forgetFollowHint()
        self.Close()

    def OnText(self, evt):
        self.viCtrl.searchStr = self.tfInput.GetValue()
        link_number, link = self.viCtrl.executeFollowHint(self.tfInput.GetValue())

        if link_number < 1:
            # Nothing found
            self.tfInput.SetBackgroundColour(ViHintDialog.COLOR_RED)
        elif link_number == 1:
            # Single link found
            # launch it and finish
            self.tfInput.SetBackgroundColour(self.colour)
            self.parent._activateLink(link, tabMode=self.tabMode)
            self.Close()
        else:
            # Multiple links found
            self.tfInput.SetBackgroundColour(self.colour)

        self.primary_link = link
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
            self.viCtrl.endFollowHint()
            if self.primary_link is not None:
                self.parent._activateLink(self.primary_link, tabMode=self.tabMode)

            self.Close()
        elif accP == (wx.ACCEL_NORMAL, wx.WXK_ESCAPE):
            # Esc -> Abort inc. search, go back to start
            self.viCtrl.resetFollowHint()
            self.Close()
        elif matchesAccelPair("ContinueSearch", accP):
            foundPos = self.viCtrl.executeFollowHint(searchString)
        # do the next search on another ctrl-f
        elif matchesAccelPair("StartFollowHint", accP):
            foundPos = self.viCtrl.executeFollowHint(searchString)
        elif accP in ((wx.ACCEL_NORMAL, wx.WXK_DOWN),
                (wx.ACCEL_NORMAL, wx.WXK_PAGEDOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_PAGEDOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NEXT)):
            foundPos = self.viCtrl.executeFollowHint(searchString)
            
        elif matchesAccelPair("ActivateLink", accP) or \
                matchesAccelPair("ActivateLinkNewTab", accP) or \
                matchesAccelPair("ActivateLink2", accP) or \
                matchesAccelPair("ActivateLinkBackground", accP) or \
                matchesAccelPair("ActivateLinkNewWindow", accP):
            # ActivateLink is normally Ctrl-L
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            # ActivateLink2 is normally Ctrl-Return
            self.viCtrl.endFollowHint()
            self.Close()
            self.viCtrl.OnKeyDown(evt)
        # handle the other keys
        else:
            evt.Skip()

        if foundPos == False:
            # Nothing found
            self.tfInput.SetBackgroundColour(ViHintDialog.COLOR_YELLOW)
        else:
            # Found
            self.tfInput.SetBackgroundColour(self.colour)

        # Else don't change

    if SystemInfo.isOSX():
        # Fix focus handling after close
        def Close(self):
            wx.Frame.Close(self)
            wx.CallAfter(self.viCtrl.SetFocus)

    def OnTimerIncSearchClose(self, evt):
        self.viCtrl.endFollowHint()  # TODO forgetFollowHint() instead?
        self.Close()

 
