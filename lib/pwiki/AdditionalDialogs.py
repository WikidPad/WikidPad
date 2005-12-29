import sys, traceback
from time import strftime
import re

from os.path import exists

from wxPython.wx import *
from wxPython.html import *
import wxPython.xrc as xrc

from wxHelper import *

from StringOps import uniToGui, guiToUni, mbcsEnc, mbcsDec
import WikiFormatting
import Exporters


class OpenWikiWordDialog(wxDialog):
    def __init__(self, pWiki, ID, title="Open Wiki Word",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D):

        d = wxPreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki
        self.value = None     
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "OpenWikiWordDialog")
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        
        EVT_BUTTON(self, wxID_OK, self.OnOk)
        # EVT_TEXT(self, XRCID("text"), self.OnText) 

        EVT_TEXT(self, ID, self.OnText)
        EVT_CHAR(self.ctrls.text, self.OnCharText)
        EVT_CHAR(self.ctrls.lb, self.OnCharListBox)
        EVT_LISTBOX(self, ID, self.OnListBox)
        EVT_LISTBOX_DCLICK(self, XRCID("lb"), self.OnOk)
        EVT_BUTTON(self, wxID_OK, self.OnOk)
        EVT_BUTTON(self, XRCID("btnCreate"), self.OnCreate)
        
    def OnOk(self, evt):
        if not self.pWiki.wikiData.isDefinedWikiWord(self.value):
            words = self.pWiki.wikiData.getWikiWordsWith(self.value.lower())
            if len(words) > 0:
                self.value = words[0]
            else:
                wikiWord = self.value
                wikiWordN = self.pWiki.getFormatting().normalizeWikiWord(wikiWord)

                if wikiWordN is None:
                    # Entered text is not a valid wiki word
                    self.ctrls.text.SetFocus()
                    return
                    
                # wikiWord is valid but nonexisting, so maybe create it?
                # TODO Special case [WikiWord]
                result = wxMessageBox(
                        uniToGui(u"'%s' is not an existing wikiword. Create?" %
                        wikiWord), uniToGui(u"Create"),
                        wxYES_NO | wxYES_DEFAULT | wxICON_QUESTION, self)
                
                if result == wxNO:
                    self.ctrls.text.SetFocus()
                    return
                
                self.value = wikiWord
                                
        self.EndModal(wxID_OK)
        
                
    def GetValue(self):
        return self.value

    def OnText(self, evt):
        self.value = guiToUni(evt.GetString())
        self.ctrls.lb.Clear()
        if len(self.value) > 0:
            words = self.pWiki.wikiData.getWikiWordsWith(self.value.lower())
            for word in words:
                self.ctrls.lb.Append(word)

    def OnListBox(self, evt):
        self.value = guiToUni(evt.GetString())

    def OnCharText(self, evt):
        if (evt.GetKeyCode() == WXK_DOWN) and not self.ctrls.lb.IsEmpty():
            self.ctrls.lb.SetFocus()
            self.ctrls.lb.SetSelection(0)
        elif (evt.GetKeyCode() == WXK_UP):
            pass
        else:
            evt.Skip()
            

    def OnCharListBox(self, evt):
        if (evt.GetKeyCode() == WXK_UP) and (self.ctrls.lb.GetSelection() == 0):
            self.ctrls.text.SetFocus()
            self.ctrls.lb.Deselect(0)
        else:
            evt.Skip()
            
            
    def OnCreate(self, evt):
        """
        Create new WikiWord
        """
        wikiWord = self.pWiki.getFormatting().normalizeWikiWord(self.value)
        if wikiWord is None:
            self.pWiki.displayErrorMessage(u"'%s' is an invalid WikiWord" % self.value)
            self.ctrls.text.SetFocus()
            return
        
        if self.pWiki.wikiData.isDefinedWikiWord(wikiWord):
            self.pWiki.displayErrorMessage(u"'%s' exists already" % wikiWord)
            self.ctrls.text.SetFocus()
            return
            
        self.value = wikiWord
        self.EndModal(wxID_OK)
 
 

