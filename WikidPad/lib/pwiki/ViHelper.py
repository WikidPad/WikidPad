import wx, wx.xrc, wx.html
import wx.lib.dialogs
from . import SystemInfo
from .wxHelper import GUI_ID, getAccelPairFromKeyDown, getTextFromClipboard
from collections import defaultdict
from .StringOps import pathEnc, urlQuote
import os
import configparser
import re
import copy
import string
from . import PluginManager
import subprocess

from .wxHelper import * # Needed for  XrcControls

from .WindowLayout import setWindowSize
from functools import reduce

from .Utilities import DUMBTHREADSTOP, callInMainThread, callInMainThreadAsync
#TODO:  Multiple registers
#       Page marks
#       Alt-combinations
#       .rc


# TODO: should be configurable
AUTOCOMPLETE_BOX_HEIGHT = 50

# # Key accels use a different sep in >= 2.9
# if wx.version() >= 2.9:
#     ACCEL_SEP = "+"
# else:
ACCEL_SEP = "-"

def formatListBox(x, y):
    html = "<table width=100% height=5px><tr><td>{0}</td><td align='right'><font color='gray'>{1}</font></td></tr></table>".format(x, y)
    return html

class ViHelper():
    """
    Base class for ViHandlers to inherit from.

    Contains code and functions that are relevent to VI emulation in
    both editor and preview mode.
    """
    # Modes
    # Current these are only (partly) implemented for the editor
    NORMAL, INSERT, VISUAL, REPLACE = list(range(4))

    MODE_TEXT = { 
                    0 : "", 
                    1 : "--INSERT--", 
                    2 : "--VISUAL--", 
                    3 : "--REPLACE--" 
                }

    # Default key bindings - can be overridden by wikidrc
    KEY_BINDINGS = {
                        "!" : 33,
                        "\"" : 34,
                        "#" : 35,
                        "$" : 36,
                        "%" : 37,
                        "&" : 38,
                        "'" : 39,
                        "(" : 40,
                        ")" : 41,
                        "*" : 42,
                        "+" : 43,
                        "," : 44,
                        "-" : 45,
                        "." : 46,
                        "/" : 47,
                        "0" : 48,
                        "1" : 49,
                        "2" : 50,
                        "3" : 51,
                        "4" : 52,
                        "5" : 53,
                        "6" : 54,
                        "7" : 55,
                        "8" : 56,
                        "9" : 57,
                        ":" : 58,
                        ";" : 59,
                        "<" : 60,
                        "=" : 61,
                        ">" : 62,
                        "?" : 63,
                        "@" : 64,
                        "A" : 65,
                        "B" : 66,
                        "C" : 67,
                        "D" : 68,
                        "E" : 69,
                        "F" : 70,
                        "G" : 71,
                        "H" : 72,
                        "I" : 73,
                        "J" : 74,
                        "K" : 75,
                        "L" : 76,
                        "M" : 77,
                        "N" : 78,
                        "O" : 79,
                        "P" : 80,
                        "Q" : 81,
                        "R" : 82,
                        "S" : 83,
                        "T" : 84,
                        "U" : 85,
                        "V" : 86,
                        "W" : 87,
                        "X" : 88,
                        "Y" : 89,
                        "Z" : 90,
                        "[" : 91,
                        "\\" : 92,
                        "]" : 93,
                        "^" : 94,
                        "_" : 95,
                        "`" : 96,
                        "a" : 97,
                        "b" : 98,
                        "c" : 99,
                        "d" : 100,
                        "e" : 101,
                        "f" : 102,
                        "g" : 103,
                        "h" : 104,
                        "i" : 105,
                        "j" : 106,
                        "k" : 107,
                        "l" : 108,
                        "m" : 109,
                        "n" : 110,
                        "o" : 111,
                        "p" : 112,
                        "q" : 113,
                        "r" : 114,
                        "s" : 115,
                        "t" : 116,
                        "u" : 117,
                        "v" : 118,
                        "w" : 119,
                        "x" : 120,
                        "y" : 121,
                        "z" : 122,
                        "{" : 123,
                        "|" : 124,
                        "}" : 125,
                        "~" : 126,
                    }
                            

    CMD_INPUT_DELAY = 1000
    STRIP_BULLETS_ON_LINE_JOIN = True


    def __init__(self, ctrl):
        # ctrl is WikiTxtCtrl in the case of the editor,
        # WikiHtmlViewWk for the preview mode.
        self.ctrl = ctrl

        self.key_map = {}
        for varName in vars(wx):
            if varName.startswith("WXK_"):
                self.key_map[getattr(wx, varName)] = varName


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

        self.selection_mode = "NORMAL"

        self.tag_input = False
                    
        # The following dictionary holds the menu shortcuts that have been
        # disabled upon entering ViMode
        self.menuShortCuts = {}

        self.viKeyAccels = set()

        self.register = ViRegister(self.ctrl)


        # Settings are stored as a dict
        self.settings = { 
                "filter_wikipages" : True,
                "caret_scroll" : False, # Large performance hit
                
                # The following settings apply to SetHeading()
                "blank_line_above_headings" : True,
                "strip_headings" : True,

                # No. spaces to put between +++ and heading text
                "pad_headings" : 0,

                "gvim_path" : "gvim", 
                "vim_path" : "vim", 

                "caret_colour_normal" : "#FF0000",
                "caret_colour_visual" : "#FFD700",
                "caret_colour_insert" : "#0000FF",
                "caret_colour_replace" : "#8B0000",
                "caret_colour_command" : "#00FFFF",

                "set_wrap_indent_mode": 1,
                "set_wrap_start_indent": 0,
                

                "min_wikipage_search_len" : 2,
                
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
                        if len(key) > 1 and key[0] == "key":
                            if type(key[1]) == tuple:
                                l = list(key[1])
                                key_char = l.pop()

                                l.extend([k[key_char]])

                                return tuple(l)

                            else:
                                return k[key[1]]
                        elif key == "motion" or "m":
                            return "m"
                        elif key == "*":
                            return "*"
                        else:
                            raise PluginKeyError("ERROR LOADING PLUGIN")
                            
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

        NOTE: Should move out of ViHelper as per tab setting are probably
              not required
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
            config = configparser.ConfigParser()
            config.read(rc_file)

            # Load custom key bindings
            try:
                for key in config.options("keys"):
                    try:
                        self.KEY_BINDINGS[key] = config.getint("keys", key)
                    except ValueError:
                        print("Keycode must be a integer: {0}".format(key))
            except configparser.NoSectionError:
                pass
                

            try:
                for setting in config.options("settings"):
                    if setting in self.settings:
                        try:
                            self.settings[setting] = config.getboolean(
                                    "settings", setting)
                        except ValueError:
                            print("Setting '{1}' must be boolean".format(setting))

            except configparser.NoSectionError:
                pass

        self.ApplySettings()

    def ApplySettings(self):
        pass

    def OnChar(self, evt):
        """
        Handles EVT_CHAR events necessary for MS Windows
        """
        m = self.mode

        key = evt.GetKeyCode()

        # OnChar seems to throw different keycodes if ctrl is pressed.
        # a = 1, b = 2 ... z = 26
        # will not handle different cases
        if evt.ControlDown():
            key = key + 96
            key = ("Ctrl", key)

        self.HandleKey(key, m, evt)


    def OnViKeyDown(self, evt):
        """
        Handle keypresses when in Vi mode

        Ideally much of this would be moved to ViHelper

        """
            
        m = self.mode
        key = evt.GetKeyCode()

        if m == ViHelper.INSERT:

            # TODO: Allow navigation with Ctrl-N / Ctrl-P
            accP = getAccelPairFromKeyDown(evt)
            matchesAccelPair = self.ctrl.presenter.getMainControl().\
                                    keyBindings.matchesAccelPair

            if matchesAccelPair("AutoComplete", accP):
                # AutoComplete is normally Ctrl-Space
                # Handle autocompletion
                self.ctrl.autoComplete()

            if self.ctrl.AutoCompActive():
                self.OnAutocompleteKeyDown(evt)

            # The following code is mostly duplicated from OnKeyDown (should be
            # rewritten to avoid duplication)
            # TODO Check all modifiers
            if not evt.ControlDown() and not evt.ShiftDown():  
                if key == wx.WXK_TAB:
                    if self.ctrl.pageType == "form":
                        if not self.ctrl._goToNextFormField():
                            self.ctrl.presenter.getMainControl().showStatusMessage(
                                    _("No more fields in this 'form' page"), -1)
                        return
                    evt.Skip()
                elif key == wx.WXK_RETURN and not self.ctrl.AutoCompActive():
                    text = self.ctrl.GetText()
                    wikiDocument = self.ctrl.presenter.getWikiDocument()
                    bytePos = self.ctrl.GetCurrentPos()
                    lineStartBytePos = self.ctrl.PositionFromLine(
                                            self.ctrl.LineFromPosition(bytePos))

                    lineStartCharPos = len(self.ctrl.GetTextRange(0, 
                                                            lineStartBytePos))
                    charPos = lineStartCharPos + len(self.ctrl.GetTextRange(
                                                    lineStartBytePos, bytePos))

                    autoUnbullet = self.ctrl.presenter.getConfig().getboolean("main",
                            "editor_autoUnbullets", False)

                    settings = {
                            "autoUnbullet": autoUnbullet,
                            "autoBullets": self.ctrl.autoBullets,
                            "autoIndent": self.ctrl.autoIndent
                            }

                    if self.ctrl.wikiLanguageHelper.handleNewLineBeforeEditor(
                            self.ctrl, text, charPos, lineStartCharPos, 
                            wikiDocument, settings):
                        evt.Skip()
                        return
                    # Hack to maintain consistency when pressing return
                    # on an empty bullet
                    elif bytePos != self.ctrl.GetCurrentPos():
                        return

        # Pass modifier keys on
        if key in (wx.WXK_CONTROL, wx.WXK_ALT, wx.WXK_SHIFT):
            return

        # On linux we can just use GetRawKeyCode() and work directly with
        # its return. On windows we have to skip this event (for keys which 
        # will produce a char event to wait for EVT_CHAR (self.OnChar()) to 
        # get the correct key translation
        elif key not in self.key_map:
            key = evt.GetRawKeyCode()
        else:
            # Keys present in the key_map should be consitent across
            # all platforms and can be handled directly.
            key = self.AddModifierToKeychain(key, evt)
            #self.HandleKey(key, m, evt)
            if not self.HandleKey(key, m, evt):
                # For wxPython 2.9.5 we need this otherwise menu accels don't 
                # seem to be triggered (though they worked in previous versions?)
                evt.Skip()
            return

        
            # What about os-x?
        if not SystemInfo.isLinux():
            # Manual fix for some windows problems may be necessary
            # e.g. Ctrl-[ won't work
            evt.Skip()
            return

        key = self.AddModifierToKeychain(key, evt)

        if not self.HandleKey(key, m, evt):
            # For wxPython 2.9.5 we need this otherwise menu accels don't 
            # seem to be triggered (though they worked in previous versions?)
            evt.Skip()

    def AddModifierToKeychain(self, key, evt):
        """
        Checks a key event for modifiers (ctrl / alt) and adds them to
        the key if they are present

        """
        mods = []
        if evt.ControlDown():
            mods.append("Ctrl")

        if evt.AltDown():
            mods.append("Alt")

        if mods:
            mods.extend([key])
            print(mods)
            key = tuple(mods)

        return key


    def EndInsertMode(self):
        pass

    def EndReplaceMode(self):
        pass

    def LeaveVisualMode(self):
        pass

    def HandleKey(self, key, m, evt):

        # There should be a better way to monitor for selection changed
        if self.HasSelection():
            self.EnterVisualMode()


        # TODO: Replace with override keys? break and run function
        # Escape, Ctrl-[, Ctrl-C
        # In VIM Ctrl-C triggers *InsertLeave*
        if key == wx.WXK_ESCAPE or key == ("Ctrl", 91) or key == ("Ctrl", 99): 
            # TODO: Move into ViHandler?
            self.EndInsertMode()
            self.EndReplaceMode()
            self.LeaveVisualMode()
            self.FlushBuffers()
            return True

        # Registers
        if m != 1 and key == 34 and self._acceptable_keys is None \
                and not self.key_inputs: # "
            self.register.select_register = True
            return True
        elif self.register.select_register:
            self.register.SelectRegister(key)
            self.register.select_register = False
            return True


        if m in [1, 3]: # Insert mode, replace mode, 
            # Store each keyevent
            # NOTE:
            #       !!may need to seperate insert and replace modes!!
            #       what about autocomplete?
            # It would be possbile to just store the text that is inserted
            # however then actions would be ignored
            self.insert_action.append(key)

            # Data is reset if the mouse is used or if a non char is pressed
            # Arrow up / arrow down
            if key in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT]: 
                self.EndBeginUndo()
                self.insert_action = []
            if not self.RunKeyChain((key,), m):
                evt.Skip()
                return False
            return True

        if (self._acceptable_keys is None or \
                "*" not in self._acceptable_keys) \
                                and type(key) is not tuple:
            if 48 <= key <= 57: # Normal
                if self.SetNumber(key-48):
                    return True
            elif 65456 <= key <= 65465: # Numpad
                if self.SetNumber(key-65456):
                    return True

        self.SetCount()

        if self._motion and self._acceptable_keys is None:
            #self._acceptable_keys = None
            self._motion.append(key)

            temp = self._motion[:-1]
            temp.append("*")
            if tuple(self._motion) in self.motion_keys[m]:
                self.RunKeyChain(tuple(self.key_inputs), m)
                return True
                #self._motion = []
            elif tuple(temp) in self.motion_keys[m]:
                self._motion[-1] = "*"
                self._motion_wildcard.append(key)
                self.RunKeyChain(tuple(self.key_inputs), m)
                #self._motion = []
                return True
                
            elif tuple(self._motion) in self.motion_key_mods[m]:
                #self._acceptable_keys = self.motion_key_mods[m][tuple(self._motion)]
                return True

            self.FlushBuffers()
            return True


        if self._acceptable_keys is not None:
            if key in self._acceptable_keys:
                self._acceptable_keys = None
                pass
            elif "*" in self._acceptable_keys:
                self._wildcard.append(key)
                self.key_inputs.append("*")
                self._acceptable_keys = None
                self.RunKeyChain(tuple(self.key_inputs), m)

                return True
            elif "m" in self._acceptable_keys:
                self._acceptable_keys = None
                self._motion.append(key)
                if (key,) in self.motion_keys[m]:
                    self.key_inputs.append("m")
                    self.RunKeyChain(tuple(self.key_inputs), m)
                    return True
                elif (key,) == -999:
                    self.key_inputs.append("m")
                    self.RunKeyChain(tuple(self.key_inputs), m)
                if (key,) in self.motion_key_mods[m]:
                    self.key_inputs.append("m")
                    return True


        self.key_inputs.append(key)
        self.updateViStatus()

        key_chain = tuple(self.key_inputs)

        if self.RunKeyChain(key_chain, m):
            return True

        self.FlushBuffers()

        # If a chain command has been started prevent evt.Skip() from being
        # called
        if len(key_chain) > 1:
            return True

        try:
            if "Ctrl" in key or "Alt" in key:   
                return False
        except TypeError:
            pass

        return True

    def KeyCommandInProgress(self):
        return self.key_inputs

    def NextKeyCommandCanBeMotion(self):
        """
        Checks if the next key can be a motion cmd
        """
        if "m" in self._acceptable_keys:
            return True

        return False


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
            # Check for modifiers
            if type(keycode) == tuple:
                l = list(keycode)
                k = l.pop()
                mods = ACCEL_SEP.join(l)
                return "{0}{1}{2}".format(mods, ACCEL_SEP, chr(k))
            try:
                return chr(keycode)
            # This may occur when special keys (e.g. WXK_SPACE) are used
            except TypeError as ValueError: # >wx2.9 ?valueerror?
                return keycode
        else:
            return ""

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
                        l = list(accel)
                        k = l.pop()
                        mods = ACCEL_SEP.join(l)
                        # wx accels chars are always uppercase
                        to_add = "{0}{1}{2}".format(mods, ACCEL_SEP, chr(k).upper())
                        key_accels.add(to_add)
                
        self.viKeyAccels.update(key_accels)

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
                self.SetCaretColour(self.settings['caret_colour_command'])

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
            # TODO: finish
            # If the motion is a mouse event it should have already been run
            if motion != -999:
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

    def SelectionIsForward(self):
        """
        Should be overridden by child class if necessary
        """
        return True

    def GetSelectionDetails(self, selection_type=None):
        """
        Should be overridden by child class if necessary
        """
        return (True, len(self.ctrl.GetSelectedText()))

    def _GetSelectionRange(self):
        return None

    def SetCaretColour(self, colour):
        # TODO: implement this
        pass

    def minmax(self, a, b):
        return min(a, b), max(a, b)

    def updateViStatus(self, force=False):
        # can this be right aligned?
        mode = self.mode
        text = ""
        if mode in self.keys:
            cmd = "".join([self.GetCharFromCode(i) for i in self.key_inputs])
            text = "{0}{1}{2}".format(
                            ViHelper.MODE_TEXT[self.mode],
                            "".join(map(str, self.key_number_modifier)),
                            cmd
                            )

        self.ctrl.presenter.getMainControl().statusBar.SetStatusText(text , 0)

    def _enableMenuShortcuts(self, enable):
        # TODO: should only be called once (at startup / plugin load)
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
                        if chr(accel.GetKeyCode()) in self.viKeyAccels:
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

        self.ctrl.presenter.setTabTitleColour("BLUE")

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
        raise NotImplementedError("To be overridden by derived class")

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
        #mainAreaPanel.presenters[mainAreaPanel.GetSelection()].SetFocus()

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

    def GoogleSelection(self):
        self.StartCmdInput("google ", run_cmd=True)


