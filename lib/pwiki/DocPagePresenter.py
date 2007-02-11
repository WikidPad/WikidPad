## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback

import wx

from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID

from MiscEvent import MiscEventSourceMixin  # , KeyFunctionSink
import DocPages

from StringOps import uniToGui

# import Exporters


class LayeredControlPresenter(MiscEventSourceMixin):
    """
    Controls appearance of multiple controls laying over each other in
    one panel or notebook.
    """
    def __init__(self, mainControl):
        self.mainControl = mainControl
        self.subControls = [None] * len(
                self.mainControl.getPagePresenterControlNames())
        self.lastVisibleIdx = 0
        self.visible = False
        self.shortTitle = ""
        self.longTitle = ""

        self.mainControl.getMiscEvent().addListener(self)

    def getMainControl(self):
        return self.mainControl

    def setSubControl(self, scName, sc):
        try:
            idx = self.mainControl.getPagePresenterControlNames().index(scName)
            self.subControls[idx] = sc
        except ValueError:
            traceback.print_exc()
            
    def getSubControl(self, scName):
        try:
            idx = self.mainControl.getPagePresenterControlNames().index(scName)
            return self.subControls[idx]
        except ValueError:
            traceback.print_exc()
            return None


    def switchSubControl(self, scName):
        """
        Make the chosen subcontrol visible, all other invisible
        """
        try:
            idx = self.mainControl.getPagePresenterControlNames().index(scName)

            if self.visible:
                # First show subControl scName, then hide the others
                # to avoid flicker
                self.subControls[idx].setVisible(True)
                for i in xrange(len(self.subControls)):
                    if i != idx:
                        self.subControls[i].setVisible(False)

            self.lastVisibleIdx = idx
            self.setTitle(self.shortTitle)

        except ValueError:
            traceback.print_exc()
            
    def getCurrentSubControlName(self):
        if self.lastVisibleIdx == -1:
            return None

        return self.mainControl.getPagePresenterControlNames()[
                self.lastVisibleIdx]
        
            


    def isCurrent(self):
        return self.getMainControl().getCurrentDocPagePresenter() is self
    
    def makeCurrent(self):
        self.mainControl.getMainAreaPanel().setCurrentDocPagePresenter(self)


    def setVisible(self, vis):
        if self.visible == vis:
            return
        
        if vis:
            for i in xrange(len(self.subControls)):
                self.subControls[i].setVisible(i == self.lastVisibleIdx)
        else:
            for i in xrange(len(self.subControls)):
                self.subControls[i].setVisible(False)

        self.visible = vis
        
    def close(self):
        for i in xrange(len(self.subControls)):
            self.subControls[i].close()
#             self.subControls[i].Destroy()

        self.mainControl.getMiscEvent().removeListener(self)

        
    def SetFocus(self):
        self.subControls[self.lastVisibleIdx].SetFocus()
        
#     def setSubFocus(self):
#         """
#         Setfocus for currently active subcontrol
#         """
#         self.subControls[self.lastVisibleIdx].SetFocus()

    # TODO getPageAst


    def setTitle(self, shortTitle):
        self.shortTitle = shortTitle
        self.longTitle = shortTitle
        self.fireMiscEventProps({"changed presenter title": True})

    def getShortTitle(self):
        return self.shortTitle

    def getLongTitle(self):
        return self.longTitle



class BasicDocPagePresenter(LayeredControlPresenter):
    """
    Controls the group of all widgets (subcontrols) used to present/edit 
    a particular doc page, currently only WikiTxtCtrl and WikiHtmlView.
    This version isn't itself a wx panel and is mainly thought for
    controlling e.g. a notebook which has the actual subcontrols as
    children
    """

    def getConfig(self):
        return self.getMainControl().getConfig()

    def getDefaultFontFaces(self):
        return self.getMainControl().presentationExt.faces

    def getWikiDocument(self):
        return self.getMainControl().getWikiDocument()
        
    def getFormatting(self):
        return self.getWikiDocument().getFormatting()
    
    def SetStatusText(self, text, field):
            self.getStatusBar().SetStatusText(uniToGui(text), field)
    
    # TODO move doc page into PagePresenter
    def getDocPage(self):
        return self.getSubControl("textedit").getLoadedDocPage()
    
    def getWikiWord(self):
        docPage = self.getDocPage()
        if docPage is None or not isinstance(docPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            return None
        return docPage.getWikiWord()

    def getLiveText(self):
        return self.getSubControl("textedit").GetText()
        
        
    def informLiveTextChanged(self, changer):
        self.fireMiscEventProps({"changed live text": True, "changer": changer})


    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        if miscevt.getSource() is self.getMainControl():
            # TODO? Check if mainControl's current presenter is this one
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

        p2 = evtprops.copy()
        p2.update({"loaded current functional page": True})
        # p2.update({"loaded current page": True})
        self.fireMiscEventProps(p2)        


    def openWikiPage(self, wikiWord, addToHistory=True,
            forceTreeSyncFromRoot=False, forceReopen=False, **evtprops):
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
                        createWikiPage(wikiWord)
                # trigger hooks
                self.getMainControl().hooks.newWikiWord(self, wikiWord)
                self.getStatusBar().SetStatusText(uniToGui(u"Wiki page not found, a new "
                        u"page will be created"), 0)
                self.getStatusBar().SetStatusText(uniToGui(u""), 1)
    
            self.getSubControl("textedit").loadWikiPage(page, evtprops)
            self.getMainControl().refreshPageStatus()  # page)
    
            p2 = evtprops.copy()
            p2.update({"loaded current page": True,
                    "loaded current wiki page": True})
            self.fireMiscEventProps(p2)
    
            # set the title and add the word to the history
#             self.SetTitle(uniToGui(u"Wiki: %s - %s" %
#                     (self.getWikiConfigPath(), self.getCurrentWikiWord())))   # TODO Handle by mainControl
    
            self.getMainControl().getConfig().set("main", "last_wiki_word",
                    wikiWord)
    
            # sync the tree
            if forceTreeSyncFromRoot:
                self.getMainControl().findCurrentWordInTree()  # TODO ?
        except (IOError, OSError, DbAccessError), e:
            self.getMainControl().lostAccess(e)
            raise

        # trigger hook
        self.getMainControl().hooks.openedWikiWord(self, wikiWord)


    # TODO 
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
            idx = self.mainControl.getPagePresenterControlNames().index(scName)

            # First show subControl scName, then hide the others
            # to avoid flicker
            if self.visible:
                self.subControls[idx].setVisible(True)
            self.subControls[idx].Show(True)

            for i in xrange(len(self.subControls)):
                if i != idx:
                    if self.visible:
                        self.subControls[i].setVisible(False)
                    self.subControls[i].Show(False)

            if gainFocus:
                self.subControls[idx].SetFocus()

            self.lastVisibleIdx = idx
        except ValueError:
            traceback.print_exc()