class IconSelectDialog(wxDialog):
    def __init__(self, pWiki, ID, title="Select Icon",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D|wxDEFAULT_DIALOG_STYLE|wxRESIZE_BORDER):
        wxDialog.__init__(self, pWiki, ID, title, pos, size, style)
        self.pWiki = pWiki
        self.iconImageList = self.pWiki.iconImageList
        self.lookupIconIndex = self.pWiki.lookupIconIndex
        
        self.iconNames = filter(lambda n: not n.startswith("tb_"),
                self.pWiki.iconLookupCache.keys())
        self.iconNames.sort()
        
        # Now continue with the normal construction of the dialog
        # contents
        sizer = wxBoxSizer(wxVERTICAL)

        label = wxStaticText(self, -1, "Select Icon")
        sizer.Add(label, 0, wxALIGN_CENTRE|wxALL, 5)

        box = wxBoxSizer(wxVERTICAL)

        self.lc = wxListCtrl(self, -1, wxDefaultPosition, wxSize(145, 200), 
                style = wxLC_REPORT | wxLC_NO_HEADER)    ## | wxBORDER_NONE
                
        self.lc.SetImageList(self.iconImageList, wxIMAGE_LIST_SMALL)
        self.lc.InsertColumn(0, "Icon")

        for icn in self.iconNames:
            self.lc.InsertImageStringItem(sys.maxint, icn,
                    self.lookupIconIndex(icn))
        self.lc.SetColumnWidth(0, wxLIST_AUTOSIZE)
        
        
        box.Add(self.lc, 1, wxALIGN_CENTRE|wxALL|wxEXPAND, 5)

        sizer.Add(box, 1, wxGROW|wxALIGN_CENTER_VERTICAL|wxALL, 5)

        line = wxStaticLine(self, -1, size=(20,-1), style=wxLI_HORIZONTAL)
        sizer.Add(line, 0, wxGROW|wxALIGN_CENTER_VERTICAL|wxRIGHT|wxTOP, 5)

        box = wxBoxSizer(wxHORIZONTAL)

        btn = wxButton(self, wxID_OK, " OK ")
        btn.SetDefault()
        box.Add(btn, 0, wxALIGN_CENTRE|wxALL, 5)

        btn = wxButton(self, wxID_CANCEL, " Cancel ")
        box.Add(btn, 0, wxALIGN_CENTRE|wxALL, 5)

        sizer.Add(box, 0, wxALIGN_CENTER_VERTICAL|wxALL, 5)

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        sizer.Fit(self)

        self.value = None

        EVT_BUTTON(self, wxID_OK, self.OnOkPressed)
        EVT_LIST_ITEM_ACTIVATED(self, self.lc.GetId(), self.OnOkPressed)

    def GetValue(self):
        """
        Return name of selected icon or None
        """
        return self.value    


    def OnOkPressed(self, evt):
        no = self.lc.GetNextItem(-1, state = wxLIST_STATE_SELECTED)
        if no > -1:
            self.value = self.iconNames[no]
        else:
            self.value = None
            
        self.EndModal(wxID_OK)



class SavedVersionsDialog(wxDialog):
    def __init__(self, pWiki, ID, title="Saved Versions",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D):
        wxDialog.__init__(self, pWiki, ID, title, pos, size, style)
        self.pWiki = pWiki
        self.value = None        
        
        # Now continue with the normal construction of the dialog
        # contents
        sizer = wxBoxSizer(wxVERTICAL)

        label = wxStaticText(self, -1, "Saved Versions")
        sizer.Add(label, 0, wxALIGN_CENTRE|wxALL, 5)

        box = wxBoxSizer(wxVERTICAL)

        self.lb = wxListBox(self, -1, wxDefaultPosition, wxSize(165, 200), [], wxLB_SINGLE)

        # fill in the listbox
        self.versions = self.pWiki.wikiData.getStoredVersions()
            
        for version in self.versions:
            self.lb.Append(version[1])

        box.Add(self.lb, 1, wxALIGN_CENTRE|wxALL, 5)

        sizer.AddSizer(box, 0, wxGROW|wxALIGN_CENTER_VERTICAL|wxALL, 5)

        line = wxStaticLine(self, -1, size=(20,-1), style=wxLI_HORIZONTAL)
        sizer.Add(line, 0, wxGROW|wxALIGN_CENTER_VERTICAL|wxRIGHT|wxTOP, 5)

        box = wxBoxSizer(wxHORIZONTAL)

        btn = wxButton(self, wxID_OK, " Retrieve ")
        btn.SetDefault()
        box.Add(btn, 0, wxALIGN_CENTRE|wxALL, 5)

        btn = wxButton(self, wxID_CANCEL, " Cancel ")
        box.Add(btn, 0, wxALIGN_CENTRE|wxALL, 5)

        sizer.AddSizer(box, 0, wxALIGN_CENTER_VERTICAL|wxALL, 5)

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        sizer.Fit(self)

        ## EVT_BUTTON(self, wxID_OK, self.OnRetrieve)
        EVT_LISTBOX(self, ID, self.OnListBox)
        EVT_LISTBOX_DCLICK(self, ID, lambda evt: self.EndModal(wxID_OK))
        
