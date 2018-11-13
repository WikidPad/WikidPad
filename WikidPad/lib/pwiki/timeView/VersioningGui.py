import traceback

import wx, wx.xrc

from pwiki.WikiExceptions import *

from .. import Utilities
from ..wxHelper import GUI_ID, EnhancedListControl, wxKeyFunctionSink, \
        getAccelPairFromKeyDown, appendToMenuByMenuDesc
 
from ..WindowLayout import LayeredControlPanel

from ..DiffGui import InlineDiffControl

from ..DocPages import FunctionalPage

from .Versioning import WikiPageSnapshot, VersionOverview


# class VersionExplorerPresenterControl(wx.Panel):
#     """
#     Panel which can be added to presenter in main area panel as tab showing
#     search results.
#     """
#     def __init__(self, presenter, mainControl, ID):
#         super(VersionExplorerPresenterControl, self).__init__(presenter, ID)
# 
#         self.mainControl = mainControl
#         self.presenter = presenter
# 
#         mainsizer = wx.BoxSizer(wx.VERTICAL)
#         self.splitter = wx.SplitterWindow(self, -1)
#         mainsizer.Add(self.splitter, 1, wx.ALL | wx.EXPAND, 0)        
# 
#         self.editCtrl = WikiTxtCtrl(self.presenter, self.splitter, -1)
# 
#         self.versionListCtrl = EnhancedListControl(self.splitter, -1,
#                 style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
# 
# 
#     def close(self):
#         self.editCtrl.close()



class VersionExplorerPanel(EnhancedListControl):
    
    _ACTIVATION_MODE_NORMAL = 0
    _ACTIVATION_MODE_SET_FROM = 1
    _ACTIVATION_MODE_SET_TO = 2
    _ACTIVATION_MODE_FROM_PREV_TO_THIS = 3
    
    def __init__(self, parent, ID, mainControl):
        EnhancedListControl.__init__(self, parent, ID,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER)

        self.mainControl = mainControl

        self.InsertColumn(0, "", width=3000)

        self.updatingThreadHolder = Utilities.ThreadHolder()
        
        self.versionEntries = []
        self.versionOverview = None
        self.activationMode = self._ACTIVATION_MODE_NORMAL
        
        self.mainControl.getMiscEvent().addListener(self)

        self.layerVisible = True
        self.sizeVisible = True   # False if this window has a size
                # that it can't be read (one dim. less than 5 pixels)
        self.ignoreOnChange = False

        self.docPagePresenterSink = wxKeyFunctionSink((
                ("loaded current doc page", self.onUpdateNeeded),
        ))

        self.versionOverviewSink = wxKeyFunctionSink((
                ("changed version overview", self.onUpdateNeeded),
                ("invalidated version overview", self.onUpdateNeeded)
        ))

        self.__sinkApp = wxKeyFunctionSink((
                ("options changed", self.onUpdateNeeded),
        ), wx.GetApp().getMiscEvent(), self)

        if not self.mainControl.isMainWindowConstructed():
            # Install event handler to wait for construction
            self.__sinkMainFrame = wxKeyFunctionSink((
                    ("constructed main window", self.onConstructedMainWindow),
            ), self.mainControl.getMiscEvent(), self)
        else:
            self.onConstructedMainWindow(None)

#         currPres = self.mainControl.getCurrentDocPagePresenter()
#         if currPres is not None:
#             self.docPagePresenterSink.setEventSource(currPres.getMiscEvent())

        self.docPagePresenterSink.setEventSource(
                self.mainControl.getCurrentPresenterProxyEvent())

        self.lastSelection = (-1, -1)

        self.updateList()

        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, id=self.GetId())
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated, id=self.GetId())
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)

        self.Bind(wx.EVT_MENU, self.OnCmdDiffInline, id=GUI_ID.CMD_VERSIONING_DIFF_INLINE)

        self.Bind(wx.EVT_MENU, self.OnCmdDiffSetFrom, id=GUI_ID.CMD_VERSIONING_DIFF_SET_FROM)
        self.Bind(wx.EVT_MENU, self.OnCmdDiffSetTo, id=GUI_ID.CMD_VERSIONING_DIFF_SET_TO)

        self.Bind(wx.EVT_MENU, self.OnCmdDeleteVersion, id=GUI_ID.CMD_VERSIONING_DELETE_VERSION)
        self.Bind(wx.EVT_MENU, self.OnCmdDeleteAllVersionData, id=GUI_ID.CMD_VERSIONING_DELETE_ALL_VERSION_DATA)

