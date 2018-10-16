#! /usr/bin/env python3
# -*- coding: iso-8859-1 -*-
# Originally written by Barry Warsaw <barry@python.org>
#
# Minimally patched to make it even more xgettext compatible
# by Peter Funk <pf@artcom-gmbh.de>
#
# 2002-11-22 Jürgen Hermann <jh@web.de>
# Added checks that _() only contains string literals, and
# command line args are resolved to module lists, i.e. you
# can now pass a filename, a module or package name, or a
# directory (including globbing chars, important for Win32).
# Made docstring fit in 80 chars wide displays using pydoc.
# 
# 2007-11-04 Michael Butscher <mbutscher@gmx.de>
# Specialized version for WikidPad which can update existing po files
# and reads strings from XRC files


# # for selftesting
# try:
#     import fintl
#     _ = fintl.gettext
# except ImportError:
#     _ = lambda s: s

__doc__ = ("""pygettext -- Python equivalent of xgettext(1)

Many systems (Solaris, Linux, Gnu) provide extensive tools that ease the
internationalization of C programs. Most of these tools are independent of
the programming language and can be used from within Python programs.
Martin von Loewis' work[1] helps considerably in this regard.

There's one problem though; xgettext is the program that scans source code
looking for message strings, but it groks only C (or C++). Python
introduces a few wrinkles, such as dual quoting characters, triple quoted
strings, and raw strings. xgettext understands none of this.

Enter pygettext, which uses Python's standard tokenize module to scan
Python source code, generating .pot files identical to what GNU xgettext[2]
generates for C and C++ code. From there, the standard GNU tools can be
used.

A word about marking Python strings as candidates for translation. GNU
xgettext recognizes the following keywords: gettext, dgettext, dcgettext,
and gettext_noop. But those can be a lot of text to include all over your
code. C and C++ have a trick: they use the C preprocessor. Most
internationalized C source includes a #define for gettext() to _() so that
what has to be written in the source is much less. Thus these are both
translatable strings:

    gettext("Translatable String")
    _("Translatable String")

Python of course has no preprocessor so this doesn't work so well.  Thus,
pygettext searches only for _() by default, but see the -k/--keyword flag
below for how to augment this.

 [1] http://www.python.org/workshops/1997-10/proceedings/loewis.html
 [2] http://www.gnu.org/software/gettext/gettext.html

NOTE: pygettext attempts to be option and feature compatible with GNU
xgettext where ever possible. However some options are still missing or are
not fully implemented. Also, xgettext's use of command line switches with
option arguments is broken, and in these cases, pygettext just defines
additional switches.

Usage: pygettext [options] inputfile ...

Options:

    -a
    --extract-all
        Extract all strings.

    -d name
    --default-domain=name
        Rename the default output file from messages.pot to name.pot.

    -E
    --escape
        Replace non-ASCII characters with octal escape sequences.

    -D
    --docstrings
        Extract module, class, method, and function docstrings.  These do
        not need to be wrapped in _() markers, and in fact cannot be for
        Python to consider them docstrings. (See also the -X option).

    -h
    --help
        Print this help message and exit.

    -k word
    --keyword=word
        Keywords to look for in addition to the default set, which are:
        %(DEFAULTKEYWORDS)s

        You can have multiple -k flags on the command line.

    -K
    --no-default-keywords
        Disable the default set of keywords (see above).  Any keywords
        explicitly added with the -k/--keyword option are still recognized.

    --no-location
        Do not write filename/lineno location comments.

    -n
    --add-location
        Write filename/lineno location comments indicating where each
        extracted string is found in the source.  These lines appear before
        each msgid.  The style of comments is controlled by the -S/--style
        option.  This is the default.

    -o filename
    --output=filename
        Rename the default output file from messages.pot to filename.  If
        filename is `-' then the output is sent to standard out.

    -p dir
    --output-dir=dir
        Output files will be placed in directory dir.

    -S stylename
    --style stylename
        Specify which style to use for location comments.  Two styles are
        supported:

        Solaris  # File: filename, line: line-number
        GNU      #: filename:line

        The style name is case insensitive.  GNU style is the default.

    -u filename
    --update=filename
        Update an existing .po file by adding new, unknown strings and
        updating the location comments

    --xrc=filename
        Name of .xrc file to search for additional strings
    
    -v
    --verbose
        Print the names of the files being processed.

    -V
    --version
        Print the version of pygettext and exit.

    -w columns
    --width=columns
        Set width of output to columns.

    -x filename
    --exclude-file=filename
        Specify a file that contains a list of strings that are not be
        extracted from the input files.  Each string to be excluded must
        appear on a line by itself in the file.

    -X filename
    --no-docstrings=filename
        Specify a file that contains a list of files (one per line) that
        should not have their docstrings extracted.  This is only useful in
        conjunction with the -D option above.

If `inputfile' is -, standard input is read.
""")