#--------------------------------------------------------------------
# Misc commands
#--------------------------------------------------------------------
    def viError(self, text):
        """
        Display a visual error message

        """
        self.visualBell(close_delay=10000, text=text)

    def visualBell(self, colour="RED", close_delay=100, text="" ):
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

        bell = ViVisualBell(self.ctrl, -1, rect, colour, close_delay, text)

    def StartCmdInput(self, initial_input=None, run_cmd=False):
        """
        Starts a : cmd input for the currently active (or soon to be 
        activated) tab.

        """
        # TODO: handle switching between presenters
        selection_range = None
        if self.mode == ViHelper.VISUAL:
            if initial_input is None:
                initial_input = "'<,'>"
            else:
                initial_input = "{0}{1}".format(initial_input, self.ctrl.GetSelectedText())
            selection_range = self.ctrl.vi._GetSelectionRange()

        self.ctrl.presenter.setTabTitleColour("RED")

        self.input_window.StartCmd(self.ctrl, self.input_cmd_history, 
                    initial_input, selection_range=selection_range, 
                            run_cmd=run_cmd)


    def RepeatLastSubCmd(self, ignore_flags):
        self.input_window.cmd_parser.RepeatSubCmd(ignore_flags)


    def EndViInput(self):
        """
        Called when input dialog is closed
        """
        self.ctrl.presenter.setTabTitleColour("BLACK")
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

    It can also be used to display error messages (set close_delay to -1 and
    the popup will remain open until the next keyevent).
    """
    
    COLOURS = {
        "RED" : wx.Colour(255, 0, 0), 
        "GREEN" : wx.Colour(0, 255, 0),
        "YELLOW" : wx.Colour(255, 255, 0),
        "BLUE" : wx.Colour(0, 0, 255),
        "WHITE" : wx.Colour(0, 0, 0),
            }
              
    
    def __init__(self, parent, id, rect, colour="RED", close_delay=100, 
            text=""):
        wxPopupOrFrame.__init__(self, parent)
        self.SetPosition(rect.GetPosition())
        self.SetSize(rect.GetSize())
        self.SetBackgroundColour(ViVisualBell.COLOURS[colour])
        self.Show()

        if text:
            self.text = wx.TextCtrl(self, -1,
                text, style=wx.TE_PROCESS_ENTER | wx.TE_RICH)
            self.text.SetBackgroundColour(ViVisualBell.COLOURS[colour])
            self.text.SetForegroundColour(ViVisualBell.COLOURS["WHITE"])

            sizer = wx.BoxSizer(wx.HORIZONTAL)
            sizer.Add(self.text, 1, wx.ALL | wx.EXPAND, 0)

            self.SetSizer(sizer)
            self.Layout()

        self.Show()
        if close_delay > 0:
            self.Bind(wx.EVT_TIMER, self.OnClose,
                    id=GUI_ID.TIMER_VISUAL_BELL_CLOSE)

            self.closeTimer = wx.Timer(self, GUI_ID.TIMER_VISUAL_BELL_CLOSE)
            self.closeTimer.Start(close_delay, True)
        else:
            self.text.Bind(wx.EVT_KEY_DOWN, self.OnClose)
            self.text.Bind(wx.EVT_KILL_FOCUS, self.OnClose)
            self.SetFocus()


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
        wx.Frame.__init__(self, parent, id, "WikidPad Hints",
                rect.GetPosition(), rect.GetSize(),
                wx.NO_BORDER | wx.FRAME_FLOAT_ON_PARENT)

        self.tabMode = tabMode

        self.parent = parent

        self.primary_link = primary_link

        self.viCtrl = viCtrl
        self.mainControl = mainControl
        self.tfInput = wx.TextCtrl(self, GUI_ID.INC_SEARCH_TEXT_FIELD,
                _("Follow Hint:"), style=wx.TE_PROCESS_ENTER | wx.TE_RICH)

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

        self.Bind(wx.EVT_TEXT, self.OnText, id=GUI_ID.INC_SEARCH_TEXT_FIELD)
        self.tfInput.Bind(wx.EVT_KEY_DOWN, self.OnKeyDownInput)
        self.tfInput.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.Bind(wx.EVT_TIMER, self.OnTimerIncSearchClose,
                id=GUI_ID.TIMER_INC_SEARCH_CLOSE)
        self.tfInput.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouseAnyInput)

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
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_PAGEDOWN)):
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

        self.registers['"'] = ""

    def SelectRegister(self, key_code):
        if key_code is None:
            self.current_reg = None
            return

        if type(key_code) == int:
            reg = chr(key_code)
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
    def __init__(self, ctrl, viInputListBox, selection_range=None, ):
        self.ctrl = ctrl

        self.viInputListBox = viInputListBox

        self.selection_range = selection_range
        self.last_sub_cmd = None

        self.cmds = {
            "&" : (self.Pass, self.RepeatSubCmd, "Repeat last command"),
            "&&" : (self.Pass, self.RepeatSubCmdWithFlags,
                        "Repeat last command with flags"),
            "reloadplugins" : (self.Pass, self.ReloadPlugins, 
                    "Reload plugins (use sparingly)"),
            "parents" : (self.GetParentPages, self.OpenWikiPageCurrentTab,
                        "Goto parent page in current page"),
            "tabparents" : (self.GetParentPages, self.OpenWikiPageNewTab,
                        "Goto parent page in new tab"),
            "bgparents" : (self.GetParentPages, self.OpenWikiPageBackgroundTab,
                        "Goto parent page in background tab"),
            "w" : (self.Pass, self.SaveCurrentPage, 
                        "Write (save) current page"),
            "write" : (self.Pass, self.SaveCurrentPage, 
                        "Write (save) current page"),
            "open" : (self.GetWikiPages, self.OpenWikiPageCurrentTab,
                        "Open page in current tab"),
            "edit" : (self.GetWikiPages, self.OpenWikiPageCurrentTab,
                        "Open page in current tab"),
            "tabopen" : (self.GetWikiPages, self.OpenWikiPageNewTab,
                        "Open pagge in new tab"),
            "bgtabopen" : (self.GetWikiPages, self.OpenWikiPageBackgroundTab,
                        "Open page in new background tab"),
            "winopen" : (self.GetWikiPages, self.OpenWikiPageNewWindow,
                        "Open page in new window"),

            "tab" : (self.GetTabs, self.GotoTab, "Goto tab"),
            "buffer" : (self.GetTabs, self.GotoTab, "Goto tab"),

            "split" : (self.GetWikiPages, self.SplitTab, "Split tab"),

            "google" : (self.GetWikiPagesOrSearch, self.OpenPageInGoogle, 
                        "Search google for ..."),
            "wikipedia" : (self.GetWikiPagesOrSearch, self.OpenPageInWikipedia,
                        "Search wikipedia for ..."),

            # TODO: rewrite with vi like confirmation
            "deletepage" : (self.GetDefinedWikiPages, 
                self.ctrl.presenter.getMainControl().showWikiWordDeleteDialog,
                "Delete page"),
            "delpage" : (self.GetDefinedWikiPages, 
                self.ctrl.presenter.getMainControl().showWikiWordDeleteDialog,
                "Delete page"),

            "renamepage" : (self.GetDefinedWikiPages, 
                self.ctrl.presenter.getMainControl().showWikiWordRenameDialog, 
                "Rename page"),

            # Currently bdelete and bwipeout are currently synonymous
            "quit" : (self.GetTabs, self.CloseTab, "Close tab"),
            "bdelete" : (self.GetTabs, self.CloseTab, "Close tab"),
            "bwipeout" : (self.GetTabs, self.CloseTab, "Close tab"),
            "quitall" : (self.Pass, self.CloseWiki, "Close wiki"),
            "tabonly" : (self.GetTabs, self.CloseOtherTabs, 
                        "Close all other tabs"),
            "exit" : (self.Pass, self.CloseWiki,
                        "Close all other tabs"),

            "reloadplugins" : (self.Pass, self.ReloadPlugins, 
                    "Reload plugins (use sparingly)"),

            # Stuff below is for debugging
            "start_pdb_debug" : (self.Pass, self.StartPDBDebug,
                        "Begin a PDB debug session"),

            "inspect" : (self.Pass, self.StartInspection,
                        "Launch the wxPython inspection tool"),

            "start_trace" : (self.Pass, self.StartStackTrace,
                        "Starts logging a stacktrace file"),

            "start_logging" : (self.Pass, self.StartLogging,
                        "Starts logging at a higher level"),

            "list-keybindings" : (self.Pass, self.ShowKeybindings,
                        "Displays a list of the currently \
                            loaded keybindings"),
            }

        if self.ctrl.presenter.getWikiDocument().getDbtype() == \
                "original_sqlite":
            self.cmds["vim"] = (self.GetWikiPages, self.EditWithVim,
                        "Edit page with vim")
            self.cmds["gvim"] = (self.GetWikiPages, self.EditWithGvim,
                        "Edit page with gvim")

        # Attempt to load webkit specific commands
        try:
            if self.ctrl.ViewSource:
                self.cmds["viewsource"] = (self.Pass, self.ctrl.ViewSource, 
                        "View current pages HTML source")
        except AttributeError:
            pass
            

        # marks? search patterns?
        self.cmd_range_starters = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, ".", "$", "%", ",")
        self.range_cmds = {
                            "s" : self.SearchAndReplace,
                            "sort" : self.Sort
                          }
        # TODO: :s repeats last command

        self.range_regex = "(\d+|%|\.|\$|'.)?,?(\d+|%|\.|\$|'.)({0})(.*$)".format(
                                            "|".join(list(self.range_cmds.keys())))

    def StartPDBDebug(self, args=None):
        import pdb; pdb.set_trace()

    def StartInspection(self, args=None):
        import wx.lib.inspection
        wx.CallAfter(wx.lib.inspection.InspectionTool().Show)
        return True

    def StartStackTrace(self, args=None):
        import stacktracer
        stacktracer.trace_start("trace.html",interval=5,auto=True)

    def StartLogging(self, args=None):
        import multiprocessing, logging
        logger = multiprocessing.log_to_stderr()
        logger.setLevel(multiprocessing.SUBDEBUG)



    def ShowKeybindings(self, args=None):
        # A quick and dirty way to view all currently registered vi
        # keybindings and the functions they call

        keys = self.ctrl.vi.keys

        text = []

        for mode in keys:
            text.append("")
            text.append("MODE: {0}".format(mode))

            for binding in keys[mode]:
                chain = " ".join([self.ctrl.vi.GetCharFromCode(i) 
                                        for i in binding])

                text.append("{0} : {1}".format(chain, 
                        keys[mode][binding][1][0].__name__))

        text = "\n".join(text)

        dlg = wx.lib.dialogs.ScrolledMessageDialog(
                self.ctrl.presenter.getMainControl(), text, "Keybindings")

        if dlg.ShowModal():
            pass

        dlg.Destroy()

    
    def SearchAndReplace(self, pattern, ignore_flags=False):
        """
        Function to mimic the :s behavior of vi(m)

        It is designed to be mostly compatable but it currently (and for at
        least the forseable future) has a number of important differences from 
        the native implementation.

        TODO: implement flags
        """
        # As in vim the expression delimeter can be one of a number of 
        # characters
        delims = "/;$|^%,"
        if pattern[0] in delims:
            delim = "\{0}".format(pattern[0])
        else:
            self.ctrl.vi.viError(
                    _("Error: {0} is not a valid delimiter".format(
                        pattern[0])))
            return 2

        # NOTE: Vim does not require all arguments to be present
        #       Current implementation here does
        try:
            search, replace, flags = re.split(r"(?<!\\){0}".format(delim), pattern)[1:]
        except ValueError:
            self.ctrl.vi.viError(_("Incorrect :sub cmd (unable to split patterns using '{0}')".format(delim)))
            return 2

        # First check if there are any pattern modifiers
        #
        # Currently we only check for \V
        # if it exists we escape the search pattern (so it acts as a literal string)
        if search.startswith("\V"):
            search = re.escape(search[2:])


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
        if "g" in flags:
            count = 0

        re_flags = re.M

        # Hack for replaing newline chars
        search = re.sub(r"(?<!\\)\\n", "\n", search)

        try:
            search_regex = re.compile(search, flags=re_flags)
        except re.error as e:
            self.ctrl.vi.viError(_("re compile error: {0}".format(e)))
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
            try:
                self.ctrl.ReplaceSelection(search_regex.sub(replace, text_to_sub))
            except re.error as e:
                self.ctrl.vi.viError(_("Error '{0}')".format(e)))
                return False

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
        return None, None, None

    def CheckForRangeCmd(self, text_input):
        # TODO: improve cmd checking
        if re.match(self.range_regex, text_input):
            return True
        elif re.match("(\d+|%|\.|\$)?,?(\d+|%|\.|\$)({0})".format(
                                "|".join(list(self.range_cmds.keys()))), text_input):
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
        try:
            start_range, end_range, cmd, args = re.match(self.range_regex, text_input).groups()
        except AttributeError as e:
            self.ctrl.vi.viError(_("Error '{0}')".format(e)))

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
        if start_range == "%" or end_range == "%":
            start_range = 0
            end_range = self.ctrl.GetLineCount()
        elif start_range in (None, ""):
            start_range = end_range
            

        # Convert line ranges to char positions
        if type(start_range) == int:
            start_range = self.ctrl.vi.GetLineStartPos(start_range)
        elif start_range == ".":
            start_range = self.ctrl.vi.GetLineStartPos(
                    self.ctrl.GetCurrentLine())
        elif len(start_range) == 2 and start_range.startswith("'"):
            if start_range[1] == "<":
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
        elif end_range == "$":
            end_range = self.ctrl.GetLineEndPosition(
                                self.ctrl.GetLineCount()) + 1
        elif end_range == ".":
            end_range = self.ctrl.GetLineEndPosition(
                                self.ctrl.GetCurrentLine()) + 1
        elif len(end_range) == 2 and end_range.startswith("'"):
            if end_range[1] == ">":
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
            if split_cmd[1] != "":
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

        split_cmd = text_input.split(" ")

        arg = None
        action = split_cmd[0]
        if len(split_cmd) > 1:
            arg = " ".join(split_cmd[1:])

        cmd_list = []
        list_box = []
        
        for cmd in self.cmds:
            if cmd.startswith(action):
                if arg is not None or text_input.endswith(" "):
                    return self.cmds[cmd][0](arg)
                else:
                    cmd_list.append(cmd)
                    list_box.append(formatListBox(cmd, self.cmds[cmd][2]))

        return cmd_list, list_box, cmd_list

    def RunCmd(self, text_input, viInputListBox_selection):
        """
        Handles the executing of a : command
        """
        if self.CheckForRangeCmd(text_input):
            return self.ExecuteRangeCmd(text_input)

        if viInputListBox_selection is not None and \
                viInputListBox_selection > -1 and self.viInputListBox.HasData():
            arg = (0, self.viInputListBox.GetData(viInputListBox_selection))
        else:
            arg = None

        split_cmd = [i for i in text_input.split(" ") if len(i) > 0]

        action = split_cmd[0]
        if arg is None and len(split_cmd) > 1: #and len(split_cmd[1]) > 0:
            arg = (1, " ".join(split_cmd[1:]))

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
        self.cmd_list = []

##############################################
### Helpers
##############################################

    def GetTabFromArgs(self, args, default_to_current=True):
        """
        Helper to get a tab (buffer) from an argument

        @param args: The tab to select
        @param default_to_current: Default - True. If True and no arg
            current tab will be return, else None.

        @return: The presenter belonging to the current tab.
        """
        if args is None:
            if default_to_current:
                return self.ctrl.presenter
            else:
                return None
            
        arg_type, arg = args

        if arg_type == 0:
            return arg
        elif arg_type == 1:
            if arg.strip() == "":
                return self.ctrl.presenter
            tabs = self.GetTabs(arg)

            if not tabs[0]:
                return None
            
            return tabs[0][0]

    def GetWikiPageFromArgs(self, args, default_to_current_page=False):
        """
        Helper to get wikipage from string / list data

        @return: wikipage (formatted in link format)
        """
        if args is None:
            if default_to_current_page:
                current_page = self.ctrl.presenter.getMainControl().\
                        getCurrentWikiWord()
                return ((current_page, 0, current_page, -1, -1),)

            else:
                return False

        arg_type, arg = args

        # If args is a string just use it as a wikiword directly
        if arg_type == 1:
            if arg.strip() == "":
                return False

            # Do we want to allow whitespaced wikiwords?
            arg = arg.strip()

            # We create the required link format here
            return ((arg, 0, arg, -1, -1),)

        # If arg type is data the format should be correct already
        elif arg_type == 0:
            return args

             
    def OpenWikiPage(self, args, tab_mode):
        """
        Helper to open wikipage

        Parses args through GetWikiPagesFromArgs()
        """
        #if not type(link_info) == tuple:
        #    value = ((link_info, 0, link_info, -1, -1),)
        #else:
        #    value = (link_info,)

        # TODO: think about using more of the link data

        value = self.GetWikiPageFromArgs(args)

        wikiword = value[0][2]

        strip_whitespace_from_wikiword = True
        if strip_whitespace_from_wikiword:
            wikiword = wikiword.strip()

        return self.ctrl.presenter.getMainControl().activatePageByUnifiedName(
                "wikipage/" + wikiword, tabMode=tab_mode, 
                firstcharpos=value[0][3], charlength=value[0][4])


##############################################

    def ReloadPlugins(self, args=None):
        """
        Reload plugins globally using reloadMenuPlugins() and then
        on a per tab basis. i.e. applies changes to all open tabs -
        reloadMenuPlugins() does not reload vi plugins.


        NOTE: Excessive use of this function will lead to a noticable
              increase in memory usage. i.e. should only be used for
              dev purposes.
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

        
    def EditWithVim(self, args=None):
        """
        Edit "page" in vim (using a subprocess)

        If no pages specified current page is used

        Only works with original_sqlite backend
        """
        page = self.GetWikiPageFromArgs(args, 
                default_to_current_page=True)[0][0]

        mainCtrl = self.ctrl.presenter.getMainControl()
        if page is None:
            page = self.ctrl.presenter.getWikiWord()

        file_path = self.ctrl.presenter.getMainControl().getWikiData().\
                    getWikiWordFileName(page)
        
        p = subprocess.Popen([self.ctrl.vi.settings['vim_path'], file_path], 
                shell=True)

        return True
        
    def EditWithGvim(self, args=None):
        """
        Same as above (EditWithVim) but using gvim instead
        """
        page = self.GetWikiPageFromArgs(args, 
                default_to_current_page=True)[0][0]

        mainCtrl = self.ctrl.presenter.getMainControl()
        if page is None:
            page = self.ctrl.presenter.getWikiWord()

        file_path = self.ctrl.presenter.getMainControl().getWikiData().\
                    getWikiWordFileName(page)
        
        p = subprocess.Popen([self.ctrl.vi.settings['gvim_path'], file_path])

        return True

    def OpenPageInGoogle(self, args=None):
        """
        Searches google for "args" (default = current page)
        
        Suggested args: Wikipages
        """
        page = self.GetWikiPageFromArgs(args, 
                default_to_current_page=True)[0][0]

        mainCtrl = self.ctrl.presenter.getMainControl()
        if page is None:
            page = self.ctrl.presenter.getWikiWord()

        mainCtrl.launchUrl("https://www.google.com/search?q={0}".format(
                urlQuote(page)))
        return True

    def OpenPageInWikipedia(self, args=None):
        page = self.GetWikiPageFromArgs(args, 
                default_to_current_page=True)[0][0]

        mainCtrl = self.ctrl.presenter.getMainControl()
        if page is None:
            page = self.ctrl.presenter.getWikiWord()
 
        mainCtrl.launchUrl("https://www.wikipedia.org/wiki/{0}".format(
                urlQuote(page)))
        return True

    def CloseOtherTabs(self, args=None):
        """
        Closes all tabs except for one specified by "args"

        @return True if successful, False if not (tab does not exist)
        """
        if self.GotoTab(args):
            self.ctrl.presenter.getMainControl().getMainAreaPanel()\
                    ._closeAllButCurrentTab()
            return True
        return False

    def SaveCurrentPage(self, args=None):
        """
        Force save of current page
        """
        self.ctrl.presenter.saveCurrentDocPage()
        return True

    def OpenWikiPageCurrentTab(self, args):
        return self.OpenWikiPage(args, 0)

    def OpenWikiPageNewTab(self, args):
        return self.OpenWikiPage(args, 2)

    def OpenWikiPageBackgroundTab(self, args):
        return self.OpenWikiPage(args, 3)

    def OpenWikiPageNewWindow(self, args):
        return self.OpenWikiPage(args, 6)

    def CloseTab(self, args=None):
        """
        Close specified tab

        @args: tab to close

        @return: True if successful, False if not
        """
        #if text_input is None:
        #    self.ctrl.vi.CloseCurrentTab()
        #    return True
        tab = self.GetTabFromArgs(args)

        if tab is None:
            return False
        
        wx.CallAfter(self.ctrl.presenter.getMainControl().getMainAreaPanel()\
                .closePresenterTab, tab)
        return True

    def GotoTab(self, args=None):
        """
        Goto specified tab
        """
        
        tab = self.GetTabFromArgs(args)

        if tab is None:
            return False
        
        self.ctrl.presenter.getMainControl().getMainAreaPanel()\
                .showPresenter(tab)
        return True
        #return False

    def SplitTab(self, args=None):
        if args is None:
            presenter = self.CloneCurrentTab()
        else:
            presenter = self.OpenWikiPageNewTab(args)

        presenter.makeCurrent()

        mainAreaPanel = self.ctrl.presenter.getMainControl().getMainAreaPanel()
        page = mainAreaPanel.GetPageIndex(presenter)

        wx.CallAfter(mainAreaPanel.Split, page, wx.RIGHT)

    def CloneCurrentTab(self):
        return self.ctrl.presenter.getMainControl().activatePageByUnifiedName("wikipage/" + self.ctrl.presenter.getWikiWord(), tabMode=2)
            
    def CloseWiki(self, arg=None):
        """
        Close current wiki
        """
        self.ctrl.presenter.getMainControl().exitWiki()

