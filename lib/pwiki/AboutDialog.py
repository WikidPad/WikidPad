from wxPython.wx import *
from wxPython.html import *

from StringOps import escapeHtml


class AboutDialog(wxDialog):
    """ An about box that uses an HTML window """

    textTemplate = '''
<html>
<body bgcolor="#FFFFFF">
    <center>
        <table bgcolor="#CCCCCC" width="100%%" cellspacing="0" cellpadding="0" border="1">
            <tr>
                <td align="center"><h2>wikidPad 1.7beta7</h2></td>
            </tr>
        </table>

        <p>
wikidPad is a Wiki-like notebook for storing your thoughts, ideas, todo lists, contacts, or anything else you can think of to write down.
What makes wikidPad different from other notepad applications is the ease with which you can cross-link your information.        </p>        
        <br><br>

        <table border=0 cellpadding=1 cellspacing=0>
            <tr><td width="30%%" align="right"><font size="3"><b>Author:</b></font></td><td nowrap><font size="3">Michael Butscher</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Email:</b></font></td><td nowrap><font size="3">mbutscher@gmx.de</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>URL:</b></font></td><td nowrap><font size="3">http://mbutscher.cybton.com/software.html</font></td></tr>
            <tr><td width="30%%" align="right">&nbsp;</td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Author:</b></font></td><td nowrap><font size="3">Jason Horman</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Email:</b></font></td><td nowrap><font size="3">wikidpad@jhorman.org</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>URL:</b></font></td><td nowrap><font size="3">http://www.jhorman.org/wikidPad/</font></td></tr>
            <tr><td width="30%%" align="right">&nbsp;</td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Author:</b></font></td><td nowrap><font size="3">Gerhard Reitmayr</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Email:</b></font></td><td nowrap><font size="3">gerhard.reitmayr@gmail.com</font></td></tr>
        </table>
    </center>
    
    <hr />
    
    <p />Your configuration directory is: %s
</body>
</html>
'''

    def __init__(self, pWiki):
        wxDialog.__init__(self, pWiki, -1, 'About WikidPad',
                          size=(470, 330) )
        text = self.textTemplate % (escapeHtml(pWiki.globalConfigDir),)

        html = wxHtmlWindow(self, -1)
        html.SetPage(text)
        button = wxButton(self, wxID_OK, "Okay")

        # constraints for the html window
        lc = wxLayoutConstraints()
        lc.top.SameAs(self, wxTop, 5)
        lc.left.SameAs(self, wxLeft, 5)
        lc.bottom.SameAs(button, wxTop, 5)
        lc.right.SameAs(self, wxRight, 5)
        html.SetConstraints(lc)

        # constraints for the button
        lc = wxLayoutConstraints()
        lc.bottom.SameAs(self, wxBottom, 5)
        lc.centreX.SameAs(self, wxCentreX)
        lc.width.AsIs()
        lc.height.AsIs()
        button.SetConstraints(lc)

        self.SetAutoLayout(True)
        self.Layout()
        self.CentreOnParent(wxBOTH)