import os
import imp
import sys
import glob
import time
import getopt
import token
import tokenize
import operator
import codecs
from xml.dom import minidom
from codecs import BOM_UTF8


from msgfmt import buildMessageDict
from functools import reduce

__version__ = '1.5mod'

default_keywords = ['_', 'N_']
DEFAULTKEYWORDS = ', '.join(default_keywords)

EMPTYSTRING = ''



# The normal pot-file header. msgmerge and Emacs's po-mode work better if it's
# there.
pot_header = '''\
# SOME DESCRIPTIVE TITLE.
# Copyright (C) YEAR ORGANIZATION
# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.
#
msgid ""
msgstr ""
"Project-Id-Version: PACKAGE VERSION\\n"
"POT-Creation-Date: %(time)s\\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"
"Language-Team: LANGUAGE <LL@li.org>\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: ENCODING\\n"
"Generated-By: pygettext.py %(version)s\\n"

'''


def usage(code, msg=''):
    print(__doc__ % globals(), file=sys.stderr)
    if msg:
        print(msg, file=sys.stderr)
    sys.exit(code)


ESCAPES = {}

for i in range(32):
    ESCAPES[chr(i)] = "\\%03o" % i

ESCAPES['\\'] = '\\\\'
ESCAPES['\t'] = '\\t'
ESCAPES['\r'] = '\\r'
ESCAPES['\n'] = '\\n'
ESCAPES['\"'] = '\\"'




# escapes = []
# 
# def make_escapes(esc):
#     global escapes
# 
#     for i in range(0, 32):
#         escapes.append("\\%03o" % i)
#     
#     for i in range(32, 128):
#         escapes.append(chr(i))
#         
#     if esc:
#         for i in range(128, 256):
#             escapes.append("\\%03o" % i)
#     else:
#         for i in range(128, 256):
#             escapes.append(chr(i))
# 
#     escapes[ord('\\')] = '\\\\'
#     escapes[ord('\t')] = '\\t'
#     escapes[ord('\r')] = '\\r'
#     escapes[ord('\n')] = '\\n'
#     escapes[ord('\"')] = '\\"'
        
#     if pass_iso8859:
#         # Allow iso-8859 characters to pass through so that e.g. 'msgid
#         # "Höhe"' would not result in 'msgid "H\366he"'.  Otherwise we
#         # escape any character outside the 32..126 range.
#         mod = 128
#     else:
#         mod = 256
#     for i in range(256):
#         if 32 <= (i % mod) <= 126:
#             escapes.append(chr(i))
#         else:
#             escapes.append("\\%03o" % i)


# def escape(s):
#     global escapes
#     s = list(s)
#     for i in range(len(s)):
#         s[i] = escapes[ord(s[i])]
#     return EMPTYSTRING.join(s)



def escape(s, dummy_encoding):
    s = list(s)
    for i in range(len(s)):
        s[i] = ESCAPES.get(s[i], s[i])
        
    return EMPTYSTRING.join(s)



def safe_eval(s):
    # unwrap quotes, safely
    return eval(s, {'__builtins__':{}}, {})


