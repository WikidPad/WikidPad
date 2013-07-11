## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback

import wx
import wx.xrc as xrc


from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID

from .MiscEvent import ProxyMiscEvent  # , KeyFunctionSink
from .WikiHtmlView import createWikiHtmlView
from . import DocPages

from . import SystemInfo
from .StringOps import uniToGui, escapeForIni, unescapeForIni

from .WindowLayout import LayeredControlPresenter, LayerSizer, StorablePerspective

from .PageHistory import PageHistory



class BasicDocPagePresenter(LayeredControlPresenter):
    """
    Controls the group of all widgets (subcontrols) used to present/edit 
    a particular doc page, currently only the WikiTxtCtrl (subcontrol name
    "textedit") and WikiHtmlView or WikiHtmlViewIE (name "preview").
    This version isn't itself a wx panel and is mainly thought for
    controlling e.g. a notebook which has the actual subcontrols as
    children
    """

    def __init__(self, mainControl):
        LayeredControlPresenter.__init__(self)
        self.mainControl = mainControl
        self.docPage = None

        self.currentDocPageProxyEvent = ProxyMiscEvent(self)
        self.currentDocPageProxyEvent.addListener(self)

        # Connect page history
        self.pageHistory = PageHistory(self.getMainControl(), self)
        
        self.getMainControl().getMiscEvent().addListener(self)


    def getMainControl(self):
        return self.mainControl

    def getConfig(self):
        return self.getMainControl().getConfig()

    def getDefaultFontFaces(self):
        return self.getMainControl().presentationExt.faces

    def getWikiDocument(self):
        return self.getMainControl().getWikiDocument()
        
    def getPageHistory(self):
        return self.pageHistory


    def getActiveEditor(self):
        """
        For compatibility with older scripts.
        """
        return self.getSubControl("textedit")

    def SetStatusText(self, text, field):
        self.getStatusBar().SetStatusText(uniToGui(text), field)

    def showStatusMessage(self, msg, duration=0, key=None):
        self.getMainControl().showStatusMessage(msg, duration, key)


    def isCurrent(self):
        return self.getMainControl().getCurrentDocPagePresenter() is self
    
    def makeCurrent(self):
        self.mainControl.getMainAreaPanel().prepareCurrentPresenter(self)

    def close(self):
        LayeredControlPresenter.close(self)
        self.getMainControl().getMiscEvent().removeListener(self)
        self.pageHistory.close()
        self.setDocPage(None)  # TODO: Was commented out?


    def getDocPage(self):
        return self.docPage


    def setDocPage(self, dp):
        self.docPage = dp
        self.currentDocPageProxyEvent.setWatchedSource(dp)


    def getCurrentDocPageProxyEvent(self):
        """
        This ProxyMiscEvent resends any messsages from the currently
        active DocPage
        """
        return self.currentDocPageProxyEvent


    def getWikiWord(self):
        docPage = self.getDocPage()
        if docPage is None or not isinstance(docPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            return None
        return docPage.getWikiWord()


    def getUnifiedPageName(self):
        docPage = self.getDocPage()
        if docPage is None:
            return None
        
        return docPage.getUnifiedPageName()
        

    def getLiveText(self):
        docPage = self.getDocPage()
        if docPage is None:
            return None
        
        return docPage.getLiveText()


    def informEditorTextChanged(self, changer):
        """
        Called by the txt editor control
        """
        if self.getDocPage() is not None:
            self.getDocPage().informEditorTextChanged(changer)

        self.fireMiscEventProps({"changed editor text": True,
                "changed live text": True, "changer": changer})


    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        if miscevt.getSource() is self.getMainControl():
            # TODO? Check if mainControl's current presenter is this one
            self.fireMiscEventProps(miscevt.getProps())

        elif miscevt.getSource() is self.docPage:
#             if miscevt.has_key("changed editor text"):
#                 self.fireMiscEventProps(miscevt.getProps())
#             elif miscevt.has_key("deleted page"):
#                 self.pageHistory.goAfterDeletion()
            if miscevt.has_key("renamed wiki page"):
#                 oldWord = self.docPage.getWikiWord()
                newWord = miscevt.get("newWord")

                self.getSubControl("textedit").loadWikiPage(None)
                self.openWikiPage(newWord, forceTreeSyncFromRoot=False)


    def getStatusBar(self):
        return self.getMainControl().GetStatusBar()


    def openDocPage(self, unifiedPageName, *args, **kwargs):
        """
        Open a doc page identified by its unified page name
        """
        if len(unifiedPageName) == 0:
            return
        
        if unifiedPageName.startswith(u"wikipage/"):
            self.openWikiPage(unifiedPageName[9:], *args, **kwargs)
        else:
            self.openFuncPage(unifiedPageName, *args, **kwargs)


    def openFuncPage(self, funcTag, addToHistory=True, **evtprops):
        if not self.getMainControl().requireReadAccess():
            return
            
        oldPage = self.getDocPage()

        evtprops["addToHistory"] = addToHistory
        try:
            page = self.getMainControl().getWikiDocument().getFuncPage(funcTag)
    
            self.getSubControl("textedit").loadFuncPage(page, evtprops)
        except (IOError, OSError, DbAccessError), e:
            self.getMainControl().lostAccess(e)
            raise
            
        self.switchSubControl("textedit")

        p2 = evtprops.copy()
        p2.update({"loaded current doc page": True,
                "loaded current functional page": True,
                "docPage": page,
                "oldDocPage": oldPage})
        # p2.update({"loaded current page": True})
        self.fireMiscEventProps(p2)
        page.informVisited()


    def openWikiPage(self, wikiWord, addToHistory=True,
            forceTreeSyncFromRoot=False, forceReopen=False,
            suggNewPageTitle=None, **evtprops):
        """
        Opens a wiki page in the editor of this presenter
        """
        if not self.getMainControl().requireReadAccess():
            return

#         oldPage = self.getDocPage()

        evtprops["addToHistory"] = addToHistory
        evtprops["forceTreeSyncFromRoot"] = forceTreeSyncFromRoot

        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.getWikiDocument().getWikiDefaultWikiLanguage())

        errMsg = None

        # The "if" ensures that existing pages can be opened even
        # if the syntax is (or became) incompatible
        if not self.getWikiDocument().isDefinedWikiPageName(wikiWord):
            errMsg = langHelper.checkForInvalidWikiWord(wikiWord,
                    self.getWikiDocument())

        if errMsg is not None:
            self.getMainControl().displayErrorMessage(
                    _(u"'%s' is an invalid wiki word. %s.") % (wikiWord, errMsg))
            return
            
        try:
            # don't reopen the currently open page, only send an event
            if (wikiWord == self.getWikiWord()) and not forceReopen:
                p2 = evtprops.copy()
                p2.update({"reloaded current doc page": True,
                        "reloaded current wiki page": True})
                self.fireMiscEventProps(p2)

                if forceTreeSyncFromRoot:
                    self.getMainControl().findCurrentWordInTree()
                return

            # trigger hook
            self.getMainControl().hooks.openWikiWord(self, wikiWord)

            # check if this is an alias
            wikiDoc = self.getMainControl().getWikiDocument()
            wikiWord = wikiDoc.getWikiPageNameForLinkTermOrAsIs(wikiWord)

            # fetch the page info from the database
            try:
                page = wikiDoc.getWikiPage(wikiWord)
