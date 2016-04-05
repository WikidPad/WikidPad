import re

import wx, wx.xrc

from wxHelper import *

from . import SystemInfo
from . import Utilities

from .StringOps import uniToGui, guiToUni, colorDescToRgbTuple,\
        rgbToHtmlColor, strToBool, splitIndent, escapeForIni, unescapeForIni

from .AdditionalDialogs import DateformatDialog, FontFaceDialog

from .WikiTxtCtrl import WikiTxtCtrl

from . import Localization
from . import OsAbstract

from . import WikiHtmlView



class DefaultOptionsPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

    def setVisible(self, vis):
        return True

    def checkOk(self):
        return True

    def handleOk(self):
        pass


class ResourceOptionsPanel(DefaultOptionsPanel):
    """
    GUI of panel is defined by a ressource.
    """
    def __init__(self, parent, resName):
        p = wx.PrePanel()
        self.PostCreate(p)
#         self.optionsDlg = optionsDlg
        res = wx.xrc.XmlResource.Get()

        res.LoadOnPanel(self, parent, resName)

    def setVisible(self, vis):
        return True

    def checkOk(self):
        return True

    def handleOk(self):
        pass


class PluginOptionsPanel(DefaultOptionsPanel):
    def __init__(self, parent, optionsDlg):
        DefaultOptionsPanel.__init__(self, parent)

        self.idToOptionEntryMap = {}
        self.oldSettings = {}
        self.optionToControl = []
        self.mainControl = optionsDlg.getMainControl()


    def addOptionEntry(self, opt, ctl, typ, *params):
        self.optionToControl.append((opt, ctl, typ) + params)


    def transferOptionsToDialog(self, config=None):
        # List of tuples (<configuration file entry>, <gui control name>, <type>)
        # Supported types:
        #     b: boolean checkbox
        #     i0+: nonnegative integer
        #     t: text
        #     tes: text with escaped spaces, using StringOps.escapeForIni
        #     tre: regular expression
        #     ttdf: time/date format
        #     f0+: nonegative float
        #     seli: integer position of a selection in dropdown list
        #     selt: Chosen text in dropdown list
        #     color0: HTML color code or empty
        #     spin: Numeric SpinCtrl
        #
        #     guilang: special choice for GUI language

        # ttdf and color0 entries have a 4th item with the name
        #     of the "..." button to call a dialog to set.
        # selt entries have a list with the internal config names (unicode) of the
        #     possible choices as 4th item.

        # Transfer options to dialog

        if config is None:
            config = self.mainControl.getConfig()

        for oct in self.optionToControl:
            self.transferSingleOptionToDialog(config, oct)


    def transferSingleOptionToDialog(self, config, oct):
        o, ctl, t = oct[:3]
        self.idToOptionEntryMap[ctl.GetId()] = oct
        self.oldSettings[o] = config.get("main", o)

        if t == "b":   # boolean field = checkbox
            ctl.SetValue(
                    config.getboolean("main", o))
        elif t == "b3":   # boolean field = checkbox
            value = config.get("main", o)
            if value == "Gray":
                ctl.Set3StateValue(wx.CHK_UNDETERMINED)
            else:
                if strToBool(value):
                    ctl.Set3StateValue(wx.CHK_CHECKED)
                else:
                    ctl.Set3StateValue(wx.CHK_UNCHECKED)

#                 ctl.SetValue(
#                         config.getboolean("main", o))
        elif t in ("t", "tre", "ttdf", "i0+", "f0+", "color0"):  # text field or regular expression field
            ctl.SetValue( uniToGui(config.get("main", o)) )
        elif t == "tes":  # Text escaped
            ctl.SetValue( unescapeForIni(uniToGui(config.get("main", o))) )
        elif t == "seli":   # Selection -> transfer index
            ctl.SetSelection(config.getint("main", o))
        elif t == "selt":   # Selection -> transfer content string
            try:
                idx = oct[3].index(config.get("main", o))
                ctl.SetSelection(idx)
            except (IndexError, ValueError):
                ctl.SetStringSelection(uniToGui(config.get("main", o)) )
        elif t == "spin":   # Numeric SpinCtrl -> transfer number
            ctl.SetValue(config.getint("main", o))
        elif t == "guilang":   # GUI language choice
            # First fill choice with options
            ctl.Append(_(u"Default"))
            for ls, lt in Localization.getLangList():
                ctl.Append(lt)

            # Then select previous setting
            optValue = config.get("main", o)
            ctl.SetSelection(Localization.findLangListIndex(optValue) + 1)


        # Register events for "..." buttons
        if t in ("color0", "ttdf"):
            params = oct[3:]
            if len(params) > 0:
                # params[0] is the "..." button after the text field
                dottedButtonId = params[0].GetId()
                self.idToOptionEntryMap[dottedButtonId] = oct

                wx.EVT_BUTTON(self, dottedButtonId,
                        self.OnDottedButtonPressed)


    def checkOk(self):
        """
        Called when "OK" is pressed in dialog. The plugin should check here if
        all input values are valid. If not, it should return False, then the
        Options dialog automatically shows this panel.

        There should be a visual indication about what is wrong (e.g. red
        background in text field). Be sure to reset the visual indication
        if field is valid again.
        """
        fieldsValid = True

        # First check validity of field contents
        for oct in self.optionToControl:
            if not self.checkSingleOptionOk(oct):
                fieldsValid = False

        return fieldsValid


    def checkSingleOptionOk(self, oct):
        o, ctl, t = oct[:3]
        fieldsValid = True

        if t == "tre":
            # Regular expression field, test if re is valid
            try:
                rexp = guiToUni(ctl.GetValue())
                re.compile(rexp, re.DOTALL | re.UNICODE | re.MULTILINE)
                ctl.SetBackgroundColour(wx.WHITE)
            except:   # TODO Specific exception
                fieldsValid = False
                ctl.SetBackgroundColour(wx.RED)
        elif t == "i0+":
            # Nonnegative integer field
            try:
                val = int(guiToUni(ctl.GetValue()))
                if val < 0:
                    raise ValueError
                ctl.SetBackgroundColour(wx.WHITE)
            except ValueError:
                fieldsValid = False
                ctl.SetBackgroundColour(wx.RED)
        elif t == "f0+":
            # Nonnegative float field
            try:
                val = float(guiToUni(ctl.GetValue()))
                if val < 0:
                    raise ValueError
                ctl.SetBackgroundColour(wx.WHITE)
            except ValueError:
                fieldsValid = False
                ctl.SetBackgroundColour(wx.RED)
        elif t == "color0":
            # HTML Color field or empty field
            val = guiToUni(ctl.GetValue())
            rgb = colorDescToRgbTuple(val)

            if val != "" and rgb is None:
                ctl.SetBackgroundColour(wx.RED)
                fieldsValid = False
            else:
                ctl.SetBackgroundColour(wx.WHITE)
        elif t == "spin":
            # SpinCtrl
            try:
                val = ctl.GetValue()
                if val < ctl.GetMin() or \
                        val > ctl.GetMax():
                    raise ValueError
                ctl.SetBackgroundColour(wx.WHITE)
            except ValueError:
                fieldsValid = False
                ctl.SetBackgroundColour(wx.RED)

        return fieldsValid



    def transferDialogToOptions(self, config=None):
        if config is None:
            config = self.mainControl.getConfig()

        for oct in self.optionToControl:
            self.transferDialogToSingleOption(config, oct)


    def transferDialogToSingleOption(self, config, oct):
        """
        Transfer option from dialog to config object
        """
        o, ctl, t = oct[:3]

        # TODO Handle unicode text controls
        if t == "b":
            config.set("main", o, repr(ctl.GetValue()))
        elif t == "b3":
            value = ctl.Get3StateValue()
            if value == wx.CHK_UNDETERMINED:
                config.set("main", o, "Gray")
            elif value == wx.CHK_CHECKED:
                config.set("main", o, "True")
            elif value == wx.CHK_UNCHECKED:
                config.set("main", o, "False")

        elif t in ("t", "tre", "ttdf", "i0+", "f0+", "color0"):
            config.set("main", o, guiToUni(ctl.GetValue()) )
        elif t == "tes":
            config.set( "main", o, guiToUni(escapeForIni(ctl.GetValue(),
                    toEscape=u" ")) )
        elif t == "seli":   # Selection -> transfer index
            config.set(
                    "main", o, unicode(ctl.GetSelection()) )
        elif t == "selt":   # Selection -> transfer content string
            try:
                config.set("main", o,
                        oct[3][ctl.GetSelection()])
            except IndexError:
                config.set("main", o,
                        guiToUni(ctl.GetStringSelection()))
        elif t == "spin":   # Numeric SpinCtrl -> transfer number
            config.set(
                    "main", o, unicode(ctl.GetValue()) )
        elif t == "guilang":    # GUI language choice
            idx = ctl.GetSelection()
            if idx < 1:
                config.set("main", o, u"")
            else:
                config.set("main", o,
                        Localization.getLangList()[idx - 1][0])

    def OnDottedButtonPressed(self, evt):
        """
        Called when a "..." button is pressed (for some of them) to show
        an alternative way to specify the input, e.g. showing a color selector
        for color entries instead of using the bare text field
        """
        oct = self.idToOptionEntryMap[evt.GetId()]
        o, ctl, t = oct[:3]
        params = oct[3:]

        if t == "color0":
            self.selectColor(ctl)
        elif t == "ttdf":   # Date/time format
            self.selectDateTimeFormat(ctl)


    def selectColor(self, tfield):
        rgb = colorDescToRgbTuple(tfield.GetValue())
        if rgb is None:
            rgb = (0, 0, 0)

        color = wx.Colour(*rgb)
        colordata = wx.ColourData()
        colordata.SetColour(color)

        dlg = wx.ColourDialog(self, colordata)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                color = dlg.GetColourData().GetColour()
                if color.Ok():
                    tfield.SetValue(
                            rgbToHtmlColor(color.Red(), color.Green(),
                            color.Blue()))
        finally:
            dlg.Destroy()

    def selectDateTimeFormat(self, tfield):
        dlg = DateformatDialog(self, -1, self.mainControl,
                deffmt=tfield.GetValue())
        try:
            if dlg.ShowModal() == wx.ID_OK:
                tfield.SetValue(dlg.GetValue())
        finally:
            dlg.Destroy()



