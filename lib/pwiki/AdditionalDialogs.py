import sys, traceback
# from time import strftime
import re

from os.path import exists, isdir, isfile

import wx, wx.html, wx.xrc


from wxHelper import *

from StringOps import uniToGui, guiToUni, mbcsEnc, mbcsDec, \
        escapeForIni, unescapeForIni, escapeHtml, strftimeUB
import WikiFormatting
from WikiExceptions import *
import Exporters, Importers

from Consts import VERSION_STRING

from SearchAndReplaceDialogs import WikiPageListConstructionDialog
from SearchAndReplace import ListWikiPagesOperation


class SelectWikiWordDialog(wx.Dialog):
    def __init__(self, pWiki, ID, title="Select Wiki Word",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):

        d = wx.PreDialog()
        self.PostCreate(d)

        self.pWiki = pWiki
        self.wikiWord = None  
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "SelectWikiWordDialog")

        self.SetTitle(title)

        self.ctrls = XrcControls(self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)

        wx.EVT_TEXT(self, ID, self.OnText)
        wx.EVT_CHAR(self.ctrls.text, self.OnCharText)
        wx.EVT_CHAR(self.ctrls.lb, self.OnCharListBox)
        wx.EVT_LISTBOX(self, ID, self.OnListBox)
        wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lb, self.OnOk)

    def OnOk(self, evt):
        if not self.pWiki.getWikiData().isDefinedWikiWord(self.wikiWord):
            words = self.pWiki.getWikiData().getWikiWordsWith(self.wikiWord,
                    True)
            if len(words) > 0:
                self.wikiWord = words[0]
            else:
                formatting = self.pWiki.getFormatting()
                wikiWord = self.wikiWord
                nakedWord = formatting.wikiWordToLabel(wikiWord)

                if not formatting.isNakedWikiWord(nakedWord):
                    # Entered text is not a valid wiki word
                    self.ctrls.text.SetFocus()
                    return

#                 # wikiWord is valid but nonexisting, so maybe create it?
#                 result = wxMessageBox(
#                         uniToGui(u"'%s' is not an existing wikiword. Create?" %
#                         wikiWord), uniToGui(u"Create"),
#                         wxYES_NO | wxYES_DEFAULT | wxICON_QUESTION, self)
# 
#                 if result == wxNO:
#                     self.ctrls.text.SetFocus()
#                     return
#                 
                self.wikiWord = wikiWord

        self.EndModal(wx.ID_OK)
        
                
    def GetValue(self):
        return self.wikiWord

    def OnText(self, evt):
        self.wikiWord = guiToUni(evt.GetString())
        self.ctrls.lb.Clear()
        if len(self.wikiWord) > 0:
            words = self.pWiki.getWikiData().getWikiWordsWith(self.wikiWord,
                    True)
            for word in words:
                self.ctrls.lb.Append(word)

    def OnListBox(self, evt):
        self.wikiWord = guiToUni(evt.GetString())

    def OnCharText(self, evt):
        if (evt.GetKeyCode() == wx.WXK_DOWN) and not self.ctrls.lb.IsEmpty():
            self.ctrls.lb.SetFocus()
            self.ctrls.lb.SetSelection(0)
        elif (evt.GetKeyCode() == wx.WXK_UP):
            pass
        else:
            evt.Skip()
            

    def OnCharListBox(self, evt):
        if (evt.GetKeyCode() == wx.WXK_UP) and (self.ctrls.lb.GetSelection() == 0):
            self.ctrls.text.SetFocus()
            self.ctrls.lb.Deselect(0)
        else:
            evt.Skip()
     

