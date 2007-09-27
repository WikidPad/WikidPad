## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback

import wx

from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID

from MiscEvent import MiscEventSourceMixin  # , KeyFunctionSink
import DocPages

from StringOps import uniToGui

from WindowLayout import LayeredControlPresenter


class BasicDocPagePresenter(LayeredControlPresenter, MiscEventSourceMixin):
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

        self.getMainControl().getMiscEvent().addListener(self)


    def getMainControl(self):
        return self.mainControl

    def getConfig(self):
        return self.getMainControl().getConfig()

    def getDefaultFontFaces(self):
        return self.getMainControl().presentationExt.faces

    def getWikiDocument(self):
        return self.getMainControl().getWikiDocument()

    def getActiveEditor(self):
        """
        For compatibility with older scripts.
        """
        return self.getSubControl("textedit")

    def getFormatting(self):
        return self.getWikiDocument().getFormatting()

    def SetStatusText(self, text, field):
            self.getStatusBar().SetStatusText(uniToGui(text), field)

    def isCurrent(self):
        return self.getMainControl().getCurrentDocPagePresenter() is self
    
    def makeCurrent(self):
        self.mainControl.getMainAreaPanel().setCurrentDocPagePresenter(self)

    def setTitle(self, shortTitle):
        LayeredControlPresenter.setTitle(self, shortTitle)
        self.fireMiscEventProps({"changed presenter title": True})
        
    def close(self):
        LayeredControlPresenter.close(self)
        self.getMainControl().getMiscEvent().removeListener(self)


    # TODO move doc page into PagePresenter
    def getDocPage(self):
        return self.docPage
