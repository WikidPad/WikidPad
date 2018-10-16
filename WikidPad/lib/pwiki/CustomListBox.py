import wx 

from .wxHelper import copyTextToClipboard

class CustomListBox(wx.ListBox):
    """
    Custom class to enable copying of listbox contents via context menu
    """
    def __init__(self, *args, **kwargs):
        """
        As Xrc is used it needs to be initialized in a special way
        """
        wx.ListBox.__init__(self, *args, **kwargs)
        self.Bind( wx.EVT_WINDOW_CREATE , self.OnCreate)

    def OnCreate(self,evt):
        self.Unbind ( wx.EVT_WINDOW_CREATE )
        wx.CallAfter(self.__PostInit)
        evt.Skip()
        return True

    def __PostInit(self):
        #wx.ListBox.__init__(self)
        self.CreateContextMenu()
        self.Bind (wx.EVT_CONTEXT_MENU, self.ShowPopupMenu)

    def CreateContextMenu(self):
        self.menu = wx.Menu()
        copy_menu_item = wx.MenuItem(self.menu, wx.NewId(), '&Copy text')
        self.menu.Bind(wx.EVT_MENU, self.CopySelection, copy_menu_item)
        self.menu.Append(copy_menu_item)

    def ShowPopupMenu(self, evt):
        position = self.ScreenToClient(wx.GetMousePosition())

        clicked_item = self.HitTest(position)
        selected_items = self.GetSelections()

        if clicked_item not in selected_items:
            self.DeselectAll()
            self.SetSelection(clicked_item)

        self.PopupMenu(self.menu, position)
  
    def CopySelection(self, evt):
        text = []
        for n in self.GetSelections():
             text.append(self.GetString(n))

        copyTextToClipboard("\n".join(text))
  
