import os
import urllib
import string
import re

from time import time, strftime

from wxPython.wx import *
from wxPython.stc import *

import WikiFormatting
from WikiData import WikiWordNotFoundException, WikiFileNotFoundException
from TextWrapper import fill
from Config import faces

class WikiTxtCtrl(wxStyledTextCtrl):
    def __init__(self, pWiki, parent, ID):        
        wxStyledTextCtrl.__init__(self, parent, ID)
        self.pWiki = pWiki
        self.evalScope = None
        
        # editor settings
        self.SetIndent(4)
        self.SetTabIndents(1)
        self.SetBackSpaceUnIndents(1)
        self.SetTabWidth(4)
        self.SetUseTabs(0)
        self.SetEOLMode(wxSTC_EOL_LF)

        self.StyleSetSpec(wxSTC_STYLE_DEFAULT, "face:%(mono)s,size:%(size)d" % faces)

        # i plan on lexing myself
        self.SetLexer(wxSTC_LEX_CONTAINER)

        # make the text control a drop target for files
        self.SetDropTarget(WikiTxtCtrlDropTarget(self))

        # register some keyboard commands
        self.CmdKeyAssign(ord('+'), wxSTC_SCMOD_CTRL, wxSTC_CMD_ZOOMIN)
        self.CmdKeyAssign(ord('-'), wxSTC_SCMOD_CTRL, wxSTC_CMD_ZOOMOUT)

        self.CmdKeyAssign(wxSTC_KEY_INSERT, wxSTC_SCMOD_CTRL, wxSTC_CMD_COPY)
        self.CmdKeyAssign(wxSTC_KEY_INSERT, wxSTC_SCMOD_SHIFT, wxSTC_CMD_PASTE)
        self.CmdKeyAssign(wxSTC_KEY_DELETE, wxSTC_SCMOD_SHIFT, wxSTC_CMD_CUT)

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
        EVT_IDLE(self, self.OnIdle)

        # search related vars        
        self.inIncrementalSearch = False
        self.anchorPosition = -1
        self.searchStartPos = 0

        # are WikiWords enabled
        self.wikiWordsEnabled = True

        # when was a key pressed last. used to check idle time.
        self.lastKeyPressed = time()
        self.eolMode = self.GetEOLMode()

    def setWrap(self, onOrOff):
        if onOrOff:
            self.SetWrapMode(wxSTC_WRAP_WORD)
        else:
            self.SetWrapMode(wxSTC_WRAP_NONE)
        
    def SetStyles(self, styleFaces=faces):
        # create the styles
        for type, style in WikiFormatting.getStyles(styleFaces):
            self.StyleSetSpec(type, style)

    def SetText(self, text):
        self.inIncrementalSearch = False
        self.anchorPosition = -1
        self.searchStartPos = 0

        self.SetSelection(-1, -1)
        self.ignoreOnChange = True
        wxStyledTextCtrl.SetText(self, text)
        self.ignoreOnChange = False
        self.EmptyUndoBuffer()

    def OnStyleNeeded(self, evt):
        "Styles the text of the editor"

        wikiData = self.pWiki.wikiData
        
        # get the text to regex against        
        text = self.GetText()

        # keeps track of the positions that have been styled        
        styledPositions = []

        for re, style in WikiFormatting.FormatExpressions:
            styleToApply = style

            # if WikiWords are not enabled skip ahead
            if not self.wikiWordsEnabled and style == WikiFormatting.FormatTypes.WikiWord:
                continue
            
            match = re.search(text)
            while match:
                # make sure these positions don't intersect with positions that
                # have already been styled. this guarantees that URL's can have wiki words.
                if not self.checkForStyleIntersection(styledPositions, match.start(), match.end()):
                    if style == WikiFormatting.FormatTypes.WikiWord or style == WikiFormatting.FormatTypes.WikiWord2:
                        if wikiData.isWikiWord(match.group(0)):
                            styleToApply = WikiFormatting.FormatTypes.AvailWikiWord
                        else:
                            styleToApply = WikiFormatting.FormatTypes.WikiWord

                    self.StartStyling(match.start(), 0xff)
                    self.SetStyling(match.end() - match.start(), styleToApply)
                    styledPositions.append((match.start(), match.end()))

                match = re.search(text, match.end())

        # sort the styled positions by start pos
        styledPositions.sort(lambda (aStart, aEnd), (bStart, bEnd): cmp(aStart, bStart))

        # now restyle the sections not styled by the above code to
        # the default style
        start = 0
        styledEnd = 0
        for (styledStart, styledEnd) in styledPositions:
            if styledStart > start:
                self.StartStyling(start, 0xff)
                self.SetStyling(styledStart - start, WikiFormatting.FormatTypes.Default)
            start = styledEnd+1

        # style the rest of the doc
        if styledEnd <= self.GetLength():            
           self.StartStyling(styledEnd, 0xff)
           self.SetStyling(self.GetLength() - styledEnd, WikiFormatting.FormatTypes.Default)
    
    def checkForStyleIntersection(self, styleList, start, end):
        "true if start to end intersects with an existing applied style"
        for (styleStart, styleEnd) in styleList:
            if start >= styleStart and start <= styleEnd:
                return True
            if end <= styleEnd and end >= styleStart:
                return True
            if start < styleStart and end > styleEnd:
                return True
        return False

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
            content = "++ Scratch Pad\n"

        content = "%s\n%s\n---------------------------\n\n%s\n" % (content, strftime("%x %I:%M %p"), text)
        wikiPage.save(content, False)
        self.pWiki.statusBar.SetStatusText("Copied snippet to ScratchPad", 0)

    def styleSelection(self, styleChars):
        (startPos, endPos) = self.GetSelection()
        if startPos == endPos:
            (startPos, endPos) = self.getNearestWordPositions()

        pos = self.GetCurrentPos()
        self.GotoPos(startPos)
        self.AddText(styleChars)
        self.GotoPos(endPos+len(styleChars))
        self.AddText(styleChars)
        self.GotoPos(pos)        

    def wikiStyleSelection(self, styleChars, startPos=0, endPos=0):
        if startPos == endPos:
            (startPos, endPos) = self.getNearestWordPositions()

        pos = self.GetCurrentPos()
        self.GotoPos(startPos)
        self.AddText(styleChars)
        self.GotoPos(endPos+1)
        self.AddText(styleChars)
        self.GotoPos(pos)        

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
                if chr(self.GetCharAt(end+1)) == "#":
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
                script = re.sub("^[\r\n\s]+", "", match.group(1))
                script = re.sub("[\r\n\s]+$", "", script)
                try:                    
                    if index == -1:
                        script = re.sub("^\d:?\s?", "", script)
                        exec(script) in self.evalScope
                    elif index > 0 and script.startswith(str(index)):
                        script = re.sub("^\d:?\s?", "", script)
                        exec(script) in self.evalScope
                        
                except Exception, e:
                    self.AddText("\nException: %s" % str(e))                
                    
                match = WikiFormatting.ScriptRE.search(text, match.end())
        else:
            text = self.GetSelectedText()
            try:
                result = eval(re.sub("[\n\r]", "", text))
            except Exception, e:
                result = e
                
            pos = self.GetCurrentPos()
            self.GotoPos(endPos)
            self.AddText(" = %s" % str(result))
            self.GotoPos(pos)

    def startIncrementalSearch(self, searchStr=''):
        self.SetFocus()
        self.searchStr = searchStr
        self.pWiki.statusBar.SetStatusText("Search (ESC to stop): ", 0)    
        self.searchStartPos = self.GetCurrentPos()
        self.inIncrementalSearch = True
        self.anchorPosition = -1

    def executeSearch(self, searchStr=None, searchStartPos=-1, next=False, replacement=None, caseSensitive=False, cycleToStart=True):
        if not searchStr:
            searchStr = self.searchStr
        if searchStartPos < 0:
            searchStartPos = self.searchStartPos
            
        self.pWiki.statusBar.SetStatusText("Search (ESC to stop): %s" % searchStr, 0)
        if len(searchStr) > 0 and not searchStr.endswith("\\"):
            text = self.GetText()
            startPos = searchStartPos
            if next and (self.anchorPosition != -1):
                startPos = self.anchorPosition

            regex = None
            if caseSensitive:
                regex = re.compile(searchStr)
            else:
                regex = re.compile(searchStr, re.IGNORECASE)
                
            match = regex.search(text, startPos, self.GetLength())
            if match:
                self.anchorPosition = match.end()
                self.SetSelection(match.start(), self.anchorPosition)
                if replacement != None:
                    self.ReplaceSelection(replacement)
                    selEnd = match.start() + len(replacement)
                    self.SetSelection(match.start(), selEnd)
                    self.anchorPosition = selEnd
                    return selEnd
                else:
                    return self.anchorPosition
                    
            elif startPos > 0 and cycleToStart:
                match = regex.search(text, 0, startPos)
                if match:
                    self.anchorPosition = match.end()
                    self.SetSelection(match.start(), self.anchorPosition)
                    if replacement:
                        self.ReplaceSelection(replacement)
                        selEnd = match.start() + len(replacement)
                        self.SetSelection(match.start(), selEnd)
                        self.anchorPosition = selEnd
                        return selEnd
                    else:
                        return self.anchorPosition
        else:
            self.SetSelection(-1, -1)
            self.anchorPosition = -1
            self.GotoPos(searchStartPos)

        return -1            

    def endIncrementalSearch(self):
        self.pWiki.statusBar.SetStatusText("", 0)    
        self.inIncrementalSearch = False
        self.anchorPosition = -1

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
                
            filledText = fill(text, wrapPosition, " " * indent, " " * subIndent)
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
            
    def getNearestWordPositions(self, pos=None):
        if not pos:
            pos = self.GetCurrentPos()
        return (self.WordStartPosition(pos, 1), self.WordEndPosition(pos, 1))

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
                        prevNumStr = match.group(2)
                        prevNum = int(prevNumStr)
                        nextNum = prevNum+1
                        adjustment = len(str(nextNum)) - len(prevNumStr)
                        
                        self.AddText("%s%d. " % (" " * (self.GetLineIndentation(currentLine-1) - adjustment), int(prevNum)+1))
                    else:
                        self.AddText(" " * self.GetLineIndentation(currentLine-1))

    def OnKeyDown(self, evt):
        key = evt.GetKeyCode()
        self.lastKeyPressed = time()

        if key == WXK_F3 and not self.inIncrementalSearch:
            self.startIncrementalSearch()
            evt.Skip()
        else:

            # handle key presses while in incremental search here
            if self.inIncrementalSearch:            
                # support some shift chars for regex search
                if evt.ShiftDown():
                    if key == ord('/'):
                        key = ord('?')
                    elif key == ord('8'):
                        key = ord('*')
                    elif key == ord('\\'):
                        key = ord('|')                            
                    elif key == ord('9'):
                        key = ord('(')                            
                    elif key == ord('0'):
                        key = ord(')')                            
                    elif key == ord('='):
                        key = ord('+')                            
                    elif key == ord('-'):
                        key = ord('_')                            
                    elif key == ord('6'):
                        key = ord('^')                            
                    elif key == ord('\''):
                        key = ord('"')                            
                
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
                        self.searchStr = self.searchStr + chr(key).lower()
                        self.executeSearch();
                elif key == WXK_F3:
                    self.executeSearch(next=True)                
                else:
                    self.anchorPosition = self.GetCurrentPos()
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
                        nearestWord = "[" + nearestWord
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
        linkPos = self.PositionFromPoint(wxPoint(evt.GetX(), evt.GetY()))
        if evt.ControlDown() and (self.isPositionInWikiWord(linkPos) or self.isPositionInLink(linkPos)):
            self.pWiki.SetCursor(wxStockCursor(wxCURSOR_HAND))
        else:
            evt.Skip()

    def OnIdle(self, evt):
        if (self.IsEnabled):
            # fix the line, pos and col numbers
            currentLine = self.GetCurrentLine()+1
            currentPos = self.GetCurrentPos()
            currentCol = self.GetColumn(currentPos)
            self.pWiki.statusBar.SetStatusText("Line: %d Col: %d Pos: %d" %
                                            (currentLine, currentCol, currentPos), 1)        
        
    def OnDestroy(self, evt):
        # This is how the clipboard contents can be preserved after
        # the app has exited.
        wxTheClipboard.Flush()
        evt.Skip()


class WikiTxtCtrlDropTarget(wxFileDropTarget):
    def __init__(self, editor):
        wxFileDropTarget.__init__(self)
        self.editor = editor

    def OnDropFiles(self, x, y, filenames):
        for file in filenames:
            url = urllib.pathname2url(file)
            if file.endswith(".wiki"):
                self.editor.AddText("wiki:%s" % url)
            else:
                self.editor.AddText("file:%s" % url)
