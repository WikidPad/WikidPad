# -*- coding: iso8859-1 -*-
import os, sys, traceback
from os.path import *

import wx, wx.grid

from .WikiExceptions import *

from . import SystemInfo

from .wxHelper import WindowUpdateLocker, isDeepChildOf



def replaceStandIn(container, standIn, grid):
    """
    The default wxXmlResource::AttachUnknownControl doesn't work well for
    wxGrid on wxGTK. Instead of an unknown control, something else like
    wxStaticBox is placed as standIn and replaced with grid when container
    (usually a dialog or a panel in it) is opened
    """
    standInId = standIn.GetId()
    grid.SetId(standInId)
    
    result = container.GetSizer().Replace(standIn, grid, recursive=True)
    
    if result:
        standIn.Destroy()
        container.GetSizer().Layout()
    else:
        raise InternalError(("Can't replace standin. Container: %s, standIn: %s,"
                "replacement: %s") % (repr(container), repr(standIn), repr(grid)))




class EnhancedGrid(wx.grid.Grid):
    def __init__(self, parent, id=-1):
        wx.grid.Grid.__init__(self, parent, id)
        
        self.__closed = False
        
        self.Bind(wx.EVT_KEY_DOWN, self.__OnKeyDown)
        self.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.__OnSelectCell)
        self.Bind(wx.grid.EVT_GRID_EDITOR_CREATED, self.__OnGridEditorCreated)
        self.Bind(wx.EVT_SET_FOCUS, self.__OnSetFocus)
        self.Bind(wx.grid.EVT_GRID_RANGE_SELECT, self.__OnGridRangeSelect)

    def _isDirectEdit(self, row, col):
        """
        Should return True iff editor should start directly if cell
        (row, col) is selected.
        Can be overwritten by derived classes.
        """
        return False


    def _isMoveTarget(self, row, col):
        """
        Returns True if cell can be visited by moving with cursor or tab keys.
        Can be overwritten by derived classes.
        Default implementation forbids move to readonly cells
        """
        return not self.IsReadOnly(row, col)

    def __OnSelectCell(self, evt):
        evt.Skip()
        if self._isDirectEdit(evt.GetRow(), evt.GetCol()):
            wx.CallAfter(self._runEditor)


    if SystemInfo.isLinux():

        def _runEditor(self):
            if self.CanEnableCellControl():
                sx, sy = self.GetViewStart()
                # This call may trigger unwanted scrolling on wxGTK
                # Therefore it is scrolled back afterwards
                self.EnableCellEditControl()
                self.Scroll(sx, sy)
                # Just in case scrolling was wrong
                self.MakeCellVisible(self.GetGridCursorRow(),
                        self.GetGridCursorCol())

    else:  # TODO: What is right for MacOS?
        
        def _runEditor(self):
            if self.CanEnableCellControl():
                self.EnableCellEditControl()


    def __OnGridEditorCreated(self, evt):
        evt.Skip()

        control = evt.GetControl()
        
        control.SetWindowStyleFlag(control.GetWindowStyleFlag() | wx.WANTS_CHARS)
        # control.Bind(wx.EVT_KEY_DOWN, self.__OnKeyDown)


    def __OnGridRangeSelect(self, evt):
        evt.Skip()
        self.SetFocus()

    def __OnSetFocus(self, evt):
        evt.Skip()
        if not isDeepChildOf(evt.GetWindow(), self):
            for row in range(self.GetNumberRows()):
                for col in range(self.GetNumberCols()):
                    if self._isMoveTarget(row, col):
                        self.SetGridCursor(row, col)
                        return

            self.SetGridCursor(0, 0)


#     CURSORKEY_TO_DIR = {wx.WXK_UP: "up", wx.WXK_NUMPAD_UP: "up",
#             wx.WXK_DOWN: "down", wx.WXK_NUMPAD_DOWN: "down"}

#             wx.WXK_LEFT: "left", wx.WXK_NUMPAD_LEFT: "left",
#             wx.WXK_RIGHT: "right", wx.WXK_NUMPAD_RIGHT: "right",

            
    def __OnKeyDown(self, evt):
        if evt.ControlDown() or evt.AltDown() or evt.MetaDown():
            evt.Skip()
            return
#         if evt.GetKeyCode() != wx.WXK_TAB:
#             evt.Skip()
#             return


        direction = None
        if evt.GetKeyCode() == wx.WXK_TAB:
            if evt.ShiftDown():
                direction = "left"
            else:
                direction = "right"
#         else:
#             if not evt.ShiftDown():
#                 direction = self.CURSORKEY_TO_DIR.get(evt.GetKeyCode())

        if direction is None:
            evt.Skip()
            return


        self.DisableCellEditControl()
        if direction == "left":
            while True:
                success = self.MoveCursorLeft(False)
                if not success:
                    newRow = self.GetGridCursorRow() - 1
                    if newRow >= 0:
                        colPos = self.GetTable().GetNumberCols() - 1
                        self.SetGridCursor(newRow, colPos)
                        self.MakeCellVisible(newRow, colPos)
                    else:
                        self.Navigate(False)
                        break

                if self._isMoveTarget(self.GetGridCursorRow(),
                        self.GetGridCursorCol()):
                    break

        elif direction == "right":
            while True:
                success = self.MoveCursorRight(False)
                if not success:
                    newRow = self.GetGridCursorRow() + 1
                    if newRow < self.GetTable().GetNumberRows():
                        self.SetGridCursor(newRow, 0)
                        self.MakeCellVisible(newRow, 0)
                    else:
                        self.Navigate(True)
                        break

                if self._isMoveTarget(self.GetGridCursorRow(),
                        self.GetGridCursorCol()):
                    break

