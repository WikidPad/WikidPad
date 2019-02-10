

import traceback
import difflib, re

import wx, wx.stc, wx.xrc

from .wxHelper import GUI_ID, copyTextToClipboard, WindowUpdateLocker, \
        appendToMenuByMenuDesc

from Consts import FormatTypes

from . import StringOps


from .WikiPyparsing import TerminalNode, NonTerminalNode

from .EnhancedScintillaControl import StyleCollector
from .SearchableScintillaControl import SearchableScintillaControl




def bytelenSct(us):
    """
    us -- unicode string
    returns: Number of bytes us requires in Scintilla (with UTF-8 encoding=Unicode)
    """
    return len(StringOps.utf8Enc(us)[0])




_WORD_DIVIDER = re.compile(r"(\b[\w']+)",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# TODO: Handle editing and rename/delete of baseDocPage
class InlineDiffControl(SearchableScintillaControl):
    def __init__(self, presenter, mainControl, parent, ID):
        SearchableScintillaControl.__init__(self, presenter, mainControl,
                parent, ID)
        
        self.fromText = None
        self.toText = None
        self.fromVerNo = None
        self.toVerNo = None

#         self.presenter = presenter
#         self.mainControl = mainControl
        self.procTokens = None # NonTerminalNode with TerminalNode s
        self.stylebytes = None
        self.baseDocPage = None

        res = wx.xrc.XmlResource.Get()
        self.tabContextMenu = res.LoadMenu("MenuDiffTabPopup")

        config = self.mainControl.getConfig()
        self.defaultFont = config.get("main", "font",
                self.mainControl.presentationExt.faces["mono"])
        self.setWrapMode(config.getboolean("main", "wrap_mode"))

        self.Bind(wx.stc.EVT_STC_STYLENEEDED, self.OnStyleNeeded, id=ID)

        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)

        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

        self.Bind(wx.EVT_MENU, lambda evt: self.Copy(), id=GUI_ID.CMD_CLIPBOARD_COPY)
        self.Bind(wx.EVT_MENU, lambda evt: self.SelectAll(), id=GUI_ID.CMD_SELECT_ALL)

        self.tabContextMenu.Bind(wx.EVT_MENU, self.OnCmdSwapFromTo, id=GUI_ID.CMD_DIFF_SWAP_FROM_TO)

        self.Bind(wx.EVT_MENU, lambda evt: self.CmdKeyExecute(wx.stc.STC_CMD_ZOOMIN), id=GUI_ID.CMD_ZOOM_IN)
        self.Bind(wx.EVT_MENU, lambda evt: self.CmdKeyExecute(wx.stc.STC_CMD_ZOOMOUT), id=GUI_ID.CMD_ZOOM_OUT)



# TODO: Make work
#         self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT, "face:%(mono)s,size:%(size)d" %
#                 self.presenter.getDefaultFontFaces())

        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT, "face:%(mono)s,size:%(size)d" %
                        self.mainControl.presentationExt.faces)

        self.StyleSetSpec(2, "face:%(mono)s,size:%(size)d" %
                        self.mainControl.presentationExt.faces)

        self.setStyles()


    def close(self):
        """
        Close the editor (=prepare for destruction)
        """
        pass
#         self.calltipThreadHolder.setThread(None)
# 
#         self.presenterListener.disconnect()


    def setLayerVisible(self, vis, scName=""):
        """
        Informs the widget if it is really visible on the screen or not
        """
