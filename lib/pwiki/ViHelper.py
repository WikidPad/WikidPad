import wx, wx.stc
import SystemInfo
from wxHelper import GUI_ID, getAccelPairFromKeyDown, getTextFromClipboard
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

    MODE_TEXT = { 
                    0 : u"", 
                    1 : u"--INSERT--", 
                    2 : u"--VISUAL--", 
                    3 : u"--REPLACE" 
                }

    KEY_BINDINGS = {
                        u"!" : 33,
                        u"\"" : 34,
                        u"#" : 35,
                        u"$" : 36,
                        u"%" : 37,
                        u"&" : 38,
                        u"'" : 39,
                        u"(" : 40,
                        u")" : 41,
                        u"*" : 42,
                        u"+" : 43,
                        u"," : 44,
                        u"-" : 45,
                        u"." : 46,
                        u"/" : 47,
                        u"0" : 48,
                        u"1" : 49,
                        u"2" : 50,
                        u"3" : 51,
                        u"4" : 52,
                        u"5" : 53,
                        u"6" : 54,
                        u"7" : 55,
                        u"8" : 56,
                        u"9" : 57,
                        u":" : 58,
                        u";" : 59,
                        u"<" : 60,
                        u"=" : 61,
                        u">" : 62,
                        u"?" : 63,
                        u"@" : 64,
                        u"A" : 65,
                        u"B" : 66,
                        u"C" : 67,
                        u"D" : 68,
                        u"E" : 69,
                        u"F" : 70,
                        u"G" : 71,
                        u"H" : 72,
                        u"I" : 73,
                        u"J" : 74,
                        u"K" : 75,
                        u"L" : 76,
                        u"M" : 77,
                        u"N" : 78,
                        u"O" : 79,
                        u"P" : 80,
                        u"Q" : 81,
                        u"R" : 82,
                        u"S" : 83,
                        u"T" : 84,
                        u"U" : 85,
                        u"V" : 86,
                        u"W" : 87,
                        u"X" : 88,
                        u"Y" : 89,
                        u"Z" : 90,
                        u"[" : 91,
                        u"\\" : 92,
                        u"]" : 93,
                        u"^" : 94,
                        u"_" : 95,
                        u"`" : 96,
                        u"a" : 97,
                        u"b" : 98,
                        u"c" : 99,
                        u"d" : 100,
                        u"e" : 101,
                        u"f" : 102,
                        u"g" : 103,
                        u"h" : 104,
                        u"i" : 105,
                        u"j" : 106,
                        u"k" : 107,
                        u"l" : 108,
                        u"m" : 109,
                        u"n" : 110,
                        u"o" : 111,
                        u"p" : 112,
                        u"q" : 113,
                        u"r" : 114,
                        u"s" : 115,
                        u"t" : 116,
                        u"u" : 117,
                        u"v" : 118,
                        u"w" : 119,
                        u"x" : 120,
                        u"y" : 121,
                        u"z" : 122,
                        u"{" : 123,
                        u"|" : 124,
                        u"}" : 125,
                        u"~" : 126,
                    }
                            

    def __init__(self, ctrl):
        # ctrl is WikiTxtCtrl in the case of the editor,
        # WikiHtmlViewWk for the preview mode.
        self.ctrl = ctrl

        self.mode = 0

        self._motion = []
        self._motion_wildcard = []
        self._wildcard = []
        self._acceptable_keys = None
        self.key_inputs = []

        self.key_number_modifier = [] # holds the count

        self.count = 1
        self.true_count = False

        self.hintDialog = None

        self.marks = defaultdict(dict)
        
        self.last_find_cmd = None

        self.last_search_args = None
        self.last_search_cmd = None
        self.jumps = []
        self.current_jump = -1

        self.last_cmd = None
        self.insert_action = []

        self.selection_mode = "NORMAL"
                    
        # The following dictionary holds the menu shortcuts that have been
        # disabled upon entering ViMode
        self.menuShortCuts = {}

        self.register = ViRegister(self.ctrl)

    def SetCount(self):
        self.count = 1
        self.true_count = False # True if count is specified
        if len(self.key_number_modifier) > 0:
            self.count = int("".join(map(str, self.key_number_modifier)))

            # Set a max count
            if self.count > 10000:
                self.count = 10000
            self.true_count = True

    def SetNumber(self, n):
        # TODO: move to ViHelper
        # If 0 is first modifier it is a command
        if len(self.key_number_modifier) < 1 and n == 0:
            return False
        self.key_number_modifier.append(n)
        self.updateViStatus(True)
        return True

    def GetCharFromCode(self, keycode):
        """
        Converts keykeycode to unikeycode character. If no keykeycode is specified
        returns an empty string.

        @param keycode: Raw keycode value

        @return:        Requested character
        """
        # TODO: Rewrite
        if keycode is not None:
            # If we have a tuple the keycode includes a modifier, e.g. ctrl
            if type(keycode) == tuple:
                return "{0}-{1}".format(keycode[0], unichr(keycode[1]))
            try:
                return unichr(keycode)
            except TypeError:
                return keycode
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
        
    def GenerateMotionKeys(self, keys):
        key_mods = defaultdict(dict)
        for mode in keys:
            key_mods[mode] = set()
            for accel in keys[mode]:
                if keys[mode][accel][0] == 1:
                        key_mods[mode].add(accel)

        return key_mods

    def GenerateKeyModifiers(self, keys):
        """
        Takes dictionary of key combinations and returns all possible
        key starter combinations

        @param keys: see self.keys in derived classes
        """
        key_mods = defaultdict(dict)
        for mode in keys:
            key_mods[mode] = defaultdict(set)
            for accel in keys[mode]:
                if len(accel) > 1:
                    for i in range(1, len(accel)):
                        if i == 1:
                            key_mods[mode][(accel[0],)].add(accel[1])
                        else:
                            key_mods[mode][accel[:i]].add(accel[i])

        return key_mods

    def GenerateKeyAccelerators(self, keys):
        """
        This could be improved
        """
        key_accels = set()
        for j in keys:
            for accels in keys[j]:
                for accel in accels:
                    if type(accel) == tuple and len(accel) > 1:
                        key_accels.add("{0}-{1}".format(accel[0], unichr(accel[1]).upper()))
                
        return key_accels

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

    def RunKeyChain(self, key_chain, mode):
        self.updateViStatus()
        if key_chain in self.keys[mode]:
            self.RunFunction(key_chain)
            self.FlushBuffers()
            return True
        else:
            if key_chain in self.key_mods[mode]:
                # TODO: better fix
                try:
                    self.ctrl.SetCaretForeground(wx.Colour(0, 255, 255))
                except:
                    pass
                self._acceptable_keys = self.key_mods[mode][key_chain]
                return True
        return False

    def RunFunction(self, key, motion=None, motion_wildcard=None, 
                                                        wildcards=None):
        """
        Called when a key command is run

        keys is a dictionary which holds the "key" and its
        respective function.

        """
        if motion is None:
            motion = self._motion
        if wildcards is None:
            wildcards = self._wildcard
        if motion_wildcard is None:
            motion_wildcard = tuple(self._motion_wildcard)

        def RunFunc(func, args):
            if type(args) == dict:
                ret = func(**args)
            elif args is not None:
                ret = func(args)
            else:
                ret = func()

        keys = self.keys[self.mode]

        com_type, command, repeatable = keys[key]
        func, args = command

        selected_text_len = None
    
        # If a motion is present in the command (but not the main command)
        # it needs to be run first
        if "motion" in key:
            # If in visual mode we don't want to change the selection start point
            if self.mode != ViHelper.VISUAL:
                # Otherwise the "pre motion" commands work by setting a start point
                # at the current positions, running the motion command and
                # finishing with a "post motion" command, i.e. deleting the
                # text that was selected.
                self.StartSelection()
            else:
                selected_text_len = len(self.ctrl.GetSelectedText())

            motion_key = tuple(motion)

            
            junk, (motion_func, motion_args), junk = keys[motion_key]
            if motion_wildcard:
                motion_args = tuple(motion_wildcard)
                if len(motion_args) == 1:
                    motion_args = motion_args[0]
                else:
                    motion_args = tuple(motion_args)

            RunFunc(motion_func, motion_args)
            

        # Special case if single char is selected (anchor needs to be reversed
        # if movement moves in a particular direction
        
        # horrible hack
        try:
            start_pos = self.ctrl.GetCurrentPos()
        except:
            print "REMOVE THIS HACK"

        single = False
        if self.mode == ViHelper.VISUAL:
            if len(self.ctrl.GetSelectedText()) <= 1:
                single = True
            #else:
            #    if start_pos - self.GetSelectionAnchor() <= 0:
            #        reverse = True

            #print self.ctrl.GetCurrentPos() - self.GetSelectionAnchor()

        if type(key) == tuple and "*" in key:
            args = tuple(wildcards)
            if len(args) == 1:
                args = args[0]
            else:
                args = tuple(args)
        # Run the actual function
        RunFunc(func, args)
            
        # If the command is repeatable save its type and any other settings
        if repeatable in [1, 2, 3]:
            self.last_cmd = repeatable, key, self.count, motion, \
                                            motion_wildcard, wildcards, \
                                            selected_text_len

        # Some commands should cause the mode to revert back to normal if run
        # from visual mode, others shouldn't.
        # NOTE: This is currently dependent on a number of function and
        #       variables on present in the WikiTxtCtrl implementation
        if self.mode == ViHelper.VISUAL:
            if com_type not in [1, 2]:
                self.SetMode(ViHelper.NORMAL)
            else:
                if single:
                    if self.ctrl.GetCurrentPos() < start_pos:
                        self.StartSelection(start_pos+1)
                        start_pos +=1
                if self.ctrl.GetCurrentPos() > start_pos:
                    self.ctrl.CharRight()
                    
                #else:
                #    if reverse:
                #        if self.ctrl.GetCurrentPos() - \
                #                self.GetSelectionAnchor() >= -1:
                #            self.StartSelection(self.GetSelectionAnchor()+1)
                            

                self.SelectSelection()
                if self.selection_mode == "LINE":
                    self.SelectFullLines()
 
        self.FlushBuffers()

    def FlushBuffers(self):
        """
        Clear modifiers and start keys so next input will be fresh

        Should be called after (most?) successful inputs and all failed
        ones.
        """
        self._acceptable_keys = None

        self._motion = []
        self._motion_wildcard = []
        self._wildcard = []
        self.key_inputs = []

        self.key_modifier = []
        self.key_number_modifier = []
        self.updateViStatus()

        self.FlushBuffersExtra()

        
    def FlushBuffersExtra(self):
        """
        To be overidden by derived class
        """
        pass

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
            cmd = u"".join([self.GetCharFromCode(i) for i in self.key_inputs])
            text = u"{0}{1}{2}".format(
                            ViHelper.MODE_TEXT[self.mode],
                            u"".join(map(str, self.key_number_modifier)),
                            cmd
                            )

        self.ctrl.presenter.getMainControl().statusBar.SetStatusText(text , 0)

    def _enableMenuShortcuts(self, enable):
        if enable and len(self.menuShortCuts) < 1:
            return

        self.menu_bar = self.ctrl.presenter.getMainControl().mainmenu

        if enable:
            for i in self.menuShortCuts:
                self.menu_bar.FindItemById(i).SetText(self.menuShortCuts[i])
            self.ctrl.presenter.getMainControl() \
                                        .SetAcceleratorTable( self.accelTable)
        else:
            self.accelTable = self.ctrl.presenter.getMainControl() \
                                                        .GetAcceleratorTable()

            self.ctrl.presenter.getMainControl() \
                                .SetAcceleratorTable(wx.NullAcceleratorTable)

            menus = self.menu_bar.GetMenus()

            menu_items = []

            def getMenuItems(menu):
                for i in menu.GetMenuItems():
                    menu_items.append(i.GetId())
                    if i.GetSubMenu() is not None:
                        getMenuItems(i.GetSubMenu())
                
            for menu, x in menus:
                getMenuItems(menu)
            
            for i in menu_items:
                menu_item = self.menu_bar.FindItemById(i)
                accel = menu_item.GetAccel()
		if accel is not None:
		    try:
			if accel.ToString() in self.viKeyAccels:
			    label = menu_item.GetItemLabel()
			    self.menuShortCuts[i] = (label)
			    # Removing the end part of the label is enough to disable the
			    # accelerator. This is used instead of SetAccel() so as to
			    # preserve menu accelerators.
			    # NOTE: doesn't seem to override ctrl-n!
			    menu_item.SetText(label.split("\t")[0]+"\tNone")
		    except:
			# Key errors appear in windows! (probably due to
			# unicode support??).
			if unichr(accel.GetKeyCode()) in self.viKeyAccels:
			    label = menu_item.GetItemLabel()
			    self.menuShortCuts[i] = (label)
			    menu_item.SetText(label.split("\t")[0]+"\tNone")

    #def _enableMenuShortcuts(self, enable):
    #    if (enable and len(self.menuShortCuts) < 1) or \
    #            (not enable and len(self.menuShortCuts) > 0):
    #        return

    #    self.menu_bar = self.ctrl.presenter.getMainControl().mainmenu

    #    if enable:
    #        for i in self.menuShortCuts:
    #            self.menu_bar.FindItemById(i).SetText(self.menuShortCuts[i])
    #        self.ctrl.presenter.getMainControl().SetAcceleratorTable(self.accelTable)
    #    else:
    #        self.accelTable = self.ctrl.presenter.getMainControl().GetAcceleratorTable()

    #        menus = self.menu_bar.GetMenus()

    #        menu_items = []

    #        def getMenuItems(menu):
    #            for i in menu.GetMenuItems():
    #                menu_items.append(i.GetId())
    #                if i.GetSubMenu() is not None:
    #                    getMenuItems(i.GetSubMenu())
    #            
    #        for menu, x in menus:
    #            getMenuItems(menu)
    #        
    #        for i in menu_items:
    #            menu_item = self.menu_bar.FindItemById(i)
    #            accel = menu_item.GetAccel()
    #            if accel is not None and accel.ToString() in self.viKeyAccels:
    #                label = menu_item.GetItemLabel()
    #                self.menuShortCuts[i] = (label)
    #                # Removing the end part of the label is enough to disable the
    #                # accelerator. This is used instead of SetAccel() so as to
    #                # preserve menu accelerators.
    #                menu_item.SetText(label.split("\t")[0]+"\tNone")

    #    #for i in range(self.menu_bar.GetMenuCount()):
    #    #    menu = self.menu_bar.GetMenu(i)
    #    #    enableMenu(menu, i)
    #    #    for menuItem in menu.GetMenuItems():
    #    #        enableMenu(menuItem)




