import re

class _DummmyWikiLanguageDetails:
    """
    Dummy class for simpler comparing of wiki language format details if real
    details are not given.
    """
    __slots__ = ("__weakref__",)

    @staticmethod
    def getWikiLanguageName():
        return "nonexisting dummy wiki language identifier"

    def isEquivTo(self, details):
         return self.getWikiLanguageName() == details.getWikiLanguageName()


DUMMY_WIKI_LANGUAGE_DETAILS = _DummmyWikiLanguageDetails()



class WikiPageFormatDetails:
    """
    Store some details of the formatting of a specific page
    """
    __slots__ = ("__weakref__", "withCamelCase",
            "wikiDocument", "basePage", "autoLinkMode", "noFormat",
            "paragraphMode", "wikiLanguageDetails")
    
    def __init__(self, withCamelCase=True,
            wikiDocument=None, basePage=None, autoLinkMode="off", noFormat=False,
            paragraphMode=False, wikiLanguageDetails=DUMMY_WIKI_LANGUAGE_DETAILS):
        self.wikiDocument = wikiDocument   # WikiDocument object (needed for autoLink)
        self.basePage = basePage    # Base for calculating relative links

        self.withCamelCase = withCamelCase   # Interpret CamelCase as wiki word?
        self.autoLinkMode = autoLinkMode   # Mode to automatically create links from plain text
        self.noFormat = noFormat   # No formatting at all, overrides other settings
        
        # If True, ignore single newlines, only empty line starts new paragraph
        # Not relevant for page AST creation but for exporting (e.g. to HTML)
        self.paragraphMode = paragraphMode
        
        # Wiki language details object which must provide an isEquivTo() method
        # to be compared to another such object.
        self.wikiLanguageDetails = wikiLanguageDetails


    def getUsesDummyWikiLanguageDetails(self):
        return self.wikiLanguageDetails is DUMMY_WIKI_LANGUAGE_DETAILS
        
    def setWikiLanguageDetails(self, wikiLanguageDetails):
        # TODO Allow only if currently dummy language is set?
        self.wikiLanguageDetails = wikiLanguageDetails

    def isEquivTo(self, details):
        """
        Compares with other details object if both are "equivalent"
        """
        if self.noFormat or details.noFormat:
            # Remaining doesn't matter in this case
            return self.noFormat == details.noFormat

        return self.withCamelCase == details.withCamelCase and \
                self.autoLinkMode == details.autoLinkMode and \
                self.paragraphMode == details.paragraphMode and \
                self.wikiLanguageDetails.isEquivTo(details.wikiLanguageDetails)



def getFootnoteAnchorDict(pageAst):
    """
    Returns a new or cached dictionary of footnote anchors
    {footnoteId: anchorNode} from a page ast.
    """
    if pageAst is None:
        return
    if not hasattr(pageAst, "footnoteAnchorDict"):
        result = {}
#         fnNodes = pageAst.iterSelectedDeepByName("footnote",
#                 frozenset(("indentedText", "orderedList", "unorderedList",
#                 "heading", "headingContent")))

        fnNodes = pageAst.iterDeepByName("footnote")

        for node in fnNodes:
            result[node.footnoteId] = node

        pageAst.footnoteAnchorDict = result

    return pageAst.footnoteAnchorDict



# def coalesceTokens(tokens):
#     """
#     Coalesce neighboured "Default" tokens.
#     """
#     result = []
#     lenT = len(tokens)
#     if lenT < 2:
#         return tokens
#         
#     prevToken = tokens[0]
#     for token in itertools.islice(tokens, 1, None):
#         if prevToken.ttype == FormatTypes.Default and \
#                token.ttype == FormatTypes.Default:
#             prevToken.text = prevToken.text + token.text
#             continue
# 
#         result.append(prevToken)
#         prevToken = token
#     
#     result.append(prevToken)
#     
#     return result


_RE_LINE_INDENT = re.compile(r"^[ \t]*")