class OpenWikiWordDialog(wx.Dialog):
    def __init__(self, pWiki, ID, title="Open Wiki Word",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):

        d = wx.PreDialog()
        self.PostCreate(d)

        self.pWiki = pWiki
        self.wikiWord = u""  
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "OpenWikiWordDialog")

        self.SetTitle(title)

        self.ctrls = XrcControls(self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)

        wx.EVT_TEXT(self, ID, self.OnText)
        wx.EVT_CHAR(self.ctrls.text, self.OnCharText)
        wx.EVT_CHAR(self.ctrls.lb, self.OnCharListBox)
        wx.EVT_LISTBOX(self, ID, self.OnListBox)
        wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lb, self.OnOk)
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_BUTTON(self, GUI_ID.btnCreate, self.OnCreate)
        wx.EVT_BUTTON(self, GUI_ID.btnNewTab, self.OnNewTab)
        wx.EVT_BUTTON(self, GUI_ID.btnNewTabBackground, self.OnNewTabBackground)

    def OnOk(self, evt):
        self.activateSelectedWikiWord(0)
        self.EndModal(wx.ID_OK)


    def activateSelectedWikiWord(self, tabMode):
        if len(self.wikiWord) == 0:
            return

        if not self.pWiki.getWikiData().isDefinedWikiWord(self.wikiWord):
            words = self.pWiki.getWikiData().getWikiWordsWith(self.wikiWord,
                    True)
            if len(words) > 0:
                self.wikiWord = words[0]
            else:
                formatting = self.pWiki.getFormatting()
                wikiWord = self.wikiWord
                nakedWord = formatting.wikiWordToLabel(wikiWord)

                if not formatting.isNakedWikiWord(nakedWord):
                    # Entered text is not a valid wiki word
                    self.ctrls.text.SetFocus()
                    return

                # wikiWord is valid but nonexisting, so maybe create it?
                result = wx.MessageBox(
                        uniToGui(_(u"'%s' is not an existing wikiword. Create?") %
                        wikiWord), uniToGui(_(u"Create")),
                        wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

                if result == wx.NO:
                    self.ctrls.text.SetFocus()
                    return
                
                self.wikiWord = nakedWord

        self.pWiki.activatePageByUnifiedName(u"wikipage/" + self.wikiWord,
                tabMode=tabMode)


    def GetValue(self):
        return self.wikiWord

    def OnText(self, evt):
        self.wikiWord = guiToUni(evt.GetString())
        self.ctrls.lb.Clear()
        if len(self.wikiWord) > 0:
            words = self.pWiki.getWikiData().getWikiWordsWith(self.wikiWord,
                    True)
            for word in words:
                self.ctrls.lb.Append(word)

    def OnListBox(self, evt):
        self.wikiWord = guiToUni(evt.GetString())

    def OnCharText(self, evt):
        if (evt.GetKeyCode() == wx.WXK_DOWN) and not self.ctrls.lb.IsEmpty():
            self.ctrls.lb.SetFocus()
            self.ctrls.lb.SetSelection(0)
        elif (evt.GetKeyCode() == wx.WXK_UP):
            pass
        else:
            evt.Skip()
            

    def OnCharListBox(self, evt):
        if (evt.GetKeyCode() == wx.WXK_UP) and (self.ctrls.lb.GetSelection() == 0):
            self.ctrls.text.SetFocus()
            self.ctrls.lb.Deselect(0)
        else:
            evt.Skip()
            
            
    def OnCreate(self, evt):
        """
        Create new WikiWord
        """
        formatting = self.pWiki.getFormatting()
        nakedWord = formatting.wikiWordToLabel(self.wikiWord)
        if not formatting.isNakedWikiWord(nakedWord):
            self.pWiki.displayErrorMessage(_(u"'%s' is an invalid WikiWord") % nakedWord)
            self.ctrls.text.SetFocus()
            return
        
        if self.pWiki.getWikiData().isDefinedWikiWord(nakedWord):
            self.pWiki.displayErrorMessage(_(u"'%s' exists already") % nakedWord)
            self.ctrls.text.SetFocus()
            return
            
        self.wikiWord = nakedWord
#         self.pWiki.activateWikiWord(self.wikiWord, tabMode=0)
        self.pWiki.activatePageByUnifiedName(u"wikipage/" + self.wikiWord,
                tabMode=0)
        self.EndModal(wx.ID_OK)
 
    def OnNewTab(self, evt):
        self.activateSelectedWikiWord(2)
        self.EndModal(wx.ID_OK)

    def OnNewTabBackground(self, evt):
        self.activateSelectedWikiWord(3)


 

class SelectIconDialog(wx.Dialog):
    def __init__(self, parent, ID, iconCache, title="Select Icon",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D|wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):
        wx.Dialog.__init__(self, parent, ID, title, pos, size, style)

        self.iconCache = iconCache
        self.iconImageList = self.iconCache.iconImageList
        
        self.iconNames = [n for n in self.iconCache.iconLookupCache.keys()
                if not n.startswith("tb_")]
#         filter(lambda n: not n.startswith("tb_"),
#                 self.iconCache.iconLookupCache.keys())
        self.iconNames.sort()
        
        # Now continue with the normal construction of the dialog
        # contents
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self, -1, _(u"Select Icon"))
        sizer.Add(label, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        box = wx.BoxSizer(wx.VERTICAL)

        self.lc = wx.ListCtrl(self, -1, wx.DefaultPosition, wx.Size(145, 200), 
                style = wx.LC_REPORT | wx.LC_NO_HEADER)    ## | wx.BORDER_NONE
                
        self.lc.SetImageList(self.iconImageList, wx.IMAGE_LIST_SMALL)
        self.lc.InsertColumn(0, _(u"Icon"))

        for icn in self.iconNames:
            self.lc.InsertImageStringItem(sys.maxint, icn,
                    self.iconCache.lookupIconIndex(icn))
        self.lc.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        
        
        box.Add(self.lc, 1, wx.ALIGN_CENTRE|wx.ALL|wx.EXPAND, 5)

        sizer.Add(box, 1, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        line = wx.StaticLine(self, -1, size=(20,-1), style=wx.LI_HORIZONTAL)
        sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP, 5)

        box = wx.BoxSizer(wx.HORIZONTAL)

        btn = wx.Button(self, wx.ID_OK, _(u" OK "))
        btn.SetDefault()
        box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        btn = wx.Button(self, wx.ID_CANCEL, _(u" Cancel "))
        box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        sizer.Add(box, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        sizer.Fit(self)

        self.value = None
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOkPressed)
        wx.EVT_LIST_ITEM_ACTIVATED(self, self.lc.GetId(), self.OnOkPressed)

    def GetValue(self):
        """
        Return name of selected icon or None
        """
        return self.value

    @staticmethod
    def runModal(parent, ID, iconCache, title="Select Icon",
            pos=wx.DefaultPosition, size=wx.DefaultSize,
            style=wx.NO_3D|wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):

        dlg = SelectIconDialog(parent, ID, iconCache, title, pos, size, style)
        try:
            dlg.CenterOnParent(wx.BOTH)
            if dlg.ShowModal() == wx.ID_OK:
                return dlg.GetValue()
            else:
                return None

        finally:
            dlg.Destroy()


    def OnOkPressed(self, evt):
        no = self.lc.GetNextItem(-1, state = wx.LIST_STATE_SELECTED)
        if no > -1:
            self.value = self.iconNames[no]
        else:
            self.value = None
            
        self.EndModal(wx.ID_OK)



class SavedVersionsDialog(wx.Dialog):
    def __init__(self, pWiki, ID, title="Saved Versions",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):
        wx.Dialog.__init__(self, pWiki, ID, title, pos, size, style)
        self.pWiki = pWiki
        self.value = None        
        
        # Now continue with the normal construction of the dialog
        # contents
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self, -1, _(u"Saved Versions"))
        sizer.Add(label, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        box = wx.BoxSizer(wx.VERTICAL)

        self.lb = wx.ListBox(self, -1, wx.DefaultPosition, wx.Size(165, 200),
                [], wx.LB_SINGLE)

        # fill in the listbox
        self.versions = self.pWiki.getWikiData().getStoredVersions()
            
        for version in self.versions:
            self.lb.Append(version[1])

        box.Add(self.lb, 1, wx.ALIGN_CENTRE|wx.ALL, 5)

        sizer.AddSizer(box, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        line = wx.StaticLine(self, -1, size=(20,-1), style=wx.LI_HORIZONTAL)
        sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP, 5)

        box = wx.BoxSizer(wx.HORIZONTAL)

        btn = wx.Button(self, wx.ID_OK, _(u" Retrieve "))
        btn.SetDefault()
        box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        btn = wx.Button(self, wx.ID_CANCEL, _(u" Cancel "))
        box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        sizer.AddSizer(box, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        sizer.Fit(self)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        ## wx.EVT_BUTTON(self, wxID_OK, self.OnRetrieve)
        wx.EVT_LISTBOX(self, ID, self.OnListBox)
        wx.EVT_LISTBOX_DCLICK(self, ID, lambda evt: self.EndModal(wx.ID_OK))
        
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



class DateformatDialog(wx.Dialog):

    # HTML explanation for strftime:
    FORMATHELP = N_(ur"""<html>
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
    <tr><td align="center" valign="baseline"><code>%u</code></td>
        <td align="left">Weekday as a decimal number [1(Monday),7].</td></tr>
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
    <tr><td align="center" valign="baseline"><code>\n</code></td>
        <td align="left">A newline.</td></tr>
    <tr><td align="center" valign="baseline"><code>\\</code></td>
        <td align="left">A literal "<tt class="character">\</tt>" character.</td></tr>
    </tbody>
</table>
</body>
</html>
""")

    def __init__(self, parent, ID, mainControl, title="Choose Date Format",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D, deffmt=u""):
        """
        deffmt -- Initial value for format string
        """
        d = wx.PreDialog()
        self.PostCreate(d)
        
        self.mainControl = mainControl
        self.value = u""     
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "DateformatDialog")
        self.SetTitle(title)
        
        # Create HTML explanation
        html = wx.html.HtmlWindow(self, -1)
        html.SetPage(_(self.FORMATHELP))
        res.AttachUnknownControl("htmlExplain", html, self)
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Set dropdown list of recent time formats
        tfs = self.mainControl.getConfig().get("main", "recent_time_formats")
        self.recentFormats = [unescapeForIni(s) for s in tfs.split(u";")]
        for f in self.recentFormats:
            self.ctrls.fieldFormat.Append(f)

        self.ctrls.fieldFormat.SetValue(deffmt)
        self.OnText(None)
        
        # Fixes focus bug under Linux
        self.SetFocus()
        
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_TEXT(self, XRCID("fieldFormat"), self.OnText) 


    def OnText(self, evt):
        preview = _(u"<invalid>")
        text = guiToUni(self.ctrls.fieldFormat.GetValue())
        try:
#             # strftime can't handle unicode correctly, so conversion is needed
#             mstr = mbcsEnc(text, "replace")[0]
#             preview = mbcsDec(strftime(mstr), "replace")[0]
            preview = strftimeUB(text)
            self.value = text
        except:
            traceback.print_exc()
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

        self.EndModal(wx.ID_OK)



class FontFaceDialog(wx.Dialog):
    """
    Presents a list of available fonts (its face names) and renders a sample
    string with currently selected face.
    """
    def __init__(self, parent, ID, mainControl, value="",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):
        """
        value -- Current value of a text field containing a face name (used to
                 choose default item in the shown list box)
        """
        d = wx.PreDialog()
        self.PostCreate(d)

        self.parent = parent
        self.mainControl = mainControl
        self.value = value

        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.parent, "FontFaceDialog")

        self.ctrls = XrcControls(self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        # Fill font listbox
        fenum = wx.FontEnumerator()
        fenum.EnumerateFacenames()
        facelist = fenum.GetFacenames()
        self.mainControl.getCollator().sort(facelist)

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
            
        # Fixes focus bug under Linux
        self.SetFocus()
            
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_LISTBOX(self, GUI_ID.lbFacenames, self.OnFaceSelected)
        wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lbFacenames, self.OnOk)


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



