import os, traceback, codecs, array
from cStringIO import StringIO
import urllib_red as urllib
import string
import re
import threading

from time import time, strftime

from wxPython.wx import *
from wxPython.stc import *
import wxPython.xrc as xrc

from wxHelper import GUI_ID, XrcControls, XRCID

import WikiFormatting
from WikiData import WikiWordNotFoundException, WikiFileNotFoundException
# from TextWrapper import fill
from textwrap import fill

from StringOps import utf8Enc, utf8Dec, mbcsEnc, mbcsDec, uniToGui, guiToUni
from Configuration import isUnicode


def bytelenSct_utf8(us):
    """
    us -- unicode string
    returns: Number of bytes us requires in Scintilla (with UTF-8 encoding=Unicode)
    """
    return len(utf8Enc(us)[0])


def bytelenSct_mbcs(us):
    """
    us -- unicode string
    returns: Number of bytes us requires in Scintilla (with mbcs encoding=Ansi)
    """
    return len(mbcsEnc(us)[0])



class WikiTxtCtrl(wxStyledTextCtrl):
    def __init__(self, pWiki, parent, ID):
        wxStyledTextCtrl.__init__(self, parent, ID)
        self.pWiki = pWiki
        self.evalScope = None
        self.stylebytes = None
        self.stylethread = None

        # editor settings
        self.SetIndent(4)
        self.SetTabIndents(1)
        self.SetBackSpaceUnIndents(1)
        self.SetTabWidth(4)
        self.SetUseTabs(0)  # TODO Configurable
        self.SetEOLMode(wxSTC_EOL_LF)
        
        # Self-modify to ansi/unicode version
        if isUnicode():
            self.bytelenSct = bytelenSct_utf8
        else:
            self.bytelenSct = bytelenSct_mbcs
            
            self.GetText = self.GetText_unicode
            self.GetTextRange = self.GetTextRange_unicode
            self.GetSelectedText = self.GetSelectedText_unicode
            self.GetLine = self.GetLine_unicode
            self.ReplaceSelection = self.ReplaceSelection_unicode
            self.AddText = self.AddText_unicode


        # Popup menu must be created by Python code to replace clipboard functions
        # for unicode built
        self.UsePopUp(0)

        self.StyleSetSpec(wxSTC_STYLE_DEFAULT, "face:%(mono)s,size:%(size)d" % self.pWiki.presentationExt.faces)

        # i plan on lexing myself
        self.SetLexer(wxSTC_LEX_CONTAINER)

        # make the text control a drop target for files and text
        self.SetDropTarget(WikiTxtCtrlDropTarget(self))

        # register some keyboard commands
        self.CmdKeyAssign(ord('+'), wxSTC_SCMOD_CTRL, wxSTC_CMD_ZOOMIN)
        self.CmdKeyAssign(ord('-'), wxSTC_SCMOD_CTRL, wxSTC_CMD_ZOOMOUT)

        # Clear all key mappings for clipboard operations
        # PersonalWikiFrame handles them and calls the special clipboard functions
        # instead of the normal ones
        self.CmdKeyClear(wxSTC_KEY_INSERT, wxSTC_SCMOD_CTRL)
        self.CmdKeyClear(wxSTC_KEY_INSERT, wxSTC_SCMOD_SHIFT)
        self.CmdKeyClear(wxSTC_KEY_DELETE, wxSTC_SCMOD_SHIFT)

        self.CmdKeyClear(ord('X'), wxSTC_SCMOD_CTRL)
        self.CmdKeyClear(ord('C'), wxSTC_SCMOD_CTRL)
        self.CmdKeyClear(ord('V'), wxSTC_SCMOD_CTRL)

        # set the autocomplete separator
        self.AutoCompSetSeparator(ord('~'))

        # register some event handlers
        EVT_STC_STYLENEEDED(self, ID, self.OnStyleNeeded)
        EVT_STC_CHARADDED(self, ID, self.OnCharAdded)
        EVT_STC_CHANGE(self, ID, self.OnChange)
        EVT_LEFT_DOWN(self, self.OnClick)
        EVT_LEFT_DCLICK(self, self.OnDoubleClick)
        EVT_MOTION(self, self.OnMouseMove)
        #EVT_STC_DOUBLECLICK(self, ID, self.OnDoubleClick)
        EVT_KEY_DOWN(self, self.OnKeyDown)
        EVT_CHAR(self, self.OnChar)
        EVT_IDLE(self, self.OnIdle)
        EVT_CONTEXT_MENU(self, self.OnContextMenu)

        # search related vars
        self.inIncrementalSearch = False
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1
        self.searchCharStartPos = 0

        # are WikiWords enabled
        self.wikiWordsEnabled = True

        # when was a key pressed last. used to check idle time.
        self.lastKeyPressed = time()
        self.eolMode = self.GetEOLMode()

        # Stock cursors. Created here because the App object must be created first
        WikiTxtCtrl.CURSOR_IBEAM = wxStockCursor(wxCURSOR_IBEAM)
        WikiTxtCtrl.CURSOR_HAND = wxStockCursor(wxCURSOR_HAND)

        res = xrc.wxXmlResource.Get()
        self.contextMenu = res.LoadMenu("MenuTextctrlPopup")

        # Connect context menu events to functions
        EVT_MENU(self, XRCID("txtUndo"), lambda evt: self.Undo())
        EVT_MENU(self, XRCID("txtRedo"), lambda evt: self.Redo())

        EVT_MENU(self, XRCID("txtCut"), lambda evt: self.Cut())
        EVT_MENU(self, XRCID("txtCopy"), lambda evt: self.Copy())
        EVT_MENU(self, XRCID("txtPaste"), lambda evt: self.Paste())
        EVT_MENU(self, XRCID("txtDelete"), lambda evt: self.ReplaceSelection(""))

        EVT_MENU(self, XRCID("txtSelectAll"), lambda evt: self.SelectAll())


    def Cut(self):
        self.Copy()
        self.ReplaceSelection("")


    def Copy(self):
        cdataob = wxCustomDataObject(wxDataFormat(wxDF_TEXT))
        udataob = wxCustomDataObject(wxDataFormat(wxDF_UNICODETEXT))
        realuni = self.GetSelectedText()
        arruni = array.array("u")
        arruni.fromunicode(realuni+u"\x00")
        rawuni = arruni.tostring()
        # print "Copy", repr(realuni), repr(rawuni), repr(mbcsenc(realuni)[0])
        udataob.SetData(rawuni)
        cdataob.SetData(mbcsEnc(realuni)[0]+"\x00")

        dataob = wxDataObjectComposite()
        dataob.Add(udataob)
        dataob.Add(cdataob)

        cb = wxTheClipboard
        cb.Open()
        try:
            cb.SetData(dataob)
        finally:
            cb.Close()


    def Paste(self):
        cb = wxTheClipboard
        cb.Open()
        try:
            # datob = wxTextDataObject()
            # datob = wxCustomDataObject(wxDataFormat(wxDF_TEXT))
            dataob = wxDataObjectComposite()
            cdataob = wxCustomDataObject(wxDataFormat(wxDF_TEXT))
            udataob = wxCustomDataObject(wxDataFormat(wxDF_UNICODETEXT))
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
                    realuni = arruni.tounicode()
                    self.ReplaceSelection(realuni)
                elif cdataob.GetDataSize() > 0:
                    realuni = mbcsDec(cdataob.GetData(), "replace")[0]
                    self.ReplaceSelection(realuni)
                # print "Test getData", cdataob.GetDataSize(), udataob.GetDataSize()

            # print "Test text", repr(datob.GetData())       # GetDataHere())
        finally:
            cb.Close()


    def setWrap(self, onOrOff):
        if onOrOff:
            self.SetWrapMode(wxSTC_WRAP_WORD)
        else:
            self.SetWrapMode(wxSTC_WRAP_NONE)

    def SetStyles(self, styleFaces = None):
        # create the styles
        if styleFaces is None:
            styleFaces = self.pWiki.presentationExt.faces

        for type, style in WikiFormatting.getStyles(styleFaces):
            self.StyleSetSpec(type, style)

    def SetText(self, text):
        """
        Overrides the wxStyledTextCtrl method.
        text -- Unicode text content to set
        """
        self.inIncrementalSearch = False
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1
        self.searchCharStartPos = 0

        self.SetSelection(-1, -1)
        self.ignoreOnChange = True
        if isUnicode():
            wxStyledTextCtrl.SetText(self, text)
        else:
            # TODO Configure if "replace" or "strict"
            wxStyledTextCtrl.SetText(self, mbcsEnc(text, "replace")[0])
        self.ignoreOnChange = False
        self.EmptyUndoBuffer()

        
    def GetText_unicode(self):
        """
        Overrides the wxStyledTextCtrl.GetText method in ansi mode
        to return unicode.
        """
        return mbcsDec(wxStyledTextCtrl.GetText(self), "replace")[0]

    
    def GetTextRange_unicode(self, startPos, endPos):
        """
        Overrides the wxStyledTextCtrl.GetTextRange method in ansi mode
        to return unicode.
        startPos and endPos are byte(!) positions into the editor buffer
        """
        return mbcsDec(wxStyledTextCtrl.GetTextRange(self, startPos, endPos),
                "replace")[0]


    def GetSelectedText_unicode(self):
        """
        Overrides the wxStyledTextCtrl.GetSelectedText method in ansi mode
        to return unicode.
        """
        return mbcsDec(wxStyledTextCtrl.GetSelectedText(self), "replace")[0]


    def GetLine_unicode(self, line):
        return mbcsDec(wxStyledTextCtrl.GetLine(self, line), "replace")[0]


    def ReplaceSelection_unicode(self, txt):
        return wxStyledTextCtrl.ReplaceSelection(self, mbcsEnc(txt, "replace")[0])


    def AddText_unicode(self, txt):
        return wxStyledTextCtrl.AddText(self, mbcsEnc(txt, "replace")[0])


    def OnStyleNeeded(self, evt):
        "Styles the text of the editor"

        # get the text to regex against
        text = self.GetText()
        textlen = len(text)

        if textlen < 10240:    # Arbitrary value
            # Synchronous styling
            self.stylethread = None
            self.buildStyling(text, True, sync=True)
            self.applyStyling(self.stylebytes)
            self.stylebytes = None
        else:
            # Asynchronous styling
            # This avoids further request from STC:
            self.StartStyling(self.GetLength(), 0xff)  # len(text) may be != self.GetLength()
            self.SetStyling(0, 0)

            self.stylebytes = None

            t = threading.Thread(target = self.buildStyling, args = (text, True))
            self.stylethread = t
            t.start()

        # self.buildStyling(text, True)


    def OnContextMenu(self, evt):
        # Enable/Disable appropriate menu items
        self.contextMenu.FindItemById(XRCID("txtUndo")).Enable(self.CanUndo())
        self.contextMenu.FindItemById(XRCID("txtRedo")).Enable(self.CanRedo())

        cancopy = self.GetSelectionStart() != self.GetSelectionEnd()
        self.contextMenu.FindItemById(XRCID("txtDelete")).\
                Enable(cancopy and self.CanPaste())
        self.contextMenu.FindItemById(XRCID("txtCut")).\
                Enable(cancopy and self.CanPaste())
        self.contextMenu.FindItemById(XRCID("txtCopy")).Enable(cancopy)
        self.contextMenu.FindItemById(XRCID("txtPaste")).Enable(self.CanPaste())

        # Show menu
        self.PopupMenu(self.contextMenu)


    def buildStyling(self, text, withCamelCase, sync = False):
        """
        Unicode text
        """
        # print "buildStyling start", self.wikiWordsEnabled
        if self.wikiWordsEnabled:
            combre = WikiFormatting.CombinedSyntaxHighlightWithCamelCaseRE
        else:
            combre = WikiFormatting.CombinedSyntaxHighlightWithoutCamelCaseRE

        charstylepos = 0  # styling position in characters in text
        styleresult = []
        textlen = len(text) # Text length (in characters)
        wikiData = self.pWiki.wikiData

        while true:
            mat = combre.search(text, charstylepos)
            if mat is None:
                if charstylepos < textlen:
                    bytestylelen = self.bytelenSct(text[charstylepos:])
                    # print "styledefault1", charstylepos, bytestylelen
                    styleresult.append(chr(WikiFormatting.FormatTypes.Default) * bytestylelen)
                break

            groupdict = mat.groupdict()
            for m in groupdict.keys():
                if not groupdict[m] is None:
                    start, end = mat.span()
                    styleno = int(m[5:])  # m is of the form:   style<style number>
                    if charstylepos < start:
                        bytestylelen = self.bytelenSct(text[charstylepos:start])
                        # print "styledefault2", charstylepos, start, bytestylelen

                        styleresult.append(chr(WikiFormatting.FormatTypes.Default) * bytestylelen)
                        charstylepos = start

                    if styleno == WikiFormatting.FormatTypes.WikiWord or \
                            styleno == WikiFormatting.FormatTypes.WikiWord2:

                        if wikiData.isDefinedWikiWord(mat.group(0)):
                            styleno = WikiFormatting.FormatTypes.AvailWikiWord
                        else:
                            styleno = WikiFormatting.FormatTypes.WikiWord

                    bytestylelen = self.bytelenSct(text[charstylepos:end])
                    # print "style3", charstylepos, start, end, bytestylelen, styleno
                    styleresult.append(chr(styleno) * bytestylelen)
                    charstylepos = end
                    break

            if (not threading.currentThread() is self.stylethread) and not sync:
                break

        if (threading.currentThread() is self.stylethread) or sync:
            self.stylebytes = "".join(styleresult)

        # print "buildStyling end", type(self.stylebytes)


    def applyStyling(self, stylebytes):
        self.StartStyling(0, 0xff)
        self.SetStyleBytes(len(stylebytes), stylebytes)


    def snip(self):
        # get the selected text
        text = self.GetSelectedText()

        # copy it to the clipboard also
        self.Copy()

        # load the ScratchPad
        try:
            wikiPage = self.pWiki.wikiData.getPage("ScratchPad", ["info"])
        except WikiWordNotFoundException, e:
            wikiPage = self.pWiki.wikiData.createPage("ScratchPad")

        content = ""

        # get the text from the scratch pad
        try:
            content = wikiPage.getContent()
        except WikiFileNotFoundException, e:
            content = u"++ Scratch Pad\n"

        # TODO strftime
        content = u"%s\n%s\n---------------------------\n\n%s\n" % \
                (content, mbcsDec(strftime("%x %I:%M %p"))[0], text)
        wikiPage.save(content, False)
        self.pWiki.statusBar.SetStatusText(uniToGui("Copied snippet to ScratchPad"), 0)

    def styleSelection(self, styleChars):
        """
        Currently len(styleChars) must be 1.
        """
        (startBytePos, endBytePos) = self.GetSelection()
        if startBytePos == endBytePos:
            (startBytePos, endBytePos) = self.getNearestWordPositions()
            
        endBytePos = self.PositionAfter(endBytePos)

        bytePos = self.PositionAfter(self.GetCurrentPos())
        self.GotoPos(startBytePos)
        self.AddText(styleChars)
        self.GotoPos(endBytePos)   # +len(styleChars)
        self.AddText(styleChars)
        self.GotoPos(bytePos)        




    def activateLink(self, mousePosition=None):
        "returns true if the link was activated"
        linkPos = self.GetCurrentPos()
        # mouse position overrides current pos
        if mousePosition:
            linkPos = self.PositionFromPoint(mousePosition)

        inWikiWord = False
        if self.isPositionInWikiWord(linkPos):
            inWikiWord = True
        if not inWikiWord:
            # search back one char b/c the position could be "WikiWord|"
            if linkPos > 0 and self.isPositionInWikiWord(linkPos-1):
                linkPos = linkPos - 1
                inWikiWord = True

        if inWikiWord:
            searchStr = None
            (start, end) = self.getWikiWordBeginEnd(linkPos)
            if end+2 < self.GetLength():
                if chr(self.GetCharAt(end+1)) == "#":    # This may be a problem under rare circumstances
                    searchStr = self.GetTextRange(end+2, self.WordEndPosition(end+2, 1))

            # open the wiki page
            self.pWiki.openWikiPage(self.getWikiWordText(linkPos))

            # if a search str was found execute the search
            if searchStr:
                self.pWiki.editor.executeSearch(searchStr, 0)

            return True
        elif self.isPositionInLink(linkPos):
            self.launchUrl(self.getTextInStyle(linkPos, WikiFormatting.FormatTypes.Url))
            return True
        return False

    def launchUrl(self, link):
        match = WikiFormatting.UrlRE.match(link)
        try:
            os.startfile(match.group(1))
            return True
        except:
            pass
        return False

    def evalScriptBlocks(self, index=-1):
        # it is important to python to have consistent eol's
        self.ConvertEOLs(self.eolMode)
        (startPos, endPos) = self.GetSelection()

        # if no selection eval all scripts
        if startPos == endPos or index > 0:
            # get the text of the current page
            text = self.GetText()

            # process script imports
            if self.pWiki.currentWikiPage.props.has_key("import_scripts"):
                scripts = self.pWiki.currentWikiPage.props["import_scripts"]
                for script in scripts:
                    try:
                        importPage = self.pWiki.wikiData.getPage(script, [])
                        content = importPage.getContent()
                        text = text + "\n" + content
                    except:
                        pass

            match = WikiFormatting.ScriptRE.search(text)
            while(match):
                script = re.sub(u"^[\r\n\s]+", "", match.group(1))
                script = re.sub(u"[\r\n\s]+$", "", script)
                try:
                    if index == -1:
                        script = re.sub(u"^\d:?\s?", "", script)
                        exec(script) in self.evalScope
                    elif index > 0 and script.startswith(str(index)):
                        script = re.sub(u"^\d:?\s?", "", script)
                        exec(script) in self.evalScope

                except Exception, e:
                    self.AddText(u"\nException: %s" % unicode(e))

                match = WikiFormatting.ScriptRE.search(text, match.end())
        else:
            text = self.GetSelectedText()
            try:
                result = eval(re.sub(u"[\n\r]", u"", text), self.evalScope)
            except Exception, e:
                s = StringIO()
                traceback.print_exc(file=s)
                result = s.getvalue()

            pos = self.GetCurrentPos()
            self.GotoPos(endPos)
            self.AddText(u" = %s" % unicode(result))
            self.GotoPos(pos)

    def startIncrementalSearch(self, searchStr=u''):
        self.SetFocus()
        self.searchStr = searchStr
        self.pWiki.statusBar.SetStatusText(uniToGui(u"Search (ESC to stop): "), 0)
        self.searchCharStartPos = len(self.GetTextRange(0, self.GetCurrentPos()))

        self.inIncrementalSearch = True
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1


    # TODO char to byte mapping
    def executeSearch(self, searchStr=None, searchCharStartPos=-1, next=False, replacement=None, caseSensitive=False, cycleToStart=True):
        if not searchStr:
            searchStr = self.searchStr
        if searchCharStartPos < 0:
            searchCharStartPos = self.searchCharStartPos

        self.pWiki.statusBar.SetStatusText(uniToGui(u"Search (ESC to stop): %s" % searchStr), 0)
        text = self.GetText()
        if len(searchStr) > 0:   # and not searchStr.endswith("\\"):
            charStartPos = searchCharStartPos
            if next and (self.anchorCharPosition != -1):
                charStartPos = self.anchorCharPosition

            regex = None
            try:
                if caseSensitive:
                    regex = re.compile(searchStr, re.MULTILINE | re.LOCALE)
                else:
                    regex = re.compile(searchStr, re.IGNORECASE | \
                        re.MULTILINE | re.LOCALE)
            except:
                # Regex error
                return self.anchorCharPosition

            match = regex.search(text, charStartPos, len(text))
            if not match and charStartPos > 0 and cycleToStart:
                match = regex.search(text, 0, charStartPos)

            if match:
                matchbytestart = self.bytelenSct(text[:match.start()])
                self.anchorBytePosition = matchbytestart + \
                        self.bytelenSct(text[match.start():match.end()])
                self.anchorCharPosition = match.end()

                self.SetSelection(matchbytestart, self.anchorBytePosition)

                if replacement is not None:
                    self.ReplaceSelection(replacement)
                    selByteEnd = matchbytestart + self.bytelenSct(replacement)
                    selCharEnd = match.start() + len(replacement)
                    self.SetSelection(matchbytestart, selByteEnd)
                    self.anchorBytePosition = selByteEnd
                    self.anchorCharPosition = selCharEnd

                    return selCharEnd
                else:
                    return self.anchorCharPosition

        self.SetSelection(-1, -1)
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1
        self.GotoPos(self.bytelenSct(text[:searchCharStartPos]))

        return -1

    def endIncrementalSearch(self):
        self.pWiki.statusBar.SetStatusText("", 0)
        self.inIncrementalSearch = False
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1


    def rewrapText(self):
        curPos = self.GetCurrentPos()

        # search back for start of the para
        curLineNum = self.GetCurrentLine()
        curLine = self.GetLine(curLineNum)
        while curLineNum > 0:
            # don't wrap previous bullets with this bullet
            if (WikiFormatting.BulletRE.match(curLine) or WikiFormatting.NumericBulletRE.match(curLine)):
                break

            if WikiFormatting.EmptyLineRE.match(curLine):
                curLineNum = curLineNum + 1
                break

            curLineNum = curLineNum - 1
            curLine = self.GetLine(curLineNum)
        startLine = curLineNum

        # search forward for end of the para
        curLineNum = self.GetCurrentLine()
        curLine = self.GetLine(curLineNum)
        while curLineNum <= self.GetLineCount():
            # don't wrap the next bullet with this bullet
            if curLineNum > startLine:
                if (WikiFormatting.BulletRE.match(curLine) or WikiFormatting.NumericBulletRE.match(curLine)):
                    curLineNum = curLineNum - 1
                    break

            if WikiFormatting.EmptyLineRE.match(curLine):
                curLineNum = curLineNum - 1
                break

            curLineNum = curLineNum + 1
            curLine = self.GetLine(curLineNum)
        endLine = curLineNum

        if (startLine <= endLine):
            # get the start and end of the lines
            startPos = self.PositionFromLine(startLine)
            endPos = self.GetLineEndPosition(endLine)

            # get the indentation for rewrapping
            indent = self.GetLineIndentation(startLine)
            subIndent = indent

            # if the start of the para is a bullet the subIndent has to change
            if WikiFormatting.BulletRE.match(self.GetLine(startLine)):
                subIndent = indent + 2
            else:
                match = WikiFormatting.NumericBulletRE.match(self.GetLine(startLine))
                if match:
                    subIndent = indent + len(match.group(2)) + 2

            # get the text that will be wrapped
            text = self.GetTextRange(startPos, endPos)
            # remove spaces, newlines, etc
            text = re.sub("[\s\r\n]+", " ", text)

            # wrap the text
            wrapPosition = 70
            try:
                if self.pWiki.currentWikiPage.props.has_key("wrap"):
                    wrapPosition = int(self.pWiki.currentWikiPage.props["wrap"][0])
                else:
                    styleProps = self.pWiki.wikiData.getGlobalProperties()
                    if styleProps.has_key("global.wrap"):
                        wrapPosition = int(styleProps["global.wrap"])
            except:
                pass

            # make the min wrapPosition 5
            if wrapPosition < 5:
                wrapPosition = 5

            filledText = fill(text, width=wrapPosition,
                    initial_indent=u" " * indent, 
                    subsequent_indent=u" " * subIndent)
            # replace the text based on targetting
            self.SetTargetStart(startPos)
            self.SetTargetEnd(endPos)
            self.ReplaceTarget(filledText)
            self.GotoPos(curPos)

    def getWikiWordText(self, position):
        word = self.getTextInStyle(position, WikiFormatting.FormatTypes.WikiWord)
        if not word:
            word = self.getTextInStyle(position, WikiFormatting.FormatTypes.WikiWord2)
        if not word:
            word = self.getTextInStyle(position, WikiFormatting.FormatTypes.AvailWikiWord)
        return word

    def getWikiWordBeginEnd(self, position):
        (start, end) = self.getBeginEndOfStyle(position, WikiFormatting.FormatTypes.WikiWord)
        if start == -1 and end == -1:
            (start, end) = self.getBeginEndOfStyle(position, WikiFormatting.FormatTypes.WikiWord2)
        if start == -1 and end == -1:
            (start, end) = self.getBeginEndOfStyle(position, WikiFormatting.FormatTypes.AvailWikiWord)
        return (start, end)

    def isPositionInWikiWord(self, position):
        return self.isPositionInStyle(position, WikiFormatting.FormatTypes.WikiWord) \
               or self.isPositionInStyle(position, WikiFormatting.FormatTypes.WikiWord2) \
               or self.isPositionInStyle(position, WikiFormatting.FormatTypes.AvailWikiWord)

    def isPositionInLink(self, position):
        return self.isPositionInStyle(position, WikiFormatting.FormatTypes.Url)

    def isPositionInStyle(self, position, style):
        return self.GetStyleAt(position) == style

    def getTextInStyle(self, position, style):
        (start, end) = self.getBeginEndOfStyle(position, style)
        if start >= 0 and end >= 0:
            return self.GetTextRange(start, end+1)

    def getBeginEndOfStyle(self, position, style):
        currentStyle = self.GetStyleAt(position)
        if currentStyle != style:
            return (-1, -1)

        startPos = 0
        currentPos = position
        while currentPos >= 0:
            currentStyle = self.GetStyleAt(currentPos)
            if currentStyle == style:
                startPos = currentPos
                if currentPos > 0:
                    currentPos = currentPos - 1
                else:
                    break
            else:
                break

        endPos = 0
        currentPos = position
        while currentPos < self.GetLength():
            currentStyle = self.GetStyleAt(currentPos)
            if currentStyle == style:
                endPos = currentPos
                currentPos = currentPos + 1
            else:
                break

        if endPos > startPos:
            return (startPos, endPos)
        else:
            return (-1, -1)

    def getNearestWordPositions(self, bytepos=None):
        if not bytepos:
            bytepos = self.GetCurrentPos()
        return (self.WordStartPosition(bytepos, 1), self.WordEndPosition(bytepos, 1))

    def OnChange(self, evt):
        if not self.ignoreOnChange:
            self.pWiki.currentWikiPage.setDirty(True)

    def OnCharAdded(self, evt):
        "When the user presses enter reindent to the previous level"
        key = evt.GetKey()

        if key == 10:
            currentLine = self.GetCurrentLine()
            if currentLine > 0:
                previousLine = self.GetLine(currentLine-1)

                # check if the prev level was a bullet level
                if (WikiFormatting.BulletRE.search(previousLine)):
                    self.AddText("%s* " % (" " * self.GetLineIndentation(currentLine-1)))
                else:
                    match = WikiFormatting.NumericBulletRE.search(previousLine)
                    if match:
                        prevNumStr = match.group(3)
                        prevNum = int(prevNumStr)
                        nextNum = prevNum+1
                        adjustment = len(str(nextNum)) - len(prevNumStr)

                        self.AddText(u"%s%s%d. " % (u" " * (self.GetLineIndentation(currentLine-1) - adjustment), match.group(2), int(prevNum)+1))
                    else:
                        self.AddText(u" " * self.GetLineIndentation(currentLine-1))


    def OnKeyDown(self, evt):
        key = evt.GetKeyCode()
        self.lastKeyPressed = time()

        if key == WXK_F3 and not self.inIncrementalSearch:
            self.startIncrementalSearch()
            evt.Skip()
        else:

            # handle key presses while in incremental search here
            if self.inIncrementalSearch:
                if key < 256:
                    # escape ends the search
                    if key == WXK_ESCAPE:
                        self.endIncrementalSearch()
                    # do the next search on another ctrl-s, or f
                    elif evt.ControlDown() and (key == ord('S') or key == ord('F')):
                        self.executeSearch(next=True)
                    # handle the delete key
                    elif key == WXK_BACK or key == WXK_DELETE:
                        self.searchStr = self.searchStr[:len(self.searchStr)-1]
                        self.executeSearch();
                    # handle the other keys
                    else:
                        evt.Skip() # OnChar is responsible for that

                elif key == WXK_F3:
                    self.executeSearch(next=True)
                else:
                    # TODO Should also work for mouse!
                    self.anchorBytePosition = self.GetCurrentPos()
                    self.anchorCharPosition = \
                            len(self.GetTextRange(0, self.GetCurrentPos()))

                    evt.Skip()

            elif evt.ControlDown():
                (selectStart, selectEnd) = self.GetSelection()

                # activate link
                if key == ord('F'):
                    self.startIncrementalSearch()

                elif key == WXK_SPACE:
                    pos = self.GetCurrentPos()
                    (startPos, endPos) = self.getNearestWordPositions()
                    nearestWord = self.GetTextRange(startPos, endPos)

                    if (startPos-1) > 0 and self.GetCharAt(startPos-1) == ord('['):
                        nearestWord = u"[" + nearestWord
                        startPos = startPos-1

                    if len(nearestWord) > 0:
                        wikiWords = self.pWiki.wikiData.getWikiWordsStartingWith(nearestWord, True)

                        if len(wikiWords) > 0:
                            wordListAsStr = string.join(wikiWords, "~")
                            self.AutoCompShow(pos-startPos, wordListAsStr)
                        else:
                            # see if we should complete a property name
                            curLine = self.GetLine(self.GetCurrentLine())
                            if nearestWord.startswith("["):
                                props = self.pWiki.wikiData.getPropertyNamesStartingWith(nearestWord[1:])
                                self.AutoCompShow(pos-(startPos+1), string.join(props, "~"))
                    else:
                        # see if we should autocomplete the complete property name list
                        curLine = self.GetLine(self.GetCurrentLine())
                        if curLine.find("[") != -1:
                            props = self.pWiki.wikiData.getPropertyNames()
                            self.AutoCompShow(pos-startPos, string.join(props, "~"))

                elif key == WXK_RETURN:
                    self.activateLink()
                else:
                    evt.Skip()

            else:
                evt.Skip()


    def OnChar(self, evt):
        key = evt.GetKeyCode()
        # handle key presses while in incremental search here
        if self.inIncrementalSearch and key < WXK_START and key > 31 and \
                not evt.ControlDown():

            if isUnicode():
                self.searchStr += unichr(evt.GetUnicodeKey())
            else:
                self.searchStr += mbcsDec(chr(key))[0]

            self.executeSearch();
        else:
            evt.Skip()


    def OnClick(self, evt):
        if evt.ControlDown():
            x = evt.GetX()
            y = evt.GetY()
            if not self.activateLink(wxPoint(x, y)):
                evt.Skip()
        else:
            evt.Skip()

    def OnDoubleClick(self, evt):
        x = evt.GetX()
        y = evt.GetY()
        if not self.activateLink(wxPoint(x, y)):
            evt.Skip()

    def OnMouseMove(self, evt):
        if (not evt.ControlDown()) or evt.Dragging():
            # self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
            evt.Skip()
            return
        else:
            textPos = self.PositionFromPoint(evt.GetPosition())

            if (self.isPositionInWikiWord(textPos) or
                        self.isPositionInLink(textPos)):
                self.SetCursor(WikiTxtCtrl.CURSOR_HAND)
                return
            else:
                # self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
                evt.Skip()
                return


    def OnIdle(self, evt):
        if (self.IsEnabled):
            # fix the line, pos and col numbers
            currentLine = self.GetCurrentLine()+1
            currentPos = self.GetCurrentPos()
            currentCol = self.GetColumn(currentPos)
            self.pWiki.statusBar.SetStatusText(uniToGui(u"Line: %d Col: %d Pos: %d" %
                                            (currentLine, currentCol, currentPos)), 1)
            stylebytes = self.stylebytes
            self.stylebytes = None

            if stylebytes:
                self.applyStyling(stylebytes)


    def OnDestroy(self, evt):
        # This is how the clipboard contents can be preserved after
        # the app has exited.
        wxTheClipboard.Flush()
        evt.Skip()


    # TODO !!!!!!!!!!!!!