#-----------------------------------------------------------------------------
# The following functions are common to both preview and editor mode
# -----------------------------------------------------------------------------

# Jumps
    
    # TODO: generalise so they work with wikihtmlview as well
    #       should work in lines (so if line is deleted)
    def AddJumpPosition(self, pos=None):
        if pos is None: pos = self.ctrl.GetCurrentPos()

        current_page = self.ctrl.presenter.getWikiWord()
        if self.jumps:
            last_page, last_pos = self.jumps[self.current_jump]
            if last_page == current_page and pos == last_pos:
                return

        if self.current_jump < len(self.jumps):
            self.jumps = self.jumps[:self.current_jump+1]
        self.jumps.append((current_page, pos))
        self.current_jump += 1

    def GotoNextJump(self):
        if self.current_jump + 1 < len(self.jumps):
            self.current_jump += 1
        else: 
            return

        word, pos = self.jumps[self.current_jump]
        if word != self.ctrl.presenter.getWikiWord():
            self.ctrl.presenter.openWikiPage(word)
        self.ctrl.GotoPos(pos)

    def GotoPreviousJump(self):
        if self.current_jump + 1 == len(self.jumps):
            self.AddJumpPosition(self.ctrl.GetCurrentPos())
        if self.current_jump - 1 >= 0:
            self.current_jump -= 1
        else:
            return
        word, pos = self.jumps[self.current_jump]
        if word != self.ctrl.presenter.getWikiWord():
            self.ctrl.presenter.openWikiPage(word)
        self.ctrl.GotoPos(pos)

            

    def SwitchEditorPreview(self, scName=None):
        mainControl = self.ctrl.presenter.getMainControl()
        mainControl.setDocPagePresenterSubControl(scName)

    def StartSearch(self):
        # TODO: customise the search to make it more vim-like
        #       allow starting search backwards
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

 
# TODO:numbered registers
#      special registers
class ViRegister():
    def __init__(self, ctrl):
        self.ctrl = ctrl

        self.select_register = False
        self.current_reg = None

        self.alpha = """
                        abcdefghijklmnopqrstuvwxyz
                        ABCDEFGHIJKLMNOPQRSTUVWXYZ
                     """
        self.special = '"+01.'
        self.registers = {}

        for i in self.alpha:
            self.registers[i] = None

        for i in self.special:
            self.registers[i] = None

        self.registers['"'] = u""

    def SelectRegister(self, key_code):
        if key_code is None:
            self.current_reg = None
            return

        if type(key_code) == int:
            reg = unichr(key_code)
        else:
            reg = key_code

        if reg in self.registers:
            self.current_reg = reg
            print 1
            return True
        else:
            print 2
            self.current_reg = None
            return False

    def GetSelectedRegister(self):
        return self.current_reg

    def SetCurrentRegister(self, value):
        self.registers['"'] = value
        if self.current_reg is None:
            pass
        elif self.current_reg in self.alpha:
            self.registers[self.current_reg] = value
        elif self.current_reg == "+":
            self.ctrl.Copy()
        self.current_reg = None

    def GetRegister(self, reg):
        if reg in self.registers:
            return self.registers[reg]

    def GetCurrentRegister(self):
        if self.current_reg == "+":
            text = getTextFromClipboard()
        elif self.current_reg is None:
            text = self.registers['"']
        elif self.current_reg in self.registers:
            text = self.registers[self.current_reg]
        else: # should never occur
            return
        self.current_reg = None
        return text
