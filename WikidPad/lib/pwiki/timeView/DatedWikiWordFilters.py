# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback, abc

import wx



class DatedWikiWordFilterBase(metaclass=abc.ABCMeta):
    """
    Provides for a given date or list of dates a list of wiki words
    related to that date. Subclasses of this class define which
    "relation" is meant.
    """
    def __init__(self):
        self.wikiDocument = None
        self.dayResolution = 1

    def setWikiDocument(self, wikiDoc):
        self.wikiDocument = wikiDoc

    def getWikiDocument(self):
        return self.wikiDocument

    def setDayResolution(self, dr):
        self.dayResolution = dr

    def getDayResolution(self):
        return self.dayResolution

    @abc.abstractmethod 
    def getDisplayName(self):
        """
        Return a short name describing what the date of the wiki word means.
        """
        raise NotImplementedError
        
    @abc.abstractmethod 
    def getWikiWordsForDay(self, day):
        """
        Get a list of all wiki words related to a date beginning with day
        (a wx.DateTime) up to so many days as set in self.dayResolution
        """
        raise NotImplementedError
        
    def getMassWikiWordCountForDays(self, startDay, count):
        """
        Returns a list dayWordCounts where dayWordCounts[i] is the same as
        len(self.getWikiWordsForDay(startDay + wx.TimeSpan.Days(self.dayResolution) * i))
        and len(dayWordCounts) == count.
        
        This base class contains a default implementation
        """
        day = startDay
        step = wx.TimeSpan.Days(self.dayResolution)

        dayWordCounts = []
        for i in range(count):
            dayWordCounts.append(len(self.getWikiWordsForDay(day)))
            day = day + step
        
        return dayWordCounts


        # The "float" fixes a problem with database engines
    def _getDayFromTimeT(self, timeT):
        day = wx.DateTime.FromTimeT(float(timeT))
        day.ResetTime()
        
        return day
        
    def _getNextDayFromTimeT(self, timeT):
        day = wx.DateTime.FromTimeT(float(timeT))
        day.ResetTime()
        day += wx.TimeSpan.Day()

        return day


    def _getMinMaxDaysFromTimeT(self, timeMinMax):
        """
        Helper to convert time_t min/max values from WikiDocument to
        wx.DateTime objects.
        """
        if timeMinMax == (None, None):
            return (None, None)

        return (self._getDayFromTimeT(timeMinMax[0]),
                self._getNextDayFromTimeT(timeMinMax[1]))


    # TODO The following things are not very efficient

    def _getDayListFromTimeList(self, wtList):
        if len(wtList) == 0:
            return []

        days = [self._getDayFromTimeT(wt[1]) for wt in wtList]

        result = [days[0]]
        lastDay = days[0]        
        
        for d in days[1:]:
            if lastDay != d:
                result.append(d)
                lastDay = d

        return result


    def getMinMaxDay(self):
        """
        Return a tuple (minD, maxD) with the first day a wikiword is related
        to and the day AFTER the last which is related (wx.DateTime objects).
        
        If no wikiwords are available, (None, None) is returned.
        """
        assert 0  # Abstract

    @abc.abstractmethod
    def getDaysBefore(self, day, limit):
        raise NotImplementedError
   
    @abc.abstractmethod
    def getDaysAfter(self, day, limit):
        raise NotImplementedError



class DatedWikiWordFilterModified(DatedWikiWordFilterBase):

    def getDisplayName(self):
        return _("Modified")
        
    def getWikiWordsForDay(self, day):
        wikiDocument = self.getWikiDocument()
        if wikiDocument is None:
            return []
        
        startTime = day.GetTicks()
        endTime = float(startTime + 86400 * self.getDayResolution())

        return wikiDocument.getWikiPageNamesModifiedWithin(startTime,
                endTime)

    def getMinMaxDay(self):
        return self._getMinMaxDaysFromTimeT(
                self.getWikiDocument().getWikiData().getTimeMinMax(0))


    def getDaysBefore(self, day, limit=None):
        wtList = self.getWikiDocument().getWikiData().getWikiPageNamesBefore(
                0, day.GetTicks(), limit)
        wtList.reverse()

        return self._getDayListFromTimeList(wtList)


    def getDaysAfter(self, day, limit=None):
        wtList = self.getWikiDocument().getWikiData().getWikiPageNamesAfter(
                0, (day + wx.TimeSpan.Day()).GetTicks(), limit)

        return self._getDayListFromTimeList(wtList)