def normalize(s, encoding):
    # This converts the various Python string types into a format that is
    # appropriate for .po files, namely much closer to C style.
    lines = s.split('\n')
    if len(lines) == 1:
        s = '"' + escape(s, encoding) + '"'
    else:
        if not lines[-1]:
            del lines[-1]
            lines[-1] = lines[-1] + '\n'
        for i in range(len(lines)):
            lines[i] = escape(lines[i], encoding)
        lineterm = '\\n"\n"'
#         s = u'""\n"' + lineterm.join(lines) + '"'
        s = '"' + lineterm.join(lines) + '"'
    return s


def containsAny(str, set):
    """Check whether 'str' contains ANY of the chars in 'set'"""
    return 1 in [c in str for c in set]


# def _visit_pyfiles(list, dirname, names):
#     """Helper for getFilesForName()."""
#     # get extension for python source files
#     if '_py_ext' not in globals():
#         global _py_ext
#         _py_ext = [triple[0] for triple in imp.get_suffixes()
#                    if triple[2] == imp.PY_SOURCE][0]
# 
#     print("--_visit_pyfiles11", repr(_py_ext))
# 
#     # don't recurse into CVS directories
#     if 'CVS' in names:
#         names.remove('CVS')
# 
#     # add all *.py files to list
#     list.extend(
#         [os.path.join(dirname, file) for file in names
#          if os.path.splitext(file)[1] == _py_ext]
#         )


def _get_modpkg_path(dotted_name, pathlist=None):
    """Get the filesystem path for a module or a package.

    Return the file system path to a file for a module, and to a directory for
    a package. Return None if the name is not found, or is a builtin or
    extension module.
    """
    # split off top-most name
    parts = dotted_name.split('.', 1)

    if len(parts) > 1:
        # we have a dotted path, import top-level package
        try:
            file, pathname, description = imp.find_module(parts[0], pathlist)
            if file: file.close()
        except ImportError:
            return None

        # check if it's indeed a package
        if description[2] == imp.PKG_DIRECTORY:
            # recursively handle the remaining name parts
            pathname = _get_modpkg_path(parts[1], [pathname])
        else:
            pathname = None
    else:
        # plain name
        try:
            file, pathname, description = imp.find_module(
                dotted_name, pathlist)
            if file:
                file.close()
            if description[2] not in [imp.PY_SOURCE, imp.PKG_DIRECTORY]:
                pathname = None
        except ImportError:
            pathname = None

    return pathname


def getFilesForName(name):
    """Get a list of module files for a filename, a module or package name,
    or a directory.
    """
    if not os.path.exists(name):
        # check for glob chars
        if containsAny(name, "*?[]"):
            files = glob.glob(name)
            list = []
            for file in files:
                list.extend(getFilesForName(file))
            return list

        # try to find module or package
        name = _get_modpkg_path(name)
        if not name:
            return []

    if os.path.isdir(name):
        if '_py_ext' not in globals():
            global _py_ext
            _py_ext = [triple[0] for triple in imp.get_suffixes()
                       if triple[2] == imp.PY_SOURCE][0]

        # find all python files in directory
        list = []
        
        for dirpath, dirnames, filenames in os.walk(name):
            # don't recurse into CVS directories
            if 'CVS' in dirnames:
                dirnames.remove('CVS')

            # add all *.py files to list
            list.extend(
                [os.path.join(dirpath, file) for file in filenames
                 if os.path.splitext(file)[1] == _py_ext]
                )
        
        return list
    elif os.path.exists(name):
        # a single file
        return [name]

    return []