#         wx.EVT_UPDATE_UI(self, GUI_ID.CMD_CHECKBOX_TIMELINE_DATE_ASCENDING,
#                 self.OnCmdCheckUpdateDateAscending)



    def close(self):
        """
        """
        self.updatingThreadHolder.setThread(None)
        self.docPagePresenterSink.disconnect()
        self.__sinkApp.disconnect()
        self.setVersionOverview(None)


    def isVisibleEffect(self):
        """
        Is this control effectively visible?
        """
        return self.layerVisible and self.sizeVisible


    def handleVisibilityChange(self):
        """
        Only call after isVisibleEffect() really changed its value.
        The new value is taken from isVisibleEffect(), the old is assumed
        to be the opposite.
        """
        if self.isVisibleEffect():
            # Trick to make switching look faster
            wx.CallLater(1, self.updateList)


    def OnContextMenu(self, evt):
        mousePos = evt.GetPosition()
        if mousePos == wx.DefaultPosition:
            idx = self.GetFirstSelected()
        else:
            pos = self.ScreenToClient(wx.GetMousePosition())
            idx = self.HitTest(pos)[0]
            if not self.GetIsSelected(idx):
                self.SelectSingle(idx)

        if idx < 0 or idx > len(self.versionEntries):
            # Use the tab context menu
            self.showContextMenuOnTab()
            return

        menu = wx.Menu()

        if self.activationMode == self._ACTIVATION_MODE_NORMAL:
            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_DIFF_ON_WIKI_PAGE)
        else:
            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_DIFF_ON_DIFF_CTRL)

        if idx < len(self.versionEntries):
            # Usable version entry selected
            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_VERSIONING_ITEM)
        else:
            # Entry "<Current>" selected, but at least one version present
            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_VERSIONING_CURRENT_ITEM)

        self.PopupMenu(menu)


    def showContextMenuOnTab(self):
        """
        Called by the TimeView to show a context menu if the tab was
        context-clicked.
        """
        menu = wx.Menu()
        appendToMenuByMenuDesc(menu, _CONTEXT_MENU_VERSIONING_TAB)
        self.PopupMenu(menu)



    def OnKeyDown(self, evt):
#         key = evt.GetKeyCode()
        accP = getAccelPairFromKeyDown(evt)
