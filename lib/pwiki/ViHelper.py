import wx, wx.xrc
import SystemInfo
from wxHelper import GUI_ID, getAccelPairFromKeyDown, getTextFromClipboard
from collections import defaultdict
from StringOps import pathEnc, urlQuote
import os
import ConfigParser
import re
import copy
import string
import PluginManager

from wxHelper import * # Needed for  XrcControls

from WindowLayout import setWindowSize

#TODO:  Multiple registers
#       Page marks
#       Alt-combinations
#       .rc


# TODO: should be configurable
AUTOCOMPLETE_BOX_HEIGHT = 50

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
                    3 : u"--REPLACE--" 
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
                            

    CMD_INPUT_DELAY = 1000
    STRIP_BULLETS_ON_LINE_JOIN = True


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

        self.input_window = self.ctrl.presenter.getMainControl().windowLayouter.getWindowByName("vi input")

        self.input_search_history = ViInputHistory()
        self.input_cmd_history = ViInputHistory()

        self.last_cmd = None
        self.insert_action = []

        self.selection_mode = u"NORMAL"

        self.tag_input = False
                    
        # The following dictionary holds the menu shortcuts that have been
        # disabled upon entering ViMode
        self.menuShortCuts = {}

        self.register = ViRegister(self.ctrl)


        # Settings are stored as a dict
        self.settings = { 
                "filter_wikipages" : True,
                "caret_scroll" : False, # Large performance hit
                
             }
        self.LoadSettings()

        self.RegisterPlugins()

    def RegisterPlugins(self):
        """
        Register the plugins to be loaded.
        """
        self.pluginFunctions = []
        main_control = self.ctrl.presenter.getMainControl()

        self.pluginFunctions = reduce(lambda a, b: a+list(b), 
                main_control.viPluginFunctions.describeViFunctions(
                main_control), [])

    def LoadPlugins(self, presenter):
        """
        Helper which loads the plugins.

        To be called by derived class.
        """
        # Load plugin functions
        k = self.KEY_BINDINGS
        for keys, presenter_type, vi_mode, function in self.pluginFunctions:
            try:
                if presenter in presenter_type:
                    def returnKey(key):
                        if len(key) > 1 and key[0] == u"key":
                            return k[key[1]]
                        elif key == "motion" or "m":
                            return "m"
                        elif key == "*":
                            return "*"
                        else:
                            raise PluginKeyError(u"ERROR LOADING PLUGIN")
                            
                    key_chain = tuple([returnKey(i) for i in keys])
                    for mode in vi_mode:
                        self.keys[mode][key_chain] = function
            except PluginKeyError:
                continue

        self.pluginFunctions = []

        self.GenerateKeyKindings()

    def ReloadPlugins(self, name):
        self.RegisterPlugins()
        self.LoadPlugins(name)

    def LoadSettings(self):
        """
        Settings are loaded from the file vi.rc in the wikidpad global config
        dir

        Can be called at any time to update / reload settings

        ? May need to regenerate keybindings if they have been changed
        """
        rc_file = None
        rc_file_names = (".WikidPad.virc", "WikidPad.virc")

        config_dir = wx.GetApp().globalConfigDir

        for n in rc_file_names:
            path = pathEnc(os.path.join(config_dir, n))
            if os.path.isfile(path):
                rc_file = path
                break

        if rc_file is not None:
            config = ConfigParser.ConfigParser()
            config.read(rc_file)

            # Load custom key bindings
            try:
                for key in config.options("keys"):
                    try:
                        self.KEY_BINDINGS[key] = config.getint("keys", key)
                    except ValueError:
                        print "Keycode must be a integer: {0}".format(key)
            except ConfigParser.NoSectionError:
                pass
                

            try:
                for setting in config.options("settings"):
                    if setting in self.settings:
                        try:
                            self.settings[setting] = config.getboolean(
                                    "settings", setting)
                        except ValueError:
                            print "Setting '{0}' must be boolean".format(setting)

            except ConfigParser.NoSectionError:
                pass


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
                try:
                    return "{0}-{1}".format(keycode[0], unichr(keycode[1]))
                except TypeError:
                    return keycode
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

    def GenerateKeyKindings(self):
        """Stub to be overridden by derived class"""
        
    def GenerateMotionKeys(self, keys):
        key_mods = defaultdict(dict)
        for mode in keys:
            key_mods[mode] = set()
            for accel in keys[mode]:
                if keys[mode][accel][0] > 0:
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
                            wildcards=None, text_to_select=None, repeat=False):
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

        if text_to_select is not None:
            # Use visual keys instead
            keys = self.keys[ViHelper.VISUAL]

            # If we are already in visual mode use the selected text
            # Otherwise we use the same amount of text used for initial cmd
            # NOTE: this should prob be put into another cmd (in WikiTxtCtrl)
            if not self.mode == ViHelper.VISUAL:
                lines, n = text_to_select
                if lines:
                    start_line = self.ctrl.GetCurrentLine()
                    self.SelectLines(start_line, start_line - 1 + n, 
                                                        include_eol=True)
                else:
                    self.StartSelection()
                    self.MoveCaretPos(n, allow_last_char=True)
                    self.SelectSelection(2)

        com_type, command, repeatable, selection_type = keys[key]
        func, args = command

        
        # If in visual mode need to prep in case we change selection direction
        start_selection_direction = None
        if self.mode == ViHelper.VISUAL:
            start_selection_direction = self.SelectionIsForward()

    
        # If a motion is present in the command (but not the main command)
        # it needs to be run first
        if "m" in key:
            # If in visual mode we don't want to change the selection start point
            if self.mode != ViHelper.VISUAL:
                # Otherwise the "pre motion" commands work by setting a start point
                # at the current positions, running the motion command and
                # finishing with a "post motion" command, i.e. deleting the
                # text that was selected.
                self.StartSelection()

            motion_key = tuple(motion)

            # Extract the cmd we need to run (it is irrelevent if it is
            # repeatable or if it has a different selection_type)
            motion_com_type, (motion_func, motion_args), junk, junk = keys[motion_key]
            if motion_wildcard:
                motion_args = tuple(motion_wildcard)
                if len(motion_args) == 1:
                    motion_args = motion_args[0]
                else:
                    motion_args = tuple(motion_args)
 
            RunFunc(motion_func, motion_args)

            # Test if the motion has caused a movement in the caret
            # If not consider it an invalid cmd
            if self._anchor == self.ctrl.GetCurrentPos():
                return False

            self.SelectSelection(motion_com_type)
            
        # If in visual mode we save some details about the selection so the
        # command can be repeated
        selected_text = None
        if self.mode == ViHelper.VISUAL:
            # TODO: fix line selection mode
            selected_text = self.GetSelectionDetails(selection_type)

        if type(key) == tuple and "*" in key:
            args = tuple(wildcards)
            if len(args) == 1:
                args = args[0]
            else:
                args = tuple(args)
        # Run the actual function
        RunFunc(func, args)
            
        # If the command is repeatable save its type and any other settings
        if repeatable in [1, 2, 3] and not repeat:
            self.last_cmd = [repeatable, key, self.count, motion, \
                                            motion_wildcard, wildcards, \
                                            selected_text]

        # Some commands should cause the mode to revert back to normal if run
        # from visual mode, others shouldn't.
        if self.mode == ViHelper.VISUAL:
            if com_type < 1:
                self.SetMode(ViHelper.NORMAL)
            else:
                if start_selection_direction is not None:
                    end_selection_direction = \
                            self.ctrl.GetCurrentPos() > self._anchor

                    if start_selection_direction != end_selection_direction:
                        if end_selection_direction:
                            self._anchor = self._anchor - 1
                        else:
                            self._anchor = self._anchor + 1
                        
                self.SelectSelection(com_type)

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

    def HasSelection(self):
        """
        Should be overridden by child class if necessary
        """
        return False

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

    def StartForwardSearch(self, initial_input=None):
        self.StartSearchInput(initial_input=initial_input, forward=True)

    def StartReverseSearch(self, initial_input=None):
        self.StartSearchInput(initial_input=initial_input, forward=False)

    def StartSearchInput(self, initial_input=None, forward=True):

        text = initial_input

        if self.HasSelection():
            text = self.ctrl.GetSelectedText()
            text = text.split("\n", 1)[0]
            text = text[:30]

        self.input_window.StartSearch(self.ctrl, self.input_search_history, text, forward)


    def ContinueLastSearchSameDirection(self):
        """Helper function to allow repeats"""
        self.ContinueLastSearch(False)

    def ContinueLastSearchReverseDirection(self):
        """Helper function to allow repeats"""
        self.ContinueLastSearch(True)

    def ContinueLastSearch(self, reverse):
        """
        Repeats last search command
        """
        args = self.last_search_args
        if args is not None:
            # If "N" we need to reverse the search direction
            if reverse:
                args['forward'] = not args['forward']

            args['repeat_search'] = True

            self._SearchText(**args)

            # Restore search direction (could use copy())
            if reverse:
                args['forward'] = not args['forward']

    def _SearchText(self):
        raise NotImplementedError, "To be overridden by derived class"

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

    def CloseCurrentTab(self, junk=None):
        """
        Closes currently focused tab
        """
        mainAreaPanel = self.ctrl.presenter.getMainControl().getMainAreaPanel()
        wx.CallAfter(mainAreaPanel.closePresenterTab, mainAreaPanel.getCurrentPresenter())
        #return True

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
        recieved.
        
        Sign is a popup box that overlays the leftmost segment
        of the status bar.

        Default is colour is red however a number of different
        colours can be used.
        """
        sb = self.ctrl.presenter.getMainControl().GetStatusBar()

        rect = sb.GetFieldRect(0)
        if SystemInfo.isOSX():
            # needed on Mac OSX to avoid cropped text
            rect = wx._core.Rect(rect.x, rect.y - 2, rect.width, rect.height + 4)

        rect.SetPosition(sb.ClientToScreen(rect.GetPosition()))

        bell = ViVisualBell(self.ctrl, -1, rect, colour)

    def StartCmdInput(self, initial_input=None):

        selection_range = None
        if self.mode == ViHelper.VISUAL:
            if initial_input is None:
                initial_input = u"'<,'>"
            selection_range = self.ctrl.vi._GetSelectionRange()

        self.input_window.StartCmd(self.ctrl, self.input_cmd_history, 
                                            initial_input, selection_range=selection_range)

    def RepeatLastSubCmd(self, ignore_flags):
        self.input_window.cmd_parser.RepeatSubCmd(ignore_flags)


    def EndViInput(self):
        """
        Called when input dialog is closed
        """
        self.ctrl.presenter.getMainControl().windowLayouter.collapseWindow("vi input")

    def GotoSelectionStart(self):
        """
        Goto start of selection
        """
        #raise NotImplementedError, "To be overridden by derived class"

    def GotoSelectionEnd(self):
        """
        Goto end of selection
        """
        #raise NotImplementedError, "To be overridden by derived class"






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

    #def Close(self):
    #     wx.Frame.Close(self)
    #     self.ctrl.SetFocus()


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

        foundPos = -26
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

        elif matchesAccelPair("ActivateLink", accP):
            # ActivateLink is normally Ctrl-L
            self.viCtrl.endFollowHint()
            self.Close()
            self.viCtrl.OnKeyDown(evt)

        elif matchesAccelPair("ActivateLinkNewTab", accP):
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            self.viCtrl.endFollowHint()
            self.Close()
            self.viCtrl.OnKeyDown(evt)

        elif matchesAccelPair("ActivateLink2", accP):
            # ActivateLink2 is normally Ctrl-Return
            self.viCtrl.endFollowHint()
            self.Close()
            self.viCtrl.OnKeyDown(evt)

        elif matchesAccelPair("ActivateLinkBackground", accP):
            # ActivateLinkNewTab is normally Ctrl-Alt-L
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

 
class ViRegister():
    def __init__(self, ctrl):
        self.ctrl = ctrl

        self.select_register = False
        self.current_reg = None

        # Uppercase registers do not exist (although they can be selected)
        self.alpha = "abcdefghijklmnopqrstuvwxyz"
        self.special = '"+-.'
        self.registers = {}

        # Create the named (alpha) registers
        for i in self.alpha:
            self.registers[i] = None

        # Create the special registers
        for i in self.special:
            self.registers[i] = None

        # Create numbered registers
        for i in range(0, 10):
            self.registers[str(i)] = None

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
            return True
        # Uppercase alpha regs
        elif reg.lower() in self.registers:
            self.current_reg = reg
            return True
        else:
            self.current_reg = None
            return False

    def GetSelectedRegister(self):
        return self.current_reg

    def SetCurrentRegister(self, value, yank_register=False):
        # Whenever a register is set the unnamed (") register is also.
        self.registers['"'] = value
        if self.current_reg is None:
            if yank_register:
                self.SetRegisterZero(value)
            else:
                # TODO: decide if following vim here is sensible.
                # If the deleted text spans multiple lines it is put in the
                # numbered register
                if "\n" in value:
                    self.SetNumberedRegister(value)
                # Otherwise the small delete register is used.
                else:
                    self.SetRegister("-", value)
        # Lowercase letters replace the contents of the selected register
        elif self.current_reg in self.alpha:
            self.registers[self.current_reg] = value
        # Uppercase letters append
        elif self.current_reg.lower() in self.alpha:
            current_reg = self.current_reg.lower()
            self.registers[current_reg] = self.registers[current_reg] + value
        # The "+ reg copies selected text to the clipboard
        elif self.current_reg == "+":
            self.ctrl.Copy()
        self.current_reg = None


    def SetRegister(self, register, value):
        self.registers[register] = value


    def SetRegisterZero(self, value):
        """
        Helper to set the "0 register.
        """
        self.registers["0"] = value

    def SetNumberedRegister(self, value):
        """
        Puts the selection into the "1 register and shifts
        the other registers up by one

        e.g.

        "1 -> "2, "2 -> "3, etc...

        Register "9 is lost in the process
        """
        for i in range (2, 10)[::-1]:
            self.registers[str(i)] = self.registers[str(i-1)]

        self.registers["1"] = value


    def GetRegister(self, reg):
        if reg in self.registers:
            return self.registers[reg]

    def GetCurrentRegister(self):
        if self.current_reg == "+":
            text = getTextFromClipboard()
        elif self.current_reg is None:
            text = self.registers['"']
        # If the register is alpha we need to check if it is uppercase and
        # convert it if it is.
        elif self.current_reg in string.ascii_letters:
            text = self.registers[self.current_reg.lower()]
        elif self.current_reg in self.registers:
            text = self.registers[self.current_reg]
        else: # should never occur
            return
        self.current_reg = None
        return text



class CmdParser():
    def __init__(self, ctrl, selection_range=None):
        self.ctrl = ctrl

        self.selection_range = selection_range
        self.last_sub_cmd = None

        self.data = []

        self.cmds = {
            "&" : (self.Pass, self.RepeatSubCmd),
            "&&" : (self.Pass, self.RepeatSubCmdWithFlags),
            "parents" : (self.GetParentPages, self.OpenWikiPageCurrentTab),
            "tabparents" : (self.GetParentPages, self.OpenWikiPageNewTab),
            "bgparents" : (self.GetParentPages, self.OpenWikiPageBackgroundTab),
            "w" : (self.Pass, self.SaveCurrentPage),
            "write" : (self.Pass, self.SaveCurrentPage),
            "open" : (self.GetWikiPages, self.OpenWikiPageCurrentTab),
            "edit" : (self.GetWikiPages, self.OpenWikiPageCurrentTab),
            "tabopen" : (self.GetWikiPages, self.OpenWikiPageNewTab),
            "bgtabopen" : (self.GetWikiPages, self.OpenWikiPageBackgroundTab),

            "tab" : (self.GetTabs, self.GotoTab),
            "buffer" : (self.GetTabs, self.GotoTab),

            "google" : (self.GetWikiPages, self.OpenPageInGoogle),
            "wikipedia" : (self.GetWikiPages, self.OpenPageInWikipedia),

            # TODO: rewrite with vi like confirmation
            "deletepage" : (self.GetDefinedWikiPages, self.ctrl.presenter.getMainControl().showWikiWordDeleteDialog),
            "delpage" : (self.GetDefinedWikiPages, self.ctrl.presenter.getMainControl().showWikiWordDeleteDialog),

            #"renamepage" : (self.GetDefinedWikiPages, self.Pass),

            # Currently bdelete and bwipeout are currently synonymous
            "quit" : (self.GetTabs, self.CloseTab),
            "bdelete" : (self.GetTabs, self.CloseTab),
            "bwipeout" : (self.GetTabs, self.CloseTab),
            "quitall" : (self.Pass, self.CloseWiki),
            "tabonly" : (self.GetTabs, self.CloseOtherTabs),
            "exit" : (self.Pass, self.CloseWiki),

            "reloadplugins" : (self.Pass, self.ReloadPlugins),
            }

        # marks? search patterns?
        self.cmd_range_starters = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, u".", u"$", u"%", u",")
        self.range_cmds = {
                            u"s" : self.SearchAndReplace,
                            u"sort" : self.Sort
                          }
        # TODO: :s repeats last command

        self.range_regex = u"(\d+|%|\.|\$|'.)?,?(\d+|%|\.|\$|'.)({0})(.*$)".format(
                                            "|".join(self.range_cmds.keys()))
    
    def SearchAndReplace(self, pattern, ignore_flags=False):
        # TODO: implement flags
        if pattern.startswith(u"/"):
            delim = u"\/"
        elif pattern.startswith(u";"):
            delim = u"\;"
        elif pattern.startswith(u"$"):
            delim = u"\$"
        elif pattern.startswith(u"|"):
            delim = u"\|"
        elif pattern.startswith(u"^"):
            delim = u"\^"
        else:
            return False

        try:
            search, replace, flags = re.split(r"(?<!\\){0}".format(delim), pattern)[1:]
        except ValueError:
            return False

        count = 1
        # TODO: Flags
        #           & : flags from previous sub
        #           c : confirm (see :s_flags
        #           e : no error
        #           i : ignore case
        #           I : don't ignore case
        #           n : report match number (no substitution
        #           p : print the line containing the last substitute
        #           # : like [p] and prepend line number
        #           l : like [p] but print the text like [:list]
        if u"g" in flags:
            count = 0

        re_flags = re.M

        # Hack for replaing newline chars
        search = re.sub(r"(?<!\\)\\n", "\n", search)

        try:
            search_regex = re.compile(search, flags=re_flags)
        except re.error:
            return False

        self.ctrl.vi.AddJumpPosition()

        text_to_sub = self.ctrl.GetSelectedText()


        # If our regex contains a newline character we need to search over
        # all text
        if "\n" not in search:
            new_text = []

            # We do the subs on a per line basis as by default vim only
            # replaces the first occurance
            for i in text_to_sub.split("\n"):
                try:
                    new_text.append(search_regex.sub(replace, i, count))
                except re.error:
                    return False
            
            self.ctrl.ReplaceSelection("\n".join(new_text))

        else:
            self.ctrl.ReplaceSelection(search_regex.sub(replace, text_to_sub))

        self.last_sub_cmd = pattern

        return True

    def Sort(self, sort_type=None):
        eol_char = self.ctrl.GetEOLChar()
        sorted_text = eol_char.join(
                sorted(self.ctrl.GetSelectedText().split(eol_char)))
        self.ctrl.ReplaceSelection(sorted_text)

    def RepeatSubCmdWithFlags(self):
        self.RepeatSubCmd(ignore_flags=False)

    def RepeatSubCmd(self, ignore_flags=True):
        cmd = self.last_sub_cmd
        if cmd is not None:
            if ignore_flags:
                # TODO: strip flags
                pass
            return self.ExecuteRangeCmd(cmd)
        else:
            return False
        

    def Pass(self, junk=None):
        pass

    def CheckForRangeCmd(self, text_input):
        # TODO: improve cmd checking
        if re.match(self.range_regex, text_input):
            return True
        elif re.match("(\d+|%|\.|\$)?,?(\d+|%|\.|\$)({0})".format(
                                "|".join(self.range_cmds.keys())), text_input):
            return True
        elif re.match("(\d+|%|\.|\$)?,?(\d+|%|\.|\$)", text_input):
            return True
        elif re.match("(\d+|%|\.|\$)?,", text_input):
            return True
        elif re.match("(\d+|%|\.|\$)", text_input):
            return True
        else:
            return False

    def ExecuteRangeCmd(self, text_input):
        start_range, end_range, cmd, args = re.match(self.range_regex, text_input).groups()

        try:
            if start_range is not None:
                start_range = int(start_range) - 1
        except ValueError:
            pass

        try:
            if end_range is not None:
                end_range = int(end_range) - 1
        except ValueError:
            pass

            
        # Ranges are by default lines
        if start_range == u"%" or end_range == u"%":
            start_range = 0
            end_range = self.ctrl.GetLineCount()
        elif start_range in (None, u""):
            start_range = end_range
            

        # Convert line ranges to char positions
        if type(start_range) == int:
            start_range = self.ctrl.vi.GetLineStartPos(start_range)
        elif start_range == u".":
            start_range = self.ctrl.vi.GetLineStartPos(
                    self.ctrl.GetCurrentLine())
        elif len(start_range) == 2 and start_range.startswith(u"'"):
            if start_range[1] == u"<":
                start_range = self.selection_range[0]
            else:
                page = self.ctrl.presenter.getWikiWord()
                # TODO: create helper to prevent mark going past page end?
                try:
                    start_range = self.ctrl.vi.marks[page][ord(start_range[1])]
                except KeyError:
                    return False # mark not set
        else:
            return False # invalid start_range input

        if type(end_range) == int:
            end_range = self.ctrl.GetLineEndPosition(end_range) + 1
        elif end_range == u"$":
            end_range = self.ctrl.GetLineEndPosition(
                                self.ctrl.GetLineCount()) + 1
        elif end_range == u".":
            end_range = self.ctrl.GetLineEndPosition(
                                self.ctrl.GetCurrentLine()) + 1
        elif len(end_range) == 2 and end_range.startswith(u"'"):
            if end_range[1] == u">":
                end_range = self.selection_range[1]
            else:
                page = self.ctrl.presenter.getWikiWord()
                try:
                    end_range = self.ctrl.vi.marks[page][ord(end_range[1])]
                except KeyError:
                    return False # mark not set
        else:
            return False # invalid end_range input


        self.ctrl.SetSelection(start_range, end_range)

        self.ctrl.vi.BeginUndo()
        rel = self.range_cmds[cmd](args)
        self.ctrl.vi.EndUndo()

        self.ClearInput()

        # If the cmd is :s save it so it can be repeated
        if rel and cmd == "s":
            self.last_sub_cmd = text_input

        return rel

    def ParseCmd(self, text_input):
        if self.CheckForRangeCmd(text_input):
            return True, False

        split_cmd = text_input.split(" ")

        args = False
        if len(split_cmd) > 1:
            if split_cmd[1] != u"":
                args = True
            else:
                args = False

        cmd_list = []
        for cmd in self.cmds:
            if cmd.startswith(split_cmd[0]):
                cmd_list.append(cmd)

        return cmd_list, args

    def ParseCmdWithArgs(self, text_input):
        if self.CheckForRangeCmd(text_input):
            return []

        split_cmd = text_input.split(u" ")

        arg = None
        action = split_cmd[0]
        if len(split_cmd) > 1:
            arg = u" ".join(split_cmd[1:])

        cmd_list = []
        
        for cmd in self.cmds:
            if cmd.startswith(action):
                if arg is not None or text_input.endswith(u" "):
                    return self.cmds[cmd][0](arg)
                else:
                    cmd_list.append(cmd)

        return cmd_list

    def RunCmd(self, text_input, viInputListBox_selection):
        if self.CheckForRangeCmd(text_input):
            return self.ExecuteRangeCmd(text_input)

        if viInputListBox_selection > -1 and self.data:
            arg = self.data[viInputListBox_selection]
        else:
            arg = None

        split_cmd = text_input.split(" ")

        action = split_cmd[0]
        if arg is None and len(split_cmd) > 1 and len(split_cmd[1]) > 0:
            arg = u" ".join(split_cmd[1:])

        # If a full cmd name has been entered use it
        if action in self.cmds:
            return self.cmds[action][1](arg)
        
        # Otherwise use the first one found in the cmd list
        # TODO: sort order
        for cmd in self.cmds:
            if cmd.startswith(action):
                return self.cmds[cmd][1](arg)

        self.ClearInput()
        
    def ClearInput(self):
        self.data = []

    def ReloadPlugins(self, args=None):
        """
        Reload plugins globally using reloadMenuPlugins() and then
        on a per tab basis
        """
        self.ctrl.presenter.getMainControl().reloadMenuPlugins()

        # NOTE: should probably unify names
        for scName, name in (("textedit", "editor"), ("preview", "preview")):
            for tab in self.ctrl.presenter.getMainControl().getMainAreaPanel().getPresenters():
                # Try and reload key bindings for each presenter on each tab
                # (if they exist)
                try:
                    tab.getSubControl(scName).vi.ReloadPlugins(name)
                except AttributeError:
                    pass

        

    def OpenPageInGoogle(self, text_input=None):
        if type(text_input) == tuple:
            text_input = text_input[0]
        mainCtrl = self.ctrl.presenter.getMainControl()
        if text_input is None:
            text_input = self.ctrl.presenter.getWikiWord()

        mainCtrl.launchUrl("https://www.google.com/search?q={0}".format(
                urlQuote(text_input)))
        return True

    def OpenPageInWikipedia(self, text_input=None):
        if type(text_input) == tuple:
            text_input = text_input[0]
        mainCtrl = self.ctrl.presenter.getMainControl()
        if text_input is None:
            text_input = self.ctrl.presenter.getWikiWord()
 
        mainCtrl.launchUrl("https://www.wikipedia.org/wiki/{0}".format(
                urlQuote(text_input)))
        return True

    def CloseOtherTabs(self, text_input=None):
        if self.GotoTab(text_input):
            self.ctrl.presenter.getMainControl().getMainAreaPanel()\
                    ._closeAllButCurrentTab()

    def SaveCurrentPage(self, args=None):
        self.ctrl.presenter.saveCurrentDocPage()
        return True

    def OpenWikiPageCurrentTab(self, link_info):
        return self.OpenWikiPage(link_info, 0)

    def OpenWikiPageNewTab(self, link_info):
        return self.OpenWikiPage(link_info, 2)

    def OpenWikiPageBackgroundTab(self, link_info):
        return self.OpenWikiPage(link_info, 3)

    def OpenWikiPage(self, link_info, tab_mode):
        if not type(link_info) == tuple:
            value = ((link_info, 0, link_info, -1, -1),)
        else:
            value = (link_info,)

        wikiword = value[0][2]

        strip_whitespace_from_wikiword = True
        if strip_whitespace_from_wikiword:
            wikiword = wikiword.strip()

        self.ctrl.presenter.getMainControl().activatePageByUnifiedName(
                u"wikipage/" + wikiword, tabMode=tab_mode, 
                firstcharpos=value[0][3], charlength=value[0][4])

        return True

    def GetTabs(self, text_input):
        mainAreaPanel = self.ctrl.presenter.getMainControl().getMainAreaPanel()
        page_count = mainAreaPanel.GetPageCount()

        tabs = []

        return_data = []

        for i in range(page_count):
            page = mainAreaPanel.GetPage(i)

            wikiword = page.getWikiWord()

            if wikiword.startswith(text_input):
                return_data.append(wikiword)
                tabs.append(page)

        self.data = tabs

        return return_data


    def CloseTab(self, text_input):
        if text_input is None:
            self.ctrl.vi.CloseCurrentTab()
            return True
            #currentTabNum = mainAreaPanel.GetSelection() + 1

        if text_input in self.data:
            self.ctrl.presenter.getMainControl().getMainAreaPanel()\
                    .closePresenterTab(text_input)
            return True
        elif len(self.data) == 1:
            self.ctrl.presenter.getMainControl().getMainAreaPanel()\
                    .closePresenterTab(self.data[0])
            return True
        else:
            self.ctrl.vi.visualBell("RED")
            return False


    def GotoTab(self, text_input):
        if text_input is None:
            return False

        if text_input in self.data:
            self.ctrl.presenter.getMainControl().getMainAreaPanel()\
                    .showPresenter(text_input)
            return True
        elif len(self.data) == 1:
            self.ctrl.presenter.getMainControl().getMainAreaPanel()\
                    .showPresenter(self.data[0])
            return True
        return False
        
    def CloseWiki(self, arg=None):
        self.ctrl.presenter.getMainControl().exitWiki()

    def GetDefinedWikiPages(self, search_text):
        if search_text is None:
            return [(_(u"Enter wikiword..."),)]

        results = self.ctrl.presenter.getMainControl().getWikiData().\
                                                getAllDefinedWikiPageNames()
        self.data = results

        if search_text.strip() == u"":
            return results

        results = [i for i in self.data if i.find(search_text) > -1]

        if not results:
            return None

        return results


    def GetWikiPages(self, search_text):
        if search_text is None:
            return [(_(u"Enter wikiword..."),)]

        if search_text.strip() == u"":
            return [_(u"Enter wikiword...")]

        results = self.ctrl.presenter.getMainControl().getWikiData().\
                    getWikiWordMatchTermsWith(
                            search_text, orderBy="word", descend=False)

        filter_results = True
        # Quick hack to filter repetative alias'
        if filter_results:
            print results
            pages = [x[2] for x in results if x[4] > -1 and x[3] == -1]
            
            l = []
            for x in results:
                # Orginial wikiwords are always displayed
                if x[4] > -1:
                    pass
                else:
                    alias = x[0].lower()
                    wikiword = x[2]
                    wikiword_mod = wikiword.lower()
                    
                    for r in (("'s", ""), ("disease", ""), ("syndrome", ""), ("-", ""), (" ", ""), ("cancer", ""), ("carcinoma", "")):
                        alias = alias.replace(*r)
                        wikiword_mod = wikiword_mod.replace(*r)

                    # Only hide aliases if the actually page is in the list
                    if (alias in wikiword_mod or wikiword_mod in alias) and \
                            wikiword in pages:
                        continue

                l.append(x)

            results = l
                

        self.data = results

        results = [i[0] for i in self.data]
        if not results:
            return None

        return results

    def GetParentPages(self, search_text):
        presenter = self.ctrl.presenter
        word = presenter.getWikiWord()

        parents = presenter.getMainControl().getWikiData(). \
                    getParentRelationships(word)
 
        # If no parents give a notification and exit
        if len(parents) == 0:
            self.ctrl.vi.visualBell()
            return None

        return parents

class ViInputHistory():
    def __init__(self):
        self.cmd_history = []
        self.cmd_position = -1

    def AddCmd(self, cmd):
        self.cmd_history.append(cmd)
        self.cmd_position = len(self.cmd_history) - 1

    def IncrementCmdPos(self):
        self.cmd_position += 1

    def GoForwardInHistory(self):
        if self.cmd_position < 0:
            return False
        if self.cmd_position + 1 >= len(self.cmd_history):
            return u""
        self.cmd_position = min(len(self.cmd_history)-1, self.cmd_position + 1)

        return self.cmd_history[self.cmd_position]
            

    def GoBackwardsInHistory(self):
        if self.cmd_position < 0:
            return False
        cmd = self.cmd_history[self.cmd_position]
        self.cmd_position = max(0, self.cmd_position - 1)
        return cmd

# NOTE: It may make more sense to seperate the search and cmdline components
#       into to seperate classes
class ViInputDialog(wx.Panel):
    
    COLOR_YELLOW = wx.Colour(255, 255, 0);
    COLOR_GREEN = wx.Colour(0, 255, 0);
    COLOR_RED = wx.Colour(255, 0, 0);
    COLOR_WHITE = wx.Colour(255, 255, 255);
    
    def __init__(self, parent, id, mainControl):
#        # Frame title is invisible but is helpful for workarounds with
#        # third-party tools
#        wx.Frame.__init__(self, parent, id, u"ViInputDialog",
#                rect.GetPosition(), rect.GetSize(),
#                wx.NO_BORDER | wx.FRAME_FLOAT_ON_PARENT | wx.FRAME_NO_TASKBAR)

        d = wx.PrePanel()
        self.PostCreate(d)

        self.mainControl = mainControl

        res = wx.xrc.XmlResource.Get()
        res.LoadOnPanel(self, parent, "ViInputDialog")
        self.ctrls = XrcControls(self)

        self.sizeVisible = True

#        self.dialog_start_pos = rect.GetPosition()
#        self.dialog_start_size = rect.GetSize()
        #self.dialog_start_size = rect.GetSize()

        wx.EVT_SIZE(self, self.OnSize)

        self.run_cmd_timer = wx.Timer(self, GUI_ID.TIMER_VI_UPDATE_CMD)
        wx.EVT_TIMER(self, GUI_ID.TIMER_VI_UPDATE_CMD, self.CheckViInput)

        self.ctrls.viInputTextField.SetBackgroundColour(
                ViInputDialog.COLOR_YELLOW)

        self.closeDelay = 0 # Milliseconds to close or 0 to deactivate

        #wx.EVT_SET_FOCUS(self.ctrls.viInputListBox, self.FocusInputField)

        wx.EVT_TEXT(self, GUI_ID.viInputTextField, self.OnText)
        wx.EVT_KEY_DOWN(self.ctrls.viInputTextField, self.OnKeyDownInput)
        wx.EVT_TIMER(self, GUI_ID.TIMER_INC_SEARCH_CLOSE,
                self.OnTimerIncViInputClose)
        wx.EVT_MOUSE_EVENTS(self.ctrls.viInputTextField, self.OnMouseAnyInput)

        wx.EVT_LEFT_DOWN(self.ctrls.viInputListBox, self.OnLeftMouseListBox)
        wx.EVT_LEFT_DCLICK(self.ctrls.viInputListBox, self.OnLeftMouseDoubleListBox)

        if self.closeDelay:
            self.closeTimer = wx.Timer(self, GUI_ID.TIMER_INC_SEARCH_CLOSE)
            self.closeTimer.Start(self.closeDelay, True)

        self.selection_range = None

        self.block_kill_focus = False
        wx.EVT_KILL_FOCUS(self.ctrls.viInputTextField, self.OnKillFocus)

    def StartCmd(self, ctrl, cmd_history, text, selection_range=None):
        self.search = False
        self.selection_range = selection_range
        self.StartInput(text, ctrl, cmd_history)

    def StartSearch(self, ctrl, cmd_history, text, forward):
        """
        Called to start a search input
        """
        self.search = True

        self.search_args = {
                            'text' : text, 
                            'forward' : forward, 
                            'match_case' : False,
                            'whole_word' : False,
                            'wrap' : True,
                            'regex' : True,
                         }

        self.StartInput(text, ctrl, cmd_history)

    def StartInput(self, initial_input, ctrl, cmd_history):
        """
        Code common to both search and cmd inputs
        """
        self.ctrl = ctrl

        self.cmd_list = []

        self.cmd_parser = CmdParser(self.ctrl, self.selection_range)
        
        self.initial_scroll_pos = self.ctrl.GetScrollAndCaretPosition()

        self.block_list_reload = False

        if initial_input is not None:
            self.ctrls.viInputTextField.AppendText(initial_input)
            self.ctrls.viInputTextField.SetSelection(-1, -1)


        self.cmd_history = cmd_history

        self.UpdateLayout()

        self.ShowPanel()

        wx.CallAfter(self.FocusInputField, None)


    def close(self):
        pass

    def Close(self):
        self.ctrl.vi.RemoveSelection()
        self.cmd_parser.ClearInput()
        self.ClearListBox()
        self.ctrls.viInputTextField.Clear()

        self.ctrl.vi.EndViInput()
        self.ctrl.SetFocus()

    def UpdateLayout(self, show_viInputListBox=False):
        pass

    def OnKillFocus(self, evt):
        """
        Called if a user clicks outside of the viInputPanel
        """
        if self.search and not self.block_kill_focus:
            self.Close()

    def FocusInputField(self, evt=None):
        self.ctrls.viInputTextField.SetFocus()
        self.ctrls.viInputTextField.SetInsertionPointEnd()

    def GetInput(self):
        """
        Helper to get current text in input box
        """
        return self.ctrls.viInputTextField.GetValue()

    def SetInput(self, text, clear=False):
        # Check if we just want to change the cmd argument
        if not clear:
            current_text = self.GetInput().split(" ")
            if len(current_text) > 1:
                text = "{0} {1}".format(current_text[0], text)
        
        if text:
            self.ctrls.viInputTextField.SetValue(text)
            self.ctrls.viInputTextField.SetInsertionPointEnd()

    def OnLeftMouseListBox(self, evt):
        evt.Skip()
        wx.CallAfter(self.FocusInputField)
        wx.CallAfter(self.PostLeftMouseListBox)

    def OnLeftMouseDoubleListBox(self, evt):
        evt.Skip()
        wx.CallAfter(self.PostLeftMouseDoubleListBox)

    def PostLeftMouseListBox(self):
        self.block_list_reload = True
        self.SetInput(self.ctrls.viInputListBox.GetStringSelection())
        self.block_list_reload = False

    def PostLeftMouseDoubleListBox(self):
        self.PostLeftMouseListBox()
        self.ExecuteCmd(self.GetInput())
        self.Close()

    def OnText(self, evt):
        """
        Called whenever new text is inserted into the input box
        """
        if self.search:
            self.RunSearch()

        # cmd
        else:
            if self.block_list_reload:
                return

            cmd, args = self.cmd_parser.ParseCmd(self.GetInput())

            if cmd:
                if args:
                    self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_WHITE)
                    #self.ctrls.viInputListBox.Clear()
                    self.run_cmd_timer.Start(self.ctrl.vi.CMD_INPUT_DELAY)
                else:
                    self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_GREEN)
                    self.CheckViInput()
            else:
                self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_RED)

    def RunSearch(self):
        text = self.GetInput()

        if len(text) < 1:
            return

        self.search_args[u"text"] = text

        # would .copy() be better?
        temp_search_args = dict(self.search_args)

        temp_search_args[u"select_text"] = True

        self.block_kill_focus = True
        # TODO: set flags from config?
        result = self.ctrl.vi._SearchText(**temp_search_args)
        self.FocusInputField()
        self.block_kill_focus = False

        if not result:
            self.ctrl.vi.visualBell("RED")
            self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_YELLOW)
        else:
            self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_GREEN)

    def ExecuteCmd(self, text_input):
        # Should this close the input?
        if len(text_input) < 1:
            return False
        self.cmd_history.AddCmd(text_input)
        if self.search:
            self.search_args[u"text"] = text_input
            self.ctrl.vi.last_search_args = copy.copy(self.search_args)

            self.ctrl.vi.GotoSelectionStart()
        else:
            if self.cmd_parser.RunCmd(text_input, self.ctrls.viInputListBox.GetSelection()):
                self.ctrl.vi.visualBell("GREEN")
            else:
                self.ctrls.viInputTextField.SetBackgroundColour(
                        ViInputDialog.COLOR_YELLOW)
                self.ctrl.vi.visualBell("RED")


    def CheckViInput(self, evt=None):
        # TODO: cleanup
        self.run_cmd_timer.Stop()

        if self.cmd_parser.CheckForRangeCmd(self.ctrls.viInputTextField.GetValue()):
            self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_WHITE)
            return

        valid_cmd = self.ParseViInput(self.ctrls.viInputTextField.GetValue())

        if valid_cmd == False:
            # Nothing found
            self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_YELLOW)
        else:
            # Found
            self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_GREEN)


    def ParseViInput(self, input_text):
        data = self.cmd_parser.ParseCmdWithArgs(input_text)

        if data != self.cmd_list:
            self.cmd_list = data
            self.PopulateListBox(data)

        if not data:
            return False

        return True

    def ForgetViInput(self):
        """
        Called if user cancels the input.
        """
        # Set previous selection?
        self.cmd_history.AddCmd(self.ctrls.viInputTextField.GetValue())
        pos, x, y = self.initial_scroll_pos
        wx.CallAfter(self.ctrl.SetScrollAndCaretPosition, pos, x, y)

    def ClearListBox(self):
        self.ctrls.viInputListBox.Clear()

    def PopulateListBox(self, data):
        
        if data is None or len(data) < 1:
            self.list_data = None
            # No items
            self.ctrls.viInputListBox.Clear()
            self.ctrls.viInputListBox.AppendItems([u"No items / data found."])
            return
        else:
            self.list_data = data

            self.ctrls.viInputListBox.Clear()
            self.ctrls.viInputListBox.AppendItems(data)
        #self.ctrls.viInputListBox.SetSelection(0)

        self.UpdateLayout(show_viInputListBox=True)

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

        searchString = self.GetInput()

        foundPos = -2
        if accP in ((wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER),
                (wx.ACCEL_NORMAL, wx.WXK_RETURN)):
            # Return pressed
            self.ExecuteCmd(self.GetInput())
            self.Close()

        elif accP == (wx.ACCEL_NORMAL, wx.WXK_ESCAPE) or \
                (accP == (wx.ACCEL_NORMAL, wx.WXK_BACK) 
                    and len(searchString) == 0) or \
                        accP == (wx.ACCEL_CTRL, 91):
            # TODO: add ctrl-c (ctrl-[)?
            # Esc -> Abort input, go back to start
            self.ForgetViInput()
            self.Close()
        elif accP == (wx.ACCEL_NORMAL, wx.WXK_BACK):
            # When text is deleted we the search start is reset to the initial
            # position
            pos, x, y = self.initial_scroll_pos
            self.ctrl.SetScrollAndCaretPosition(pos, x, y)
            evt.Skip() # Skip so text is still deleted

        # Arrow keys can be used to navigate the cmd_lie history
        elif accP == (wx.ACCEL_NORMAL, wx.WXK_UP):
            self.SetInput(self.cmd_history.GoBackwardsInHistory(), clear=True)

        elif accP == (wx.ACCEL_NORMAL, wx.WXK_DOWN):
            self.SetInput(self.cmd_history.GoForwardInHistory(), clear=True)

        elif accP == (wx.ACCEL_NORMAL, wx.WXK_TAB):
            self.SelectNextListBoxItem()

        elif accP == (wx.ACCEL_SHIFT, wx.WXK_TAB):
            self.SelectPreviousListBoxItem()

        elif matchesAccelPair("ActivateLink", accP) or \
                matchesAccelPair("ActivateLinkNewTab", accP) or \
                matchesAccelPair("ActivateLink2", accP) or \
                matchesAccelPair("ActivateLinkBackground", accP) or \
                matchesAccelPair("ActivateLinkNewWindow", accP):
            # ActivateLink is normally Ctrl-L
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            # ActivateLink2 is normally Ctrl-Return
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            self.Close()
            self.ctrl.OnKeyDown(evt)
        # handle the other keys
        else:
            evt.Skip()

        if foundPos == False:
            # Nothing found
            self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_YELLOW)
        else:
            # Found
            self.ctrls.viInputTextField.SetBackgroundColour(ViInputDialog.COLOR_GREEN)

        # Else don't change


    def SelectNextListBoxItem(self):
        self.MoveListBoxSelection(1)

    def SelectPreviousListBoxItem(self):
        self.MoveListBoxSelection(-1)

    def MoveListBoxSelection(self, offset):
        if self.ctrls.viInputListBox.GetCount() < 1 or self.list_data is None:
            self.ctrl.vi.visualBell(u"RED")
            return

        if offset < 0:
            select = max
            n = 0
        else:
            select = min
            n = self.ctrls.viInputListBox.GetCount()

        self.ctrls.viInputListBox.SetSelection(select(n, 
                                    self.ctrls.viInputListBox.GetSelection() + offset))
        #split_text = self.GetInput().split(u" ")

        self.block_list_reload = True
        self.SetInput(self.ctrls.viInputListBox.GetStringSelection())
        #if len(split_text) > 1:# and split_text[1] != u"":
        #    self.ctrls.viInputTextField.SetValue("{0} {1}".format(self.ctrls.viInputTextField.GetValue().split(u" ")[0], self.ctrls.viInputListBox.GetStringSelection()))
        #else:
        #    self.ctrls.viInputTextField.SetValue("{0}".format(self.ctrls.viInputListBox.GetStringSelection()))
        self.ctrls.viInputTextField.SetInsertionPointEnd()
        self.block_list_reload = False
        self.run_cmd_timer.Stop()

    def OnTimerIncViInputClose(self, evt):
        self.Close()

    def OnSize(self, evt):
        evt.Skip()
    #    #oldVisible = self.isVisibleEffect()
    #    size = evt.GetSize()
    #    self.sizeVisible = size.GetHeight() >= 5 and size.GetWidth() >= 5

    def ShowPanel(self):
        self.mainControl.windowLayouter.expandWindow("vi input")
        self.FocusInputField()


class PluginKeyError(Exception): pass