class MessageContainer:
    def __init__(self, options):
        self.__options = options
        self.__messages = {}
        
    
    def addentry(self, msg, curfile, lineno=0, isdocstring=0):
        if not msg in self.__options.toexclude:
            entry = (curfile, lineno)
            self.__messages.setdefault(msg, {})[entry] = isdocstring


    def write(self, stwr, presetMessages=None):
        global pot_header
        
        if presetMessages is None:
            presetMessages = {}
        options = self.__options
        timestamp = str(time.strftime('%Y-%m-%d %H:%M'))  # +%Z'
        # The time stamp in the header doesn't have the same format as that
        # generated by xgettext...
        header = presetMessages.get("")
        if header:
            stwr.write('msgid ""\n')
            stwr.write('msgstr %s\n\n' % normalize(header, 'UTF-8'))
        else:
            stwr.write((pot_header + '\n') %
                    {'time': timestamp, 'version': __version__})

        # Sort the entries.  First sort each particular entry's keys, then
        # sort all the entries by their first item.
        reverse = {}
        for k, v in list(self.__messages.items()):
            keys = list(v.keys())
            keys.sort()
            reverse.setdefault(tuple(keys), []).append((k, v))
        rkeys = list(reverse.keys())
        rkeys.sort()
        for rkey in rkeys:
            rentries = reverse[rkey]
            rentries.sort()
            for k, v in rentries:
                isdocstring = 0
                # If the entry was gleaned out of a docstring, then add a
                # comment stating so.  This is to aid translators who may wish
                # to skip translating some unimportant docstrings.
                if reduce(operator.__add__, list(v.values())):
                    isdocstring = 1
                # k is the message string, v is a dictionary-set of (filename,
                # lineno) tuples.  We want to sort the entries in v first by
                # file name and then by line number.
                v = list(v.keys())
                v.sort()
                if not options.writelocations:
                    pass
                # location comments are different b/w Solaris and GNU:
                elif options.locationstyle == options.SOLARIS:
                    for filename, lineno in v:
                        d = {'filename': filename, 'lineno': lineno}
                        stwr.write(
                                '# File: %(filename)s, line: %(lineno)d\n' % d)
                elif options.locationstyle == options.GNU:
                    # fit as many locations on one line, as long as the
                    # resulting line length doesn't exceeds 'options.width'
                    locline = '#:'
                    for filename, lineno in v:
                        d = {'filename': filename, 'lineno': lineno}
                        s = ' %(filename)s:%(lineno)d' % d
                        if len(locline) + len(s) <= options.width:
                            locline = locline + s
                        else:
                            stwr.write(locline + '\n')
                            locline = "#:" + s
                    if len(locline) > 2:
                        stwr.write(locline + '\n')
                if isdocstring:
                    stwr.write('#, docstring\n')
                stwr.write('msgid %s\n' % normalize(k, 'UTF-8'))

                if k in presetMessages:
                    stwr.write('msgstr %s\n\n' % normalize(presetMessages[k], 'UTF-8'))
                else:
                    stwr.write('msgstr ""\n\n')



class TokenEater:
    def __init__(self, options, messageContainer):
        self.__options = options
        self.__messageContainer = messageContainer
        self.__state = self.__waiting
        self.__data = []
        self.__lineno = -1
        self.__freshmodule = 1
        self.__curfile = None

    def __call__(self, ttype, tstring, stup, etup, line):
        # dispatch
