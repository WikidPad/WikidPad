from time import strftime
import pwiki.urllib_red as urllib

def now():
    return strftime("%x %I:%M %p")

def addDateTime(editor):
    return editor.AddText(now())

def date():
    return strftime("%x")

def addDate(editor):
    return editor.AddText(date())

def time():
    return strftime("%I:%M %p")

def addTime(editor):
    return editor.AddText(time())

def encodeSelection(editor):
    text = editor.GetSelectedText()
    url = urllib.pathname2url(text)
    editor.ReplaceSelection("file:%s" % url)