##    def OnRetrieve(self, evt):
##        if self.value:
##            self.pWiki.wikiData.deleteSavedSearch(self.value)
##            self.EndModal(wxID_CANCEL)
        
    def GetValue(self):
        """ Returns None or tuple (<id>, <description>, <creation date>)
        """
        return self.value

    def OnListBox(self, evt):
        self.value = self.versions[evt.GetSelection()]




class DateformatDialog(wxDialog):

    # HTML explanation for strftime:
    FORMATHELP = """<html>
<body bgcolor="#FFFFFF">

<table border="1" align="center" style="border-collapse: collapse">
    <tr><td align="center" valign="baseline"><b>Directive</b></td>
        <td align="left"><b>Meaning</b></td></tr>
    <tr><td align="center" valign="baseline"><code>%a</code></td>
        <td align="left">Locale's abbreviated weekday name.</td></tr>
    <tr><td align="center" valign="baseline"><code>%A</code></td>
        <td align="left">Locale's full weekday name.</td></tr>
    <tr><td align="center" valign="baseline"><code>%b</code></td>
        <td align="left">Locale's abbreviated month name.</td></tr>
    <tr><td align="center" valign="baseline"><code>%B</code></td>
        <td align="left">Locale's full month name.</td></tr>
    <tr><td align="center" valign="baseline"><code>%c</code></td>
        <td align="left">Locale's appropriate date and time representation.</td></tr>
    <tr><td align="center" valign="baseline"><code>%d</code></td>
        <td align="left">Day of the month as a decimal number [01,31].</td></tr>
    <tr><td align="center" valign="baseline"><code>%H</code></td>
        <td align="left">Hour (24-hour clock) as a decimal number [00,23].</td></tr>
    <tr><td align="center" valign="baseline"><code>%I</code></td>
        <td align="left">Hour (12-hour clock) as a decimal number [01,12].</td></tr>
    <tr><td align="center" valign="baseline"><code>%j</code></td>
        <td align="left">Day of the year as a decimal number [001,366].</td></tr>
    <tr><td align="center" valign="baseline"><code>%m</code></td>
        <td align="left">Month as a decimal number [01,12].</td></tr>
    <tr><td align="center" valign="baseline"><code>%M</code></td>
        <td align="left">Minute as a decimal number [00,59].</td></tr>
    <tr><td align="center" valign="baseline"><code>%p</code></td>
        <td align="left">Locale's equivalent of either AM or PM.</td></tr>
    <tr><td align="center" valign="baseline"><code>%S</code></td>
        <td align="left">Second as a decimal number [00,61].</td></tr>
    <tr><td align="center" valign="baseline"><code>%U</code></td>
        <td align="left">Week number of the year (Sunday as the first day of the
                week) as a decimal number [00,53].  All days in a new year
                preceding the first Sunday are considered to be in week 0.</td></tr>
    <tr><td align="center" valign="baseline"><code>%w</code></td>
        <td align="left">Weekday as a decimal number [0(Sunday),6].</td></tr>
    <tr><td align="center" valign="baseline"><code>%W</code></td>
        <td align="left">Week number of the year (Monday as the first day of the
                week) as a decimal number [00,53].  All days in a new year
                preceding the first Monday are considered to be in week 0.</td></tr>
    <tr><td align="center" valign="baseline"><code>%x</code></td>
        <td align="left">Locale's appropriate date representation.</td></tr>
    <tr><td align="center" valign="baseline"><code>%X</code></td>
        <td align="left">Locale's appropriate time representation.</td></tr>
    <tr><td align="center" valign="baseline"><code>%y</code></td>
        <td align="left">Year without century as a decimal number [00,99].</td></tr>
    <tr><td align="center" valign="baseline"><code>%Y</code></td>
        <td align="left">Year with century as a decimal number.</td></tr>
    <tr><td align="center" valign="baseline"><code>%Z</code></td>
        <td align="left">Time zone name (no characters if no time zone exists).</td></tr>
    <tr><td align="center" valign="baseline"><code>%%</code></td>
        <td align="left">A literal "<tt class="character">%</tt>" character.</td></tr>
    </tbody>
</table>
</body>
</html>
"""
    
    def __init__(self, pWiki, ID, title="Select Date Format",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D, deffmt=u""):
        """
        deffmt -- Initial value for format string
        """
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki
        self.value = None     
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "DateformatDialog")
        
        html = wxHtmlWindow(self, -1)
        html.SetPage(self.FORMATHELP)
        res.AttachUnknownControl("htmlExplain", html, self)
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        
        self.ctrls.fieldFormat.SetValue(deffmt)
        self.OnText(None)
        
        ## EVT_BUTTON(self, wxID_OK, self.OnOk)
        EVT_TEXT(self, XRCID("fieldFormat"), self.OnText) 

        
    def OnText(self, evt):
        preview = "<invalid>"
        text = guiToUni(self.ctrls.fieldFormat.GetValue())
        try:
            # strftime can't handle unicode correctly, so conversion is needed
            mstr = mbcsEnc(text, "replace")[0]
            preview = mbcsDec(strftime(mstr), "replace")[0]
            self.value = text
        except:
            pass

        self.ctrls.fieldPreview.SetLabel(preview)
        
        
    def GetValue(self):
        return self.value
        

