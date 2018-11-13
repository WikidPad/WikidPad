from pwiki.StringOps import urlFromPathname, strftimeUB

def now():
    return strftimeUB("%x %I:%M %p")

def addDateTime(editor):
    return editor.AddText(now())

def date():
    return strftimeUB("%x")

def addDate(editor):
    return editor.AddText(date())

def time():
    return strftimeUB("%I:%M %p")

def addTime(editor):
    return editor.AddText(time())

def encodeSelection(editor):
    text = editor.GetSelectedText()
    url = urlFromPathname(text)
    editor.ReplaceSelection("file:%s" % url)