#     def setMouseCursor(self):
#         """
#         Set the right mouse cursor depending on some circumstances.
#         Returns True iff a special cursor was choosen.
#         """
#         mousePos = wxGetMousePosition()
#         mouseBtnPressed = wxGetKeyState(WXK_LBUTTON) or \
#                 wxGetKeyState(WXK_MBUTTON) or \
#                 wxGetKeyState(WXK_RBUTTON)
# 
#         ctrlPressed = wxGetKeyState(WXK_CONTROL)
# 
#         if (not ctrlPressed) or mouseBtnPressed:
#             self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
#             return False
#         else:
#             linkPos = self.PositionFromPoint(wxPoint(*self.ScreenToClientXY(*mousePos)))
# 
#             if (self.isPositionInWikiWord(linkPos) or
#                         self.isPositionInLink(linkPos)):
#                 self.SetCursor(WikiTxtCtrl.CURSOR_HAND)
#                 return True
#             else:
#                 self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
#                 return False



# Already defined in WikiTreeCtrl
def _getTextForNode(text):
    if text.startswith("["):
        return text[1:len(text)-1]
    return text


# sorter for relations, removes brackets and sorts lower case
# Already defined in WikiTreeCtrl
def _removeBracketsAndSort(a, b):
    a = _getTextForNode(a)
    b = _getTextForNode(b)
    return cmp(a.lower(), b.lower())


