from Enum import Enumeration
# from Config import faces

import re

FormatTypes = Enumeration("FormatTypes", ["Default", "WikiWord2", "WikiWord", "AvailWikiWord",                                          
                                          "Bold", "Italic", "Heading4", "Heading3", "Heading2", "Heading1",
                                          "Url", "Script", "Property", "ToDo"], 1)

def initialize(wikiSyntax):
    global BoldRE
    global ItalicRE
    global Heading4RE
    global Heading3RE
    global Heading2RE
    global Heading1RE
    global WikiWordRE
    global WikiWordRE2
    global UrlRE
    global ScriptRE
    global PropertyRE
    global BulletRE
    global NumericBulletRE
    global IndentedContentRE
    global ToDoRE
    global ToDoREWithContent
    global EmptyLineRE
    global HorizLineRE
    global IndentedRE
    global SuppressHighlightingRE
    global ToDoREWithCapturing
    global FormatExpressions
    global CombinedSyntaxHighlightWithCamelCaseRE
    global CombinedSyntaxHighlightWithoutCamelCaseRE
    
    BoldRE = wikiSyntax.BoldRE
    ItalicRE = wikiSyntax.ItalicRE
    Heading4RE = wikiSyntax.Heading4RE
    Heading3RE = wikiSyntax.Heading3RE
    Heading2RE = wikiSyntax.Heading2RE
    Heading1RE = wikiSyntax.Heading1RE
    WikiWordRE = wikiSyntax.WikiWordRE
    WikiWordRE2 = wikiSyntax.WikiWordRE2
    UrlRE = wikiSyntax.UrlRE
    ScriptRE = wikiSyntax.ScriptRE
    PropertyRE = wikiSyntax.PropertyRE
    BulletRE = wikiSyntax.BulletRE
    NumericBulletRE = wikiSyntax.NumericBulletRE
    IndentedContentRE = wikiSyntax.IndentedContentRE
    ToDoRE = wikiSyntax.ToDoRE
    ToDoREWithContent = wikiSyntax.ToDoREWithContent
    EmptyLineRE = wikiSyntax.EmptyLineRE
    HorizLineRE = wikiSyntax.HorizLineRE
    IndentedRE = wikiSyntax.IndentedRE
    SuppressHighlightingRE = wikiSyntax.SuppressHighlightingRE
    # used in the tree control to parse saved todos
    ToDoREWithCapturing = wikiSyntax.ToDoREWithCapturing
    
##    FormatExpressions = [(SuppressHighlightingRE, FormatTypes.Default), (ScriptRE, FormatTypes.Script), (PropertyRE, FormatTypes.Property),
##                         (UrlRE, FormatTypes.Url), (ToDoRE, FormatTypes.ToDo),
##                         (WikiWordRE2, FormatTypes.WikiWord2), (WikiWordRE, FormatTypes.WikiWord), (BoldRE, FormatTypes.Bold),
##                         (ItalicRE, FormatTypes.Italic), (Heading3RE, FormatTypes.Heading3), (Heading4RE, FormatTypes.Heading4),
##                         (Heading2RE, FormatTypes.Heading2), (Heading1RE, FormatTypes.Heading1)]

# Reordered version, most specific first

    FormatExpressions = [
            (SuppressHighlightingRE, FormatTypes.Default),
            (ScriptRE, FormatTypes.Script),
            (UrlRE, FormatTypes.Url),
            (ToDoRE, FormatTypes.ToDo),
            (PropertyRE, FormatTypes.Property),
            (WikiWordRE2, FormatTypes.WikiWord2),
            (WikiWordRE, FormatTypes.WikiWord),
            (BoldRE, FormatTypes.Bold),
            (ItalicRE, FormatTypes.Italic),
            (Heading4RE, FormatTypes.Heading4),
            (Heading3RE, FormatTypes.Heading3),
            (Heading2RE, FormatTypes.Heading2),
            (Heading1RE, FormatTypes.Heading1)
            ]

    # Build combined regexps
    WithCamelCase = []
    WithoutCamelCase = []
    for r, s in FormatExpressions:
        WithCamelCase.append((u"(?P<style%i>" % s) + r.pattern + u")")
        if not s is FormatTypes.WikiWord:
            WithoutCamelCase.append((u"(?P<style%i>" % s) + r.pattern + u")")


    CombinedSyntaxHighlightWithCamelCaseRE = \
            re.compile(u"|".join(WithCamelCase),
                    re.DOTALL | re.LOCALE | re.MULTILINE | re.UNICODE)
    CombinedSyntaxHighlightWithoutCamelCaseRE = \
            re.compile(u"|".join(WithoutCamelCase),
                    re.DOTALL | re.LOCALE | re.MULTILINE | re.UNICODE)
    


def getStyles(styleFaces):
    return [(FormatTypes.Default, "face:%(mono)s,size:%(size)d" % styleFaces),
            (FormatTypes.WikiWord, "fore:#000000,underline,face:%(mono)s,size:%(size)d" % styleFaces),      
            (FormatTypes.AvailWikiWord, "fore:#0000BB,underline,face:%(mono)s,size:%(size)d" % styleFaces),      
            (FormatTypes.Bold, "bold,face:%(mono)s,size:%(size)d" % styleFaces),   
            (FormatTypes.Italic, "italic,face:%(mono)s,size:%(size)d" % styleFaces), 
            (FormatTypes.Heading4, "bold,face:%(mono)s,size:%(heading4)d" % styleFaces),       
            (FormatTypes.Heading3, "bold,face:%(mono)s,size:%(heading3)d" % styleFaces),       
            (FormatTypes.Heading2, "bold,face:%(mono)s,size:%(heading2)d" % styleFaces),       
            (FormatTypes.Heading1, "bold,face:%(mono)s,size:%(heading1)d" % styleFaces), 
            (FormatTypes.Url, "fore:#0000BB,underline,face:%(mono)s,size:%(size)d" % styleFaces), 
            (FormatTypes.Script, "fore:#555555,face:%(mono)s,size:%(size)d" % styleFaces),
            (FormatTypes.Property, "bold,fore:#555555,face:%(mono)s,size:%(size)d" % styleFaces),
            (FormatTypes.ToDo, "bold,face:%(mono)s,size:%(size)d" % styleFaces)]

def isWikiWord(word):
    return WikiWordRE.match(word) or WikiWordRE2.match(word)
 