# class KeyDefField(wx.TextCtrl):
#     def __init__(self, parent, ID=-1):
#         wx.TextCtrl.__init__(self, parent, ID)
#         self.mods = None
#         self.vkCode = None
#         EVT_
#     def


class OptionsDialog(wx.Dialog):
    # List of tuples (<configuration file entry>, <gui control name>, <type>)
    # Supported types:
    #     b: boolean checkbox
    #     i0+: nonnegative integer
    #     t: text
    #     tes: text with escaped spaces, using StringOps.escapeForIni
    #     tre: regular expression
    #     ttdf: time/date format
    #     f0+: nonegative float
    #     seli: integer position of a selection in dropdown list
    #     selt: Chosen text in dropdown list
    #     color0: HTML color code or empty
    #     spin: Numeric SpinCtrl
    #
    #     guilang: special choice for GUI language
    #     wikilang: special choice for wiki language

    # ttdf and color0 entries have a 4th item with the name
    #     of the "..." button to call for a dialog to set.
    # selt entries have a list with the internal config names (unicode) of the
    #     possible choices as 4th item.

    _lastShownPanelName = None


    OPTION_TO_CONTROL_GLOBAL = (
            # application-wide options
            ("single_process", "cbSingleProcess", "b"),
            ("zombieCheck", "cbZombieCheck", "b"),
            ("wikiPathes_relative", "cbWikiPathesRelative", "b"),
            ("wikiOpenNew_defaultDir", "tfWikiOpenNewDefaultDir",
                "t"),
            ("collation_order", "chCollationOrder", "selt",
                [u"Default", u"C"]),
            ("collation_uppercaseFirst", "cbCollationUppercaseFirst", "b"),
            ("wikiWord_renameDefault_modifyWikiLinks",
                "cbRenameDefaultModifyLinks", "b"),
            ("wikiWord_renameDefault_renameSubPages",
                "cbRenameDefaultRenameSubPages", "b"),
            ("hotKey_showHide_byApp_isActive", "cbHotKeyShowHideByAppIsActive",
                "b"),
            ("hotKey_showHide_byApp", "tfHotKeyShowHideByApp", "t"),

            ("tempHandling_preferMemory", "cbTempHandlingPreferMemory", "b"),
            ("tempHandling_tempMode", "chTempHandlingTempMode", "selt",
                [u"system", u"config", u"given"]),
            ("tempHandling_tempDir", "tfTempHandlingTempDir", "tdir",
                "btnSelectTempHandlingTempDir"),

            ("showontray", "cbShowOnTray", "b"),
            ("minimize_on_closeButton", "cbMinimizeOnCloseButton", "b"),
            ("mainTabs_switchMruOrder", "cbMainTabsSwitchMruOrder", "b"),
            ("startup_splashScreen_show", "cbStartupSplashScreenShow", "b"),
            ("openWordDialog_askForCreateWhenNonexistingWord",
                "cbOpenWordDialogAskForCreateWhenNonexistingWord", "b"),

            ("pagestatus_timeformat", "tfPageStatusTimeFormat", "ttdf",
                "btnSelectPageStatusTimeFormat"),
            ("gui_language", "chGuiLanguage", "guilang"),
            ("recentWikisList_length", "scRecentWikisListLength", "spin"),

            ("option/user/log_window_autoshow", "cbLogWindowAutoShowUser", "b"),
            ("log_window_autohide", "cbLogWindowAutoHide", "b"),
            ("docStructure_position", "chDocStructurePosition", "seli"),
            ("docStructure_depth", "scDocStructureDepth", "spin"),
            ("docStructure_autohide", "cbDocStructureAutoHide", "b"),
            ("docStructure_autofollow", "cbDocStructureAutoFollow", "b"),


            ("process_autogenerated_areas", "cbProcessAutoGenerated", "b"),
            ("insertions_allow_eval", "cbInsertionsAllowEval", "b"),
#             ("tempFiles_inWikiDir", "cbTempFilesInWikiDir", "b"),
            ("script_security_level", "chScriptSecurityLevel", "seli"),
            ("script_search_reverse", "cbScriptSearchReverse", "b"),


            ("mainTree_position", "chMainTreePosition", "seli"),
            ("viewsTree_position", "chViewsTreePosition", "seli"),
            ("tree_auto_follow", "cbTreeAutoFollow", "b"),
            ("tree_update_after_save", "cbTreeUpdateAfterSave", "b"),
            ("hideundefined", "cbHideUndefinedWords", "b"),
            ("tree_no_cycles", "cbTreeNoCycles", "b"),
            ("tree_autohide", "cbTreeAutoHide", "b"),
            ("tree_bg_color", "tfTreeBgColor", "color0",
                    "btnSelectTreeBgColor"),
            ("tree_font_nativeDesc", "tfTreeFontNativeDesc", "tfont0",
                    "btnSelectTreeFont"),
            ("tree_updateGenerator_minDelay", "tfTreeUpdateGeneratorMinDelay",
                    "f0+"),

            ("start_browser_after_export", "cbStartBrowserAfterExport", "b"),
            ("facename_html_preview", "tfFacenameHtmlPreview", "t"),
            ("html_preview_proppattern_is_excluding",
                    "cbHtmlPreviewProppatternIsExcluding", "b"),
            ("html_preview_proppattern", "tfHtmlPreviewProppattern", "tre"),
            ("html_export_proppattern_is_excluding",
                    "cbHtmlExportProppatternIsExcluding", "b"),
            ("html_export_proppattern", "tfHtmlExportProppattern", "tre"),
            ("html_preview_pics_as_links", "cbHtmlPreviewPicsAsLinks", "b"),
            ("html_export_pics_as_links", "cbHtmlExportPicsAsLinks", "b"),

            ("export_table_of_contents", "chTableOfContents", "seli"),
            ("html_toc_title", "tfHtmlTocTitle", "t"),
            ("html_export_singlePage_sepLineCount",
                    "tfHtmlExportSinglePageSepLineCount", "i0+"),

            ("html_preview_renderer", "chHtmlPreviewRenderer", "seli"),
            ("html_preview_ieShowIframes", "cbHtmlPreviewIeShowIframes", "b"),
            ("html_preview_webkitViKeys", "cbHtmlPreviewWebkitViKeys", "b"),


            ("html_body_link", "tfHtmlLinkColor", "color0",
                "btnSelectHtmlLinkColor"),
            ("html_body_alink", "tfHtmlALinkColor", "color0",
                "btnSelectHtmlALinkColor"),
            ("html_body_vlink", "tfHtmlVLinkColor", "color0",
                "btnSelectHtmlVLinkColor"),
            ("html_body_text", "tfHtmlTextColor", "color0",
                "btnSelectHtmlTextColor"),
            ("html_body_bgcolor", "tfHtmlBgColor", "color0",
                "btnSelectHtmlBgColor"),
            ("html_body_background", "tfHtmlBgImage", "t"),
            ("html_header_doctype", "tfHtmlDocType", "t"),


            ("sync_highlight_byte_limit", "tfSyncHighlightingByteLimit", "i0+"),
            ("async_highlight_delay", "tfAsyncHighlightingDelay", "f0+"),
            ("editor_shortHint_delay", "tfEditorShortHintDelay", "i0+"),
            ("editor_autoUnbullets", "cbAutoUnbullets", "b"),
            ("editor_autoComplete_closingBracket",
                "cbAutoCompleteClosingBracket", "b"),
            ("editor_sync_byPreviewSelection", "cbEditorSyncByPreviewSelection",
                "b"),
            ("editor_colorizeSearchFragments", "cbEditorColorizeSearchFragments", "b"),
            ("attributeDefault_global.wrap_type",
                    "chAttributeDefaultGlobalWrapType", "selt",
                    [
                    u"word",
                    u"char"
                    ]),
            ("editor_tabWidth", "scEditorTabWidth", "spin"),

            ("editor_imageTooltips_localUrls", "cbEditorImageTooltipsLocalUrls",
                "b"),
            ("editor_imageTooltips_maxWidth", "scEditorImageTooltipsMaxWidth",
                "spin"),
            ("editor_imageTooltips_maxHeight", "scEditorImageTooltipsMaxHeight",
                "spin"),

            ("editor_imagePaste_filenamePrefix", "tfEditorImagePasteFilenamePrefix", "t"),
            ("editor_imagePaste_fileType", "chEditorImagePasteFileType", "seli"),
            ("editor_imagePaste_quality", "tfEditorImagePasteQuality", "i0+"),
            ("editor_imagePaste_askOnEachPaste", "cbEditorImagePasteAskOnEachPaste", "b"),
            ("editor_filePaste_prefix", "tfEditorFilePastePrefix", "tes"),
            ("editor_filePaste_middle", "tfEditorFilePasteMiddle", "tes"),
            ("editor_filePaste_suffix", "tfEditorFilePasteSuffix", "tes"),
            ("editor_filePaste_bracketedUrl", "cbEditorFilePasteBracketedUrl", "b"),
            ("userEvent_event/paste/editor/files", "chEditorFilePaste", "selt",
                    [
                    u"action/none",
                    u"action/editor/this/paste/files/insert/url/absolute",
                    u"action/editor/this/paste/files/insert/url/relative",
                    u"action/editor/this/paste/files/insert/url/tostorage",
                    u"action/editor/this/paste/files/insert/url/movetostorage",
                    u"action/editor/this/paste/files/insert/url/ask"
                    ]),

            ("editor_plaintext_color", "tfEditorPlaintextColor", "color0",
                    "btnSelectEditorPlaintextColor"),
            ("editor_link_color", "tfEditorLinkColor", "color0",
                    "btnSelectEditorLinkColor"),
            ("editor_attribute_color", "tfEditorAttributeColor", "color0",
                    "btnSelectEditorAttributeColor"),
            ("editor_bg_color", "tfEditorBgColor", "color0",
                    "btnSelectEditorBgColor"),
            ("editor_selection_fg_color", "tfEditorSelectionFgColor", "color0",
                    "btnSelectEditorSelectionFgColor"),
            ("editor_selection_bg_color", "tfEditorSelectionBgColor", "color0",
                    "btnSelectEditorSelectionBgColor"),
            ("editor_margin_bg_color", "tfEditorMarginBgColor", "color0",
                    "btnSelectEditorMarginBgColor"),
            ("editor_caret_color", "tfEditorCaretColor", "color0",
                    "btnSelectEditorCaretColor"),


            ("mouse_reverseWheelZoom", "cbMouseReverseWheelZoom", "b"),
            ("mouse_middleButton_withoutCtrl", "chMouseMiddleButtonWithoutCtrl", "seli"),
            ("mouse_middleButton_withCtrl", "chMouseMiddleButtonWithCtrl", "seli"),
            ("userEvent_mouse/leftdoubleclick/preview/body", "chMouseDblClickPreviewBody", "selt",
                    [
                    u"action/none",
                    u"action/presenter/this/subcontrol/textedit",
                    u"action/presenter/new/foreground/end/page/this/subcontrol/textedit"
                    ]),

            ("userEvent_mouse/middleclick/pagetab", "chMouseMdlClickPageTab", "selt",
                    [
                    u"action/none",
                    u"action/presenter/this/close",
                    u"action/presenter/this/clone"
                    ]),

            ("userEvent_mouse/leftdrop/editor/files", "chMouseLeftDropEditor", "selt",
                    [
                    u"action/none",
                    u"action/editor/this/paste/files/insert/url/absolute",
                    u"action/editor/this/paste/files/insert/url/relative",
                    u"action/editor/this/paste/files/insert/url/tostorage",
                    u"action/editor/this/paste/files/insert/url/movetostorage",
                    u"action/editor/this/paste/files/insert/url/ask"
                    ]),

            ("userEvent_mouse/leftdrop/editor/files/modkeys/shift", "chMouseLeftDropEditorShift", "selt",
                    [
                    u"action/none",
                    u"action/editor/this/paste/files/insert/url/absolute",
                    u"action/editor/this/paste/files/insert/url/relative",
                    u"action/editor/this/paste/files/insert/url/tostorage",
                    u"action/editor/this/paste/files/insert/url/movetostorage",
                    u"action/editor/this/paste/files/insert/url/ask"
                    ]),

            ("userEvent_mouse/leftdrop/editor/files/modkeys/ctrl", "chMouseLeftDropEditorCtrl", "selt",
                    [
                    u"action/none",
                    u"action/editor/this/paste/files/insert/url/absolute",
                    u"action/editor/this/paste/files/insert/url/relative",
                    u"action/editor/this/paste/files/insert/url/tostorage",
                    u"action/editor/this/paste/files/insert/url/movetostorage",
                    u"action/editor/this/paste/files/insert/url/ask"
                    ]),

            ("timeView_position", "chTimeViewPosition", "seli"),
            ("timeView_dateFormat", "tfTimeViewDateFormat", "ttdf",
                "btnSelectTimeViewDateFormat"),
            ("timeView_autohide", "cbTimeViewAutoHide", "b"),

            ("timeView_showWordListOnHovering",
                    "cbTimeViewShowWordListOnHovering", "b"),
            ("timeView_showWordListOnSelect",
                    "cbTimeViewShowWordListOnSelect", "b"),
            ("timeline_showEmptyDays", "cbTimelineShowEmptyDays", "b"),
            ("timeline_sortDateAscending", "cbTimelineSortDateAscending", "b"),
            ("versioning_dateFormat", "tfVersioningDateFormat", "ttdf",
                "btnSelectVersioningDateFormat"),
            ("wikiWideHistory_dateFormat", "tfWikiWideHistoryDateFormat", "ttdf",
                "btnSelectWikiWideHistoryDateFormat"),

            ("newWikiDefault_editor_text_mode",
                "cbNewWikiDefaultEditorForceTextMode", "b"),
            ("newWikiDefault_wikiPageFiles_asciiOnly",
                "cbNewWikiDefaultWikiPageFilesAsciiOnly", "b"),

            ("search_stripSpaces", "cbSearchStripSpaces", "b"),
            ("search_wiki_searchType", "rboxWwSearchSearchType", "seli"),
            ("search_wiki_caseSensitive", "cbWwSearchCaseSensitive", "b"),
            ("search_wiki_wholeWord", "cbWwSearchWholeWord", "b"),
            ("search_wiki_context_before", "tfWwSearchContextBefore", "i0+"),
            ("search_wiki_context_after", "tfWwSearchContextAfter", "i0+"),
            ("search_wiki_count_occurrences", "cbWwSearchCountOccurrences", "b"),
            ("search_wiki_max_count_occurrences",
                    "tfWwSearchMaxCountOccurrences", "i0+"),

            ("incSearch_autoOffDelay", "tfIncSearchAutoOffDelay", "i0+"),
            ("fastSearch_searchType", "rboxFastSearchSearchType", "seli"),
            ("fastSearch_caseSensitive", "cbFastSearchCaseSensitive", "b"),
            ("fastSearch_wholeWord", "cbFastSearchWholeWord", "b"),


            ("wikiLockFile_ignore", "cbWikiLockFileIgnore", "b"),
            ("wikiLockFile_create", "cbWikiLockFileCreate", "b"),


            ("editor_useImeWorkaround", "cbEditorUseImeWorkaround", "b"),
            ("menu_accels_kbdTranslate", "cbMenuAccelsKbdTranslate", "b"),
            ("search_dontAllowCancel", "cbSearchDontAllowCancel", "b"),
            ("editor_compatibility_ViKeys", "cbEditorCompatibilityViKeys", "b"),
            ("mouse_scrollUnderPointer", "cbMouseScrollUnderPointer", "b"),
            ("html_preview_reduceUpdateHandling",
                    "cbHtmlPreviewReduceUpdateHandling", "b"),

            ("auto_save", "cbAutoSave", "b"),
            ("auto_save_delay_key_pressed", "tfAutoSaveDelayKeyPressed", "i0+"),
            ("auto_save_delay_dirty", "tfAutoSaveDelayDirty", "i0+"),
    )

            # wiki-specific options