class ExportDialog(wx.Dialog):
    def __init__(self, pWiki, ID, title="Export",
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki
        
        self.listPagesOperation = ListWikiPagesOperation()
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "ExportDialog")
        
        self.ctrls = XrcControls(self)
        
        self.emptyPanel = None
        
        exporterList = [] # List of tuples (<exporter object>, <export tag>,
                          # <readable description>, <additional options panel>)
        
        addOptSizer = LayerSizer()
        
        for ob in Exporters.describeExporters(self.pWiki):   # TODO search plugins
            for tp in ob.getExportTypes(self.ctrls.additOptions):
                panel = tp[2]
                if panel is None:
                    if self.emptyPanel is None:
                        # Necessary to avoid a crash        
                        self.emptyPanel = wx.Panel(self.ctrls.additOptions)
                        # self.emptyPanel.Fit()
                    panel = self.emptyPanel
                else:
                    pass
                    # panel.Fit()

                # Add Tuple (Exporter object, export type tag,
                #     export type description, additional options panel)
                exporterList.append((ob, tp[0], tp[1], panel))
                addOptSizer.Add(panel)


        self.ctrls.additOptions.SetSizer(addOptSizer)
        self.ctrls.additOptions.SetMinSize(addOptSizer.GetMinSize())

        self.ctrls.additOptions.Fit()
        self.Fit()