#         matchesAccelPair = self.presenter.getMainControl().keyBindings.\
#                 matchesAccelPair

        if accP in ((wx.ACCEL_NORMAL, wx.WXK_DELETE),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DELETE)):
            self.OnCmdDeleteVersion(evt)
        else:
            evt.Skip()


    def OnCmdDeleteVersion(self, evt):
        selIdx = self.GetFirstSelected()
        if selIdx == -1 or selIdx == len(self.versionEntries):
            return
        
        if self.versionOverview is None:
            return

        if selIdx != 0 and selIdx != (len(self.versionEntries) - 1):
            self.mainControl.displayErrorMessage(
                    _("Deleting in-between versions is not supported yet"))
            return
        
        answer = wx.MessageBox(_("Do you want to delete this version?"),
                _("Delete version"), wx.YES_NO | wx.ICON_QUESTION, self)
        
        if answer == wx.YES:
            entry = self.versionEntries[selIdx]
            self.versionOverview.deleteVersion(entry.versionNumber)
            if not self.versionOverview.isInvalid():
                self.versionOverview.writeOverview()


    def OnCmdDeleteAllVersionData(self, evt):
        if self.versionOverview is not None:
            answer = wx.MessageBox(
                    _("Do you want to delete all version data of this page?"),
                    _("Delete all versions"), wx.YES_NO | wx.ICON_QUESTION, self)

            if answer == wx.YES:
                self.versionOverview.delete()
                self.updateList()
        else:
            # User wants to delete a page which has no valid version data
            # so check if there is invalid version data to delete
            
            presenter = self.mainControl.getCurrentDocPagePresenter()
            if presenter is None:
                return

            docPage = presenter.getDocPage()
            if docPage is None or isinstance(docPage, FunctionalPage):
                return

            try:
                versionOverview = docPage.getVersionOverview()

                # this should not happen under normal circumstances    
                self.setVersionOverview(versionOverview)
                return

            except VersioningException:
                pass

            # Here: A VersioningException was thrown, so ask if to clean up
            # the broken parts of the version data
            
            answer = wx.MessageBox(
                    _("Do you want to delete all version data of this page?"),
                    _("Delete all versions"), wx.YES_NO | wx.ICON_QUESTION, self)

            if answer == wx.YES:
                VersionOverview.deleteBrokenDataForDocPage(docPage)
                self.updateList()



    def _getTextAndVersionNoStringBySelection(self, selIdx, baseDocPage):
        if selIdx < len(self.versionEntries):
            entry = self.versionEntries[selIdx]
            text = self.versionOverview.getVersionContent(entry.versionNumber)
            verNoStr = "%d" % entry.versionNumber
        else:
            verNoStr = "<" + _("Current") + ">"

            text = baseDocPage.getLiveText()
        
        return text, verNoStr


    def OnCmdDiffInline(self, evt):
        selIdx = self.GetFirstSelected()
        if selIdx == -1 or selIdx > len(self.versionEntries):
            return

        if self.versionOverview is None:
            return
        
        if self.activationMode != self._ACTIVATION_MODE_NORMAL:
            return

        presenter = self.mainControl.getCurrentDocPagePresenter()
        if presenter is None:
            return

        docPage = presenter.getDocPage()
        if docPage is None:
            return

        if isinstance(docPage, WikiPageSnapshot):
            baseDocPage = docPage.getSnapshotBaseDocPage()
        else:
            baseDocPage = docPage

        maPanel = self.mainControl.getMainAreaPanel()
        newPresenter = LayeredControlPanel(maPanel)
        
        subCtl = InlineDiffControl(newPresenter, self.mainControl,
                newPresenter, -1)
        newPresenter.setSubControl("inline diff", subCtl)
        newPresenter.switchSubControl("inline diff")
        maPanel.appendPresenterTab(newPresenter)
        
        # Actually not the numbers but a string for presentation
        fromText, fromVerNo = self._getTextAndVersionNoStringBySelection(selIdx,
                baseDocPage)

#         if selIdx < len(self.versionEntries):
#             entry = self.versionEntries[selIdx]
#             fromText = self.versionOverview.getVersionContent(entry.versionNumber)
#             fromVerNo = u"%d" % entry.versionNumber
#         else:
#             fromVerNo = u"<" + _(u"Current") + u">"
# 
#             if isinstance(docPage, WikiPageSnapshot):
#                 fromText = baseDocPage.getLiveText()
#             else:
#                 # TODO: ? This would compare <Current> with itself
#                 fromText = docPage.getLiveText() 


        if isinstance(docPage, WikiPageSnapshot):
            toVerNo = "%d" % docPage.getSnapshotVersionNumber()
        else:
            toVerNo = "<" + _("Current") + ">"

        toText = docPage.getLiveText()

        subCtl.showDiffs(baseDocPage, fromText, toText, fromVerNo, toVerNo)

        maPanel.showPresenter(newPresenter)



    def OnCmdDiffSetFrom(self, evt):
        selIdx = self.GetFirstSelected()
        if selIdx == -1 or selIdx > len(self.versionEntries):
            return

        if self.versionOverview is None:
            return
        
        subCtrl = self.mainControl.getMainAreaPanel().getCurrentSubControl()
        if not isinstance(subCtrl, InlineDiffControl):
            return

        baseDocPage = subCtrl.getBaseDocPage()

        text, verNo = self._getTextAndVersionNoStringBySelection(selIdx,
                baseDocPage)
        
        subCtrl.showDiffsNewFrom(baseDocPage, text, verNo)
        

    def OnCmdDiffSetTo(self, evt):
        selIdx = self.GetFirstSelected()
        if selIdx == -1 or selIdx > len(self.versionEntries):
            return

        if self.versionOverview is None:
            return
        
        subCtrl = self.mainControl.getMainAreaPanel().getCurrentSubControl()
        if not isinstance(subCtrl, InlineDiffControl):
            return

        baseDocPage = subCtrl.getBaseDocPage()

        text, verNo = self._getTextAndVersionNoStringBySelection(selIdx,
                baseDocPage)
        
        subCtrl.showDiffsNewTo(baseDocPage, text, verNo)
            



    def setLayerVisible(self, vis, scName=""):
        oldVisible = self.isVisibleEffect()
        self.layerVisible = vis
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()


    def setVersionOverview(self, versionOverview):
        if versionOverview is not None:
            self.versionEntries = versionOverview.getVersionEntries()
            self.versionOverviewSink.setEventSource(versionOverview.getMiscEvent())
        else:
            self.versionEntries = []
            self.versionOverviewSink.disconnect()
        
        self.versionOverview = versionOverview


    def OnDestroy(self, evt):
        self.close()


    def OnSize(self, evt):
        evt.Skip()
        oldVisible = self.isVisibleEffect()
        size = evt.GetSize()
        self.sizeVisible = size.GetHeight() >= 5 and size.GetWidth() >= 5
        
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()


    def onConstructedMainWindow(self, evt):
        """
        Now we can register idle handler.
        """
        pass
