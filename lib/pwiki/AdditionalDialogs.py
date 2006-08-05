import sys, traceback
from time import strftime
import re

from os.path import exists, isdir, isfile

from wxPython.wx import *
from wxPython.html import *
import wxPython.xrc as xrc

from wxHelper import *

from StringOps import uniToGui, guiToUni, mbcsEnc, mbcsDec, htmlColorToRgbTuple,\
        rgbToHtmlColor, wikiWordToLabel, escapeForIni, unescapeForIni
import WikiFormatting
from WikiExceptions import *
import Exporters, Importers

from SearchAndReplaceDialogs import WikiPageListConstructionDialog
from SearchAndReplace import ListWikiPagesOperation


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

        self.SetTitle(title)

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
        if not self.pWiki.getWikiData().isDefinedWikiWord(self.value):
#             words = self.pWiki.getWikiData().getWikiWordsWith(self.value.lower(),
#                     True)
            words = self.pWiki.getWikiData().getWikiWordsWith(self.value,
                    True)
            if len(words) > 0:
                self.value = words[0]
            else:
                wikiWord = self.value
                nakedWord = wikiWordToLabel(wikiWord)

                if not self.pWiki.getFormatting().isNakedWikiWord(nakedWord):
                    # Entered text is not a valid wiki word
                    self.ctrls.text.SetFocus()
                    return

                # wikiWord is valid but nonexisting, so maybe create it?
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
#             words = self.pWiki.getWikiData().getWikiWordsWith(self.value.lower(),
#                     True)
            words = self.pWiki.getWikiData().getWikiWordsWith(self.value,
                    True)
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
        nakedWord = wikiWordToLabel(self.value)
        if not self.pWiki.getFormatting().isNakedWikiWord(nakedWord):
            self.pWiki.displayErrorMessage(u"'%s' is an invalid WikiWord" % nakedWord)
            self.ctrls.text.SetFocus()
            return
        
        if self.pWiki.getWikiData().isDefinedWikiWord(nakedWord):
            self.pWiki.displayErrorMessage(u"'%s' exists already" % nakedWord)
            self.ctrls.text.SetFocus()
            return
            
        self.value = nakedWord
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
        self.versions = self.pWiki.getWikiData().getStoredVersions()
            
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
##            self.pWiki.getWikiData().deleteSavedSearch(self.value)
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

    def __init__(self, parent, ID, mainControl, title="Choose Date Format",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D, deffmt=u""):
        """
        deffmt -- Initial value for format string
        """
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.mainControl = mainControl
        self.value = None     
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, parent, "DateformatDialog")
        self.SetTitle(title)
        
        # Create HTML explanation
        html = wxHtmlWindow(self, -1)
        html.SetPage(self.FORMATHELP)
        res.AttachUnknownControl("htmlExplain", html, self)
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        
        # Set dropdown list of recent time formats
        tfs = self.mainControl.getConfig().get("main", "recent_time_formats")
        self.recentFormats = [unescapeForIni(s) for s in tfs.split(u";")]
        for f in self.recentFormats:
            self.ctrls.fieldFormat.Append(f)

        self.ctrls.fieldFormat.SetValue(deffmt)
        self.OnText(None)
        
        EVT_BUTTON(self, wxID_OK, self.OnOk)
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
        
    
    def OnOk(self, evt):
        if self.value != u"":
            # Update recent time formats list
            
            try:
                self.recentFormats.remove(self.value)
            except ValueError:
                pass
                
            self.recentFormats.insert(0, self.value)
            if len(self.recentFormats) > 10:
                self.recentFormats = self.recentFormats[:10]

            # Escape to store it in configuration
            tfs = u";".join([escapeForIni(f, u";") for f in self.recentFormats])
            self.mainControl.getConfig().set("main", "recent_time_formats", tfs)

        self.EndModal(wxID_OK)


