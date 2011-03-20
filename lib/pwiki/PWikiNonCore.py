## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

"""
Additional non-core functionality for PersonalWikiFrame.
TODO: Maybe creation of respective menu items should be done here (somehow)
"""


import traceback, os.path

import wx

from . import wxHelper, StringOps


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
            path = wx.FileSelector(_(u"Choose a file to create URL for"),
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
                _(u"     Scanning     "),
                _(u"     Scanning     "), 0, self.mainControl)
        
        FileCleanup.runFileCleanup(self.mainControl, self.dlgParent,
                progresshandler)


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
                _(u'&File URL...'), _(u'Use file dialog to add URL'),
                kb.AddFileUrl, None, None,
                (mc.OnUpdateDisReadOnlyPage, mc.OnUpdateDisNotTextedit)),
            "insertCurrentDate": (self.OnInsertCurrentDate,
                _(u'Current &Date'), _(u'Insert current date'),
                kb.InsertDate, "date", None,
                (mc.OnUpdateDisReadOnlyPage, mc.OnUpdateDisNotTextedit,
                    mc.OnUpdateDisNotWikiPage)),
            "showFileCleanupDialog": (self.OnShowFileCleanup,
                _(u'File cleanup...'), _(u'Remove orphaned files and dead links'),
                kb.FileCleanup, None, None,
                None),
            }

        return descriptorDict
