import os, urllib.request, urllib.parse, urllib.error

import wx

WIKIDPAD_PLUGIN = (("InsertionByKey", 1),)

def describeInsertionKeys(ver, app):
    """
    API function for "InsertionByKey" plugins
    Returns a sequence of tuples describing the supported
    insertion keys. Each tuple has the form (insKey, exportTypes, handlerFactory)
    where insKey is the insertion key handled, exportTypes is a sequence of
    strings describing the supported export types and handlerFactory is
    a factory function (normally a class) taking the wxApp object as
    parameter and returning a handler object fulfilling the protocol
    for "insertion by key" (see EqnHandler as example).
    
    This plugin uses the special export type "wikidpad_language" which is
    not a real type like HTML export, but allows to return a string
    which conforms to WikidPad wiki syntax and is postprocessed before
    exporting.
    Therefore this plugin is not bound to a specific export type.

    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """
    return (("testexample", ("wikidpad_language",), ExampleHandler),)


class ExampleHandler:
    """
    Class fulfilling the "insertion by key" protocol.
    """
    def __init__(self, app):
        self.app = app
        
    def taskStart(self, exporter, exportType):
        """
        This is called before any call to createContent() during an
        export task.
        An export task can be a single HTML page for
        preview or a single page or a set of pages for export.
        exporter -- Exporter object calling the handler
        exportType -- string describing the export type
        
        Calls to createContent() will only happen after a 
        call to taskStart() and before the call to taskEnd()
        """
        pass

        
    def taskEnd(self):
        """
        Called after export task ended and after the last call to
        createContent().
        """
        pass


    def createContent(self, exporter, exportType, insToken):
        """
        Handle an insertion and create the appropriate content.

        exporter -- Exporter object calling the handler
        exportType -- string describing the export type
        insToken -- insertion token to create content for

        An insertion token has the following member variables:
            key: insertion key (unistring)
            value: value of an insertion (unistring)
            appendices: sequence of strings with the appendices

        Meaning and type of return value is solely defined by the type
        of the calling exporter.
        
        For HtmlExporter a unistring is returned with the HTML code
        to insert instead of the insertion.        
        """
        result = "Value: " + insToken.value
        for i, apx in enumerate(insToken.appendices):
            result += " %i. appendix: %s" % (i, apx)

        return result


    def getExtraFeatures(self):
        """
        Returns a list of bytestrings describing additional features supported
        by the plugin. Currently not specified further.
        """
        return ()