#         self.Bind(wx.EVT_IDLE, self.OnIdle)


#     def OnIdle(self, evt):
#         self.checkSelectionChanged()
#         
#         
#     def checkSelectionChanged(self, callAlways=False):
#         if not self.isVisibleEffect():
#             return
# 
#         presenter = self.mainControl.getCurrentDocPagePresenter()
#         if presenter is None:
#             return
# 
#         subCtrl = presenter.getSubControl("textedit")
#         if subCtrl is None:
#             return
#         
#         sel = subCtrl.GetSelectionCharPos()
#         
#         if sel != self.lastSelection or callAlways:
#             self.lastSelection = sel
#             self.onSelectionChanged(sel)
# 
# 
#     def onSelectionChanged(self, sel):
#         """
#         This is not directly supported by Scintilla, but called by OnIdle().
#         """
#         if not self.mainControl.getConfig().getboolean("main",
#                 "docStructure_autofollow"):
#             return
# 
#         idx = bisect.bisect_right(self.tocListStarts, sel[0]) - 1
# 
#         self.ignoreOnChange = True
#         try:
#             self.SelectSingle(idx, scrollVisible=True)
#         finally:    
#             self.ignoreOnChange = False



    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        if self.isVisibleEffect() and miscevt.getSource() is self.mainControl:
            if "changed current presenter" in miscevt:
#                 presenter = self.mainControl.getCurrentDocPagePresenter()
#                 if presenter is not None:
#                     self.docPagePresenterSink.setEventSource(presenter.getMiscEvent())
#                 else:
#                     self.docPagePresenterSink.setEventSource(None)

                self.onUpdateNeeded(miscevt)


    def onUpdateNeeded(self, miscevt):
        if self.isVisibleEffect():
#             if miscevt.has_key("appended version"):
#                 self.extendList()
#             else:
            self.updateList()



    def updateList(self):
        presenter = self.mainControl.getCurrentDocPagePresenter()

        if presenter is not None:
            docPage = presenter.getDocPage()
            self.activationMode = self._ACTIVATION_MODE_NORMAL
            self.buildTocList(docPage)
            return

        subCtrl = self.mainControl.getMainAreaPanel().getCurrentSubControl()

        if isinstance(subCtrl, InlineDiffControl):
            docPage = subCtrl.getBaseDocPage()
            self.activationMode = self._ACTIVATION_MODE_FROM_PREV_TO_THIS
            self.buildTocList(docPage)
            return


        self.setVersionOverview(None)
        self.applyTocList()