# "wiki_wikiLanguage"

#             ("footnotes_as_wikiwords", "cbFootnotesAsWws", "b"),

    OPTION_TO_CONTROL_WIKI = (

            ("export_default_dir", "tfExportDefaultDir", "t"),

            ("tree_expandedNodes_rememberDuration",
                    "chTreeExpandedNodesRememberDuration", "seli"),
            ("indexSearch_enabled", "cbIndexSearchEnabled", "b"),
            ("tabs_maxCharacters", "tfMaxCharactersOnTab", "i0+"),
            ("template_pageNamesRE", "tfTemplatePageNamesRE", "tre"),
            ("tree_force_scratchpad_visibility",
                    "cbTreeForceScratchpadVisibility", "b"),

            ("option/wiki/log_window_autoshow", "cbLogWindowAutoShowWiki", "b3"),

            # The following three need special handling on dialog construction
            ("wikiPageFiles_asciiOnly", "cbWikiPageFilesAsciiOnly", "b"),
            ("wikiPageFiles_maxNameLength", "tfWikiPageFilesMaxNameLength", "i0+"),
            ("wikiPageFiles_gracefulOutsideAddAndRemove",
                    "cbWikiPageFilesGracefulOutsideAddAndRemove", "b"),

            ("wikiPageFiles_writeFileMode",
                    "chWikiPageFilesWriteFileMode", "seli"),

            ("wiki_icon", "tfWikiIcon", "t"),
            ("hotKey_showHide_byWiki", "tfHotKeyShowHideByWiki", "t"),

            ("trashcan_maxNoOfBags", "tfTrashcanMaxNoOfBags", "i0+"),
            ("trashcan_askOnDelete", "cbTrashcanAskOnDelete", "b"),
            ("trashcan_storageLocation", "chTrashcanStorageLocation", "seli"),

            ("first_wiki_word", "tfFirstWikiWord", "t"),
            ("wiki_onOpen_rebuild", "chWikiOnOpenRebuild", "seli"),
            ("wiki_onOpen_tabsSubCtrl", "chWikiOnOpenTabsSubCtrl", "selt",
                    [
                    u"",
                    u"preview",
                    u"textedit"
                    ]),

            ("wikiPageTitlePrefix", "tfWikiPageTitlePrefix", "t"),
            ("wikiPageTitle_headingLevel", "scWikiPageTitleHeadingLevel" , "spin"),

            ("wikiPageTitle_creationMode", "chWikiPageTitleCreationMode", "seli"),
            ("wikiPageTitle_fromLinkTitle", "cbWikiPageTitleFromLinkTitle", "b"),
            ("headingsAsAliases_depth", "scHeadingsAsAliasesDepth", "spin"),

            ("versioning_storageLocation", "chVersioningStorageLocation", "seli"),
            ("versioning_completeSteps", "tfVersioningCompleteSteps", "i0+"),
            ("tabHistory_maxEntries", "tfTabHistoryMaxEntries", "i0+"),
            ("wikiWideHistory_maxEntries", "tfWikiWideHistoryMaxEntries", "i0+"),

            ("wiki_wikiLanguage", "chWikiWikiLanguage", "wikilang"),

            ("fileStorage_identity_modDateMustMatch", "cbFsModDateMustMatch", "b"),
            ("fileStorage_identity_filenameMustMatch", "cbFsFilenameMustMatch", "b"),
            ("fileStorage_identity_modDateIsEnough", "cbFsModDateIsEnough", "b"),
            ("fileSignature_timeCoarsening", "tfFileSignatureTimeCoarsening",
                    "f0+"),
            ("editor_text_mode", "cbEditorForceTextMode", "b"),
    )
    
    # Sequence of control names only enabled for wiki data backends which create
    # one file per page.
    CONTROLS_FILE_PER_PAGE_WIKI = (
            "cbWikiPageFilesAsciiOnly",
            "tfWikiPageFilesMaxNameLength",
            "cbWikiPageFilesGracefulOutsideAddAndRemove",
            "chWikiPageFilesWriteFileMode",
            "chTrashcanStorageLocation",
            "chVersioningStorageLocation",
            "cbEditorForceTextMode",
    )



    # Clipboard catcher specific options
    OPTION_TO_CONTROL_CLIPBOARD_CATCHER = (
            ("clipboardCatcher_prefix", "tfClipboardCatcherPrefix", "t"),
            ("clipboardCatcher_suffix", "tfClipboardCatcherSuffix", "t"),
            ("clipboardCatcher_filterDouble", "cbClipboardCatcherFilterDouble",
                    "b"),
            ("clipboardCatcher_userNotification", "chClipCatchUserNotification", "seli"),
            ("clipboardCatcher_soundFile", "tfClipCatchSoundFile", "t")
    )

    # Non-Windows specific options
    OPTION_TO_CONTROL_NON_WINDOWS_ONLY = (
            ("fileLauncher_path", "tfFileLauncherPath", "t"),
    )


    DEFAULT_PANEL_LIST = (
            ("OptionsPageApplication", N_(u"Application")),
            ("OptionsPageUserInterface", 2 * u" " + N_(u"User interface")),
            ("OptionsPageSecurity", 2 * u" " + N_(u"Security")),
            ("OptionsPageTree", 2 * u" " + N_(u"Tree")),
            ("OptionsPageHtml", 2 * u" " + N_(u"HTML preview/export")),
            ("OptionsPageHtmlHeader", 4 * u" " + N_(u"HTML header")),
            ("OptionsPageEditor", 2 * u" " + N_(u"Editor")),
            ("OptionsPageEditorPasteDrop", 4 * u" " + N_(u"Editor Paste/Drag'n'Drop")),
            ("OptionsPageEditorColors", 4 * u" " + N_(u"Editor Colors")),
            ("OptionsPageClipboardCatcher", 4 * u" " + N_(u"Clipboard Catcher")),
            ("OptionsPageFileLauncher", 2 * u" " + N_(u"File Launcher")),
            ("OptionsPageMouse", 2 * u" " + N_(u"Mouse")),
            ("OptionsPageChronView", 2 * u" " + N_(u"Chron. view")),
            ("OptionsPageSearching", 2 * u" " + N_(u"Searching")),
            ("OptionsPageNewWikiDefaults", 2 * u" " + N_(u"New wiki defaults")),
            ("OptionsPageAdvanced", 2 * u" " + N_(u"Advanced")),
            ("OptionsPageAdvTiming", 4 * u" " + N_(u"Timing")),
            ("OptionsPageAutosave", 4 * u" " + N_(u"Autosave")),
            ("??switch mark/current wiki/begin", u""),
            ("OptionsPageCurrentWiki", N_(u"Current Wiki")),
            ("OptionsPageCwOnOpen", 2 * u" " + N_(u"On Open")),
            ("OptionsPageCwHeadings", 2 * u" " + N_(u"Headings")),
            ("OptionsPageCwChronological", 2 * u" " + N_(u"Chronological")),
            ("OptionsPageCwWikiLanguage", 2 * u" " + N_(u"Wiki language")),
            ("??insert mark/current wiki/wiki lang", u""),
            ("OptionsPageCwAdvanced", 2 * u" " + N_(u"Advanced")),
            ("??insert mark/current wiki", u""),
            ("??switch mark/current wiki/end", u"")
    )

    def __init__(self, pWiki, ID, startPanelName=None, title="Options",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):
        d = wx.PreDialog()
        self.PostCreate(d)

        self.pWiki = pWiki
        self.oldSettings = {}
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "OptionsDialog")

        self.combinedOptionToControl = self.OPTION_TO_CONTROL_GLOBAL

        if self.pWiki.isWikiLoaded():
            self.combinedOptionToControl += self.OPTION_TO_CONTROL_WIKI

        # Hold own copy, it may need modification
        self.combinedPanelList = wx.GetApp().getOptionsDlgPanelList()[:]
        # Maps ids of the GUI controls named in self.combinedOptionToControl
        # to the entries (the appropriate tuple) there
        self.idToOptionEntryMap = {}

        # Add additional option depending on OS and environment
        if OsAbstract.supportsClipboardInterceptor():
            self.combinedOptionToControl += self.OPTION_TO_CONTROL_CLIPBOARD_CATCHER

        if not SystemInfo.isWindows():
            self.combinedOptionToControl += self.OPTION_TO_CONTROL_NON_WINDOWS_ONLY

        if not self.pWiki.isWikiLoaded():
            # Remove wiki-bound setting pages
            try:
                del self.combinedPanelList[self.combinedPanelList.index(
                        ("??switch mark/current wiki/begin", u"")) :
                        self.combinedPanelList.index(
                        ("??switch mark/current wiki/end", u""))]
            except ValueError:
                pass


        # Rewrite panel list depending on OS and environment
        newPL = []

        for e in self.combinedPanelList:
            if isinstance(e[0], basestring):
                if e[0] == "OptionsPageFileLauncher" and SystemInfo.isWindows():
                    # For Windows the OS-function is used, for other systems
                    # we need the path to an external script
                    continue
                elif e[0] == "OptionsPageClipboardCatcher" and \
                        not OsAbstract.supportsClipboardInterceptor():
                    continue
                elif e[0].startswith("??"):
                    # Entry is only a mark for inserting of panels from plugins so skip it
                    continue

            newPL.append(e)

        self.combinedPanelList = newPL

        self.ctrls = XrcControls(self)

        self.emptyPanel = None

        self.panelList = []
        self.ctrls.lbPages.Clear()


        mainsizer = LayerSizer()  # wx.BoxSizer(wx.VERTICAL)

        for pn, pt in self.combinedPanelList:
            indPt, textPt = splitIndent(pt)
            pt = indPt + _(textPt)
            if isinstance(pn, basestring):
                if pn != "":
                    panel = ResourceOptionsPanel(self.ctrls.panelPages, pn)
                else:
                    if self.emptyPanel is None:
                        # Necessary to avoid a crash
                        self.emptyPanel = DefaultOptionsPanel(self.ctrls.panelPages)
                    panel = self.emptyPanel
            else:
                # Factory function or class
                panel = pn(self.ctrls.panelPages, self, self.pWiki)

            self.panelList.append(panel)
            self.ctrls.lbPages.Append(pt)
            mainsizer.Add(panel)


        self.ctrls.panelPages.SetSizer(mainsizer)
        self.ctrls.panelPages.SetMinSize(mainsizer.GetMinSize())

        self.ctrls.panelPages.Fit()
        self.Fit()

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        # Special options to be prepared before transferring to dialog
        
        # HTML renderer (OS specific)
        self.ctrls.chHtmlPreviewRenderer.optionsDialog_clientData = [0]
        if WikiHtmlView.WikiHtmlViewIE is not None:
            self.ctrls.chHtmlPreviewRenderer.Append(_(u"IE"))
            self.ctrls.chHtmlPreviewRenderer.optionsDialog_clientData.append(1)
            self.ctrls.chHtmlPreviewRenderer.Append(_(u"Mozilla"))
            self.ctrls.chHtmlPreviewRenderer.optionsDialog_clientData.append(2)

        if WikiHtmlView.WikiHtmlViewWK is not None:
            self.ctrls.chHtmlPreviewRenderer.Append(_(u"Webkit"))
            self.ctrls.chHtmlPreviewRenderer.optionsDialog_clientData.append(3)

        if WikiHtmlView.WikiHtmlView2 is not None:
            self.ctrls.chHtmlPreviewRenderer.Append(_(u"Webview"))
            self.ctrls.chHtmlPreviewRenderer.optionsDialog_clientData.append(4)

        self.ctrls.chHtmlPreviewRenderer.Enable(
                len(self.ctrls.chHtmlPreviewRenderer.optionsDialog_clientData) > 1)

        # Reorderable paste type list
        
        # Retrieve default and configured paste order
        defPasteOrder = self.pWiki.getConfig().getDefault("main",
                "editor_paste_typeOrder").split(";")
        pasteOrder = self.pWiki.getConfig().get("main",
                "editor_paste_typeOrder", "").split(";")

        # Use default paste order to constrain which items are allowed and
        # necessary in configured paste order
        pasteOrder = Utilities.seqEnforceContained(pasteOrder, defPasteOrder)
        
        pasteLabels = [WikiTxtCtrl.getHrNameForPasteType(pasteType)
                for pasteType in pasteOrder]
        
        self.ctrls.rlPasteTypeOrder.SetLabelsAndClientDatas(pasteLabels,
                pasteOrder)
                
        # Transfer options to dialog
        for oct in self.combinedOptionToControl:
            o, c, t = oct[:3]
            self.idToOptionEntryMap[self.ctrls[c].GetId()] = oct
            self.oldSettings[o] = self.pWiki.getConfig().get("main", o)

            if t == "b":   # boolean field = checkbox
                self.ctrls[c].SetValue(
                        self.pWiki.getConfig().getboolean("main", o))
            elif t == "b3":   # boolean field = checkbox
                value = self.pWiki.getConfig().get("main", o)
                if value == "Gray":
                    self.ctrls[c].Set3StateValue(wx.CHK_UNDETERMINED)
                else:
                    if strToBool(value):
                        self.ctrls[c].Set3StateValue(wx.CHK_CHECKED)
                    else:
                        self.ctrls[c].Set3StateValue(wx.CHK_UNCHECKED)