class OptionsDialog(wxDialog):
    OPTION_TO_CONTROL = [
            ("auto_save", "cbAutoSave", "b"),
            ("showontray", "cbShowOnTray", "b"),
            ("hideundefined", "cbHideUndefinedWords", "b"),
            ("process_autogenerated_areas", "cbProcessAutoGenerated", "b"),
            
            ("tree_auto_follow", "cbTreeAutoFollow", "b"),
            ("tree_update_after_save", "cbTreeUpdateAfterSave", "b"),
            ("tree_no_cycles", "cbTreeNoCycles", "b"),
            
            ("start_browser_after_export", "cbStartBrowserAfterExport", "b"),
            ("facename_html_preview", "tfFacenameHtmlPreview", "t"),
            ("html_preview_proppattern_is_excluding",
                    "cbHtmlPreviewProppatternIsExcluding", "b"),
            ("html_preview_proppattern", "tfHtmlPreviewProppattern", "tre"),
            ("html_export_proppattern_is_excluding",
                    "cbHtmlExportProppatternIsExcluding", "b"),
            ("html_export_proppattern", "tfHtmlExportProppattern", "tre"),
            
            ("footnotes_as_wikiwords", "cbFootnotesAsWws", "b"),
            ("first_wiki_word", "tfFirstWikiWord", "t"),
            

    ]
    
    def __init__(self, pWiki, ID, title="Options",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "OptionsDialog")
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        
        # Transfer options to dialog
        for o, c, t in self.OPTION_TO_CONTROL:
            if t == "b":   # boolean field = checkbox
                self.ctrls[c].SetValue(
                        self.pWiki.configuration.getboolean("main", o))
            elif t == "t" or t == "tre":  # text field or regular expression field
                self.ctrls[c].SetValue(
                        uniToGui(self.pWiki.configuration.get("main", o)) )
            
                
            
        # Options with special treatment
        self.ctrls.cbLowResources.SetValue(
                self.pWiki.configuration.getint("main", "lowresources") != 0)

        self.ctrls.cbNewWindowWikiUrl.SetValue(
                self.pWiki.configuration.getint("main",
                "new_window_on_follow_wiki_url") != 0)

        EVT_BUTTON(self, wxID_OK, self.OnOk)
        EVT_BUTTON(self, GUI_ID.btnSelectFaceHtmlPrev, self.OnSelectFaceHtmlPrev)
        

    def OnOk(self, evt):
        fieldsValid = True
        # First check validity of field contents
        for o, c, t in self.OPTION_TO_CONTROL:
            if t == "tre":
                # Regular expression field, test if re is valid
                try:
                    rexp = guiToUni(self.ctrls[c].GetValue())
                    re.compile(rexp, re.DOTALL | re.UNICODE | re.MULTILINE)
                    self.ctrls[c].SetBackgroundColour(wxWHITE)
                except:   # TODO Specific exception
                    fieldsValid = False
                    self.ctrls[c].SetBackgroundColour(wxRED)

        if not fieldsValid:
            self.Refresh()
            return

        # Transfer options from dialog to config file
        for o, c, t in self.OPTION_TO_CONTROL:
            # TODO Handle unicode text controls
            if t == "b":
                self.pWiki.configuration.set("main", o, repr(self.ctrls[c].GetValue()))
            elif t == "t":
                self.pWiki.configuration.set(
                        "main", o, guiToUni(self.ctrls[c].GetValue()) )
            elif t == "tre":
                # Regular expression field
                rexp = guiToUni(self.ctrls[c].GetValue())
                self.pWiki.configuration.set("main", o, rexp)
                    
            
        # Options with special treatment
        if self.ctrls.cbLowResources.GetValue():
            self.pWiki.configuration.set("main", "lowresources", "1")
        else:
            self.pWiki.configuration.set("main", "lowresources", "0")

        if self.ctrls.cbNewWindowWikiUrl.GetValue():
            self.pWiki.configuration.set("main", "new_window_on_follow_wiki_url", "1")
        else:
            self.pWiki.configuration.set("main", "new_window_on_follow_wiki_url", "0")

        evt.Skip()


    def OnSelectFaceHtmlPrev(self, evt):
        dlg = FontFaceDialog(self, -1, self.ctrls.tfFacenameHtmlPreview.GetValue())
        if dlg.ShowModal() == wxID_OK:
            self.ctrls.tfFacenameHtmlPreview.SetValue(dlg.GetValue())
        dlg.Destroy()
        