##        import token
##        print >> sys.stderr, 'ttype:', token.tok_name[ttype], \
##              'tstring:', tstring
        self.__state(ttype, tstring, stup[0])

    def __waiting(self, ttype, tstring, lineno):
        opts = self.__options
        # Do docstring extractions, if enabled
        if opts.docstrings and not opts.nodocstrings.get(self.__curfile):
            # module docstring?
            if self.__freshmodule:
                if ttype == tokenize.STRING:
                    self.__addentry(safe_eval(tstring), lineno, isdocstring=1)
                    self.__freshmodule = 0
                elif ttype not in (tokenize.COMMENT, tokenize.NL):
                    self.__freshmodule = 0
                return
            # class docstring?
            if ttype == tokenize.NAME and tstring in ('class', 'def'):
                self.__state = self.__suiteseen
                return
        if ttype == tokenize.NAME and tstring in opts.keywords:
            self.__state = self.__keywordseen

    def __suiteseen(self, ttype, tstring, lineno):
        # ignore anything until we see the colon
        if ttype == tokenize.OP and tstring == ':':
            self.__state = self.__suitedocstring

    def __suitedocstring(self, ttype, tstring, lineno):
        # ignore any intervening noise
        if ttype == tokenize.STRING:
            self.__addentry(safe_eval(tstring), lineno, isdocstring=1)
            self.__state = self.__waiting
        elif ttype not in (tokenize.NEWLINE, tokenize.INDENT,
                           tokenize.COMMENT):
            # there was no class docstring
            self.__state = self.__waiting

    def __keywordseen(self, ttype, tstring, lineno):
        if ttype == tokenize.OP and tstring == '(':
            self.__data = []
            self.__lineno = lineno
            self.__state = self.__openseen
        else:
            self.__state = self.__waiting

    def __openseen(self, ttype, tstring, lineno):
        if ttype == tokenize.OP and tstring == ')':
            # We've seen the last of the translatable strings.  Record the
            # line number of the first line of the strings and update the list
            # of messages seen.  Reset state for the next batch.  If there
            # were no strings inside _(), then just ignore this entry.
            if self.__data:
                self.__addentry(EMPTYSTRING.join(self.__data))
            self.__state = self.__waiting
        elif ttype == tokenize.STRING:
            self.__data.append(safe_eval(tstring))
        elif ttype not in [tokenize.COMMENT, token.INDENT, token.DEDENT,
                           token.NEWLINE, tokenize.NL]:
            # warn if we see anything else than STRING or whitespace
            print((
                '*** %(file)s:%(lineno)s: Seen unexpected token "%(token)s"'
                ) % {
                'token': tstring,
                'file': self.__curfile,
                'lineno': self.__lineno
                }, file=sys.stderr)
            self.__state = self.__waiting

    def __addentry(self, msg, lineno=None, isdocstring=0):
        if lineno is None:
            lineno = self.__lineno
            
        self.__messageContainer.addentry(msg, self.__curfile, lineno,
                isdocstring)
            
#         if not msg in self.__options.toexclude:
#             entry = (self.__curfile, lineno)
#             self.__messages.setdefault(msg, {})[entry] = isdocstring

    def set_filename(self, filename):
        self.__curfile = filename
        self.__freshmodule = 1

    def write(self, stwr, presetMessages=None):
        self.__messageContainer.write(stwr, presetMessages)
        
        
#         global pot_header
#         
#         if presetMessages is None:
#             presetMessages = {}
#         options = self.__options
#         timestamp = time.strftime('%Y-%m-%d %H:%M+%Z')
#         # The time stamp in the header doesn't have the same format as that
#         # generated by xgettext...
#         header = presetMessages.get("")
#         if header:
#             print >> fp, 'msgid ""'
#             print >> fp, 'msgstr %s\n' % normalize(header)
#         else:
#             print >> fp, pot_header % {'time': timestamp, 'version': __version__}
#         # Sort the entries.  First sort each particular entry's keys, then
#         # sort all the entries by their first item.
#         reverse = {}
#         for k, v in self.__messages.items():
#             keys = v.keys()
#             keys.sort()
#             reverse.setdefault(tuple(keys), []).append((k, v))
#         rkeys = reverse.keys()
#         rkeys.sort()
#         for rkey in rkeys:
#             rentries = reverse[rkey]
#             rentries.sort()
#             for k, v in rentries:
#                 isdocstring = 0
#                 # If the entry was gleaned out of a docstring, then add a
#                 # comment stating so.  This is to aid translators who may wish
#                 # to skip translating some unimportant docstrings.
#                 if reduce(operator.__add__, v.values()):
#                     isdocstring = 1
#                 # k is the message string, v is a dictionary-set of (filename,
#                 # lineno) tuples.  We want to sort the entries in v first by
#                 # file name and then by line number.
#                 v = v.keys()
#                 v.sort()
#                 if not options.writelocations:
#                     pass
#                 # location comments are different b/w Solaris and GNU:
#                 elif options.locationstyle == options.SOLARIS:
#                     for filename, lineno in v:
#                         d = {'filename': filename, 'lineno': lineno}
#                         print >>fp, \
#                             '# File: %(filename)s, line: %(lineno)d' % d
#                 elif options.locationstyle == options.GNU:
#                     # fit as many locations on one line, as long as the
#                     # resulting line length doesn't exceeds 'options.width'
#                     locline = '#:'
#                     for filename, lineno in v:
#                         d = {'filename': filename, 'lineno': lineno}
#                         s = ' %(filename)s:%(lineno)d' % d
#                         if len(locline) + len(s) <= options.width:
#                             locline = locline + s
#                         else:
#                             print >> fp, locline
#                             locline = "#:" + s
#                     if len(locline) > 2:
#                         print >> fp, locline
#                 if isdocstring:
#                     print >> fp, '#, docstring'
#                 print >> fp, 'msgid', normalize(k)
#                 
#                 if presetMessages.has_key(k):
#                     print >> fp, 'msgstr %s\n' % normalize(presetMessages[k])
#                 else:
#                     print >> fp, 'msgstr ""\n'