class WikiTxtCtrlDropTarget(wxPyDropTarget):
    def __init__(self, editor):
        wxPyDropTarget.__init__(self)

        self.editor = editor
        self.resetDObject()

    def resetDObject(self):
        """
        (Re)sets the dataobject at init and after each drop
        """
        dataob = wxDataObjectComposite()
        self.tobj = wxTextDataObject()  # Char. type depends on wxPython build
        dataob.Add(self.tobj)
        self.fobj = wxFileDataObject()
        dataob.Add(self.fobj)

        self.dataob = dataob
        self.SetDataObject(dataob)

##    def OnDrop(self, x, y):
##        return 1


    def OnDragOver(self, x, y, defresult):
        return self.editor.DoDragOver(x, y, defresult)


    def OnData(self, x, y, defresult):
        try:
            if self.GetData():
                data = self.dataob
                formats = data.GetAllFormats()

                fnames = self.fobj.GetFilenames()
                text = self.tobj.GetText()

                if fnames:
                    self.OnDropFiles(x, y, fnames)
                elif text:
                    self.OnDropText(x, y, text)

            return defresult

        finally:
            self.resetDObject()



    def OnDropText(self, x, y, text):
        self.editor.DoDropText(x, y, text)

    def OnDropFiles(self, x, y, filenames):
        urls = []
        for file in filenames:
            url = urllib.pathname2url(file)
            if file.endswith(".wiki"):
                urls.append("wiki:%s" % url)
            else:
                urls.append("file:%s" % url)

        self.editor.DoDropText(x, y, " ".join(urls))
