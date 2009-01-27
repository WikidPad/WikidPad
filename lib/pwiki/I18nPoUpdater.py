# -*- coding: iso-8859-1 -*-

# Some code taken from the pygettext and msgfmt utilities which are part
# of standard Python installation

import codecs

import Localization


# Similar to functions in StringOps, but copied here to reduce dependencies
def loadEntireTxtFile(filename):
    """
    Load entire file (text mode) and return its content.
    """
    rf = open(filename, "rU")
    try:
        result = rf.read()
        return result
    finally:
        rf.close()


def writeEntireTxtFile(filename, content):
    """
    Write entire file (text mode).
    """
    rf = open(filename, "w")
    try:
        rf.write(content)
        return
    finally:
        rf.close()



EMPTYSTRING = u''


ESCAPES = {}

for i in xrange(32):
    ESCAPES[unichr(i)] = u"\\%03o" % i

ESCAPES[u'\\'] = u'\\\\'
ESCAPES[u'\t'] = u'\\t'
ESCAPES[u'\r'] = u'\\r'
ESCAPES[u'\n'] = u'\\n'
ESCAPES[u'\"'] = u'\\"'


def _escape(s):
    s = list(s)
    for i in range(len(s)):
        s[i] = ESCAPES.get(s[i], s[i])
        
    return EMPTYSTRING.join(s)


def _normalize(s):
    # This converts the various Python string types into a format that is
    # appropriate for .po files, namely much closer to C style.
    lines = s.split(u'\n')
    if len(lines) == 1:
        s = u'"' + _escape(s) + u'"'
    else:
        if not lines[-1]:
            del lines[-1]
            lines[-1] = lines[-1] + u'\n'
        for i in range(len(lines)):
            lines[i] = _escape(lines[i])
        lineterm = u'\\n"\n"'
#         s = u'""\n"' + lineterm.join(lines) + '"'
        s = u'"' + lineterm.join(lines) + '"'
    return s



def refreshPot(potFilename, presetMessages):
    messages = {}
    result = []

    def add(id, ustr, fuzzy):
        "Add a non-fuzzy translation to the result."
        ustr = presetMessages.get(id, ustr)

        if not fuzzy:
            result.append(u'msgid %s' % _normalize(id))

            if ustr:
                result.append(u'msgstr %s\n' % _normalize(ustr))
            else:
                result.append(u'msgstr ""\n')


    if potFilename.endswith('.po') or potFilename.endswith('.pot'):
        infile = potFilename
    else:
        infile = potFilename + '.pot'

    try:
        content = loadEntireTxtFile(infile)
        content = content.decode("utf-8")
        lines = content.split(u"\n")

#         lines = codecs.open(infile, "rt", "utf-8").readlines()
    except IOError, msg:
#         print >> sys.stderr, msg
        raise

    # Strip BOM
    if len(lines) > 0 and lines[0].startswith(u"\ufeff"):
        lines[0] = lines[0][1:]

    ID = 1
    STR = 2

    section = None
    fuzzy = 0

    # Parse the catalog
    lno = 0
    for line in lines:
#         if line.endswith(u"\n"):
#             line = line[:-1]

        l = line
        lno += 1
        # If we get a comment line after a msgstr, this is a new entry
        if l[:1] == u'#' and section == STR:
            add(msgid, msgstr, fuzzy)
            section = None
            fuzzy = 0
        # Record a fuzzy mark
        if l[:2] == u'#,' and u'fuzzy' in l:
            fuzzy = 1
        # Skip comments
        if l[:1] == u'#':
            result.append(line)
            continue
        # Now we are in a msgid section, output previous section
        if l.startswith(u'msgid'):
            if section == STR:
                add(msgid, msgstr, fuzzy)
            section = ID
            l = l[5:]
            msgid = msgstr = u''
        # Now we are in a msgstr section
        elif l.startswith(u'msgstr'):
            section = STR
            l = l[6:]
        # Skip empty lines
        l = l.strip()
        if not l:
            if section is None:
                result.append(line)
            continue
        # XXX: Does this always follow Python escape semantics?
#         print "eval", repr(l)
        l = eval(l)
        if type(l) is str:
            l = l.decode("utf-8")

        if section == ID:
            msgid += l
        elif section == STR:
#             print "code", repr((msgstr, l))
            msgstr += l
        else:
            print >> sys.stderr, 'Syntax error on %s:%d' % (infile, lno), \
                  'before:'
            print >> sys.stderr, l
            raise SyntaxError('Syntax error on %s:%d' % (infile, lno) + 
                    ' before: ' + l)
            # sys.exit(1)
    # Add last entry
    if section == STR:
        add(msgid, msgstr, fuzzy)
        
    return u"\n".join(result) + u"\n"




def main(args):
    presetMessages = Localization.buildMessageDict(args[0])
    newContent = refreshPot(args[1], presetMessages)
    newContent = newContent.encode("utf-8")
    writeEntireTxtFile(args[0], newContent)