def main(argv):
    global default_keywords
    try:
        opts, args = getopt.getopt(
            argv,
            'ad:DEhk:Kno:p:S:u:Vvw:x:X:',
            ['extract-all', 'default-domain=', 'escape', 'help',
             'keyword=', 'no-default-keywords',
             'add-location', 'no-location', 'output=', 'output-dir=', 'no-output',
             'xrc=', 'style=', 'update=', 'verbose', 'version', 'width=',
             'exclude-file=', 'docstrings', 'no-docstrings'
             ])
    except getopt.error as msg:
        usage(1, msg)

    # for holding option values
    class Options:
        # constants
        GNU = 1
        SOLARIS = 2
        # defaults
        extractall = 0 # FIXME: currently this option has no effect at all.
        escape = 0
        keywords = []
        outpath = ''
        outfile = 'messages.pot'
        xrcfiles = []
        updatefiles = []
        writelocations = 1
        locationstyle = GNU
        verbose = 0
        width = 78
        excludefilename = ''
        docstrings = 0
        nodocstrings = {}

    options = Options()
    locations = {'gnu' : options.GNU,
                 'solaris' : options.SOLARIS,
                 }

    # parse options
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage(0)
        elif opt in ('-a', '--extract-all'):
            options.extractall = 1
        elif opt in ('-d', '--default-domain'):
            options.outfile = arg + '.pot'
        elif opt in ('-E', '--escape'):
            options.escape = 1
        elif opt in ('-D', '--docstrings'):
            options.docstrings = 1
        elif opt in ('-k', '--keyword'):
            options.keywords.append(arg)
        elif opt in ('-K', '--no-default-keywords'):
            default_keywords = []
        elif opt in ('-n', '--add-location'):
            options.writelocations = 1
        elif opt in ('--no-location',):
            options.writelocations = 0
        elif opt in ('-S', '--style'):
            options.locationstyle = locations.get(arg.lower())
            if options.locationstyle is None:
                usage(1, 'Invalid value for --style: %s' % arg)
        elif opt in ('-o', '--output'):
            options.outfile = arg
        elif opt in ('-p', '--output-dir'):
            options.outpath = arg
        elif opt in ('--no-output', ):
            options.outfile = None            
        elif opt in ('-u', '--update'):
            options.updatefiles.append(arg)
        elif opt in ('-v', '--verbose'):
            options.verbose = 1
        elif opt in ('-V', '--version'):
            print('pygettext.py (xgettext for Python) %s' % __version__)
            sys.exit(0)
        elif opt in ('-w', '--width'):
            try:
                options.width = int(arg)
            except ValueError:
                usage(1, '--width argument must be an integer: %s' % arg)
        elif opt in ('--xrc'):
            options.xrcfiles.append(arg)
        elif opt in ('-x', '--exclude-file'):
            options.excludefilename = arg
        elif opt in ('-X', '--no-docstrings'):
            fp = open(arg)
            try:
                while 1:
                    line = fp.readline()
                    if not line:
                        break
                    options.nodocstrings[line[:-1]] = 1
            finally:
                fp.close()