#         if vis:
#             self.Enable(True)
        self.Enable(vis)


    def getTabContextMenu(self):
        return self.tabContextMenu

    def getBaseDocPage(self):
        return self.baseDocPage


    def setWrapMode(self, onOrOff, charWrap=None):
        if charWrap is None:
            docPage = self.baseDocPage
            if docPage is not None:
                charWrap = docPage.getAttributeOrGlobal("wrap_type",
                        "word").lower().startswith("char")
            else:
                charWrap = False
        if onOrOff:
            if charWrap:
                self.SetWrapMode(wx.stc.STC_WRAP_CHAR)
            else:
                self.SetWrapMode(wx.stc.STC_WRAP_WORD)
        else:
            self.SetWrapMode(wx.stc.STC_WRAP_NONE)


    def getWrapMode(self):
        return self.GetWrapMode() != wx.stc.STC_WRAP_NONE


    def showDiffs(self, baseDocPage, fromText, toText, fromVerNo, toVerNo):
        self.baseDocPage = baseDocPage
        self.fromText = fromText
        self.toText = toText
        self.fromVerNo = fromVerNo
        self.toVerNo = toVerNo
                       

        font = self.baseDocPage.getAttributeOrGlobal("font",
                self.defaultFont)
                
        # this updates depending on attribute "wrap_type" (word or character)
        self.setWrapMode(self.getWrapMode())

        faces = self.mainControl.getPresentationExt().faces.copy()
        faces["mono"] = font
        self.setStyles(faces)


        self._calcProcTokensCharWise(fromText, toText)
        text = self._buildViewText()
        self._calcViewStylebytes(text)

        readOnly = self.GetReadOnly()
        self.SetReadOnly(False)
        self.setTextScrollProtected(text)
        self.SetReadOnly(readOnly)
        
        self.presenter.setTitle(_("<Diff from %s to %s>") % (fromVerNo, toVerNo))


    def showDiffsNewFrom(self, baseDocPage, fromText, fromVerNo):
        self.showDiffs(baseDocPage, fromText, self.toText,
                fromVerNo, self.toVerNo)


    def showDiffsNewTo(self, baseDocPage, toText, toVerNo):
        self.showDiffs(baseDocPage, self.fromText, toText,
                self.fromVerNo, toVerNo)



    def _calcProcTokensCharWiseDifflib(self, fromText, toText):
        sm = difflib.SequenceMatcher(None, fromText, toText, autojunk=False)
        ops = sm.get_opcodes()

        procList = []
        charPos = 0
        for tag, i1, i2, j1, j2 in ops:
            if tag == "replace":
                procText = fromText[i1:i2].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "delete")
                procList.append(node)
                charPos += len(procText)

                procText = toText[j1:j2].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "insert")
                procList.append(node)
                charPos += len(procText)
            elif tag == "delete":
                procText = fromText[i1:i2].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "delete")
                procList.append(node)
                charPos += len(procText)
            elif tag == "insert":
                procText = toText[j1:j2].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "insert")
                procList.append(node)
                charPos += len(procText)
            elif tag == "equal":
                node = TerminalNode(fromText[i1:i2], charPos, "equal")
                procList.append(node)
                charPos += i2 - i1

        self.procTokens = NonTerminalNode(procList, 2, "diff")


    def _calcProcTokensCharWiseMyersUkkonen(self, fromText, toText):
        from .StringOps import muCompactDiff
        
        cops = muCompactDiff(fromText, toText)
        
        procList = []
        charPos = 0
        fromPos = 0
        
        for op in cops:
            if fromPos < op[1]:    # there was equal text before charPos
                node = TerminalNode(fromText[fromPos:op[1]], charPos, "equal")
                procList.append(node)
                charPos += op[1] - fromPos
    
            if op[0] == 0:  # replace
                procText = fromText[op[1]:op[2]].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "delete")
                procList.append(node)
                charPos += len(procText)

                procText = op[3].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "insert")
                procList.append(node)
                charPos += len(procText)
            elif op[0] == 1:  # delete
                procText = fromText[op[1]:op[2]].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "delete")
                procList.append(node)
                charPos += len(procText)
            elif op[0] == 2:  # insert
                procText = op[2].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "insert")
                procList.append(node)
                charPos += len(procText)

            fromPos = op[1]
    
        if fromPos < len(fromText):
            node = TerminalNode(fromText[fromPos:], charPos, "equal")
            procList.append(node)
            charPos += len(fromText) - fromPos

        self.procTokens = NonTerminalNode(procList, 2, "diff")


    _calcProcTokensCharWise = _calcProcTokensCharWiseDifflib   #   _calcProcTokensCharWiseMyersUkkonen


    @staticmethod
    def _divideToWords(text):
        divided = _WORD_DIVIDER.split(text)
        if len(divided) == 0:
            return [], []
        
        if divided[0] == "":
            del divided[0]
            if len(divided) == 0:
                return [], []
        
        if divided[-1] == "":
            del divided[-1]
            if len(divided) == 0:
                return [], []
        
        posIdx = [None] * (len(divided) + 1)    # len(divided)   # 
        pos = 0
        
        for i, s in enumerate(divided):
            posIdx[i] = pos
            pos += len(s)
            
        posIdx[-1] = pos

        return divided, posIdx


    def _calcProcTokensWordWise(self, fromText, toText):
        fromDivided, fromPosIdx = self._divideToWords(fromText)
        toDivided, toPosIdx = self._divideToWords(toText)
        
        sm = difflib.SequenceMatcher(None, fromDivided, toDivided, autojunk=False)
        ops = sm.get_opcodes()

        procList = []
        charPos = 0
        for tag, i1, i2, j1, j2 in ops:
            if tag == "replace":
                procText = fromText[fromPosIdx[i1]:fromPosIdx[i2]].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "delete")
                procList.append(node)
                charPos += len(procText)

                toPosIdx[j1]
                toPosIdx[j2]
                toText[toPosIdx[j1]:toPosIdx[j2]]

                procText = toText[toPosIdx[j1]:toPosIdx[j2]].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "insert")
                procList.append(node)
                charPos += len(procText)
            elif tag == "delete":
                procText = fromText[fromPosIdx[i1]:fromPosIdx[i2]].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "delete")
                procList.append(node)
                charPos += len(procText)
            elif tag == "insert":
                procText = toText[toPosIdx[j1]:toPosIdx[j2]].replace("\n", "\n ")
                node = TerminalNode(procText, charPos, "insert")
                procList.append(node)
                charPos += len(procText)
            elif tag == "equal":
                node = TerminalNode(fromText[fromPosIdx[i1]:fromPosIdx[i2]], charPos, "equal")
                procList.append(node)
                charPos += fromPosIdx[i2] - fromPosIdx[i1]

        self.procTokens = NonTerminalNode(procList, 2, "diff")


    def _buildViewText(self):
        return "".join([n.getText() for n in self.procTokens])



    _NODENAME_TO_STYLEBYTE = {
            "equal": 2,
            "delete": 0 | wx.stc.STC_INDIC0_MASK,
            "insert": 1 | wx.stc.STC_INDIC1_MASK
        }

    def _calcViewStylebytes(self, text):
        stylebytes = StyleCollector(wx.stc.STC_STYLE_DEFAULT, text,
                bytelenSct)
                
        _NODENAME_TO_STYLEBYTE = self._NODENAME_TO_STYLEBYTE
        
        for node in self.procTokens:
            stylebytes.bindStyle(node.pos, node.strLength,
                    _NODENAME_TO_STYLEBYTE[node.name])
        
        self.stylebytes = stylebytes.value()


    def OnCmdSwapFromTo(self, evt):
        self.showDiffs(self.baseDocPage, self.toText, self.fromText,
                self.toVerNo, self.fromVerNo)


    def OnKeyDown(self, evt):
        key = evt.GetKeyCode()

        if key == wx.WXK_TAB and not evt.ControlDown():
            nodeIdx = self.procTokens.findFlatNodeIndexForCharPos(
                    self.GetSelectionCharPos()[0])
            if nodeIdx == -1:
                return

            if not evt.ShiftDown():
                # Go forward to next change
                nodeCount = self.procTokens.getChildrenCount()
                unchangedPartFound = False
                for nodeIdx in range(nodeIdx, nodeCount):
                    node = self.procTokens[nodeIdx]
                    if node.name == "equal":
                        unchangedPartFound = True
                        continue
                    else:
                        if not unchangedPartFound:
                            # We are inside the current changes yet
                            continue
                        else:
                            self.gotoCharPos(node.pos)
                            break
            else:
                # Go backward to previous change
                state = 0
                # State transition:
                # 0 -> equal found -> 1 -> change found -> 2 -> equal found -> 3
                # In state 3 nodeIdx + 1 is index to the change node

                for nodeIdx in range(nodeIdx - 1, -1, -1):
                    node = self.procTokens[nodeIdx]
                    if node.name == "equal":
                        if state == 0:
                            state = 1
                        elif state == 2:
                            state = 3
                            node = self.procTokens[nodeIdx + 1]
                            self.gotoCharPos(node.pos)
                            break
                        continue
                    else:
                        if state == 1:
                            state = 2
                        continue

                if state == 2:
                    # Change at the very beginning of the diff (no equal before)
                    node = self.procTokens[0]
                    self.gotoCharPos(node.pos)

            return


        super(InlineDiffControl, self).OnKeyDown(evt)



    def setStyles(self, styleFaces=None):
        self.SetStyleBits(5)
        
        if styleFaces is None:
            styleFaces = self.mainControl.getPresentationExt().faces

        styles = self.mainControl.getPresentationExt().getStyles(styleFaces,
                self.mainControl.getConfig())

        # First set styles according to
        # 1. "Presentation.py" extension (default style)
        # 2. Attributes for this wiki and page
        for type, style in styles:
            if type == FormatTypes.Default:
                for i in range(3):
                    self.StyleSetSpec(i, style)
                
                break