#                 self.ctrls[c].SetValue(
#                         self.pWiki.getConfig().getboolean("main", o))
            elif t in ("t", "tre", "ttdf", "tfont0", "tdir", "i0+", "f0+",
                    "color0"):  # text field or regular expression field
                self.ctrls[c].SetValue(
                        uniToGui(self.pWiki.getConfig().get("main", o)) )
            elif t == "tes":  # Text escaped
                self.ctrls[c].SetValue(
                        unescapeForIni(uniToGui(self.pWiki.getConfig().get(
                        "main", o))) )
            elif t == "seli":   # Selection -> transfer index
                sel = self.pWiki.getConfig().getint("main", o)
                if hasattr(self.ctrls[c], "optionsDialog_clientData"):
                    # There is client data to take instead of real selection
                    try:
                        sel = self.ctrls[c].optionsDialog_clientData.index(sel)
                    except (IndexError, ValueError):
                        sel = 0
                self.ctrls[c].SetSelection(sel)
            elif t == "selt":   # Selection -> transfer content string
                try:
                    idx = oct[3].index(self.pWiki.getConfig().get("main", o))
                    self.ctrls[c].SetSelection(idx)
                except (IndexError, ValueError):
                    self.ctrls[c].SetStringSelection(
                        uniToGui(self.pWiki.getConfig().get("main", o)) )
            elif t == "spin":   # Numeric SpinCtrl -> transfer number
                self.ctrls[c].SetValue(
                        self.pWiki.getConfig().getint("main", o))
            elif t == "guilang":   # GUI language choice
                # First fill choice with options
                self.ctrls[c].Append(_(u"Default"))
                for ls, lt in Localization.getLangList():
                    self.ctrls[c].Append(lt)

                # Then select previous setting
                optValue = self.pWiki.getConfig().get("main", o)
                self.ctrls[c].SetSelection(
                        Localization.findLangListIndex(optValue) + 1)
            elif t == "wikilang":   # wiki language choice
                # Fill choice with options and find previous selection
                optValue = self.pWiki.getConfig().get("main", o)
                sel = -1
                for i, ld in enumerate(
                        wx.GetApp().listWikiLanguageDescriptions()):
                    self.ctrls[c].Append(ld[1])
                    if ld[0] == optValue:
                        sel = i

                if sel > -1:
                    # Then select previous setting
                    self.ctrls[c].SetSelection(sel)

            # Register events for "..." buttons
            if t in ("color0", "ttdf", "tfont0", "tdir"):
                params = oct[3:]
                if len(params) > 0:
                    # params[0] is name of the "..." button after the text field
                    dottedButtonId = self.ctrls[params[0]].GetId()
                    self.idToOptionEntryMap[dottedButtonId] = oct

                    wx.EVT_BUTTON(self, dottedButtonId,
                            self.OnDottedButtonPressed)

        # Options with special treatment
        self.ctrls.cbNewWindowWikiUrl.SetValue(
                self.pWiki.getConfig().getint("main",
                "new_window_on_follow_wiki_url") != 0)

        wikiDocument = self.pWiki.getWikiDocument()
        if wikiDocument is not None:
            self.ctrls.cbWikiReadOnly.SetValue(
                    wikiDocument.getWriteAccessDeniedByConfig())

            fppCap = wikiDocument.getWikiData().checkCapability("filePerPage")

            for c in self.CONTROLS_FILE_PER_PAGE_WIKI:
                getattr(self.ctrls, c).Enable(fppCap is not None)