class OptionsDialog(wxDialog):
    # List of tuples (<configuration file entry>, <gui control name>, <type>
    # Supported types: b: boolean checkbox, i0+: nonnegative integer, t: text
    #    tre: regular expression,  f0+: nonegative float, seli: integer position
    #    of a selection in dropdown list,  color0: HTML color code

    OPTION_TO_CONTROL = (
            # application-wide options
            
            ("auto_save", "cbAutoSave", "b"),
            ("auto_save_delay_key_pressed", "tfAutoSaveDelayKeyPressed", "i0+"),
            ("auto_save_delay_dirty", "tfAutoSaveDelayDirty", "i0+"),

            ("showontray", "cbShowOnTray", "b"),
            ("minimize_on_closeButton", "cbMinimizeOnCloseButton", "b"),

            ("hideundefined", "cbHideUndefinedWords", "b"),
            ("process_autogenerated_areas", "cbProcessAutoGenerated", "b"),
            ("script_security_level", "chScriptSecurityLevel", "seli"),
            ("pagestatus_timeformat", "tfPageStatusTimeFormat", "t"),
            ("log_window_autoshow", "cbLogWindowAutoShow", "b"),
            ("log_window_autohide", "cbLogWindowAutoHide", "b"),
            ("clipboardCatcher_suffix", "tfClipboardCatcherSuffix", "t"),
            ("single_process", "cbSingleProcess", "b"),

            ("mainTree_position", "chMainTreePosition", "seli"),
            ("viewsTree_position", "chViewsTreePosition", "seli"),

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
            ("html_preview_pics_as_links", "cbHtmlPreviewPicsAsLinks", "b"),
            ("html_export_pics_as_links", "cbHtmlExportPicsAsLinks", "b"),
            
            ("html_body_link", "tfHtmlLinkColor", "color0"),
            ("html_body_alink", "tfHtmlALinkColor", "color0"),
            ("html_body_vlink", "tfHtmlVLinkColor", "color0"),
            ("html_body_text", "tfHtmlTextColor", "color0"),
            ("html_body_bgcolor", "tfHtmlBgColor", "color0"),
            ("html_body_background", "tfHtmlBgImage", "t"),

            ("sync_highlight_byte_limit", "tfSyncHighlightingByteLimit", "i0+"),
            ("async_highlight_delay", "tfAsyncHighlightingDelay", "f0+"),
            ("editor_plaintext_color", "tfEditorPlaintextColor", "color0"),
            ("editor_link_color", "tfEditorLinkColor", "color0"),
            ("editor_attribute_color", "tfEditorAttributeColor", "color0"),
            ("editor_bg_color", "tfEditorBgColor", "color0"),


            # wiki specific options
            
            ("footnotes_as_wikiwords", "cbFootnotesAsWws", "b"),
            ("first_wiki_word", "tfFirstWikiWord", "t"),

            ("wikiPageTitlePrefix", "tfWikiPageTitlePrefix", "t"),

            ("fileStorage_identity_modDateMustMatch", "cbFsModDateMustMatch", "b"),
            ("fileStorage_identity_filenameMustMatch", "cbFsFilenameMustMatch", "b"),
            ("fileStorage_identity_modDateIsEnough", "cbFsModDateIsEnough", "b")
    )

    _PANEL_LIST = (
            ("OptionsPageApplication", u"Application"),    
            ("OptionsPageTree", u"  Tree"),
            ("OptionsPageHtml", u"  HTML preview/export"),
            ("OptionsPageAutosave", u"  Autosave"),
            ("OptionsPageEditor", u"  Editor"),
            ("OptionsPageCurrentWiki", u"Current Wiki")
    )

    def __init__(self, pWiki, ID, title="Options",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "OptionsDialog")

        self.ctrls = XrcControls(self)
        
        self.emptyPanel = None

        self.panelList = []
        self.ctrls.lbPages.Clear()
        
        minw = 0
        minh = 0        
        for pn, pt in self._PANEL_LIST:
            if pn:
                panel = res.LoadPanel(self.ctrls.panelPages, pn)
            else:
                if self.emptyPanel is None:
                    # Necessary to avoid a crash        
                    self.emptyPanel = wxPanel(self.ctrls.panelPages)
                    self.emptyPanel.Fit()
                panel = self.emptyPanel
                
            self.panelList.append(panel)
            self.ctrls.lbPages.Append(pt)
            mins = panel.GetSize()
            minw = max(minw, mins.width)
            minh = max(minh, mins.height)

        self.ctrls.panelPages.SetMinSize(wxSize(minw + 10, minh + 10))
        self.Fit()

        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)

        # Transfer options to dialog
        for o, c, t in self.OPTION_TO_CONTROL:
            if t == "b":   # boolean field = checkbox
                self.ctrls[c].SetValue(
                        self.pWiki.getConfig().getboolean("main", o))
            elif t in ("t", "tre", "i0+", "f0+", "color0"):  # text field or regular expression field
                self.ctrls[c].SetValue(
                        uniToGui(self.pWiki.getConfig().get("main", o)) )
            elif t == "seli":   # Selection -> transfer index
                self.ctrls[c].SetSelection(
                        self.pWiki.getConfig().getint("main", o))

        # Options with special treatment
        self.ctrls.cbLowResources.SetValue(
                self.pWiki.getConfig().getint("main", "lowresources") != 0)

        self.ctrls.cbNewWindowWikiUrl.SetValue(
                self.pWiki.getConfig().getint("main",
                "new_window_on_follow_wiki_url") != 0)

        self.ctrls.lbPages.SetSelection(0)  
        self._refreshForPage()

        EVT_LISTBOX(self, GUI_ID.lbPages, self.OnLbPages)

        EVT_BUTTON(self, wxID_OK, self.OnOk)
        EVT_BUTTON(self, GUI_ID.btnSelectFaceHtmlPrev, self.OnSelectFaceHtmlPrev)

        EVT_BUTTON(self, GUI_ID.btnSelectHtmlLinkColor,
                lambda evt: self.selectColor(self.ctrls.tfHtmlLinkColor))
        EVT_BUTTON(self, GUI_ID.btnSelectHtmlALinkColor,
                lambda evt: self.selectColor(self.ctrls.tfHtmlALinkColor))
        EVT_BUTTON(self, GUI_ID.btnSelectHtmlVLinkColor,
                lambda evt: self.selectColor(self.ctrls.tfHtmlVLinkColor))
        EVT_BUTTON(self, GUI_ID.btnSelectHtmlTextColor,
                lambda evt: self.selectColor(self.ctrls.tfHtmlTextColor))
        EVT_BUTTON(self, GUI_ID.btnSelectHtmlBgColor,
                lambda evt: self.selectColor(self.ctrls.tfHtmlBgColor))

        EVT_BUTTON(self, GUI_ID.btnSelectEditorPlaintextColor,
                lambda evt: self.selectColor(self.ctrls.tfEditorPlaintextColor))
        EVT_BUTTON(self, GUI_ID.btnSelectEditorLinkColor,
                lambda evt: self.selectColor(self.ctrls.tfEditorLinkColor))
        EVT_BUTTON(self, GUI_ID.btnSelectEditorAttributeColor,
                lambda evt: self.selectColor(self.ctrls.tfEditorAttributeColor))
        EVT_BUTTON(self, GUI_ID.btnSelectEditorBgColor,
                lambda evt: self.selectColor(self.ctrls.tfEditorBgColor))

        EVT_BUTTON(self, GUI_ID.btnSelectPageStatusTimeFormat,
                self.OnSelectPageStatusTimeFormat)


    def _refreshForPage(self):
        for p in self.panelList:
            p.Show(False)
            p.Enable(False)
            
        panel = self.panelList[self.ctrls.lbPages.GetSelection()]

        # Enable appropriate addit. options panel
        panel.Enable(True)
        panel.Show(True)


    def OnLbPages(self, evt):
        self._refreshForPage()
        evt.Skip()


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
            elif t == "i0+":
                # Nonnegative integer field
                try:
                    val = int(guiToUni(self.ctrls[c].GetValue()))
                    if val < 0:
                        raise ValueError
                    self.ctrls[c].SetBackgroundColour(wxWHITE)
                except ValueError:
                    fieldsValid = False
                    self.ctrls[c].SetBackgroundColour(wxRED)
            elif t == "f0+":
                # Nonnegative float field
                try:
                    val = float(guiToUni(self.ctrls[c].GetValue()))
                    if val < 0:
                        raise ValueError
                    self.ctrls[c].SetBackgroundColour(wxWHITE)
                except ValueError:
                    fieldsValid = False
                    self.ctrls[c].SetBackgroundColour(wxRED)
            elif t == "color0":
                # HTML Color field or empty field
                val = guiToUni(self.ctrls[c].GetValue())
                rgb = htmlColorToRgbTuple(val)
                
                if val != "" and rgb is None:
                    self.ctrls[c].SetBackgroundColour(wxRED)
                    fieldsValid = False
                else:
                    self.ctrls[c].SetBackgroundColour(wxWHITE)

        if not fieldsValid:
            self.Refresh()
            return

        # Then transfer options from dialog to config file
        for o, c, t in self.OPTION_TO_CONTROL:
            # TODO Handle unicode text controls
            if t == "b":
                self.pWiki.getConfig().set("main", o, repr(self.ctrls[c].GetValue()))
            elif t in ("t", "tre", "i0+", "f0+", "color0"):
                self.pWiki.getConfig().set(
                        "main", o, guiToUni(self.ctrls[c].GetValue()) )
            elif t == "seli":   # Selection -> transfer index
                self.pWiki.getConfig().set(
                        "main", o, unicode(self.ctrls[c].GetSelection()) )

        # Options with special treatment
        if self.ctrls.cbLowResources.GetValue():
            self.pWiki.getConfig().set("main", "lowresources", "1")
        else:
            self.pWiki.getConfig().set("main", "lowresources", "0")

        if self.ctrls.cbNewWindowWikiUrl.GetValue():
            self.pWiki.getConfig().set("main", "new_window_on_follow_wiki_url", "1")
        else:
            self.pWiki.getConfig().set("main", "new_window_on_follow_wiki_url", "0")

        self.pWiki.getConfig().informChanged()

        evt.Skip()


    def OnSelectFaceHtmlPrev(self, evt):
        dlg = FontFaceDialog(self, -1, self.ctrls.tfFacenameHtmlPreview.GetValue())
        if dlg.ShowModal() == wxID_OK:
            self.ctrls.tfFacenameHtmlPreview.SetValue(dlg.GetValue())
        dlg.Destroy()
        
    def OnSelectPageStatusTimeFormat(self, evt):
        dlg = DateformatDialog(self, -1, self.pWiki, 
                deffmt=self.ctrls.tfPageStatusTimeFormat.GetValue())
        if dlg.ShowModal() == wxID_OK:
            self.ctrls.tfPageStatusTimeFormat.SetValue(dlg.GetValue())
        dlg.Destroy()

    def selectColor(self, tfield):
        rgb = htmlColorToRgbTuple(tfield.GetValue())
        if rgb is None:
            rgb = 0, 0, 0

        color = wxColour(*rgb)
        colordata = wxColourData()
        colordata.SetColour(color)

        dlg = wxColourDialog(self, colordata)
        if dlg.ShowModal() == wxID_OK:
            color = dlg.GetColourData().GetColour()
            if color.Ok():
                tfield.SetValue(
                        rgbToHtmlColor(color.Red(), color.Green(), color.Blue()))

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
        
        self.listPagesOperation = ListWikiPagesOperation()
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "ExportDialog")
        
        self.ctrls = XrcControls(self)
        
        self.emptyPanel = None
        
        exporterList = [] # List of tuples (<exporter object>, <export tag>,
                          # <readable description>, <additional options panel>)
        
        for ob in Exporters.describeExporters(self.pWiki):   # TODO search plugins
            for tp in ob.getExportTypes(self.ctrls.additOptions):
                panel = tp[2]
                if panel is None:
                    if self.emptyPanel is None:
                        # Necessary to avoid a crash        
                        self.emptyPanel = wxPanel(self.ctrls.additOptions)
                        self.emptyPanel.Fit()
                    panel = self.emptyPanel
                else:
                    panel.Fit()

                # Add Tuple (Exporter object, export type tag,
                #     export type description, additional options panel)
                exporterList.append((ob, tp[0], tp[1], panel)) 

        self.ctrls.additOptions.Fit()
        mins = self.ctrls.additOptions.GetMinSize()

        self.ctrls.additOptions.SetMinSize(wxSize(mins.width+10, mins.height+10))
        self.Fit()

        self.exporterList = exporterList

        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)

        self.ctrls.tfDestination.SetValue(self.pWiki.getLastActiveDir())

        for e in self.exporterList:
            e[3].Show(False)
            e[3].Enable(False)
            self.ctrls.chExportTo.Append(e[2])
            
