from   wxPython.wx import wxNewId
from wx.xrc import XRCCTRL, XRCID

class wxIdPool:
    def __init__(self):
        self.poolmap={}

    def __getattr__(self, name):
        """Returns a new wx-Id for each new string <name>.
 
        If the same name is given twice, the same id is returned.
        
        If the name is in the XRC id-table its value there will be returned
        """
        try:
            return XRCID(name)
        except:
            try:
                return self.poolmap[name]
            except KeyError:
                id=wxNewId()
                self.poolmap[name]=id
                return id


GUI_ID = wxIdPool()
GUI_ID.__doc__="All purpose standard Gui-Id-Pool"

 
class XrcControls:
    """
    Convenience wrapper for XRCCTRL
    """
    def __init__(self, basepanel):
        self.__basepanel = basepanel

    def __getattr__(self, name):
        return XRCCTRL(self.__basepanel, name)
        
    def __getitem__(self, name):
        return XRCCTRL(self.__basepanel, name)
    

        