#             self.ctrls.cbWikiPageFilesAsciiOnly.Enable(fppCap is not None)
#             self.ctrls.tfWikiPageFilesMaxNameLength.Enable(fppCap is not None)
#             self.ctrls.cbWikiPageFilesGracefulOutsideAddAndRemove.Enable(
#                     fppCap is not None)
#             self.ctrls.chTrashcanStorageLocation.Enable(
#                     fppCap is not None)
#             self.ctrls.chVersioningStorageLocation.Enable(
#                     fppCap is not None)
#             self.ctrls.cbEditorForceTextMode.Enable(
#                     fppCap is not None)

        self.OnUpdateUiAfterChange(None)


        # Now show the right panel
        self.activePageIndex = -1
        for panel in self.panelList:
            panel.Show(False)
            panel.Enable(False)

        if startPanelName is None:
            startPanelName = OptionsDialog._lastShownPanelName

        if not self.selectPanelByName(startPanelName):
            self.ctrls.lbPages.SetSelection(0)
            self._refreshForPage()

        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_LISTBOX(self, GUI_ID.lbPages, self.OnLbPages)
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)


        wx.EVT_BUTTON(self, GUI_ID.btnSelectFaceHtmlPrev, self.OnSelectFaceHtmlPrev)

        wx.EVT_BUTTON(self, GUI_ID.btnSelectClipCatchSoundFile,
                lambda evt: self.selectFile(self.ctrls.tfClipCatchSoundFile,
                _(u"Wave files (*.wav)|*.wav")))

        wx.EVT_BUTTON(self, GUI_ID.btnSelectExportDefaultDir,
                lambda evt: self.selectDirectory(self.ctrls.tfExportDefaultDir))

        wx.EVT_BUTTON(self, GUI_ID.btnSelectWikiOpenNewDefaultDir,
                lambda evt: self.selectDirectory(
                self.ctrls.tfWikiOpenNewDefaultDir))

        wx.EVT_BUTTON(self, GUI_ID.btnSelectFileLauncherPath,
                lambda evt: self.selectFile(self.ctrls.tfFileLauncherPath,
                _(u"All files (*.*)|*")))

        wx.EVT_BUTTON(self, GUI_ID.btnPasteTypeOrderUp,
                lambda evt: self.ctrls.rlPasteTypeOrder.MoveSelectedUp())

        wx.EVT_BUTTON(self, GUI_ID.btnPasteTypeOrderDown,
                lambda evt: self.ctrls.rlPasteTypeOrder.MoveSelectedDown())


        wx.EVT_CHOICE(self, GUI_ID.chTempHandlingTempMode,
                self.OnUpdateUiAfterChange)

        wx.EVT_CHECKBOX(self, GUI_ID.cbEditorImageTooltipsLocalUrls,
                self.OnUpdateUiAfterChange)
        wx.EVT_CHOICE(self, GUI_ID.chEditorImagePasteFileType,
                self.OnUpdateUiAfterChange)

        wx.EVT_CHOICE(self, GUI_ID.chHtmlPreviewRenderer,
                self.OnUpdateUiAfterChange)

        wx.EVT_CHECKBOX(self, GUI_ID.cbWwSearchCountOccurrences,
                self.OnUpdateUiAfterChange)

        wx.EVT_CHECKBOX(self, GUI_ID.cbSingleProcess,
                self.OnUpdateUiAfterChange)


    def _refreshForPage(self):
        if self.activePageIndex > -1:
            panel = self.panelList[self.activePageIndex]
            if not panel.setVisible(False):
                self.ctrls.lbPages.SetSelection(self.activePageIndex)
                return

            panel.Show(False)
            panel.Enable(False)

        self.activePageIndex = self.ctrls.lbPages.GetSelection()

        panel = self.panelList[self.activePageIndex]
        panel.setVisible(True)  # Not checking return value here

        # Enable appropriate addit. options panel
        panel.Enable(True)
        panel.Show(True)


    def selectPanelByName(self, panelName):
        if panelName is None:
            return False

        for i, e in enumerate(self.combinedPanelList):
            if e[0] == panelName:
                self.ctrls.lbPages.SetSelection(i)
                self._refreshForPage()
                return True

        return False


    def getMainControl(self):
        return self.pWiki

    def OnLbPages(self, evt):
        self._refreshForPage()
        evt.Skip()


    def OnOk(self, evt):
        fieldsValid = True

        # First check validity of field contents
        for oct in self.combinedOptionToControl:
            o, c, t = oct[:3]

            if t == "tre":
                # Regular expression field, test if re is valid
                try:
                    rexp = guiToUni(self.ctrls[c].GetValue())
                    re.compile(rexp, re.DOTALL | re.UNICODE | re.MULTILINE)
                    self.ctrls[c].SetBackgroundColour(wx.WHITE)
                except:   # TODO Specific exception
                    fieldsValid = False
                    self.ctrls[c].SetBackgroundColour(wx.RED)
            elif t == "i0+":
                # Nonnegative integer field
                try:
                    val = int(guiToUni(self.ctrls[c].GetValue()))
                    if val < 0:
                        raise ValueError
                    self.ctrls[c].SetBackgroundColour(wx.WHITE)
                except ValueError:
                    fieldsValid = False
                    self.ctrls[c].SetBackgroundColour(wx.RED)
            elif t == "f0+":
                # Nonnegative float field
                try:
                    val = float(guiToUni(self.ctrls[c].GetValue()))
                    if val < 0:
                        raise ValueError
                    self.ctrls[c].SetBackgroundColour(wx.WHITE)
                except ValueError:
                    fieldsValid = False
                    self.ctrls[c].SetBackgroundColour(wx.RED)
            elif t == "color0":
                # HTML Color field or empty field
                val = guiToUni(self.ctrls[c].GetValue())
                rgb = colorDescToRgbTuple(val)

                if val != "" and rgb is None:
                    self.ctrls[c].SetBackgroundColour(wx.RED)
                    fieldsValid = False
                else:
                    self.ctrls[c].SetBackgroundColour(wx.WHITE)
            elif t == "spin":
                # SpinCtrl
                try:
                    val = self.ctrls[c].GetValue()
                    if val < self.ctrls[c].GetMin() or \
                            val > self.ctrls[c].GetMax():
                        raise ValueError
                    self.ctrls[c].SetBackgroundColour(wx.WHITE)
                except ValueError:
                    fieldsValid = False
                    self.ctrls[c].SetBackgroundColour(wx.RED)


        if not fieldsValid:
            self.Refresh()
            return

        # Check each panel
        for i, panel in enumerate(self.panelList):
            if not panel.checkOk():
                # One panel has a problem (probably invalid data)
                self.ctrls.lbPages.SetSelection(i)
                self._refreshForPage()
                return


        # Options with special treatment (before standard handling)
        wikiDocument = self.pWiki.getWikiDocument()

        if wikiDocument is not None and not self.ctrls.cbWikiReadOnly.GetValue():
            wikiDocument.setWriteAccessDeniedByConfig(False)

        config = self.pWiki.getConfig()

        # Then transfer options from dialog to config object
        for oct in self.combinedOptionToControl:
            o, c, t = oct[:3]

            # TODO Handle unicode text controls
            if t == "b":
                config.set("main", o, repr(self.ctrls[c].GetValue()))
            elif t == "b3":
                value = self.ctrls[c].Get3StateValue()
                if value == wx.CHK_UNDETERMINED:
                    config.set("main", o, "Gray")
                elif value == wx.CHK_CHECKED:
                    config.set("main", o, "True")
                elif value == wx.CHK_UNCHECKED:
                    config.set("main", o, "False")

            elif t in ("t", "tre", "ttdf", "tfont0", "tdir", "i0+", "f0+", "color0"):
                config.set( "main", o, guiToUni(self.ctrls[c].GetValue()) )
            elif t == "tes":
                config.set( "main", o, guiToUni(
                        escapeForIni(self.ctrls[c].GetValue(), toEscape=u" ")) )
            elif t == "seli":   # Selection -> transfer index
                sel = self.ctrls[c].GetSelection()
                if hasattr(self.ctrls[c], "optionsDialog_clientData"):
                    # There is client data to take instead of real selection
                    sel = self.ctrls[c].optionsDialog_clientData[sel]
                config.set("main", o, unicode(sel))
            elif t == "selt":   # Selection -> transfer content string
                try:
                    config.set("main", o, oct[3][self.ctrls[c].GetSelection()])
                except IndexError:
                    config.set("main", o,
                            guiToUni(self.ctrls[c].GetStringSelection()))
            elif t == "spin":   # Numeric SpinCtrl -> transfer number
                config.set( "main", o, unicode(self.ctrls[c].GetValue()) )
            elif t == "guilang":    # GUI language choice
                idx = self.ctrls[c].GetSelection()
                if idx < 1:
                    config.set("main", o, u"")
                else:
                    config.set("main", o,
                            Localization.getLangList()[idx - 1][0])

            elif t == "wikilang":    # GUI language choice
                idx = self.ctrls[c].GetSelection()
                config.set("main", o,
                        wx.GetApp().listWikiLanguageDescriptions()[idx][0])

        # Options with special treatment (after standard handling)
        if self.ctrls.cbNewWindowWikiUrl.GetValue():
            config.set("main", "new_window_on_follow_wiki_url", "1")
        else:
            config.set("main", "new_window_on_follow_wiki_url", "0")

        if wikiDocument is not None and self.ctrls.cbWikiReadOnly.GetValue():
            wikiDocument.setWriteAccessDeniedByConfig(True)
            
        # Store paste type order
        config.set("main", "editor_paste_typeOrder",
                ";".join(self.ctrls.rlPasteTypeOrder.GetClientDatas()))

        # Ok for each panel
        for panel in self.panelList:
            panel.handleOk()

        config.informChanged(self.oldSettings)

        if self.activePageIndex > -1:
            OptionsDialog._lastShownPanelName = self.combinedPanelList[
                    self.activePageIndex][0]

        evt.Skip()


    def getOldSettings(self):
        return self.oldSettings


    def OnSelectFaceHtmlPrev(self, evt):
        dlg = FontFaceDialog(self, -1, self.pWiki,
                self.ctrls.tfFacenameHtmlPreview.GetValue())
        if dlg.ShowModal() == wx.ID_OK:
            self.ctrls.tfFacenameHtmlPreview.SetValue(dlg.GetValue())
        dlg.Destroy()