class BasicLanguageHelper:
    @staticmethod
    def reset():
        pass

    @staticmethod
    def getWikiLanguageName():
        return "internal_basic"


    # TODO More descriptive error messages (which character(s) is/are wrong?)
    @staticmethod   # isValidWikiWord
    def checkForInvalidWikiWord(word, wikiDocument=None, settings=None):
        """
        Test if word is syntactically a valid wiki word and no settings
        are against it. The camelCase black list is not checked.
        The function returns None IFF THE WORD IS VALID, an error string
        otherwise
        """
        raise InternalError()


    # TODO More descriptive error messages (which character(s) is/are wrong?)
    @staticmethod   # isValidWikiWord
    def checkForInvalidWikiLink(word, wikiDocument=None, settings=None):
        """
        Test if word is syntactically a valid wiki link and no settings
        are against it. The camelCase black list is not checked.
        The function returns None IFF THE WORD IS VALID, an error string
        otherwise
        """
        raise InternalError()



    @staticmethod
    def extractWikiWordFromLink(word, wikiDocument=None, basePage=None):  # TODO Problems with subpages?
        """
        Strip brackets and other link details if present and return wikiWord
        if a valid wiki word can be extracted, None otherwise.
        """
        raise InternalError()


#     resolveWikiWordLink = staticmethod(resolveWikiWordLink)
#     """
#     If using subpages this is used to resolve a link to the right wiki word
#     relative to basePage on which the link is placed.
#     It returns the absolute link (page name).
#     """


    @staticmethod
    def resolvePrefixSilenceAndWikiWordLink(link, basePage):
        """
        If using subpages this is used to resolve a link to the right wiki word
        for autocompletion. It returns a tuple (prefix, silence, pageName).
        Autocompletion now searches for all wiki words starting with pageName. For
        all found items it removes the first  silence  characters, prepends the  prefix
        instead and uses the result as suggestion for autocompletion.
        
        If prefix is None autocompletion is not possible.
        """
        raise InternalError()
        



    @staticmethod
    def parseTodoValue(todoValue, wikiDocument=None):
        """
        Parse a todo value (right of the colon) and return the node or
        return None if value couldn't be parsed
        """
        raise InternalError()


    @staticmethod
    def parseTodoEntry(entry, wikiDocument=None):
        """
        Parse a complete todo entry (without end-token) and return the node or
        return None if value couldn't be parsed
        """
        raise InternalError()


    @staticmethod
    def buildAutoLinkRelaxInfo(wikiDocument):
        """
        Build some cache info needed to process auto-links in "relax" mode.
        This info will be given back in the formatDetails when calling
        _TheParser.parse().
        The implementation for this plugin creates a list of regular
        expressions and the related wiki words, but this is not mandatory.
        """
        raise InternalError()


    @staticmethod
    def createWikiLinkPathObject(*args, **kwargs):
        raise InternalError()


    @staticmethod
    def isAbsoluteLinkCore(linkCore):
        raise InternalError()


    @staticmethod
    def createLinkFromWikiWord(word, wikiPage, forceAbsolute=False):
        """
        Create a link from word which should be put on wikiPage.
        """
        raise InternalError()


    @staticmethod
    def createAbsoluteLinksFromWikiWords(words, wikiPage=None):
        """
        Create particularly stable links from a list of words which should be
        put on wikiPage.
        """
        raise InternalError()


    @staticmethod
    def createWikiLinkFromText(text, bracketed=True):
        raise InternalError()


    @staticmethod
    def createRelativeLinkFromWikiWord(word, baseWord, downwardOnly=True):
        """
        Create a link to wikiword word relative to baseWord.
        If downwardOnly is False, the link may contain parts to go to parents
            or siblings
        in path (in this wiki language, ".." are used for this).
        If downwardOnly is True, the function may return None if a relative
        link can't be constructed.
        """
        raise InternalError()

    @staticmethod
    def createUrlLinkFromPath(wikiDocument, path, relative=False,
            bracketed=False, protocol=None):
        raise InternalError()


    @staticmethod
    def createAttributeFromComponents(key, value, wikiPage=None):
        """
        Build an attribute from key and value.
        """
        raise InternalError()
        

    @staticmethod
    def isCcWikiWord(word):
        raise InternalError()


    @staticmethod
    def findNextWordForSpellcheck(text, startPos, wikiPage):
        """
        Find in text next word to spellcheck, beginning at position startPos
        
        Returns tuple (start, end, spWord) which is either (None, None, None)
        if no more word can be found or returns start and after-end of the
        spWord to spellcheck.
        
        TODO: Move away because this is specific to human language,
            not wiki language.
        """
        return (None, None, None)


    @staticmethod
    def prepareAutoComplete(editor, text, charPos, lineStartCharPos,
            wikiDocument, docPage, settings):
        """
        Called when user wants autocompletion.
        text -- Whole text of page
        charPos -- Cursor position in characters
        lineStartCharPos -- For convenience and speed, position of the 
                start of text line in which cursor is.
        wikiDocument -- wiki document object
        docPage -- DocPage object on which autocompletion is done
        closingBracket -- boolean iff a closing bracket should be suggested
                for bracket wikiwords and attributes

        returns -- a list of tuples (sortKey, entry, backStepChars) where
            sortKey -- unistring to use for sorting entries alphabetically
                using right collator
            entry -- actual unistring entry to show and to insert if
                selected
            backStepChars -- numbers of chars to delete to the left of cursor
                before inserting entry
        """
        return []


    @staticmethod
    def handleNewLineBeforeEditor(editor, text, charPos, lineStartCharPos,
            wikiDocument, settings):
        """
        Processes pressing of a newline in editor before editor processes it.
        Returns True iff the actual newline should be processed by
            editor yet.
        """
        return True


    @staticmethod
    def handleNewLineAfterEditor(editor, text, charPos, lineStartCharPos,
            wikiDocument, settings):
        """
        Processes pressing of a newline after editor processed it (if 
        handleNewLineBeforeEditor returned True).
        """
        # autoIndent, autoBullet, autoUnbullet
        currentLine = editor.GetCurrentLine()

        if currentLine > 0:
            previousLine = editor.GetLine(currentLine - 1)
            indent = _RE_LINE_INDENT.match(previousLine).group(0)
    
            if settings.get("autoIndent", False):
                editor.AddText(indent)
                return


    @staticmethod
    def handleRewrapText(editor, settings):
        pass


    @staticmethod 
    def handlePasteRawHtml(editor, rawHtml, settings):
        # Remove possible body end tags
        rawHtml = rawHtml.replace("</body>", "")
        if rawHtml:
            editor.ReplaceSelection("<body>" + rawHtml + "</body>")
            return True

        return False


    @staticmethod 
    def formatSelectedText(text, start, afterEnd, formatType, settings):
        """
        Called when selected text (between start and afterEnd)
        e.g. in editor should be formatted (e.g. bold or as heading)
        text -- Whole text
        start -- Start position of selection
        afterEnd -- After end position of selection

        formatType -- string to describe type of format
        settings -- dict with additional information, currently ignored
        
        Returns None if operation wasn't supported or possible or 
            tuple (replacement, repStart, repAfterEnd, selStart, selAfterEnd) where
    
            replacement -- replacement text
            repStart -- Start of characters to delete in original text
            repAfterEnd -- After end of characters to delete
            selStart -- Recommended start of editor selection after replacement
                was done
            selAfterEnd -- Recommended after end of editor selection after replacement
        """
        return None


    @staticmethod
    def getNewDefaultWikiSettingsPage(mainControl):
        """
        Return default text of the "WikiSettings" page for a new wiki.
        """
        return ""


    @staticmethod
    def createWikiLanguageDetails(wikiDocument, docPage):
        """
        Returns a new WikiLanguageDetails object based on current configuration
        """
        return None
        
        
    
    @staticmethod
    def getRecursiveStylingNodeNames():
        """
        Returns a set of those node names of NonTerminalNode-s  for which the
        WikiTxtCtrl.processTokens() should process children recursively.
        """
        return []
        
        
    @staticmethod
    def getFoldingNodeDict(self):
        """
        Retrieve the folding node dictionary which tells
        which AST nodes (other than "heading") should be processed by
        folding.
        The folding node dictionary has the names of the AST node types as keys,
        each value is a tuple (fold, recursive) where
        fold -- True iff node should be folded
        recursive -- True iff node should be processed recursively
        
        The value tuples may contain more than these two items, processFolding()
        must be able to handle that.
        """
        return []
        

_BASIC_LANGUAGE_HELPER_OBJECT = BasicLanguageHelper()

def getBasicLanguageHelper():
    return _BASIC_LANGUAGE_HELPER_OBJECT