#         text = presenter.getLiveText()
#         docPage = presenter.getDocPage()
# 
#         # Asynchronous update
#         uth = self.updatingThreadHolder
# 
#         depth = presenter.getConfig().getint(
#                 "main", "docStructure_depth")
#         
#         t = threading.Thread(None, self.buildTocList,
#                 args = (text, docPage, depth, uth))
#         uth.setThread(t)
#         t.start()


    def buildTocList(self, docPage, threadstop=Utilities.DUMBTHREADSTOP):
        """
        Build toc list and put data in self.tocList. Finally call applyTocList()
        to show data.
        """
        try:
#             sleep(0.3)   # Make configurable?
#             threadstop.testValidThread()

            if docPage is not None and not isinstance(docPage, FunctionalPage):
                versionOverview = docPage.getVersionOverview()
                threadstop.testValidThread()
                self.setVersionOverview(versionOverview)

                Utilities.callInMainThread(self.applyTocList)
                return

            threadstop.testValidThread()
            self.setVersionOverview(None)
            self.applyTocList()

        except NotCurrentThreadException:
            return
        except VersioningException as ve:
            self.setVersionOverview(None)
            self.applyTocList(str(ve))



    def applyTocList(self, message=None):
        """
        Show the content of self.tocList in the ListCtrl
        """
        if message is None:
            message = "<" + _("Current") + ">"
        else:
            message = "<" + message + ">"

        formatStr = self.mainControl.getConfig().get("main",
                "versioning_dateFormat", "%Y %m %d")

        selected = -1
        
        currVn = self.getCurrentVersionNumber()

        self.Freeze()
        try:
            self.DeleteAllItems()
            for entry in self.versionEntries:
                text = entry.getFormattedCreationDate(formatStr)
                if entry.versionNumber == currVn:
                    selected = self.GetItemCount()

                self.InsertItem(self.GetItemCount(), text)

            if selected == -1 and currVn == 0:
                selected = self.GetItemCount()

            self.InsertItem(self.GetItemCount(), message)
#             self.SetColumnWidth(0, wx.LIST_AUTOSIZE)
            self.autosizeColumn(0)
            self.SelectSingle(selected, scrollVisible=True)
            
#             self.checkSelectionChanged(callAlways=True)
        finally:
            self.Thaw()


#     def OnKillFocus(self, evt):
#         self.SelectSingle(-1)
#         evt.Skip()