#         # Enable first addit. options panel
#         self.exporterList[0][3].Enable(True)
#         self.exporterList[0][3].Show(True)

        self.ctrls.chExportTo.SetSelection(0)  
        self._refreshForEtype()
        
        EVT_CHOICE(self, GUI_ID.chExportTo, self.OnExportTo)
        EVT_CHOICE(self, GUI_ID.chSelectedSet, self.OnChSelectedSet)

        EVT_BUTTON(self, wxID_OK, self.OnOk)
        EVT_BUTTON(self, GUI_ID.btnSelectDestination, self.OnSelectDest)


    def _refreshForEtype(self):
        for e in self.exporterList:
            e[3].Show(False)
            e[3].Enable(False)
            
        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]

        # Enable appropriate addit. options panel
        panel.Enable(True)
        panel.Show(True)

        expDestWildcards = ob.getExportDestinationWildcards(etype)

        if expDestWildcards is None:
            # Directory destination
            self.ctrls.stDestination.SetLabel(u"Destination directory:")
        else:
            # File destination
            self.ctrls.stDestination.SetLabel(u"Destination file:")


    def OnExportTo(self, evt):
        self._refreshForEtype()
        evt.Skip()


    def OnChSelectedSet(self, evt):
        selset = self.ctrls.chSelectedSet.GetSelection()
        if selset == 3:  # Custom
            dlg = WikiPageListConstructionDialog(self, self.pWiki, -1, 
                    value=self.listPagesOperation)
            if dlg.ShowModal() == wxID_OK:
                self.listPagesOperation = dlg.getValue()
            dlg.Destroy()

    def OnOk(self, evt):
        # Run exporter
        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]
                
        # If this returns None, export goes to a directory
        expDestWildcards = ob.getExportDestinationWildcards(etype)
        if expDestWildcards is None:
            # Export to a directory
            if not exists(guiToUni(self.ctrls.tfDestination.GetValue())):
                self.pWiki.displayErrorMessage(
                        u"Destination directory does not exist")
                return
            
            if not isdir(guiToUni(self.ctrls.tfDestination.GetValue())):
                self.pWiki.displayErrorMessage(
                        u"Destination must be a directory")
                return
        else:
            if exists(guiToUni(self.ctrls.tfDestination.GetValue())) and \
                    not isfile(guiToUni(self.ctrls.tfDestination.GetValue())):
                self.pWiki.displayErrorMessage(
                        u"Destination must be a file")
                return


        # Create wordList (what to export)
        selset = self.ctrls.chSelectedSet.GetSelection()
        root = self.pWiki.getCurrentWikiWord()
        
        if root is None and selset in (0, 1):
            self.pWiki.displayErrorMessage(u"No real wiki word selected as root")
            return

        if selset == 0:
            # single page
            wordList = [root]
        elif selset == 1:
            # subtree
            wordList = self.pWiki.getWikiData().getAllSubWords([root])
        elif selset == 2:
            # whole wiki
            wordList = self.pWiki.getWikiData().getAllDefinedWikiPageNames()
        else:
            # custom list
            wordList = self.pWiki.getWikiDocument().searchWiki(self.listPagesOperation, True)

