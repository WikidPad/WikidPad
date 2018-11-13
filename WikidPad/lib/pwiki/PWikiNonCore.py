## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

"""
Additional non-core functionality for PersonalWikiFrame.
TODO: Maybe creation of respective menu items should be done here (somehow)
"""


import traceback, os.path

import wx

from . import wxHelper, StringOps, Exporters, WikiDocument, DocPages

from . import Trashcan




class PWikiNonCore:
    def __init__(self, mainControl, dlgParent):
        self.mainControl = mainControl
        self.dlgParent = dlgParent
        self.descriptorDict = self._buildDescriptorDict()


    def getDescriptorFor(self, unifName):
        if not unifName.startswith("menuItem/mainControl/builtin/"):
            return None

        # Ignore possible parameters after descriptor tag (may be changed later)
        return self.descriptorDict.get(unifName[29:].split("/", 2)[0])


    def OnShowInsertFileUrlDialog(self, evt):
        if self.mainControl.isReadOnlyPage():
            return
            
        actEd = self.mainControl.getActiveEditor()
        if actEd is None:
            return
    
        with wxHelper.TopLevelLocker:
            path = wx.FileSelector(_("Choose a file to create URL for"),
                    self.mainControl.getLastActiveDir(), wildcard="*.*",
                    flags=wx.FD_OPEN, parent=self.mainControl)
    
        if path:
            url = StringOps.urlFromPathname(path)
            if path.endswith(".wiki"):
                url = "wiki:" + url
            else:
                # Absolute file: URL
                url = "file:" + url
                
            actEd.AddText(url)
            self.mainControl.getConfig().set("main", "last_active_dir",
                    os.path.dirname(path))


    def OnInsertCurrentDate(self, evt):
        if self.mainControl.isReadOnlyPage():
            return

        mstr = self.mainControl.getConfig().get("main", "strftime")
        self.mainControl.getActiveEditor().AddText(StringOps.strftimeUB(mstr))


    def OnShowFileCleanup(self, evt):
        from . import FileCleanup

        progresshandler = wxHelper.ProgressHandler(
                _("     Scanning     "),
                _("     Scanning     "), 0, self.mainControl)
        
        FileCleanup.runFileCleanup(self.mainControl, self.dlgParent,
                progresshandler)


    def OnTogglePageReadOnly(self, evt):
        docPage = self.mainControl.getCurrentDocPage()
        if docPage is None:
            return

        docPage.setPageReadOnly(evt.IsChecked())
    
    
    def OnTogglePageReadOnlyUpdate(self, evt):
        if not evt.GetEnabled():
            evt.Check(False)
            return

        docPage = self.mainControl.getCurrentDocPage()
        if docPage is None or not docPage.isDefined():
            evt.Enable(False)
            evt.Check(False)
            return
    
        evt.Check(docPage.getPageReadOnly())


    def OnOpenTrashcan(self, evt):
        from .TrashcanGui import TrashcanDialog

        self.mainControl.saveAllDocPages()
        TrashcanDialog.runModal(self.mainControl, self.mainControl)


    def OnRecoverWikiDatabase(self, evt):
#         if self.mainControl.stdDialog("yn", _(u"Continue?"),
#                 _(u"You should run this function only if you know what you are doing\n"
#                 "Continue?")) == "no":
#             return
        
        with wxHelper.TopLevelLocker:
            wf = wx.FileSelector(_("Wiki file"),
                    "", wildcard="*.wiki",
                    flags=wx.FD_OPEN, parent=self.mainControl)

            if not wf:
                return

            exportDest = wx.FileSelector(_("MPT export target file"),
                    "", wildcard="*.mpt",
                    flags=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                    parent=self.mainControl)

            if not exportDest:
                return

        wikiDoc = WikiDocument.WikiDocument(wf, None, None, ignoreLock=True,
            createLock=False, recoveryMode=True)
            
        wikiDoc.connect()

        exp = Exporters.MultiPageTextExporter(self.mainControl)
        exp.recoveryExport(wikiDoc, exportDest, progressHandler=None)
        
        
    def OnSelectionToLink(self, evt):
        editor = self.mainControl.getActiveEditor()
        if editor is None:
            return
            
        docPage = editor.getLoadedDocPage()
        
        if docPage is None or not isinstance(docPage, (DocPages.AliasWikiPage,
                DocPages.AbstractWikiPage)):
            return
        
        if docPage.isReadOnlyEffect():
            return

        langHelper = wx.GetApp().createWikiLanguageHelper(
                docPage.getWikiLanguageName())
        
        editor.ReplaceSelection(langHelper.createWikiLinkFromText(
                editor.GetSelectedText(), bracketed=True))



    def _buildDescriptorDict(self):
        """
        Builds and returns a dictionary of tuples to describe the menu items,
        where each must contain (in this order):
            - callback function
            - menu item string
            - menu item description (string to show in status bar)
        It can contain the following additional items (in this order), each of
        them can be replaced by None:
            - shortcut string (instead of appending it to label with '\t')
            - icon descriptor (see below, if no icon found, it won't show one)
            - menu item id.
            - update function
            - kind of menu item (wx.ITEM_NORMAL, wx.ITEM_CHECK)
    
        The  callback function  must take 1 parameter:
            evt - wx.CommandEvent

        An  icon descriptor  can be one of the following:
            - a wx.Bitmap object
            - the filename of a bitmap (if file not found, no icon is used)
            - a tuple of filenames, first existing file is used
        """

        mc = self.mainControl
        kb = mc.getKeyBindings()
        
        descriptorDict = {
            "showInsertFileUrlDialog": (self.OnShowInsertFileUrlDialog,
                _('&File URL...'), _('Use file dialog to add URL'),
                kb.AddFileUrl, None, None,
                (mc.OnUpdateDisReadOnlyPage, mc.OnUpdateDisNotTextedit)),
            "insertCurrentDate": (self.OnInsertCurrentDate,
                _('Current &Date'), _('Insert current date'),
                kb.InsertDate, "date", None,
                (mc.OnUpdateDisReadOnlyPage, mc.OnUpdateDisNotTextedit,
                    mc.OnUpdateDisNotWikiPage)),

            "showFileCleanupDialog": (self.OnShowFileCleanup,
                _('File cleanup...'), _('Remove orphaned files and dead links'),
                kb.FileCleanup, None, None,
                None),

            "togglePageReadOnly": (self.OnTogglePageReadOnly,
                _('Page read only'), _('Set current page read only'),
                kb.TogglePageReadOnly, None, None,
                (mc.OnUpdateDisReadOnlyWiki, mc.OnUpdateDisNotWikiPage,
                self.OnTogglePageReadOnlyUpdate),
                wx.ITEM_CHECK),

            "openTrashcan": (self.OnOpenTrashcan, _('Open trashcan'),
                _('Open trashcan'),
                kb.OpenTrashcan, None, None,
                None),
                
            "recoverWikiDatabase": (self.OnRecoverWikiDatabase, _('Recover DB'),
                _('Recover wiki database')),
                
            "selectionToLink": (self.OnSelectionToLink, _('Selection to &Link'),
                _('Remove non-allowed characters and make sel. a wiki word link'),
                kb.MakeWikiWord, "tb_wikize",
                wxHelper.GUI_ID.CMD_FORMAT_WIKIZE_SELECTED,
                (mc.OnUpdateDisReadOnlyPage, mc.OnUpdateDisNotTextedit)),

            }


        return descriptorDict