#                 self.getStatusBar().SetStatusText(uniToGui(_(u"Opened wiki word '%s'") %
#                         wikiWord), 0)

            except (WikiWordNotFoundException, WikiFileNotFoundException), e:
                page = wikiDoc.createWikiPage(wikiWord,
                        suggNewPageTitle=suggNewPageTitle)
                # trigger hooks
                self.getMainControl().hooks.newWikiWord(self, wikiWord)
                self.showStatusMessage(
                        uniToGui(_(u"Wiki page not found, a new "
                        u"page will be created")))
#                 self.getStatusBar().SetStatusText(uniToGui(u""), 1)

            self.loadWikiPage(page, **evtprops)
            page.informVisited()

            # sync the tree
            if forceTreeSyncFromRoot:
                self.getMainControl().findCurrentWordInTree()  # TODO ?
        except (IOError, OSError, DbAccessError), e:
            self.getMainControl().lostAccess(e)
            raise

        # trigger hook
        self.getMainControl().hooks.openedWikiWord(self, wikiWord)


    def loadWikiPage(self, page, **evtprops):
        oldPage = self.getDocPage()  # TODO Test if too late to retrieve old page here

        self.getSubControl("textedit").loadWikiPage(page, evtprops)
        self.getMainControl().refreshPageStatus()  # page)

        p2 = evtprops.copy()
        p2.update({"loaded current doc page": True,
                "loaded current wiki page": True,
                "docPage": page,
                "oldDocPage": oldPage})

        self.fireMiscEventProps(p2)

        self.getMainControl().getMainAreaPanel().updateConfig()

        # Should the page by default be presented in editor or preview mode?
        pv = page.getAttributeOrGlobal(u"view_pane")
        if pv is not None:
            pv = pv.lower()
            if pv == u"preview":
                self.switchSubControl("preview")
            elif pv == u"editor":
                self.switchSubControl("textedit")
            # else: do nothing  (pv == u"off")


    def saveCurrentDocPage(self, force = False):
        ## _prof.start()

        if (force or self.getDocPage().getDirty()[0]) and \
                self.getMainControl().requireWriteAccess():
            # Reset error flag here, it can be set true again by saveDocPage
