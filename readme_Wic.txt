This is the readme file for WikidpadCompact.



++ CHANGELOG


+++ Version 1.5.5 beta3 (2005-12-29)

No further separate changelog, see the ChangeLog in the help wiki instead.



+++ Version 1.5.5 unicode beta2 (2005-12-20)

    New features:

    * Basic table support. Example:

<<|
here| nowhere| somewhere
else| where?| elsewhere
>>

    * Option to forbid cycles in trees
    * Option to filter properties to show in HTML preview and export
    * Exporting of wiki files does not use brackets in filenames anymore
      (brackets are no more used since WikidPad original 1.20beta3).

    A few bugs fixed. Among others:
        * Wrong lineendings in clipboard
        * Missing RE prevents wrap text from work
        * Creation of new wikis and importing doesn't work (wrong formatver)


+++ Version 1.5.5 unicode beta (2005-11-09)

Warning: Version uses new database format, make backups of
important data!

    New features:

    * Possibility to delete multiple wiki pages in
      some dialogs (e.g. in "parentless nodes")
    * Much better "Search wiki" dialog
    * Options to control tree behaviour better
      (e.g. automatic updating of tree icons)

    Fixed bug:

    * WikiWord and [WikiWord] were different words


+++ Version 1.5 unicode beta (2005-11-09)

    New features:

    * Integrated HTML preview of a page
    * Option to control font face of HTML preview


+++ Version 1.4.5 unicode (2005-11-08)

    This version is now claimed to be final, some minor bugs
    were removed since the first beta.


+++ Version 1.4.5 unicode beta (2005-09-16)

    This is a beta version, but mainly because of the rewritten
    HTML/XML export


    Known problems:

    * Versions stored before 1.4 may be corrupted
      (but the versioning feature is experimental anyway!)

    New features:

    * Rewritten HTML/XML export. Slower, but clearer, so further changes
      should be much simpler to do. Asian languages shouldn't be a problem
      anymore (I hope)
    * Option to use new window when following a "wiki:" URL (was default)
      or to reuse the already open window instead
    * Arbitrary nested todo and property entries in the View tree
    * Arbitrary alphanumeric characters (as defined by unicode consortium)
      in non-camelCase wiki words. Exception: Words consisting of digits
      only (e.g. "[42]") are not allowed.
    * Menu plugin (shortcut: Shift-Ctrl-N) to create new nodes which
      have the name "[New123456]" where "123456" is a unique number. Helpful
      if you want to store some text snippets in the wiki but think about
      the wiki page name later. The plugin file is "autoNew.py" in the
      "extension" directory, if you want to edit or delete it.



+++ Version 1.4 unicode (2005-08-29)

    This is the first full unicode version!

    Known problems:

    * HTML export may not work correctly for Asian languages
    * Earlier stored versions may be corrupted
      (but the versioning feature is experimental anyway!)

    New features:

    * Add menu and toolbar items as Python plugins (no documentation yet, but
      example in extensions/referrals.py). Written by Gerhard Reitmayr for
      original WikidPad.
    * "Wikize word" function. Written by endura29 and Gerhard Reitmayr.


+++ Version 1.3.1 (2005-07-30)

    Fixed bugs:

    * Updating old formats failed if versioning data existed
    * No autocomplete for non camelCase words and properties
    * Problems with non-existing wikiwords in the tree


+++ Version 1.3 (2005-07-27)

    Fixed bugs:

    * After creating new wiki in "Minimize to Tray" mode, an error about
      a missing icon appeared
    * Renaming wiki words did not work
    * Words in database are in UTF-8 now. Previous databases
      are converted automatically (but make a backup, just to be sure!)


    New features:

    * Set an arbitrary word as root of the tree
    * Auto-generated areas: Format an area as auto-generated and set a Python
      expression which will be evaluated each time the page is shown and the
      result will be presented in the area.
    * Creation date is (again) recorded for newly created pages. "Created"
      means here also to import a .wiki page file into the database for a
      not yet existing page.
    * Option "Start browser after export" to control if browser should
      start after exporting (parts of) the wiki to HTML/XML


    Other changes:

    * The mouse pointer changes to a hand over WikiWords if Ctrl is
      pressed
    * Database has a "settings" table with key/value rows which store
      database format version and a branch tag (if somebody creates his
      own version of Wic, he/she should change the tag)
    * Searching the wiki is a bit faster now
    * Additional module sqlite3api which tries to fulfill the Python
      DB-API 2.0. WikiData.py now uses that, but needs yet a few
      functions from the non-conforming SqliteThin3.py.

      pysqlite is not used, sorry.



+++ Version 1.2 (2005-07-20)

    Fixed bugs:

    * "Vacuum Wiki" crashed Wic
    * Exporter cutted of first character of bold text
    * Exporting XML didn't work


    New Features:

    * "Minimize to Tray" option
    * "Hide undefined WikiWords in Tree"
    * "Low resource usage" option
    * Open WikiWord can also create new parentless words
    * Option to set date format for "Insert Date"


    Other changes:

    * Database structure changed (prior databases are changed automatically,
      after that, they are incompatible to previous versions)
    * Creation date of wiki pages is not saved any longer. The creation date
      written in XML output is meaningless
    * Wiki-Syntax changed for "no highlighting" areas


+++ Version 1.1

    New Features:

    * "Replace Text by WikiWord" function


    Other changes:

    * Now also Windows installer provided


+++ Version 1.0

Initial version derived from WikidPad 1.15

    * Uses Sqlite instead of Gadfly
    * Stores wiki pages in a single database file
    * License-free ugly icon set used