#         self.ctrls.additOptions.Fit()
#         mins = self.ctrls.additOptions.GetMinSize()
# 
#         self.ctrls.additOptions.SetMinSize(wx.Size(mins.width+10, mins.height+10))
#         self.Fit()

        self.exporterList = exporterList

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        defdir = self.pWiki.getConfig().get("main", "export_default_dir", u"")
        if defdir == u"":
            defdir = self.pWiki.getLastActiveDir()

        self.ctrls.tfDestination.SetValue(defdir)

        for e in self.exporterList:
            e[3].Show(False)
            e[3].Enable(False)
            self.ctrls.chExportTo.Append(e[2])
            
#         # Enable first addit. options panel
#         self.exporterList[0][3].Enable(True)
#         self.exporterList[0][3].Show(True)

        self.ctrls.chExportTo.SetSelection(0)  
        self._refreshForEtype()
        
        # Fixes focus bug under Linux
        self.SetFocus()
        
        wx.EVT_CHOICE(self, GUI_ID.chExportTo, self.OnExportTo)
        wx.EVT_CHOICE(self, GUI_ID.chSelectedSet, self.OnChSelectedSet)

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_BUTTON(self, GUI_ID.btnSelectDestination, self.OnSelectDest)


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
            self.ctrls.stDestination.SetLabel(_(u"Destination directory:"))
        else:
            # File destination
            self.ctrls.stDestination.SetLabel(_(u"Destination file:"))


    def OnExportTo(self, evt):
        self._refreshForEtype()
        evt.Skip()


    def OnChSelectedSet(self, evt):
        selset = self.ctrls.chSelectedSet.GetSelection()
        if selset == 3:  # Custom
            dlg = WikiPageListConstructionDialog(self, self.pWiki, -1, 
                    value=self.listPagesOperation)
            if dlg.ShowModal() == wx.ID_OK:
                self.listPagesOperation = dlg.getValue()
            dlg.Destroy()

    def OnOk(self, evt):
        import SearchAndReplace as Sar

        # Run exporter
        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]
                
        # If this returns None, export goes to a directory
        expDestWildcards = ob.getExportDestinationWildcards(etype)
        if expDestWildcards is None:
            # Export to a directory
            if not exists(guiToUni(self.ctrls.tfDestination.GetValue())):
                self.pWiki.displayErrorMessage(
                        _(u"Destination directory does not exist"))
                return
            
            if not isdir(guiToUni(self.ctrls.tfDestination.GetValue())):
                self.pWiki.displayErrorMessage(
                        _(u"Destination must be a directory"))
                return
        else:
            if exists(guiToUni(self.ctrls.tfDestination.GetValue())) and \
                    not isfile(guiToUni(self.ctrls.tfDestination.GetValue())):
                self.pWiki.displayErrorMessage(
                        _(u"Destination must be a file"))
                return


        # Create wordList (what to export)
        selset = self.ctrls.chSelectedSet.GetSelection()
        root = self.pWiki.getCurrentWikiWord()
        
        if root is None and selset in (0, 1):
            self.pWiki.displayErrorMessage(
                    _(u"No real wiki word selected as root"))
            return
            
        lpOp = Sar.ListWikiPagesOperation()

        if selset == 0:
            # single page
            item = Sar.ListItemWithSubtreeWikiPagesNode(lpOp, [root], 0)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"  # Slow, but more intuitive
        elif selset == 1:
            # subtree
            item = Sar.ListItemWithSubtreeWikiPagesNode(lpOp, [root], -1)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"  # Slow, but more intuitive