#         self.pWiki.getConfig().set("main", "html_export_pics_as_links",
#                 self.ctrls.cbHtmlExportPicsAsLinks.GetValue())


        if panel is self.emptyPanel:
            panel = None
            
        try:
            ob.export(self.pWiki.getWikiDataManager(), wordList, etype, 
                    guiToUni(self.ctrls.tfDestination.GetValue()), 
                    self.ctrls.compatFilenames.GetValue(), ob.getAddOpt(panel))
        except ExportException, e:
            self.pWiki.displayErrorMessage("Error while exporting", unicode(e))

        self.EndModal(wxID_OK)

        
    def OnSelectDest(self, evt):
        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]

        expDestWildcards = ob.getExportDestinationWildcards(etype)

        if expDestWildcards is None:
            # Only transfer between GUI elements, so no unicode conversion
            seldir = wxDirSelector(u"Select Export Directory",
                    self.ctrls.tfDestination.GetValue(),
                    style=wxDD_DEFAULT_STYLE|wxDD_NEW_DIR_BUTTON, parent=self)
                
            if seldir:
                self.ctrls.tfDestination.SetValue(seldir)

        else:
            # Build wildcard string
            wcs = []
            for wd, wp in expDestWildcards:
                wcs.append(wd)
                wcs.append(wp)
                
            wcs.append(u"All files (*.*)")
            wcs.append(u"*")
            
            wcs = u"|".join(wcs)
            
            selfile = wxFileSelector(u"Select Export File",
                    self.ctrls.tfDestination.GetValue(),
                    default_filename = "", default_extension = "",
                    wildcard = wcs, flags=wxSAVE | wxOVERWRITE_PROMPT,
                    parent=self)

            if selfile:
                self.ctrls.tfDestination.SetValue(selfile)