#             if type == wx.stc.STC_STYLE_CALLTIP:
#                 self.CallTipUseStyle(10)

        # Then overwrite with special changes

        # Delete style
        self.IndicatorSetStyle(0, wx.stc.STC_INDIC_STRIKE)
        self.IndicatorSetForeground(0, wx.Colour(200, 0, 0))
        self.StyleSetForeground(0, wx.Colour(200, 0, 0))

        # Insert style
        self.IndicatorSetStyle(1, wx.stc.STC_INDIC_PLAIN)
        self.IndicatorSetForeground(1, wx.Colour(0, 180, 0))
        self.StyleSetForeground(1, wx.Colour(0, 180, 0))

        self.SetReadOnly(True)



    def OnStyleNeeded(self, evt):
        if self.stylebytes is None:
            self.stopStcStyler()

        self.applyStyling(self.stylebytes)


    def stopStcStyler(self):
        """
        Stops further styling requests from Scintilla until text is modified
        """
        self.StartStyling(self.GetLength(), 0xff)
        self.SetStyling(0, 0)


    def applyStyling(self, stylebytes, styleMask=0xff):
        if len(stylebytes) == self.GetLength():
            self.StartStyling(0, styleMask)
            self.SetStyleBytes(len(stylebytes), stylebytes)


    def setTextScrollProtected(self, text):
        with WindowUpdateLocker(self):
            lastPos = self.GetCurrentPos()
            scrollPosX = self.GetScrollPos(wx.HORIZONTAL)
            scrollPosY = self.GetScrollPos(wx.VERTICAL)
            
            self.SetText(text)

            self.GotoPos(lastPos)
            self.scrollXY(scrollPosX, scrollPosY)


    def Copy(self):
        text = self.GetSelectedText()
        if len(text) == 0:
            return

        cbIcept = self.mainControl.getClipboardInterceptor()  
        if cbIcept is not None:
            cbIcept.informCopyInWikidPadStart(text=text)
            try:
                copyTextToClipboard(text)
            finally:
                cbIcept.informCopyInWikidPadStop()
        else:
            copyTextToClipboard(text)



    # TODO Wrong reaction on press of context menu button on keyboard
    def OnContextMenu(self, evt):
        menu = wx.Menu()

        appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_BASE)
        
        self.PopupMenu(menu)
        menu.Destroy()





#         # create the styles
#         if styleFaces is None:
#             styleFaces = self.presenter.getDefaultFontFaces()
# 
#         config = self.presenter.getConfig()
#         styles = self.presenter.getMainControl().getPresentationExt()\
#                 .getStyles(styleFaces, config)
# 
#         for type, style in styles:
#             self.StyleSetSpec(type, style)
# 
#             if type == wx.stc.STC_STYLE_CALLTIP:
#                 self.CallTipUseStyle(10)
# 
#         self.IndicatorSetStyle(2, wx.stc.STC_INDIC_SQUIGGLE)
#         self.IndicatorSetForeground(2, wx.Colour(255, 0, 0))



_CONTEXT_MENU_INTEXT_BASE = \
"""
Copy;CMD_CLIPBOARD_COPY
Select All;CMD_SELECT_ALL
-
Close Tab;CMD_CLOSE_CURRENT_TAB
"""


# Entries to support i18n of context menus
if not True:
    N_("Copy")
    N_("Select All")

    N_("Close Tab")