#         elif direction == "down":
#             while True:
#                 success = self.MoveCursorDwon(False)
#                 if not success:
#                     newCol = self.GetGridCursorCol() + 1
#                     if newCol < self.GetTable().GetNumberCols():
#                         self.SetGridCursor(0, newCol)
#                         self.MakeCellVisible(0, newCol)
#                     else:
#                         break
# 
#                 if self._isMoveTarget(self.GetGridCursorRow(),
#                         self.GetGridCursorCol()):
#                     break



    def getSingleCurrentRow(self):
        rows = self.GetSelectedRows()
        if len(rows) == 1:
            return rows[0]
        else:
            return self.GetGridCursorRow()
        
    def _buildSelectedCellSet(self):
        result = set()
        
        for row, col in self.GetSelectedCells():
            result.add((row, col))
        
        for (t, l), (b, r) in zip(self.GetSelectionBlockTopLeft(),
                self.GetSelectionBlockBottomRight()):
            for row in range(t, b + 1):
                for col in range(l, r + 1):
                    result.add((row, col))

        for row in self.GetSelectedRows():
            for col in range(self.GetNumberCols()):
                result.add((row, col))

        for col in self.GetSelectedCols():
            for row in range(self.GetNumberRows()):
                result.add((row, col))
        
        # Take grid cursor as selection if nothing else selected
        if len(result) == 0:
            result.add((self.GetGridCursorRow(), self.GetGridCursorCol()))

        return result


#     def getSelectedBlock(self):
#         cells = self._buildSelectedCellSet()
#         if len(cells) == 0:
#             raise UnhandledBadInputException(u"Kein Bereich ausgewählt")
# 
#         t, l = cells.pop()
#         b, r = t, l
#         
#         for row, col in cells:
#             t = min(t, row)
#             b = max(b, row)
#             l = min(l, col)
#             r = max(r, col)
#         
#         blockCount = (b - t + 1) * (r - l + 1)
#         
#         if blockCount != (len(cells) + 1):
#             raise UnhandledBadInputException(
#                     u"Ausgewählter Bereich muss rechteckig sein")
# 
#         return (t, l, b, r)


#     def getSelectedBoundingBox(self):
#         cells = self._buildSelectedCellSet()
#         if len(cells) == 0:
#             raise UnhandledBadInputException(u"Kein Bereich ausgewählt")
# 
#         t, l = cells.pop()
#         b, r = t, l
#         
#         for row, col in cells:
#             t = min(t, row)
#             b = max(b, row)
#             l = min(l, col)
#             r = max(r, col)
#         
#         return (t, l, b, r)


    def getSelectedCellsRowWise(self):
        result = list(self._buildSelectedCellSet())
        result.sort()
        return result
        

#     def appendRow(self):
#         lastRow = self.GetTable().GetNumberRows()
#         self.AppendRows()
#         return lastRow
# 
# 
#     def deleteSelectedRows(self):
#         if self.GetTable().GetNumberRows() == 0:
#             return -1
# 
#         try:
#             t, l, b, r = self.getSelectedBoundingBox()
#         except UnhandledBadInputException:
#             return
#         
#         if True:   # b > t:
#             # More than one row -> select and ask
#             self.SelectRow(t)
#             for row in range(t + 1, b + 1):
#                 self.SelectRow(row, True)
#             
#             answer = wx.MessageBox(u"{0} Zeile(n) wirklich löschen?".format(
#                     b - t + 1), u"Zeile(n) löschen", wx.YES_NO, self)
#             
#             if answer != wx.YES:
#                 return
#         
#         self.DeleteRows(t, b - t + 1)
# 
# 
#     def deleteCurrentRow(self):
#         if self.GetTable().GetNumberRows() == 0:
#             return -1
#         row = self.getSingleCurrentRow()
#         self.DeleteRows(row)
#         return row


#     def moveRow(self, row, offset):
#         """
#         Currently for offset only 1 (downward) or -1 (upward) are allowed
#         Returns a dictionary {<new row>: <old row>}
#         """
#         assert offset in (-1, 1), u"Bad offset value"
# 
#         if row == -1:
#             row = self.getSingleCurrentRow()
#         
# 
#         if 0 <= (row + offset) < self.GetNumberRows():
#             curCol = self.GetGridCursorCol()
# 
#             temp = [None] * self.GetNumberCols()
#             for col in range(self.GetNumberCols()):
#                 temp[col] = self.GetCellValue(row, col)
#             for col in range(self.GetNumberCols()):
#                 self.SetCellValue(row, col, self.GetCellValue(row + offset, col))
#             for col in range(self.GetNumberCols()):
#                 self.SetCellValue(row + offset, col, temp[col])
#                 
#             self.SetGridCursor(row + offset, curCol)
#             return {row: (row + offset), (row + offset): row}
# 
#         return {}

    def close(self):
        self._runEditor = lambda: None
        self.__closed = True

    def clearRows(self):
        if self.GetNumberRows() > 0:
            self.DeleteRows(0, self.GetNumberRows())