class ImportDialog(wxDialog):
    def __init__(self, parent, ID, mainControl, title="Import",
                 pos=wxDefaultPosition, size=wxDefaultSize):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.parent = parent
        self.mainControl = mainControl
        
        self.listPagesOperation = ListWikiPagesOperation()
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.parent, "ImportDialog")

        self.ctrls = XrcControls(self)

        self.emptyPanel = None
        
        importerList = [] # List of tuples (<importer object>, <import tag=type>,
                          # <readable description>, <additional options panel>)
        
        for ob in Importers.describeImporters(self.mainControl):   # TODO search plugins
            for tp in ob.getImportTypes(self.ctrls.additOptions):
                panel = tp[2]
                if panel is None:
                    if self.emptyPanel is None:
                        # Necessary to avoid a crash        
                        self.emptyPanel = wxPanel(self.ctrls.additOptions)
                        self.emptyPanel.Fit()
                    panel = self.emptyPanel
                else:
                    panel.Fit()

                # Add Tuple (Importer object, import type tag,
                #     import type description, additional options panel)
                importerList.append((ob, tp[0], tp[1], panel)) 

        self.ctrls.additOptions.Fit()
        mins = self.ctrls.additOptions.GetMinSize()
        
        self.ctrls.additOptions.SetMinSize(wxSize(mins.width+10, mins.height+10))
        self.Fit()
        
        self.importerList = importerList

        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        
        self.ctrls.tfSource.SetValue(self.mainControl.getLastActiveDir())
        
        for e in self.importerList:
            e[3].Show(False)
            e[3].Enable(False)
            self.ctrls.chImportFormat.Append(e[2])
            