class FontFaceDialog(wxDialog):
    """
    Presents a list of available fonts (its face names) and renders a sample
    string with currently selected face.
    """
    def __init__(self, parent, ID, value="",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D):
        """
        value -- Current value of a text field containing a face name (used to
                 choose default item in the shown list box)
        """
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.parent = parent
        self.value = value

        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.parent, "FontFaceDialog")
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        
        # Fill font listbox
        fenum = wxFontEnumerator()
        fenum.EnumerateFacenames()
        facelist = fenum.GetFacenames()
        facelist.sort()
        
        for f in facelist:
            self.ctrls.lbFacenames.Append(f)
            
        if len(facelist) > 0:
            try:
                # In wxPython, this can throw an exception if self.value
                # does not match an item
                if not self.ctrls.lbFacenames.SetStringSelection(self.value):
                    self.ctrls.lbFacenames.SetSelection(0)
            except:
                self.ctrls.lbFacenames.SetSelection(0)

            self.OnFaceSelected(None)
            
        EVT_BUTTON(self, wxID_OK, self.OnOk)
        EVT_LISTBOX(self, GUI_ID.lbFacenames, self.OnFaceSelected)
        EVT_LISTBOX_DCLICK(self, GUI_ID.lbFacenames, self.OnOk)


    def OnOk(self, evt):
        self.value = self.ctrls.lbFacenames.GetStringSelection()
        evt.Skip()

        
    def OnFaceSelected(self, evt):
        face = self.ctrls.lbFacenames.GetStringSelection()
        font = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.NORMAL, False, face)
        self.ctrls.stFacePreview.SetLabel(face)
        self.ctrls.stFacePreview.SetFont(font)

    def GetValue(self):
        return self.value