#             self.getWikiDocument().setNoAutoSaveFlag(False)
            try:
                # this calls in turn saveDocPage() in PersonalWikiFrame
                self.getSubControl("textedit").saveLoadedDocPage()
            except (IOError, OSError, DbAccessError), e:
                self.getMainControl().lostAccess(e)
                raise

        self.getMainControl().refreshPageStatus()

        ## _prof.stop()
        
        
    def stdDialog(self, dlgtype, title, message, additional=None):
        """
        Show message dialogs, used for scripts.
        Calls same function from PersonalWikiFrame.
        """
        return self.mainControl.stdDialog(dlgtype, title, message, additional)


    def displayMessage(self, title, str):
        """pops up a dialog box,
        used by scripts only
        """
        self.mainControl.displayMessage(title, str)


    def displayErrorMessage(self, errorStr, e=u""):
        self.mainControl.displayErrorMessage(errorStr, e)


class DocPagePresenter(wx.Panel, BasicDocPagePresenter, StorablePerspective):
    """
    Controls the group of all widgets (subcontrols) used to present/edit 
    a particular doc page, currently only WikiTxtCtrl and WikiHtmlView.
    This version is a panel and contains the children itself.
    """
    def __init__(self, parent, mainControl, id=-1):
        wx.Panel.__init__(self, parent, id)
        BasicDocPagePresenter.__init__(self, mainControl)
        self.SetSizer(LayerSizer())

        res = xrc.XmlResource.Get()
        self.tabContextMenu = res.LoadMenu("MenuDocPagePresenterTabPopup")

        self.mainTreePositionHint = None  # The tree ctrl uses this to remember
        # which element was selected if same page appears multiple
        # times in tree. DocPagePresenter class itself does not modify it.

        wx.GetApp().getMiscEvent().addListener(self)

        wx.EVT_MENU(self, GUI_ID.CMD_PAGE_HISTORY_LIST,
                lambda evt: self.viewPageHistory())
        wx.EVT_MENU(self, GUI_ID.CMD_PAGE_HISTORY_LIST_UP,
                lambda evt: self.viewPageHistory(-1))
        wx.EVT_MENU(self, GUI_ID.CMD_PAGE_HISTORY_LIST_DOWN,
                lambda evt: self.viewPageHistory(1))
        wx.EVT_MENU(self, GUI_ID.CMD_PAGE_HISTORY_GO_BACK,
                lambda evt: self.pageHistory.goInHistory(-1))
        wx.EVT_MENU(self, GUI_ID.CMD_PAGE_HISTORY_GO_FORWARD,
                lambda evt: self.pageHistory.goInHistory(1))
        wx.EVT_MENU(self, GUI_ID.CMD_PAGE_GO_UPWARD_FROM_SUBPAGE,
                lambda evt: self.goUpwardFromSubpage())


    def close(self):
        wx.GetApp().getMiscEvent().removeListener(self)
        BasicDocPagePresenter.close(self)


    def setSubControl(self, scName, sc):
        oldSc = self.getSubControl(scName)
        if oldSc is not None:
            self.GetSizer().Detach(oldSc)
            oldSc.close()

        BasicDocPagePresenter.setSubControl(self, scName, sc)
        if sc is not None:
            self.GetSizer().Add(sc)
            self.Layout()

    def switchSubControl(self, scName, gainFocus=False):
        """
        Make the chosen subcontrol visible, all other invisible
        """
        try:
            subControl = self.subControls[scName]
        except KeyError:
            traceback.print_exc()
            return

        # First show subControl scName, then hide the others
        # to avoid flicker
        if self.visible and self.lastVisibleCtrlName != scName:
            subControl.setLayerVisible(True)

        subControl.Show(True)

        if gainFocus:
            subControl.SetFocus()

        for n, c in self.subControls.iteritems():
