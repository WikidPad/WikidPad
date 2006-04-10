import sets

from wxPython.wx import *
from wxPython.html import *

import wxPython.xrc as xrc

from wxHelper import *


try:
    from enchant import Dict
except ImportError:
    Dict = None


from StringOps import uniToGui, guiToUni

import WikiFormatting



class SpellCheckerDialog(wxDialog):
    def __init__(self, parent, ID, mainControl, title="Check spelling",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.mainControl = mainControl
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, parent, "SpellCheckDialog")
        self.SetTitle(title)
        
        # Create HTML explanation
        tfToCheck = wxTextCtrl(self, GUI_ID.tfToCheck, style=wxTE_MULTILINE|wxTE_RICH)
        res.AttachUnknownControl("tfToCheck", tfToCheck, self)

        self.ctrls = XrcControls(self)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        
        self.wordRe = self.mainControl.getFormatting().TextWordRE
        
        self.enchantDict = None
        
        self.currentCheckedWord = None
        self.currentStart = -1
        self.currentEnd = -1

        self.autoReplaceWords = {}
        
        self._createChecker()

        EVT_BUTTON(self, GUI_ID.btnIgnore, self.OnIgnore)
        EVT_BUTTON(self, GUI_ID.btnReplace, self.OnReplace)
        
        EVT_LISTBOX(self, GUI_ID.lbReplaceSuggestions,
                self.OnLbReplaceSuggestions)

        EVT_CHAR(self.ctrls.tfReplaceWith, self.OnCharReplaceWith)
        EVT_CHAR(self.ctrls.lbReplaceSuggestions, self.OnCharReplaceSuggestions)


    def _createChecker(self):
        """
        Creates the enchant spell checker object
        """
        self.enchantDict = Dict("en_US")


    def checkNext(self, startPos=0):
        self.ctrls.tfToCheck.SetValue("")

        text = self.mainControl.getActiveEditor().GetText()
        spellChkIgnore = self.mainControl.spellChkIgnore
        activeEditor = self.mainControl.getActiveEditor()

        while True:
            mat = self.wordRe.search(text, startPos)
            if mat is None:
                return False

            start, end = mat.span()
            word = mat.group()

            if mat.group("negative") is not None or \
                    word in spellChkIgnore or \
                    self.enchantDict.check(word):
                # Ignore if word is in the negative regex pattern (like numbers,
                # URLs, ...) or in the ignore list or is seen as correct
                # by the spell checker

                startPos = end
                continue

            if self.autoReplaceWords.has_key(word):
                activeEditor.SetSelectionByCharPos(start, end)
                activeEditor.ReplaceSelection(self.autoReplaceWords[word])
                continue  # ?

            break

        self.currentCheckedWord = word
        self.currentStart = start
        self.currentEnd = end

        activeEditor.SetSelectionByCharPos(start, end)

        conStart = max(0, start - 30)

        contextPre = text[conStart:start]
        contextPost = text[end:end+60]
        
        contextPre = contextPre.split(u"\n")[-1]
        contextPost = contextPost.split(u"\n", 1)[0]

        # Show misspelled word in context
        self.ctrls.tfToCheck.SetDefaultStyle(wxTextAttr(wxBLACK))
        self.ctrls.tfToCheck.AppendText(contextPre)
        self.ctrls.tfToCheck.SetDefaultStyle(wxTextAttr(wxRED))
        self.ctrls.tfToCheck.AppendText(mat.group(0))
        self.ctrls.tfToCheck.SetDefaultStyle(wxTextAttr(wxBLACK))
        self.ctrls.tfToCheck.AppendText(contextPost)
        
        self.ctrls.tfReplaceWith.SetValue(uniToGui(mat.group(0)))
        
        # List suggestions
        sugglist = self.enchantDict.suggest(mat.group(0))
        self.ctrls.lbReplaceSuggestions.Set(sugglist)
        
        self.ctrls.tfReplaceWith.SetFocus()

        return True


    def OnIgnore(self, evt):
        s, e = self.mainControl.getActiveEditor().GetSelectionCharPos()
        self.checkNext(e)


    def OnReplace(self, evt):
        activeEditor = self.mainControl.getActiveEditor()

        repl = guiToUni(self.ctrls.tfReplaceWith.GetValue())
        if repl != self.currentCheckedWord:
            activeEditor.ReplaceSelection(repl)

        s, e = self.mainControl.getActiveEditor().GetSelectionCharPos()
        self.checkNext(e)
        
        
    def OnLbReplaceSuggestions(self, evt):
        sel = guiToUni(self.ctrls.lbReplaceSuggestions.GetStringSelection())
        if sel != u"":
            self.ctrls.tfReplaceWith.SetValue(uniToGui(sel))


    def OnCharReplaceWith(self, evt):
        if (evt.GetKeyCode() == WXK_DOWN) and \
                not self.ctrls.lbReplaceSuggestions.IsEmpty():
            self.ctrls.lbReplaceSuggestions.SetFocus()
            self.ctrls.lbReplaceSuggestions.SetSelection(0)
            self.OnLbReplaceSuggestions(None)
        elif (evt.GetKeyCode() == WXK_UP):
            pass
        else:
            evt.Skip()

    def OnCharReplaceSuggestions(self, evt):
        if (evt.GetKeyCode() == WXK_UP) and \
                (self.ctrls.lbReplaceSuggestions.GetSelection() == 0):
            self.ctrls.tfReplaceWith.SetFocus()
            self.ctrls.lbReplaceSuggestions.Deselect(0)
        else:
            evt.Skip()





def isSpellCheckSupported():
    return Dict is not None