###########################################################

    def GetTabs(self, text_input):
        """
        Return a list of currently open tabs (suitable for suggest box)

        @return_type: tuple - (list, list, list)
        @return: (tab instances, tab names, tab names)
        """
        mainAreaPanel = self.ctrl.presenter.getMainControl().getMainAreaPanel()
        page_count = mainAreaPanel.GetPageCount()

        tabs = []

        tab_names = []

        for i in range(page_count):
            page = mainAreaPanel.GetPage(i)

            wikiword = page.getWikiWord()

            if wikiword.startswith(text_input):
                tab_names.append(wikiword)
                tabs.append(page)

        return tabs, tab_names, tab_names

    def GetDefinedWikiPages(self, search_text):
        if search_text is None or search.text.strip() == "":
            return None, (_("Enter wikiword..."),), None

        results = self.ctrl.presenter.getMainControl().getWikiData().\
                                                getAllDefinedWikiPageNames()
        self.cmd_list = results

        if search_text.strip() == "":
            return results

        results = [i for i in self.cmd_list if i.find(search_text) > -1]

        if not results:
            return None, None, None

        return results

    def GetWikiPagesOrSearch(self, search_text):
        if search_text is None or search_text.strip() == "":
            return None, (_("Enter wikiword (or text) to search for..."),), \
                    None
        return self.GetWikiPages(search_text)

    def GetWikiPages(self, search_text):
        if search_text is None or \
                len(search_text.strip()) < self.ctrl.vi.settings['min_wikipage_search_len']:
            return None, (_("Enter wikiword..."),), None

        results = self.ctrl.presenter.getMainControl().getWikiData().\
                    getWikiWordMatchTermsWith(
                            search_text, orderBy="word", descend=False)

        # Quick hack to filter repetative alias'
        if self.ctrl.vi.settings["filter_wikipages"]:
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

                    # Ignore alias if it points to the same page as the
                    # the item above it in the list
                    if l and l[-1][2] == wikiword:
                        continue
                    
                    for r in (("'s", ""), ("-", ""), (" ", "")):
                        alias = alias.replace(*r)
                        wikiword_mod = wikiword_mod.replace(*r)

                    # Only hide aliases if the actually page is in the list
                    if (alias in wikiword_mod or wikiword_mod in alias) and \
                            wikiword in pages:
                        continue

                l.append(x)

            results = l
                
        if not results:
            return None, None, None

        formatted_results = [formatListBox(i[0], i[2]) for i in results]

        # NOTE: it would be possible to open pages at specific positions
        pages = [i[2] for i in results]

        return pages, formatted_results, pages

    def GetParentPages(self, search_text):
        presenter = self.ctrl.presenter
        word = presenter.getWikiWord()

        parents = presenter.getMainControl().getWikiData(). \
                    getParentRelationships(word)

 
        # If no parents give a notification and exit
        if len(parents) == 0:
            self.ctrl.vi.visualBell()
            return None, (_("Page has no parents"),), None

        return parents, parents, parents

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
            return ""
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

        #d = wx.PrePanel()
        #self.PostCreate(d)
        wx.Panel.__init__(self)

        self.mainControl = mainControl

        listBox = ViCmdList(parent)

        res = wx.xrc.XmlResource.Get()
        res.LoadPanel(self, parent, "ViInputDialog")
        self.ctrls = XrcControls(self)

        res.AttachUnknownControl("viInputListBox", listBox, self)



        self.sizeVisible = True