#     # calculate escapes
#     make_escapes(options.escape)

    # calculate all keywords
    options.keywords.extend(default_keywords)

    # initialize list of strings to exclude
    if options.excludefilename:
        try:
            fp = open(options.excludefilename)
            options.toexclude = fp.readlines()
            fp.close()
        except IOError:
            print((
                "Can't read --exclude-file: %s") % options.excludefilename, file=sys.stderr)
            sys.exit(1)
    else:
        options.toexclude = []

    # resolve args to module lists
    expanded = []
    for arg in args:
        if arg == '-':
            expanded.append(arg)
        else:
            expanded.extend(getFilesForName(arg))
    args = expanded

    msgContainer = MessageContainer(options)

    # slurp through all the files
    eater = TokenEater(options, msgContainer)
    for filename in args:
        if filename == '-':
            if options.verbose:
                print('Reading standard input')
            fp = sys.stdin.buffer
            closep = 0
        else:
            if options.verbose:
                print('Working on %s' % filename)
            fp = open(filename, 'rb')
            closep = 1
        try:
            eater.set_filename(filename)
            try:
                tokens = tokenize.tokenize(fp.readline)
                for _token in tokens:
                    eater(*_token)
            except tokenize.TokenError as e:
                print('%s: %s, line %d, column %d' % (
                    e.args[0], filename, e.args[1][0], e.args[1][1]),
                    file=sys.stderr)
        finally:
            if closep:
                fp.close()
                
                
    # If xrc files are added, go through them, too
    # Not the fastest method but the simplest
    for xf in options.xrcfiles:
        fp = open(xf, 'r')
        content = fp.read()
        fp.close()
        
        xmlDoc = minidom.parseString(content)
        elementsContainingText = xmlDoc.getElementsByTagName("label") + \
                xmlDoc.getElementsByTagName("title") + \
                xmlDoc.getElementsByTagName("item")
        
        for le in elementsContainingText:
            childs = le.childNodes
            if len(childs) != 1:
                continue
                
            child = childs[0]
            if child.nodeType != child.TEXT_NODE:
                continue
            
            msgContainer.addentry(child.data, xf, lineno=0, isdocstring=0)


    # write the output to main output file
    if options.outfile is not None:
        if options.outfile == '-':
            fp = sys.stdout
            closep = 0
        else:
            if options.outpath:
                options.outfile = os.path.join(options.outpath, options.outfile)
            
            # Binary output as codec writer handles line-end conversion
            fp = open(options.outfile, 'wb')
            closep = 1
        try:
            fp.write(BOM_UTF8)
            stwr = codecs.getwriter('utf-8')(fp)
            msgContainer.write(stwr)
            stwr.reset()
        finally:
            if closep:
                fp.close()

    for updfile in options.updatefiles:
        utfMode = False
        try:
            f = open(updfile, "rU")
#             bom = f.read(len(BOM_UTF8))
#             utfMode = bom == BOM_UTF8  # TODO seek 0 on not UTF
            utfMode = True

            presetMessages = buildMessageDict(updfile)
        except IOError:
            presetMessages = {}

        # Binary output as codec writer handles line-end conversion
        fp = open(updfile, 'wb')
        try:
            if utfMode:
                fp.write(BOM_UTF8)
            stwr = codecs.getwriter('utf-8')(fp)
            msgContainer.write(stwr, presetMessages)
            stwr.reset()
        finally:
            fp.close()



if __name__ == '__main__':
    main(sys.argv[1:])


#     # some more test strings
#     _(u'a unicode string')
#     # this one creates a warning
#     _('*** Seen unexpected token "%(token)s"') % {'token': 'test'}
#     _('more' 'than' 'one' 'string')