#             wordList = self.pWiki.getWikiData().getAllSubWords([root])
        elif selset == 2:
            # whole wiki
            item = Sar.AllWikiPagesNode(lpOp)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"  # Slow, but more intuitive
#             wordList = self.pWiki.getWikiData().getAllDefinedWikiPageNames()
        else:
            # custom list
            lpOp = self.listPagesOperation

        wordList = self.pWiki.getWikiDocument().searchWiki(lpOp, True)

#         self.pWiki.getConfig().set("main", "html_export_pics_as_links",
#                 self.ctrls.cbHtmlExportPicsAsLinks.GetValue())


        if panel is self.emptyPanel:
            panel = None
            
        try:
            ob.export(self.pWiki.getWikiDataManager(), wordList, etype, 
                    guiToUni(self.ctrls.tfDestination.GetValue()), 
                    self.ctrls.compatFilenames.GetValue(), ob.getAddOpt(panel))
        except ExportException, e:
            self.pWiki.displayErrorMessage(_(u"Error while exporting"), unicode(e))

        self.EndModal(wx.ID_OK)

        
    def OnSelectDest(self, evt):
        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]

        expDestWildcards = ob.getExportDestinationWildcards(etype)

        if expDestWildcards is None:
            # Only transfer between GUI elements, so no unicode conversion
            seldir = wx.DirSelector(_(u"Select Export Directory"),
                    self.ctrls.tfDestination.GetValue(),
                    style=wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON, parent=self)
                
            if seldir:
                self.ctrls.tfDestination.SetValue(seldir)

        else:
            # Build wildcard string
            wcs = []
            for wd, wp in expDestWildcards:
                wcs.append(wd)
                wcs.append(wp)
                
            wcs.append(_(u"All files (*.*)"))
            wcs.append(u"*")
            
            wcs = u"|".join(wcs)
            
            selfile = wx.FileSelector(_(u"Select Export File"),
                    self.ctrls.tfDestination.GetValue(),
                    default_filename = "", default_extension = "",
                    wildcard = wcs, flags=wx.SAVE | wx.OVERWRITE_PROMPT,
                    parent=self)

            if selfile:
                self.ctrls.tfDestination.SetValue(selfile)


class ImportDialog(wx.Dialog):
    def __init__(self, parent, ID, mainControl, title="Import",
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)
        
        self.parent = parent
        self.mainControl = mainControl
        
        self.listPagesOperation = ListWikiPagesOperation()
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.parent, "ImportDialog")

        self.ctrls = XrcControls(self)

        self.emptyPanel = None
        
        importerList = [] # List of tuples (<importer object>, <import tag=type>,
                          # <readable description>, <additional options panel>)
        
        addOptSizer = LayerSizer()

        for ob in Importers.describeImporters(self.mainControl):   # TODO search plugins
            for tp in ob.getImportTypes(self.ctrls.additOptions):
                panel = tp[2]
                if panel is None:
                    if self.emptyPanel is None:
                        # Necessary to avoid a crash        
                        self.emptyPanel = wx.Panel(self.ctrls.additOptions)
                        # self.emptyPanel.Fit()
                    panel = self.emptyPanel
                else:
                    pass
                    # panel.Fit()

                # Add Tuple (Importer object, import type tag,
                #     import type description, additional options panel)
                importerList.append((ob, tp[0], tp[1], panel))
                addOptSizer.Add(panel)

        self.ctrls.additOptions.SetSizer(addOptSizer)
        self.ctrls.additOptions.SetMinSize(addOptSizer.GetMinSize())

        self.ctrls.additOptions.Fit()
        self.Fit()

