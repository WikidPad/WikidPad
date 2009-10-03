

class _DummmyWikiLanguageDetails(object):
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



class WikiPageFormatDetails(object):
    """
    Store some details of the formatting of a specific page
    """
    __slots__ = ("__weakref__", "withCamelCase",
            "wikiDocument", "basePage", "autoLinkMode", "noFormat",
            "paragraphMode", "wikiLanguageDetails")
    
    def __init__(self, withCamelCase=True,
            wikiDocument=None, basePage=None, autoLinkMode=u"off", noFormat=False,
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



