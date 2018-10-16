# from MiscEvent import KeyFunctionSink

from .DocPagePresenter import BasicDocPagePresenter


class AbstractAction:
    def __init__(self):
        pass
    
    def getShortDescription(self):
        raise NotImplementedError  # abstract

    def getLongDescription(self):
        return self.getShortDescription()

    def getActionUnifiedNames(self):
        raise NotImplementedError  # abstract

    def doAction(self, paramDict):
        raise NotImplementedError  # abstract
        
    def getEnabled(self):
        return True



class SimpleAction(AbstractAction):
    __slots__ = ("desc", "unifName", "fct", "fctParams", "fctKeyparams")

    def __init__(self, desc, unifName, fct, *fctParams, **fctKeyparams):
        self.desc = desc
        self.unifName = unifName
        self.fct = fct
        self.fctParams = fctParams
        self.fctKeyparams = fctKeyparams

    def getShortDescription(self):
        return self.desc
    
    def getActionUnifiedNames(self):
        return (self.unifName,)

    def doAction(self, unifName, paramDict):
        return self.fct(unifName, paramDict, *self.fctParams, **self.fctKeyparams)



def _presenterToTextEdit(unifName, paramDict):
    presenter = paramDict.get("presenter")
    if presenter is None:
        if paramDict.get("main control") is None:
            return
        else:
            presenter = paramDict["main control"].getCurrentDocPagePresenter()
            if presenter is None:
                return

    if not isinstance(presenter, BasicDocPagePresenter):
        return

    presenter.switchSubControl("textedit")



def _presenterToNewTextEdit(unifName, paramDict):
    docPage = paramDict.get("page")
    if docPage is None:
        return

    presenter = paramDict["main control"].activatePageByUnifiedName(
            docPage.getUnifiedPageName(), tabMode=2)
    
    if presenter is None:
        return

    presenter.switchSubControl("textedit")


def _presenterClose(unifName, paramDict):
    mc = paramDict.get("main control")
    if mc is None:
        return
        
    maPanel = mc.getMainAreaPanel()

    presenter = paramDict.get("presenter")
    if presenter is None:
        presenter = mc.getMainAreaPanel().getCurrentPresenter()
        if presenter is None:
            return
    
    maPanel.closePresenterTab(presenter)


def _presenterClone(unifName, paramDict):
    if paramDict.get("main control") is None:
        return

    presenter = paramDict.get("presenter")
    if presenter is None:
        presenter = paramDict["main control"].getCurrentDocPagePresenter()
        if presenter is None:
            return

    if not isinstance(presenter, BasicDocPagePresenter):
        return   # TODO Support cloning for general LayeredControlPresenter

    docPage = presenter.getDocPage()
    if docPage is None:
        return
    
    newPres = paramDict["main control"].activatePageByUnifiedName(docPage.getUnifiedPageName(),
                tabMode=2)

    if newPres is None:
        return

    scName = presenter.getCurrentSubControlName()

    if newPres.hasSubControl(scName):
        newPres.switchSubControl(scName)





# _ACTION_PRESENTER_TO_TEXT_EDIT = SimpleAction("",
#         u"action/presenter/this/subcontrol/textedit", _presenterToTextEdit)
# 
# _ACTION_PRESENTER_TO_NEW_TEXT_EDIT = SimpleAction("",
#         u"action/presenter/new/foreground/end/page/this/subcontrol/textedit", _presenterToNewTextEdit)
# 
# _ACTION_PRESENTER_CLOSE = SimpleAction("",
#         u"action/presenter/this/close", _presenterClose)
# 
# _ACTION_PRESENTER_CLONE = SimpleAction("",
#         u"action/presenter/this/clone", _presenterClone)



_ACTIONS = (
        SimpleAction("", "action/presenter/this/subcontrol/textedit",
            _presenterToTextEdit),
        SimpleAction("", "action/presenter/new/foreground/end/page/this/subcontrol/textedit",
            _presenterToNewTextEdit),
        SimpleAction("", "action/presenter/this/close",
            _presenterClose),
        SimpleAction("", "action/presenter/this/clone",
            _presenterClone)
    )





# _ACTION_PRESENTER_TO_TEXT_EDIT, _ACTION_PRESENTER_TO_NEW_TEXT_EDIT,
#         _ACTION_PRESENTER_CLOSE, _ACTION_PRESENTER_CLONE)



def registerActions(actions):
    global _ACTIONS
    _ACTIONS += actions




class UserActionCoord:
    """
    Executes simple actions and associates some user events like clicking with
    the mouse somewhere with an action.
    This object is bound to a PersonalWikiFrame object.
    """
    
    def __init__(self, mainControl):
        self.mainControl = mainControl
        self.userEventActionMap = {}


    USER_EVENTS_IN_CONFIG = (
            "mouse/leftdoubleclick/preview/body",
            "mouse/leftdoubleclick/pagetab",
            "mouse/middleclick/pagetab",
            "mouse/leftdrop/editor/files",
            "mouse/leftdrop/editor/files/modkeys/shift",
            "mouse/leftdrop/editor/files/modkeys/ctrl",
            "event/paste/editor/files"
            )

    def applyConfiguration(self):
        """
        Called at start and after configuration changes
        """
        config = self.mainControl.getConfig()
        
        for userEvent in self.USER_EVENTS_IN_CONFIG:
            actionUName = config.get("main", "userEvent_" + userEvent)
            self.associateAction(userEvent, actionUName)


    def associateAction(self, userEvent, actionUName):
        for action in _ACTIONS:
            if actionUName in action.getActionUnifiedNames():
                self.userEventActionMap[userEvent] = (actionUName, action)
                break
        else:
            self.userEventActionMap[userEvent] = (actionUName, None)


    def reactOnUserEvent(self, unifName, paramDict):
        actionUName, action = self.userEventActionMap.get(unifName)
        if action is not None:
            if "main control" not in paramDict:
                paramDict["main control"] = self.mainControl

            action.doAction(actionUName, paramDict)
    
    
    def runAction(self, actionUName, paramDict=None):
        if paramDict is None:
            paramDict = {"main control": self.mainControl}
        elif "main control" not in paramDict:
            paramDict["main control"] = self.mainControl

        for action in _ACTIONS:
            if actionUName in action.getActionUnifiedNames():
                action.doAction(actionUName, paramDict)
                break