#         self.ctrls.additOptions.Fit()
#         mins = self.ctrls.additOptions.GetMinSize()
#         
#         self.ctrls.additOptions.SetMinSize(wx.Size(mins.width+10, mins.height+10))
#         self.Fit()

        
        self.importerList = importerList

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
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
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_CHOICE(self, GUI_ID.chImportFormat, self.OnImportFormat)

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_BUTTON(self, GUI_ID.btnSelectSource, self.OnSelectSrc)


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
            self.ctrls.stSource.SetLabel(_(u"Source directory:"))
        else:
            # File source
            self.ctrls.stSource.SetLabel(_(u"Source file:"))


    def OnImportFormat(self, evt):
        self._refreshForItype()
        evt.Skip()



    def OnOk(self, evt):
        # Run importer
        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]
                
        if not exists(guiToUni(self.ctrls.tfSource.GetValue())):
            self.mainControl.displayErrorMessage(
                    _(u"Source does not exist"))
            return

        # If this returns None, import goes to a directory
        impSrcWildcards = ob.getImportSourceWildcards(itype)
        if impSrcWildcards is None:
            # Import from a directory
            
            if not isdir(guiToUni(self.ctrls.tfSource.GetValue())):
                self.mainControl.displayErrorMessage(
                        _(u"Source must be a directory"))
                return
        else:
            if not isfile(guiToUni(self.ctrls.tfSource.GetValue())):
                self.mainControl.displayErrorMessage(
                        _(u"Source must be a file"))
                return

        if panel is self.emptyPanel:
            panel = None

        try:
            ob.doImport(self.mainControl.getWikiDataManager(), itype, 
                    guiToUni(self.ctrls.tfSource.GetValue()), 
                    False, ob.getAddOpt(panel))
        except ImportException, e:
            self.mainControl.displayErrorMessage(_(u"Error while importing"),
                    unicode(e))

        self.EndModal(wx.ID_OK)

        
    def OnSelectSrc(self, evt):
        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]

        impSrcWildcards = ob.getImportSourceWildcards(itype)

        if impSrcWildcards is None:
            # Only transfer between GUI elements, so no unicode conversion
            seldir = wx.DirSelector(_(u"Select Import Directory"),
                    self.ctrls.tfSource.GetValue(),
                    style=wx.DD_DEFAULT_STYLE, parent=self)

            if seldir:
                self.ctrls.tfSource.SetValue(seldir)

        else:
            # Build wildcard string
            wcs = []
            for wd, wp in impSrcWildcards:
                wcs.append(wd)
                wcs.append(wp)
                
            wcs.append(_(u"All files (*.*)"))
            wcs.append(_(u"*"))
            
            wcs = u"|".join(wcs)
            
            selfile = wx.FileSelector(_(u"Select Import File"),
                    self.ctrls.tfSource.GetValue(),
                    default_filename = "", default_extension = "",
                    wildcard = wcs, flags=wx.OPEN | wx.FILE_MUST_EXIST,
                    parent=self)

            if selfile:
                self.ctrls.tfSource.SetValue(selfile)