#         # Enable first addit. options panel
#         self.importerList[0][3].Enable(True)
#         self.importerList[0][3].Show(True)
        self.ctrls.chImportFormat.SetSelection(0)
        self._refreshForItype()

        EVT_CHOICE(self, GUI_ID.chImportFormat, self.OnImportFormat)

        EVT_BUTTON(self, wxID_OK, self.OnOk)
        EVT_BUTTON(self, GUI_ID.btnSelectSource, self.OnSelectSrc)


    def _refreshForItype(self):
        """
        Refresh GUI depending on chosen import type
        """
        for e in self.importerList:
            e[3].Show(False)
            e[3].Enable(False)

        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]

        # Enable appropriate addit. options panel
        panel.Enable(True)
        panel.Show(True)

        impSrcWildcards = ob.getImportSourceWildcards(itype)

        if impSrcWildcards is None:
            # Directory source
            self.ctrls.stSource.SetLabel(u"Source directory:")
        else:
            # File source
            self.ctrls.stSource.SetLabel(u"Source file:")


    def OnImportFormat(self, evt):
        self._refreshForItype()
        evt.Skip()



    def OnOk(self, evt):
        # Run importer
        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]
                
        if not exists(guiToUni(self.ctrls.tfSource.GetValue())):
            self.mainControl.displayErrorMessage(
                    u"Source does not exist")
            return

        # If this returns None, import goes to a directory
        impSrcWildcards = ob.getImportSourceWildcards(itype)
        if impSrcWildcards is None:
            # Import from a directory
            
            if not isdir(guiToUni(self.ctrls.tfSource.GetValue())):
                self.mainControl.displayErrorMessage(
                        u"Source must be a directory")
                return
        else:
            if not isfile(guiToUni(self.ctrls.tfSource.GetValue())):
                self.mainControl.displayErrorMessage(
                        u"Source must be a file")
                return

        if panel is self.emptyPanel:
            panel = None

        try:
            ob.doImport(self.mainControl.getWikiDataManager(), itype, 
                    guiToUni(self.ctrls.tfSource.GetValue()), 
                    False, ob.getAddOpt(panel))
        except ImportException, e:
            self.mainControl.displayErrorMessage("Error while importing",
                    unicode(e))

        self.EndModal(wxID_OK)

        
    def OnSelectSrc(self, evt):
        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]

        impSrcWildcards = ob.getImportSourceWildcards(itype)

        if impSrcWildcards is None:
            # Only transfer between GUI elements, so no unicode conversion
            seldir = wxDirSelector(u"Select Import Directory",
                    self.ctrls.tfSource.GetValue(),
                    style=wxDD_DEFAULT_STYLE, parent=self)

            if seldir:
                self.ctrls.tfSource.SetValue(seldir)

        else:
            # Build wildcard string
            wcs = []
            for wd, wp in impSrcWildcards:
                wcs.append(wd)
                wcs.append(wp)
                
            wcs.append(u"All files (*.*)")
            wcs.append(u"*")
            
            wcs = u"|".join(wcs)
            
            selfile = wxFileSelector(u"Select Import File",
                    self.ctrls.tfSource.GetValue(),
                    default_filename = "", default_extension = "",
                    wildcard = wcs, flags=wxOPEN | wxFILE_MUST_EXIST,
                    parent=self)

            if selfile:
                self.ctrls.tfSource.SetValue(selfile)



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

            self.pWiki.saveCurrentDocPage()
            for s in self.ctrls.lb.GetSelections():
                delword = self.words[s]
                # Un-alias word
                delword = self.pWiki.getWikiData().getAliasesWikiWord(delword)
                
                if self.pWiki.getWikiData().isDefinedWikiWord(delword):
                    self.pWiki.getWikiData().deleteWord(delword)
        
                    # trigger hooks
                    self.pWiki.hooks.deletedWikiWord(self.pWiki, delword)
                    
                    p2 = {}
                    p2["deleted page"] = True
                    p2["deleted wiki page"] = True
                    p2["wikiWord"] = delword
                    self.pWiki.fireMiscEventProps(p2)
            
            self.pWiki.pageHistory.goAfterDeletion()

            self.EndModal(wxID_OK)


def _children(win, indent=0):
    print " " * indent + repr(win), win.GetId()
    for c in win.GetChildren():
        _children(c, indent=indent+2)