#        self.dialog_start_pos = rect.GetPosition()
#        self.dialog_start_size = rect.GetSize()
        #self.dialog_start_size = rect.GetSize()

        self.Bind(wx.EVT_SIZE, self.OnSize)

        self.run_cmd_timer = wx.Timer(self, GUI_ID.TIMER_VI_UPDATE_CMD)
        #wx.EVT_TIMER(self, GUI_ID.TIMER_VI_UPDATE_CMD, self.CheckViInput)
        self.Bind(wx.EVT_TIMER, self.CheckViInput, 
                id=GUI_ID.TIMER_VI_UPDATE_CMD)

        self.ctrls.viInputTextField.SetBackgroundColour(
                ViInputDialog.COLOR_YELLOW)

        self.closeDelay = 0 # Milliseconds to close or 0 to deactivate

        #wx.EVT_SET_FOCUS(self.ctrls.viInputListBox, self.FocusInputField)

        self.Bind(wx.EVT_TEXT, self.OnText, id=GUI_ID.viInputTextField)
        self.ctrls.viInputTextField.Bind(wx.EVT_KEY_DOWN, self.OnKeyDownInput)

        #wx.EVT_TIMER(self, GUI_ID.TIMER_INC_SEARCH_CLOSE,
        #        self.OnTimerIncViInputClose)
        if self.closeDelay:
            self.Bind(wx.EVT_TIMER, self.OnTimerIncViInputClose,
                    id=GUI_ID.TIMER_INC_SEARCH_CLOSE)

        self.ctrls.viInputTextField.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouseAnyInput)

        self.ctrls.viInputListBox.Bind(wx.EVT_LEFT_DOWN, self.OnLeftMouseListBox)
        self.ctrls.viInputListBox.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftMouseDoubleListBox)

        if self.closeDelay:
            self.closeTimer = wx.Timer(self, GUI_ID.TIMER_INC_SEARCH_CLOSE)
            self.closeTimer.Start(self.closeDelay, True)

        self.selection_range = None

        self.list_selection = None

        self.block_kill_focus = False
        self.ctrls.viInputTextField.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)

    def StartCmd(self, ctrl, cmd_history, text, selection_range=None, 
                                                            run_cmd=False):
        self.search = False
        self.selection_range = selection_range
        self.StartInput(text, ctrl, cmd_history)

        if run_cmd:
            wx.CallAfter(self.ExecuteCurrentCmd)

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

        self.ctrls.viInputListBox.ClearData()

        self.cmd_list = []

        self.cmd_parser = CmdParser(self.ctrl, self.ctrls.viInputListBox, self.selection_range)
        
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
        self.SetInput(self.ctrls.viInputListBox.GetCurrentArg())
        self.block_list_reload = False

    def PostLeftMouseDoubleListBox(self):
        self.PostLeftMouseListBox()
        self.list_selectionn = True
        self.ExecuteCurrentCmd()

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

        self.search_args["text"] = text

        # would .copy() be better?
        temp_search_args = dict(self.search_args)

        temp_search_args["select_text"] = True

        self.block_kill_focus = True
        # TODO: set flags from config?
        result = self.ctrl.vi._SearchText(**temp_search_args)
        self.FocusInputField()
        self.block_kill_focus = False

        if not result:
            self.ctrl.vi.visualBell("RED")
            self.SetBackgroundColour(ViInputDialog.COLOR_YELLOW)
        else:
            self.SetBackgroundColour(ViInputDialog.COLOR_GREEN)

    def ExecuteCmd(self, text_input):
        # Should this close the input?
        if len(text_input) < 1:
            return False
        self.cmd_history.AddCmd(text_input)
        if self.search:
            self.search_args["text"] = text_input
            self.ctrl.vi.last_search_args = copy.copy(self.search_args)

            self.ctrl.vi.GotoSelectionStart()
        else:
            if self.cmd_parser.RunCmd(text_input, self.list_selection):
                self.ctrl.vi.visualBell("GREEN")
            else:
                self.ctrls.viInputTextField.SetBackgroundColour(
                        ViInputDialog.COLOR_YELLOW)
                self.ctrl.vi.visualBell("RED")


    def CheckViInput(self, evt=None):
        # TODO: cleanup
        self.run_cmd_timer.Stop()

        if self.cmd_parser.CheckForRangeCmd(self.ctrls.viInputTextField.GetValue()):
            self.SetBackgroundColour(ViInputDialog.COLOR_WHITE)
            return

        valid_cmd = self.ParseViInput(self.ctrls.viInputTextField.GetValue())

        if valid_cmd == False:
            # Nothing found
            self.SetBackgroundColour(ViInputDialog.COLOR_YELLOW)
        else:
            # Found
            self.SetBackgroundColour(ViInputDialog.COLOR_GREEN)


    def ParseViInput(self, input_text):
        data, formatted_data, args = self.cmd_parser.ParseCmdWithArgs(input_text)

        #if cmd_list != self.cmd_list:
        #    self.cmd_list = cmd_list
        #    self.PopulateListBox(data)

        self.PopulateListBox(data, formatted_data, args)

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
        wx.CallAfter(self.ctrls.viInputListBox.ClearData)

    def PopulateListBox(self, data, formatted_data, args):
        if data is None or not data:
            if formatted_data:
                self.ctrls.viInputListBox.SetData(data=None, 
                        formatted_data=formatted_data)
            else:
                # No items
                self.ctrls.viInputListBox.SetData(None)
            return
        else:

            self.ctrls.viInputListBox.SetData(data, formatted_data, args)
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

        self.list_selection = None

        # If shift is presesd (by itself) we can safely skip it
        if key == 306:
            return

        foundPos = -2
        if accP in ((wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER),
                (wx.ACCEL_NORMAL, wx.WXK_RETURN)):
            # Return pressed
            self.ExecuteCurrentCmd()

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
        elif accP == (wx.ACCEL_NORMAL, wx.WXK_SPACE):
            # This may be used in the future
            self.ctrls.viInputListBox.SetSelection(-1)
            evt.Skip()
            pass
        # handle the other keys
        else:
            self.ctrls.viInputListBox.SetSelection(-1)
            evt.Skip()

        if foundPos == False:
            # Nothing found
            self.SetBackgroundColour(ViInputDialog.COLOR_YELLOW)
        else:
            # Found
            self.SetBackgroundColour(ViInputDialog.COLOR_GREEN)

        # Else don't change

    def SetBackgroundColour(self, colour):
        callInMainThread(self.ctrls.viInputTextField.SetBackgroundColour, colour)

    def ExecuteCurrentCmd(self):
        self.ExecuteCmd(self.GetInput())
        self.Close()

    def SelectNextListBoxItem(self):
        self.MoveListBoxSelection(1)

    def SelectPreviousListBoxItem(self):
        self.MoveListBoxSelection(-1)

    def MoveListBoxSelection(self, offset):
        if not self.ctrls.viInputListBox.HasData():
            self.ctrl.vi.visualBell("RED")
            return

        if offset < 0:
            select = max
            n = 0
        else:
            select = min
            n = self.ctrls.viInputListBox.GetCount()

        sel_no = select(n, self.ctrls.viInputListBox.GetSelection() + offset)

        self.ctrls.viInputListBox.SetSelection(sel_no)
        #split_text = self.GetInput().split(u" ")

        self.list_selection = sel_no

        self.block_list_reload = True
        self.SetInput(self.ctrls.viInputListBox.GetCurrentArg())
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