class ChooseWikiWordDialog(wx.Dialog):
    def __init__(self, pWiki, ID, words, motionType, title="Choose Wiki Word",
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "ChooseWikiWordDialog")
        
        self.ctrls = XrcControls(self)
        
        self.SetTitle(title)
        self.ctrls.staTitle.SetLabel(title)
        
        self.motionType = motionType
        self.words = words
        wordsgui = map(uniToGui, words)
        
        self.ctrls.lb.Set(wordsgui)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, GUI_ID.btnDelete, self.OnDelete)
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lb, self.OnOk)


    def OnOk(self, evt):
        sels = self.ctrls.lb.GetSelections()
        if len(sels) != 1:
            return # We can only go to exactly one wiki word
            
        wikiWord = self.words[sels[0]]
        try:
            self.pWiki.openWikiPage(wikiWord, forceTreeSyncFromRoot=True,
                    motionType=self.motionType)
        finally:
            self.EndModal(GUI_ID.btnDelete)


    def OnDelete(self, evt):
        sellen = len(self.ctrls.lb.GetSelections())
        if sellen > 0:
            answer = wx.MessageBox(
                    _(u"Do you want to delete %i wiki page(s)?") % sellen,
                    (u"Delete Wiki Page(s)"),
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

            if answer != wx.YES:
                return

            self.pWiki.saveAllDocPages()
            for s in self.ctrls.lb.GetSelections():
                delword = self.words[s]
                # Un-alias word
                delword = self.pWiki.getWikiData().getAliasesWikiWord(delword)
                
                if self.pWiki.getWikiData().isDefinedWikiWord(delword):
                    page = self.pWiki.getWikiDocument().getWikiPage(delword)
                    page.deletePage()
                    
                    # self.pWiki.getWikiData().deleteWord(delword)
        
                    # trigger hooks
                    self.pWiki.hooks.deletedWikiWord(self.pWiki, delword)
                    
#                     p2 = {}
#                     p2["deleted page"] = True
#                     p2["deleted wiki page"] = True
#                     p2["wikiWord"] = delword
#                     self.pWiki.fireMiscEventProps(p2)
            
            self.pWiki.pageHistory.goAfterDeletion()

            self.EndModal(wx.ID_OK)


def _children(win, indent=0):
    print " " * indent + repr(win), win.GetId()
    for c in win.GetChildren():
        _children(c, indent=indent+2)


class AboutDialog(wx.Dialog):
    """ An about box that uses an HTML window """

    TEXT_TEMPLATE = N_('''
<html>
<body bgcolor="#FFFFFF">
    <center>
        <table bgcolor="#CCCCCC" width="100%%" cellspacing="0" cellpadding="0" border="1">
            <tr>
                <td align="center"><h2>%s</h2></td>
            </tr>
        </table>

        <p>
wikidPad is a Wiki-like notebook for storing your thoughts, ideas, todo lists, contacts, or anything else you can think of to write down.
What makes wikidPad different from other notepad applications is the ease with which you can cross-link your information.        </p>        
        <br><br>

        <table border=0 cellpadding=1 cellspacing=0>
            <tr><td width="30%%" align="right"><font size="3"><b>Author:</b></font></td><td nowrap><font size="3">Michael Butscher</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Email:</b></font></td><td nowrap><font size="3">mbutscher@gmx.de</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>URL:</b></font></td><td nowrap><font size="3">http://www.mbutscher.de/software.html</font></td></tr>
            <tr><td width="30%%" align="right">&nbsp;</td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Author:</b></font></td><td nowrap><font size="3">Jason Horman</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Email:</b></font></td><td nowrap><font size="3">wikidpad@jhorman.org</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>URL:</b></font></td><td nowrap><font size="3">http://www.jhorman.org/wikidPad/</font></td></tr>
            <tr><td width="30%%" align="right">&nbsp;</td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Author:</b></font></td><td nowrap><font size="3">Gerhard Reitmayr</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Email:</b></font></td><td nowrap><font size="3">gerhard.reitmayr@gmail.com</font></td></tr>
        </table>
    </center>
    
    <hr />
    
    <p />Your configuration directory is: %s
</body>
</html>
''')

    def __init__(self, pWiki):
        wx.Dialog.__init__(self, pWiki, -1, _(u'About WikidPad'),
                          size=(470, 330) )
        text = _(self.TEXT_TEMPLATE) % (VERSION_STRING,
                escapeHtml(pWiki.globalConfigDir))

        html = wx.html.HtmlWindow(self, -1)
        html.SetPage(text)
        button = wx.Button(self, wx.ID_OK, _(u"Okay"))

        # constraints for the html window
        lc = wx.LayoutConstraints()
        lc.top.SameAs(self, wx.Top, 5)
        lc.left.SameAs(self, wx.Left, 5)
        lc.bottom.SameAs(button, wx.Top, 5)
        lc.right.SameAs(self, wx.Right, 5)
        html.SetConstraints(lc)

        # constraints for the button
        lc = wx.LayoutConstraints()
        lc.bottom.SameAs(self, wx.Bottom, 5)
        lc.centreX.SameAs(self, wx.CentreX)
        lc.width.AsIs()
        lc.height.AsIs()
        button.SetConstraints(lc)

        self.SetAutoLayout(True)
        self.Layout()
        self.CentreOnParent(wx.BOTH)
        
        # Fixes focus bug under Linux
        self.SetFocus()



class WikiInfoDialog(wx.Dialog):
    """
    Show general information about currently open wiki
    """
    def __init__(self, parent, id, mainControl):
        wx.Dialog.__init__(self, parent, id, 'Wiki Info',
                          size=(470, 330) )
                          
        self.txtBgColor = self.GetBackgroundColour()

        button = wx.Button(self, wx.ID_OK)
        button.SetDefault()
        wd = mainControl.getWikiDocument()

        wikiData = wd.getWikiData()
        
        mainsizer = wx.BoxSizer(wx.VERTICAL)

        label = _(u"Wiki database backend:")
        if wd is None:
            value = _(u"N/A")
        else:
            value = wd.getDbtype()

        mainsizer.Add(self._buildLine(label, value), 0, wx.EXPAND)

        label = _(u"Number of wiki pages:")
        if wd is None:
            value = _(u"N/A")
        else:
            value = unicode(len(wikiData.getAllDefinedWikiPageNames()))
        mainsizer.Add(self._buildLine(label, value), 0, wx.EXPAND)

        inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        inputsizer.Add(button, 0, wx.ALL | wx.EXPAND, 5)
        inputsizer.Add((0, 0), 1)   # Stretchable spacer

        mainsizer.Add(inputsizer, 0, wx.ALL | wx.EXPAND, 5)
        
        self.SetSizer(mainsizer)
        self.Fit()

        # Fixes focus bug under Linux
        self.SetFocus()


    def _buildLine(self, label, value):
        inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        inputsizer.Add(wx.StaticText(self, -1, label), 1,
                wx.ALL | wx.EXPAND, 5)
        ctl = wx.TextCtrl(self, -1, value, style = wx.TE_READONLY)
        ctl.SetBackgroundColour(self.txtBgColor)
        inputsizer.Add(ctl, 1, wx.ALL | wx.EXPAND, 5)
        
        return inputsizer




# TODO Move to better module
class ImagePasteSaver:
    """
    Helper class to store image settings (format, quality) and to 
    perform saving on request.
    """
    def __init__(self):
        self.prefix = u""  # Prefix before random numbers in filename
        self.formatNo = 0  # Currently either 0:None, 1:PNG or 2:JPG
        self.quality = 75   # Quality for JPG image


    def readOptionsFromConfig(self, config):
        """
        config -- SingleConfiguration or CombinedConfiguration to read default
                settings from into the object
        """
        self.prefix = config.get("main", "editor_imagePaste_filenamePrefix", u"")

        self.formatNo = config.getint("main", "editor_imagePaste_fileType", u"")

        quality = config.getint("main", "editor_imagePaste_quality", 75)
        quality = min(100, quality)
        quality = max(0, quality)

        self.quality = quality


    def setQualityByString(self, s):
        try:
            quality = int(s)
            quality = min(100, quality)
            quality = max(0, quality)
    
            self.quality = quality
        except ValueError:
            return


#     def setFormatByFormatNo(self, formatNo):
#         if formatNo == 1:
#             self.format = "png"
#         elif formatNo == 2:
#             self.format = "jpg"
#         else:  # formatNo == 0
#             self.format = "none"


    def saveFile(self, fs, img):
        """
        fs -- FileStorage to save into
        img -- wx.Image to save

        Returns absolute path of saved image or None if not saved
        """
        if self.formatNo < 1 or self.formatNo > 2:
            return None

        img.SetOptionInt(u"quality", self.quality)

        if self.formatNo == 1:   # PNG
            destPath = fs.findDestPathNoSource(u".png", self.prefix)
        elif self.formatNo == 2:   # JPG
            destPath = fs.findDestPathNoSource(u".jpg", self.prefix)

        if destPath is None:
            # Couldn't find unused filename
            return None

        if self.formatNo == 1:   # PNG
            img.SaveFile(destPath, wx.BITMAP_TYPE_PNG)
        elif self.formatNo == 2:   # JPG
            img.SaveFile(destPath, wx.BITMAP_TYPE_JPEG)

        return destPath



class ImagePasteDialog(wx.Dialog):
    def __init__(self, pWiki, ID, imgpastesaver, title="Image paste options",
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)

        self.pWiki = pWiki
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "ImagePasteDialog")

        self.ctrls = XrcControls(self)

        self.SetTitle(title)

        self.ctrls.tfEditorImagePasteFilenamePrefix.SetValue(imgpastesaver.prefix)
        self.ctrls.chEditorImagePasteFileType.SetSelection(imgpastesaver.formatNo)
        self.ctrls.tfEditorImagePasteQuality.SetValue(unicode(
                imgpastesaver.quality))

        self.imgpastesaver = ImagePasteSaver()

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        self.OnFileTypeChoice(None)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_CHOICE(self, GUI_ID.chEditorImagePasteFileType,
                self.OnFileTypeChoice)


    def getImagePasteSaver(self):
        return self.imgpastesaver
        
    def OnFileTypeChoice(self, evt):
        # Make quality field gray if not JPG format
        enabled = self.ctrls.chEditorImagePasteFileType.GetSelection() == 2
        self.ctrls.tfEditorImagePasteQuality.Enable(enabled)


    def OnOk(self, evt):
        try:
            imgpastesaver = ImagePasteSaver()
            imgpastesaver.prefix = \
                    self.ctrls.tfEditorImagePasteFilenamePrefix.GetValue()
            imgpastesaver.formatNo = \
                    self.ctrls.chEditorImagePasteFileType.GetSelection()
            imgpastesaver.setQualityByString(
                    self.ctrls.tfEditorImagePasteQuality.GetValue())

            self.imgpastesaver = imgpastesaver
        finally:
            self.EndModal(wx.ID_OK)





