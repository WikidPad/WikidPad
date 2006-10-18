## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback

# from wxPython.wx import *
# from wxPython.html import *


from WikiExceptions import *
from wxHelper import getAccelPairFromKeyDown, copyTextToClipboard, GUI_ID

from MiscEvent import MiscEventSourceMixin  # , KeyFunctionSink

from StringOps import uniToGui

# import Exporters



class DocPagePresenter(MiscEventSourceMixin):
    """
    Controls the group of all widgets (subcontrols) used to present/edit 
    a particular doc page, currently only WikiTxtCtrl and WikiHtmlView
    """
    def __init__(self, mainControl):
        self.mainControl = mainControl
        self.subControls = [None] * len(
                self.mainControl.getPagePresenterControlNames())
        self.lastVisibleIdx = 0
        self.visible = False

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
                for i in xrange(len(self.subControls)):
                    self.subControls[i].setVisible(i == idx)
            
            self.lastVisibleIdx = idx
        except ValueError:
            traceback.print_exc()



    # TODO !!!
    def isCurrent(self):
        return True
    
    def makeCurrent(self):
        self.mainControl.setCurrentDocPagePresenter(self)


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


    def getConfig(self):
        return self.getMainControl().getConfig()

    def getDefaultFontFaces(self):
        return self.getMainControl().presentationExt.faces

    def getWikiDocument(self):
        return self.getMainControl().getWikiDocument()
        
    def getFormatting(self):
        return self.getWikiDocument().getFormatting()
    
    def SetStatusText(self, text, field):
            self.getMainControl().statusBar.SetStatusText(uniToGui(text), field)
    
    # TODO move doc page into PagePresenter
    def getDocPage(self):
        return self.getSubControl("textedit").getLoadedDocPage()
    
    def getLiveText(self):
        return self.getSubControl("textedit").GetText()
        
        
    def informLiveTextChanged(self, changer):
        self.fireMiscEventProps({"changed live text": True, "changer": changer})


    # TODO getPageAst



    def miscEventHappened(self, miscevt):
        """
        Handle misc events from DocPages
        """
        if miscevt.getSource() is self.mainControl:
            # TODO!!! Check if mainControl's current presenter is this one
            self.fireMiscEventProps(miscevt.getProps())

    