class ViCmdList(wx.html.HtmlListBox):
    def __init__(self, parent):
        """
        Html list box which holds completion info.p

        Consists of 3 parts
          
        formatted_data: html formatted string as will appear in the list box
        data: associated data (is not restricted to a particular type)
        args: simple string that will be used as the arg if listbox item is
          selected
        """

        wx.html.HtmlListBox.__init__(self, parent, -1)

        self.parent = parent

        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnDClick, id=-1)

        self.ClearData()

    def ClearData(self):
        self.data = None
        self.formatted_data = []
        self.args = []
        self.SetItemCount(0)

    def HasData(self):
        if self.data is None:
            return False
        else:
            return True

    def SetData(self, data, formatted_data=[], args=[]):
        if data is None:
            if formatted_data:
                self.formatted_data = formatted_data
            else:
                self.formatted_data = ["No items / data found."]
            self.data = None

        else:
            self.formatted_data = formatted_data
            self.data = data
            self.args = args

        self.SetItemCount(len(self.formatted_data))

        self.Refresh()

    def GetArg(self, n):
        return self.args[n]

    def GetData(self, n):
        return self.data[n]

    def GetCurrentArg(self):
        return self.args[self.GetSelection()]

    def GetCurrentData(self):
        return self.data[self.GetSelection()]

    #def AppendItems(self, formatted_data, data, args):
    #    self.data.append(data)
    #    self.Refresh()

    def OnGetItem(self, n):
        if self.formatted_data is not None:
            return self.formatted_data[n]
        else:
            return None

    def GetCount(self):
        return len(self.data)

    def OnDClick(self, evt):
        pass

class PluginKeyError(Exception): pass