#     def OnSelectPageStatusTimeFormat(self, evt):
#         dlg = DateformatDialog(self, -1, self.pWiki,
#                 deffmt=self.ctrls.tfPageStatusTimeFormat.GetValue())
#         if dlg.ShowModal() == wx.ID_OK:
#             self.ctrls.tfPageStatusTimeFormat.SetValue(dlg.GetValue())
#         dlg.Destroy()


    def OnUpdateUiAfterChange(self, evt):
        """
        Some controls must be updated (esp. dis-/enabled) after a change.
        """
        # If temp. handling is set to "given" directory, field to enter
        # directory must be enabled
        enabled = self.ctrls.chTempHandlingTempMode.GetSelection() == 2
        self.ctrls.tfTempHandlingTempDir.Enable(enabled)
        self.ctrls.btnSelectTempHandlingTempDir.Enable(enabled)

        # Dimensions of image preview tooltips can only be set if tooltips are
        # enabled
        enabled = self.ctrls.cbEditorImageTooltipsLocalUrls.GetValue()
        self.ctrls.scEditorImageTooltipsMaxWidth.Enable(enabled)
        self.ctrls.scEditorImageTooltipsMaxHeight.Enable(enabled)

        # If image should be pasted as JPEG, quality can be set
        enabled = self.ctrls.chEditorImagePasteFileType.GetSelection() == 2
        self.ctrls.tfEditorImagePasteQuality.Enable(enabled)

        # If HTML preview is not internal one, allow to set if iframes should
        # be shown inside the preview
        self.ctrls.cbHtmlPreviewIeShowIframes.Enable(
                self.ctrls.chHtmlPreviewRenderer.GetSelection() > 0)

        # If occurrences of search terms are counted, allow to set maximum
        # number to count up to
        self.ctrls.tfWwSearchMaxCountOccurrences.Enable(
                self.ctrls.cbWwSearchCountOccurrences.GetValue())

        # If single process mode checked, allow to check for other
        # WikidPad processes already running
        self.ctrls.cbZombieCheck.Enable(self.ctrls.cbSingleProcess.GetValue())





    def OnDottedButtonPressed(self, evt):
        """
        Called when a "..." button is pressed (for some of them) to show
        an alternative way to specify the input, e.g. showing a color selector
        for color entries instead of using the bare text field
        """
        oct = self.idToOptionEntryMap[evt.GetId()]
        o, c, t = oct[:3]
        params = oct[3:]

        if t == "color0":
            self.selectColor(self.ctrls[c])
        elif t == "ttdf":   # Date/time format
            self.selectDateTimeFormat(self.ctrls[c])
        elif t == "tfont0":   # Font or empty
            self.selectFont(self.ctrls[c])
        elif t == "tdir":
            self.selectDirectory(self.ctrls[c])


    def selectColor(self, tfield):
        rgb = colorDescToRgbTuple(tfield.GetValue())
        if rgb is None:
            rgb = 0, 0, 0

        color = wx.Colour(*rgb)
        colordata = wx.ColourData()
        colordata.SetColour(color)

        dlg = wx.ColourDialog(self, colordata)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                color = dlg.GetColourData().GetColour()
                if color.Ok():
                    tfield.SetValue(
                            rgbToHtmlColor(color.Red(), color.Green(),
                            color.Blue()))
        finally:
            dlg.Destroy()


    def selectDirectory(self, tfield):
        seldir = wx.DirSelector(_(u"Select Directory"),
                tfield.GetValue(),
                style=wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON, parent=self)

        if seldir:
            tfield.SetValue(seldir)

    def selectFile(self, tfield, wildcard=u""):
        selfile = wx.FileSelector(_(u"Select File"),
                tfield.GetValue(), wildcard = wildcard + u"|" + \
                        _(u"All files (*.*)|*"),
                flags=wx.OPEN, parent=self)

        if selfile:
            tfield.SetValue(selfile)

    def selectDateTimeFormat(self, tfield):
        dlg = DateformatDialog(self, -1, self.pWiki,
                deffmt=tfield.GetValue())
        try:
            if dlg.ShowModal() == wx.ID_OK:
                tfield.SetValue(dlg.GetValue())
        finally:
            dlg.Destroy()


    def selectFont(self, tfield):
        fontDesc = tfield.GetValue()

        # if fontDesc != u"":
        font = wx.SystemSettings_GetFont(wx.SYS_DEFAULT_GUI_FONT)

        # wx.Font()    # 1, wx.FONTFAMILY_DEFAULT,

        font.SetNativeFontInfoUserDesc(fontDesc)

        newFont = wx.GetFontFromUser(self, font)  # , const wxString& caption = wxEmptyString)
        if newFont is not None and newFont.IsOk():
            tfield.SetValue(newFont.GetNativeFontInfoUserDesc())

#             GetNativeFontInfoUserDesc
#             SetNativeFontInfoUserDesc