class ExportDialog(wxDialog):
    def __init__(self, pWiki, ID, title="Export",
                 pos=wxDefaultPosition, size=wxDefaultSize):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "ExportDialog")
        
        self.ctrls = XrcControls(self)
        
        # Necessary to avoid a crash        
        emptyPanel = wxPanel(self.ctrls.additOptions)
        emptyPanel.Fit()
        
        exporterList = [] # List of tuples (<exporter object>, <export tag>,
                          # <readable description>, <additional options panel>)
        
        for ob in Exporters.describeExporters():   # TODO search plugins
            for tp in ob.getExportTypes(self.ctrls.additOptions):
                panel = tp[2]
                if panel is None:
                    panel = emptyPanel
                else:
                    panel.Fit()

                exporterList.append((ob, tp[0], tp[1], panel))
        
        self.ctrls.additOptions.Fit()
        mins = self.ctrls.additOptions.GetMinSize()
        
        self.ctrls.additOptions.SetMinSize(wxSize(mins.width+10, mins.height+10))
        self.Fit()
        
        self.exporterList = exporterList

        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        
        self.ctrls.tfDirectory.SetValue(self.pWiki.getLastActiveDir())
        
        for e in self.exporterList:
            e[3].Show(False)
            e[3].Enable(False)
            self.ctrls.chExportTo.Append(e[2])
            
        # Enable first addit. options panel
        self.exporterList[0][3].Enable(True)
        self.exporterList[0][3].Show(True)
        self.ctrls.chExportTo.SetSelection(0)       
        
        EVT_CHOICE(self, XRCID("chExportTo"), self.OnExportTo)
        EVT_BUTTON(self, wxID_OK, self.OnOk)
        EVT_BUTTON(self, XRCID("btnSelectDirectory"), self.OnSelectDir)


    def OnExportTo(self, evt):
        for e in self.exporterList:
            e[3].Show(False)
            e[3].Enable(False)
            
        # Enable appropriate addit. options panel
        self.exporterList[evt.GetSelection()][3].Enable(True)
        self.exporterList[evt.GetSelection()][3].Show(True)

        evt.Skip()


    def OnOk(self, evt):
        if not exists(guiToUni(self.ctrls.tfDirectory.GetValue())):
            self.pWiki.displayErrorMessage(u"Destination directory does not exist")
            return
            
        # Create wordList (what to export)
        selset = self.ctrls.chSelectedSet.GetSelection()
        root = self.pWiki.currentWikiWord
                    
        if selset == 0:
            # single page
            wordList = [root]
        elif selset == 1:
            # subtree
            wordList = self.pWiki.wikiData.getAllSubWords(root, True)
        else:
            # whole wiki
            wordList = self.pWiki.wikiData.getAllDefinedPageNames()
            
        # Run exporter
        ob, t, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]

        ob.export(self.pWiki, self.pWiki.wikiData, wordList, t, 
                guiToUni(self.ctrls.tfDirectory.GetValue()), 
                self.ctrls.compatFilenames.GetValue(), ob.getAddOpt(panel))

        self.EndModal(wxID_OK)

        
    def OnSelectDir(self, evt):
        # Only transfer between GUI elements, so no unicode conversion
        seldir = wxDirSelector(u"Select Export Directory",
                self.ctrls.tfDirectory.GetValue(),
                style=wxDD_DEFAULT_STYLE|wxDD_NEW_DIR_BUTTON, parent=self)
                
        if seldir:
            self.ctrls.tfDirectory.SetValue(seldir)


class ChooseWikiWordDialog(wxDialog):
    def __init__(self, pWiki, ID, words, motionType, title="Choose Wiki Word",
                 pos=wxDefaultPosition, size=wxDefaultSize):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "ChooseWikiWordDialog")
        
        self.ctrls = XrcControls(self)
        
        self.SetTitle(title)
        self.ctrls.staTitle.SetLabel(title)
        
        self.motionType = motionType
        self.words = words
        wordsgui = map(uniToGui, words)
        
        self.ctrls.lb.Set(wordsgui)

        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)

        EVT_BUTTON(self, GUI_ID.btnDelete, self.OnDelete)
        EVT_BUTTON(self, wxID_OK, self.OnOk)
        EVT_LISTBOX_DCLICK(self, GUI_ID.lb, self.OnOk)


    def OnOk(self, evt):
        sels = self.ctrls.lb.GetSelections()
        if len(sels) != 1:
            return # We can only go to exactly one wiki word
            
        wikiWord = self.words[sels[0]]
        self.pWiki.openWikiPage(wikiWord, forceTreeSyncFromRoot=True,
                motionType=self.motionType)

        self.EndModal(GUI_ID.btnDelete)


    def OnDelete(self, evt):
        sellen = len(self.ctrls.lb.GetSelections())
        if sellen > 0:
            answer = wxMessageBox(u"Do you want to delete %i wiki page(s)?" % sellen,
                    u"Delete Wiki Page(s)",
                    wxYES_NO | wxNO_DEFAULT | wxICON_QUESTION, self)

            if answer != wxYES:
                return

            self.pWiki.saveCurrentWikiPage()
            for s in self.ctrls.lb.GetSelections():
                delword = self.words[s]
                # Un-alias word
                delword = self.pWiki.wikiData.getAliasesWikiWord(delword)
                
                if self.pWiki.wikiData.isDefinedWikiWord(delword):
                    self.pWiki.wikiData.deleteWord(delword)
        
                    # trigger hooks
                    self.pWiki.hooks.deletedWikiWord(self.pWiki, delword)
                    
                    p2 = {}
                    p2["deleted page"] = True
                    p2["wikiWord"] = delword
                    self.pWiki.fireMiscEventProps(p2)
            
            self.pWiki.pageHistory.goAfterDeletion()

            self.EndModal(wxID_OK)