#             if n != scName:
            if c is not subControl:
                if self.visible:
                    c.setLayerVisible(False)
                c.Show(False)

        self.lastVisibleCtrlName = scName
        self.setTitle(self.shortTitle)   #?


    if SystemInfo.isLinux():
        def SetFocus(self):
            try:
                ctrl = self.subControls[self.lastVisibleCtrlName]
                wx.CallAfter(ctrl.SetFocus)
            except KeyError:
                wx.Panel.SetFocus(self)
    else:
        def SetFocus(self):
            try:
                self.subControls[self.lastVisibleCtrlName].SetFocus()
            except KeyError:
                wx.Panel.SetFocus(self)


    def viewPageHistory(self, posDelta=0):
        if not self.getMainControl().requireReadAccess():
            return

        try:
            hist = self.pageHistory.getHrHistoryList()
            histpos = self.pageHistory.getPosition()
        except (IOError, OSError, DbAccessError), e:
            self.getMainControl().lostAccess(e)
            raise

        historyLen = len(hist)
        dlg = wx.SingleChoiceDialog(self,
                                   _(u"History"),
                                   _(u"History"),
                                   hist,
                                   wx.CHOICEDLG_STYLE | wx.OK | wx.CANCEL)

        if historyLen > 0:
            position = histpos + posDelta - 1
            if (position < 0):
                position = 0
            elif (position >= historyLen):
                position = historyLen-1

            dlg.SetSelection(position)

        if dlg.ShowModal() == wx.ID_OK and dlg.GetSelection() > -1:
            self.pageHistory.goInHistory(dlg.GetSelection() - (histpos - 1))

        dlg.Destroy()


    def goUpwardFromSubpage(self):
        wikiWord = self.getWikiWord()
        if wikiWord is None:
            return

        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.getWikiDocument().getWikiDefaultWikiLanguage())

        wikiPath = langHelper.createWikiLinkPathObject(pageName=wikiWord)
        wikiPath.join(langHelper.createWikiLinkPathObject(upwardCount=1))
        
        upwardPageName = wikiPath.resolveWikiWord(None)
        
        if not upwardPageName or wikiWord == upwardPageName:
            # No way upward
            # TODO: Maybe alternative reaction?
            return

        # motion type "parent" isn't exactly right but a good guess
        self.openWikiPage(upwardPageName, motionType="parent")


    def getTabContextMenu(self):
        return self.tabContextMenu


    def setTitle(self, shortTitle):
        LayeredControlPresenter.setTitle(self, shortTitle)

        # Shorten title if too long
        maxLen = self.getConfig().getint("main", "tabs_maxCharacters", 0)
        if maxLen > 0 and len(shortTitle) > maxLen:
            shortTitle = shortTitle[:(maxLen//2)] + u"..." + \
                    shortTitle[-((maxLen+1)//2):]

        self.fireMiscEventProps({"changed presenter title": True,
                "title": shortTitle})


    def miscEventHappened(self, miscevt):
        if miscevt.getSource() is wx.GetApp():
            # The option "tabs_maxCharacters" may be changed, so set title again
            if miscevt.has_key("options changed"):
                self.setTitle(self.shortTitle)
                return
        
        return BasicDocPagePresenter.miscEventHappened(self, miscevt)


    def fillDefaultSubControls(self):
        self.setLayerVisible(False)
        self.Hide()

        editor = self.getMainControl().createWindow({"name": "txteditor1",
                "presenter": self}, self)
        editor.setLayerVisible(False, "textedit")
        self.setSubControl("textedit", editor)

        htmlView = createWikiHtmlView(self, self, -1)
        htmlView.setLayerVisible(False, "preview")
        self.setSubControl("preview", htmlView)

        self.switchSubControl("textedit")
    

# ----- Implementation of StorablePerspective methods -----


    @staticmethod
    def getPerspectiveType():
        return u"DocPagePresenter"
        
    def getStoredPerspective(self):
        unifName = self.getUnifiedPageName()
        if unifName is None:
            return None
        
        return escapeForIni(self.getCurrentSubControlName(), u"|") + u"|" + \
                escapeForIni(unifName, u"|")


#     def setByStoredPerspective(self, perspectType, data, typeFactory):
#         raise NotImplementedError

    def deleteForNewPerspective(self):
        self.close()
        StorablePerspective.deleteForNewPerspective(self)


    @staticmethod
    def createFromPerspective(mainControl, parent, perspectType, wndPerspective,
            typeFactory):
        """
        Not part of StorablePerspective, called by the type factory
        """
        # if more parts are available after a second '|' they are ignored
        subControl, unifName = wndPerspective.split(u"|", 2)[:2]
        
        # unescape
        subControl = unescapeForIni(subControl)
        unifName = unescapeForIni(unifName)

        wnd = DocPagePresenter(parent, mainControl)
        wnd.fillDefaultSubControls()
        wnd.openDocPage(unifName)
        wnd.switchSubControl(subControl)
        
        return wnd