#         return self.getSubControl("textedit").getLoadedDocPage()


    def setDocPage(self, dp):
        if self.docPage is not None:
            self.docPage.getMiscEvent().removeListener(self)

        self.docPage = dp

        if self.docPage is not None:
            self.docPage.getMiscEvent().addListener(self)


    def getWikiWord(self):
        docPage = self.getDocPage()
        if docPage is None or not isinstance(docPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            return None
        return docPage.getWikiWord()

    def getLiveText(self):
        docPage = self.getDocPage()
        if docPage is None:
            return None
        
        return docPage.getLiveText()
        
        # return self.getSubControl("textedit").GetText()


    def informLiveTextChanged(self, changer):
        """
        Called by the txt editor control
        """
        if self.getDocPage() is not None:
            self.getDocPage().informLiveTextChanged(changer)
#         self.fireMiscEventProps({"changed live text": True, "changer": changer})


    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        if miscevt.getSource() is self.getMainControl():
            # TODO? Check if mainControl's current presenter is this one
            self.fireMiscEventProps(miscevt.getProps())

        elif miscevt.getSource() is self.docPage:
            if miscevt.has_key("changed live text"):
                self.fireMiscEventProps(miscevt.getProps())


    def getStatusBar(self):
        return self.getMainControl().GetStatusBar()


    def openFuncPage(self, funcTag, **evtprops):
        if not self.getMainControl().requireReadAccess():
            return

        try:
            page = self.getMainControl().getWikiDataManager().getFuncPage(funcTag)
    
            self.getSubControl("textedit").loadFuncPage(page, evtprops)
        except (IOError, OSError, DbAccessError), e:
            self.getMainControl().lostAccess(e)
            raise
            
        self.switchSubControl("textedit")

        p2 = evtprops.copy()
        p2.update({"loaded current doc page": True,
                "loaded current functional page": True})
        # p2.update({"loaded current page": True})
        self.fireMiscEventProps(p2)        


    def openWikiPage(self, wikiWord, addToHistory=True,
            forceTreeSyncFromRoot=False, forceReopen=False,
            suggNewPageTitle=None, **evtprops):
        """
        Opens a wiki page in the editor of this presenter
        """
        if not self.getMainControl().requireReadAccess():
            return

        evtprops["addToHistory"] = addToHistory
        evtprops["forceTreeSyncFromRoot"] = forceTreeSyncFromRoot

#         self.statusBar.SetStatusText(uniToGui(u"Opening wiki word '%s'" %
#                 wikiWord), 0)

        # make sure this is a valid wiki word
        if not self.getMainControl().getFormatting().isNakedWikiWord(wikiWord):
            self.getMainControl().displayErrorMessage(
                    u"'%s' is an invalid wiki word." % wikiWord)
            return

        try:
            # don't reopen the currently open page, only send an event
            if (wikiWord == self.getWikiWord()) and not forceReopen:
                p2 = evtprops.copy()
                p2.update({"reloaded current page": True,
                        "reloaded current wiki page": True})
                self.fireMiscEventProps(p2)
    #             # self.tree.buildTreeForWord(self.currentWikiWord)  # TODO Needed?
    #             self.statusBar.SetStatusText(uniToGui(u"Wiki word '%s' already open" %
    #                     wikiWord), 0)
                return

            # trigger hook
            self.getMainControl().hooks.openWikiWord(self, wikiWord)

            # check if this is an alias
            wikiData = self.getMainControl().getWikiData()
            if (wikiData.isAlias(wikiWord)):
                wikiWord = wikiData.getAliasesWikiWord(wikiWord)

            # fetch the page info from the database
            try:
                page = self.getMainControl().getWikiDataManager().getWikiPage(wikiWord)
                self.getStatusBar().SetStatusText(uniToGui(u"Opened wiki word '%s'" %
                        wikiWord), 0)

            except (WikiWordNotFoundException, WikiFileNotFoundException), e:
                page = self.getMainControl().getWikiDataManager().\
                        createWikiPage(wikiWord,
                        suggNewPageTitle=suggNewPageTitle)
                # trigger hooks
                self.getMainControl().hooks.newWikiWord(self, wikiWord)
                self.getStatusBar().SetStatusText(uniToGui(u"Wiki page not found, a new "
                        u"page will be created"), 0)
                self.getStatusBar().SetStatusText(uniToGui(u""), 1)

            self.getSubControl("textedit").loadWikiPage(page, evtprops)
            self.getMainControl().refreshPageStatus()  # page)
    
            p2 = evtprops.copy()
            p2.update({"loaded current doc page": True,
                    "loaded current wiki page": True})
            self.fireMiscEventProps(p2)
    
#             self.getMainControl().getConfig().set("main", "last_wiki_word",
#                     wikiWord)

            self.getMainControl().getMainAreaPanel().updateConfig()

            # Should the page by default be presented in editor or preview mode?
            pv = page.getPropertyOrGlobal(u"view_pane")
            if pv is not None:
                pv = pv.lower()
                if pv == u"preview":
                    self.switchSubControl("preview")
                elif pv == u"editor":
                    self.switchSubControl("textedit")
                # else: do nothing  (pv == u"off")

            # sync the tree
            if forceTreeSyncFromRoot:
                self.getMainControl().findCurrentWordInTree()  # TODO ?
        except (IOError, OSError, DbAccessError), e:
            self.getMainControl().lostAccess(e)
            raise

        # trigger hook
        self.getMainControl().hooks.openedWikiWord(self, wikiWord)


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
        self.mainControl.stdDialog(dlgtype, title, message, additional)


    def displayMessage(self, title, str):
        """pops up a dialog box,
        used by scripts only
        """
        self.mainControl.displayMessage(title, str)


    def displayErrorMessage(self, errorStr, e=u""):
        self.mainControl.displayErrorMessage(errorStr, e)


class DocPagePresenter(wx.Panel, BasicDocPagePresenter):
    """
    Controls the group of all widgets (subcontrols) used to present/edit 
    a particular doc page, currently only WikiTxtCtrl and WikiHtmlView.
    This version is a panel and contains the children itself.
    """
    def __init__(self, parent, mainControl, id=-1):
        wx.Panel.__init__(self, parent, id)
        BasicDocPagePresenter.__init__(self, mainControl)


    def switchSubControl(self, scName, gainFocus=False):
        """
        Make the chosen subcontrol visible, all other invisible
        """
        try:
            # First show subControl scName, then hide the others
            # to avoid flicker
            if self.visible and self.lastVisibleCtrlName != scName:
                self.subControls[scName].setVisible(True)
            
            self.subControls[scName].Show(True)

            for n, c in self.subControls.iteritems():
                if n != scName:
                    if self.visible:
                        c.setVisible(False)
                    c.Show(False)

            if gainFocus:
                self.subControls[scName].SetFocus()

            self.lastVisibleCtrlName = scName
            self.setTitle(self.shortTitle)   #?
        except KeyError:
            traceback.print_exc()

    def SetFocus(self):
        try:
            self.subControls[self.lastVisibleCtrlName].SetFocus()
        except KeyError:
            wx.Panel.SetFocus(self)