#     def displayInSubcontrol(self, start):   # , focusToSubctrl
#         """
#         Display title in subcontrol of current presenter which
#         starts at char position  start  in page text.
# 
#         focusToSubctrl -- True iff subcontrol should become focused after
#                 displaying is done
#         """
# 
#         presenter = self.mainControl.getCurrentDocPagePresenter()
#         if presenter is None:
#             return
# 
#         # Find out which subcontrol is currently active
#         scName = presenter.getCurrentSubControlName()
#         subCtrl = presenter.getSubControl(scName)
#         
#         if scName == "textedit":
#             # Text editor is active
#             subCtrl.gotoCharPos(start)
#         elif scName == "preview": 
#             # HTML preview
#             subCtrl.gotoAnchor(u".h%i" % start)
            


    def OnItemSelected(self, evt):
        if self.ignoreOnChange:
            return

    def getCurrentVersionNumber(self):
        """
        Return version number shown in current presenter.
        """
        presenter = self.mainControl.getCurrentDocPagePresenter()
        if presenter is None:
            return 0
        
        docPage = presenter.getDocPage()
        
        if docPage is None:
            return 0
        
        if not isinstance(docPage, WikiPageSnapshot):
            return 0
        
        return docPage.getSnapshotVersionNumber()



    def OnItemActivated(self, evt):
        if self.activationMode == self._ACTIVATION_MODE_NORMAL:
            self._itemActivatedOnWikiPage(evt)
        else:
            self._itemActivatedOnDiffCtrl(evt)

        
        
        
    def _itemActivatedOnWikiPage(self, evt):
        presenter = self.mainControl.getCurrentDocPagePresenter()
        if presenter is None:
            return

        docPage = presenter.getDocPage()

        if docPage is None:
            return

        if evt.GetIndex() >= len(self.versionEntries):
            # "<Current>" selected
            if isinstance(docPage, WikiPageSnapshot):
                presenter.openWikiPage(docPage.getWikiWord(), addToHistory=False,
                        forceReopen=True)

                subCtrl = presenter.getCurrentSubControl()
                subCtrl.SetFocus()

            return

        versionNo = self.versionEntries[evt.GetIndex()].versionNumber
        
        if isinstance(docPage, WikiPageSnapshot):
            docPage = docPage.getSnapshotBaseDocPage()

        snapshotPage = WikiPageSnapshot(presenter.getWikiDocument(), docPage,
                versionNo)
                
        presenter.loadWikiPage(snapshotPage)

        subCtrl = presenter.getCurrentSubControl()
        subCtrl.SetFocus()
        # wx.CallAfter(presenter.SetFocus)




    def _itemActivatedOnDiffCtrl(self, evt):
        """
        Called when content of active diff control should be changed
        """
        selIdx = evt.GetIndex()

        subCtrl = self.mainControl.getMainAreaPanel().getCurrentSubControl()
        if not isinstance(subCtrl, InlineDiffControl):
            return

        baseDocPage = subCtrl.getBaseDocPage()

        if baseDocPage is None:
            return

        if self.activationMode == self._ACTIVATION_MODE_SET_FROM:
            text, verNo = self._getTextAndVersionNoStringBySelection(selIdx,
                    baseDocPage)
            
            subCtrl.showDiffsNewFrom(baseDocPage, text, verNo)
        elif self.activationMode == self._ACTIVATION_MODE_SET_TO:
            text, verNo = self._getTextAndVersionNoStringBySelection(selIdx,
                    baseDocPage)
            
            subCtrl.showDiffsNewTo(baseDocPage, text, verNo)
        else:  # self.activationMode == _ACTIVATION_MODE_FROM_PREV_TO_THIS
            toText, toVerNo = self._getTextAndVersionNoStringBySelection(
                    selIdx, baseDocPage)
            
            if selIdx == 0:
                # We can't go one entry back, so compare first entry with itself
                
                fromText = toText
                fromVerNo = toVerNo
            else:
                
                fromText, fromVerNo = self._getTextAndVersionNoStringBySelection(
                        selIdx - 1, baseDocPage)

            subCtrl.showDiffs(baseDocPage, fromText, toText, fromVerNo, toVerNo)





# Context menu on versioning tab
_CONTEXT_MENU_VERSIONING_TAB = \
"""
Add version;CMD_VERSIONING_ADD_VERSION;Add a new version
Delete all versions;CMD_VERSIONING_DELETE_ALL_VERSION_DATA;Delete all versions of current page
"""


# Diff part on context menu if wiki page is currently active
_CONTEXT_MENU_DIFF_ON_WIKI_PAGE = \
"""
Diff inline;CMD_VERSIONING_DIFF_INLINE;Show the difference between two versions inline
"""

# Diff part on context menu if a diff control is already active
_CONTEXT_MENU_DIFF_ON_DIFF_CTRL = \
"""
Set diff from;CMD_VERSIONING_DIFF_SET_FROM;Set the "from" version in diff
Set diff to;CMD_VERSIONING_DIFF_SET_TO;Set the "to" version in diff
"""


# Context menu on versioning entry (except "<Current>")
_CONTEXT_MENU_VERSIONING_ITEM = \
"""
-
Delete version;CMD_VERSIONING_DELETE_VERSION;Delete selected version
Add version;CMD_VERSIONING_ADD_VERSION;Add a new version
Delete all versions;CMD_VERSIONING_DELETE_ALL_VERSION_DATA;Delete all versions of current page
"""

# Context menu on versioning entry "<Current>"
_CONTEXT_MENU_VERSIONING_CURRENT_ITEM = \
"""
-
Add version;CMD_VERSIONING_ADD_VERSION;Add a new version
Delete all versions;CMD_VERSIONING_DELETE_ALL_VERSION_DATA;Delete all versions of current page
"""







# Entries to support i18n of context menus
if not True:
    N_("Diff inline")
    N_("Show the difference between two versions inline")

    N_("Set diff from")
    N_('Set the "from" version in diff')
    N_("Set diff to")
    N_('Set the "to" version in diff')

    N_("Delete version")
    N_("Delete selected version")

    N_("Add version")
    N_("Add a new version")
    N_("Delete all versions")
    N_("Delete all versions of current page")



