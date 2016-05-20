# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - MoinMoin.parser.wiki Tests

    TODO: these are actually parser+formatter tests. We should have
    parser only tests here.

    @copyright: 2003-2004 by J�rgen Hermann <jh@web.de>
    @license: GNU GPL, see COPYING for details.
"""

import unittest
import re
from MoinMoin._tests import request, TestConfig
from MoinMoin.Page import Page
from MoinMoin.parser.wiki import Parser


class ParagraphsTestCase(unittest.TestCase):
    """ Test paragraphs creating

    All tests ignoring white space in output
    """

    def testFirstParagraph(self):
         """ parser.wiki: first paragraph should be in <p> """
         result = parse('First')
         expected = re.compile(r'<p>\s*First\s*</p>')
         self.assert_(expected.search(result),
                      '"%s" not in "%s"' % (expected.pattern, result))

    def testEmptyLineBetweenParagraphs(self):
        """ parser.wiki: empty line separates paragraphs """
        result = parse('First\n\nSecond')
        expected = re.compile(r'<p>\s*Second\s*</p>')
        self.assert_(expected.search(result),
                     '"%s" not in "%s"' % (expected.pattern, result))
        
    def testParagraphAfterBlockMarkup(self):
        """ parser.wiki: create paragraph after block markup """

        markup = (
            '----\n',
            '[[en]]\n',
            '|| table ||\n',
            '= heading 1 =\n',
            '== heading 2 ==\n',
            '=== heading 3 ===\n',
            '==== heading 4 ====\n',
            '===== heading 5 =====\n',
            )
        for item in markup:
            text = item + 'Paragraph'
            result = parse(text)
            expected = re.compile(r'<p>\s*Paragraph\s*</p>')
            self.assert_(expected.search(result),
                         '"%s" not in "%s"' % (expected.pattern, result))


class HeadingsTestCase(unittest.TestCase):
    """ Test various heading problems """

    def setUp(self):
        """ Require show_section_numbers = 0 to workaround counter
        global state saved in request.
        """
        self.config = TestConfig(show_section_numbers=0)
    
    def tearDown(self):
        del self.config

    def testIgnoreWhiteSpaceAroundHeadingText(self):
        """ parser.wiki: ignore white space around heading text

        See bug: TableOfContentsBreakOnExtraSpaces.

        Does not test mapping of '=' to h number, or valid html markup.
        """
        tests = (
            '=  head =\n', # leading
            '= head  =\n', # trailing
            '=  head  =\n' # both
                 )
        expected = parse('= head =')
        for test in tests:            
            result = parse(test)
            self.assertEqual(result, expected,
                'Expected "%(expected)s" but got "%(result)s"' % locals())


class TOCTestCase(unittest.TestCase):

    def setUp(self):
        """ Require show_section_numbers = 0 to workaround counter
        global state saved in request.
        """
        self.config = TestConfig(show_section_numbers=0)
    
    def tearDown(self):
        del self.config

    def testHeadingWithWhiteSpace(self):
        """ parser.wiki: TOC links to headings with white space
        
        See bug: TableOfContentsBreakOnExtraSpaces.

        Does not test TOC or heading formating, just verify that spaces
        around heading text does not matter.
        """
        standard = """
[[TableOfContents]]
= heading =
Text
"""
        withWhitespace = """
[[TableOfContents]]
=   heading   =
Text
"""
        expected = parse(standard)
        result = parse(withWhitespace)
        self.assertEqual(result, expected,
            'Expected "%(expected)s" but got "%(result)s"' % locals())      
        

class DateTimeMacroTestCase(unittest.TestCase):
    """ Test DateTime macro """
    
    text = 'XXX %s XXX'
    needle = re.compile(text %  r'(.+)')
    _tests = (
        # test                                   expected
        ('[[DateTime(1970-01-06T00:00:00)]]',   '1970-01-06 00:00:00'),
        ('[[DateTime(259200)]]',                '1970-01-04 00:00:00'),
        ('[[DateTime(2003-03-03T03:03:03)]]',   '2003-03-03 03:03:03'),
        ('[[DateTime(2000-01-01T00:00:00Z)]]',  '2000-01-01 00:00:00'),
        ('[[Date(2002-02-02T01:02:03Z)]]',      '2002-02-02'),
        )

    def setUp(self):
        """ Require default date and time format config values """
        self.config = TestConfig(defaults=('date_fmt', 'datetime_fmt'))
    
    def tearDown(self):
        del self.config
    
    def testDateTimeMacro(self):
        """ parser.wiki: DateTime macro """
        note = """
    
    If this fails, it is likely a problem in your python / libc,
    not in moin.  See also:
    <http://sourceforge.net/tracker/index.php?func=detail&
        aid=902172&group_id=5470&atid=105470>"""

        for test, expected in self._tests:
            html = parse(self.text % test)
            result = self.needle.search(html).group(1)
            self.assertEqual(result, expected,
                'Expected "%(expected)s" but got "%(result)s"; %(note)s' % locals())
                        

class TextFormatingTestCase(unittest.TestCase):
    """ Test wiki markup """
    
    text = 'XXX %s XXX'
    needle = re.compile(text %  r'(.+)')
    _tests = (
        # test,                     expected
        ('no format',               'no format'),
        ("''em''",                  '<em>em</em>'),
        ("'''bold'''",              '<strong>bold</strong>'),
        ("__underline__",           '<span class="u">underline</span>'),
        ("'''''Mix''' at start''",  '<em><strong>Mix</strong> at start</em>'),
        ("'''''Mix'' at start'''",  '<strong><em>Mix</em> at start</strong>'),
        ("'''Mix at ''end'''''",    '<strong>Mix at <em>end</em></strong>'),
        ("''Mix at '''end'''''",    '<em>Mix at <strong>end</strong></em>'),
        )
    
    def testTextFormating(self):
        """ parser.wiki: text formating """
        for test, expected in self._tests:
            html = parse(self.text % test)
            result = self.needle.search(html).group(1)
            self.assertEqual(result, expected,
                             'Expected "%(expected)s" but got "%(result)s"' % locals())


class LinksFormatingTestCase(unittest.TestCase):
    ''' Test links generation 
    
    Since we can not know the wiki url, we ignore the first part of the href,
    and test just the part after the wiki url:
    
    <----- ignore this part ----->
    <a href="http://www.wikidomain/PageName">PageName</a>
    '''
    text = 'XXX %s XXX'
    needle = re.compile(text %  r'(.+)')
    _tests = (
        # link, end of generated a tag
        ('["../"]', '/">../</a>'),
        )
    
    def testLinkFormating(self):
        """ parser.wiki: link formating """
        for test, expected in self._tests:
            html = parse(self.text % test)
            result = self.needle.search(html).group(1)
            self.assert_(result.endswith(expected),
                '"%(expected)s" not in "%(result)s"' % locals())


class CloseInlineTestCase(unittest.TestCase):

    def testCloseOneInline(self):
        """ parser.wiki: close open inline tag when block close """
        cases = (
            # test, expected
            ("text'''text\n", r"<p>text<strong>text\s*</strong></p>"),
            ("text''text\n", r"<p>text<em>text\s*</em></p>"),
            ("text__text\n", r"<p>text<span class=\"u\">text\s*</span></p>"),
            ("text ''em '''em strong __em strong underline",
             r"text <em>em <strong>em strong <span class=\"u\">em strong underline"
             r"\s*</span></strong></em></p>"),
            )
        for test, expected in cases:
            needle = re.compile(expected)
            result = parse(test)
            self.assert_(needle.search(result),
                         'Expected "%(expected)s" but got "%(result)s"' % locals())


class InlineCrossingTestCase_Disabled(unittest.TestCase):
    """
    This test case fail with current parser/formatter and should be
    fixed in 1.4
    """
    
    def testInlineCrossing(self):
        """ parser.wiki: prevent inline crossing <a><b></a></b> """

        expected = ("<p><em>a<strong>ab</strong></em><strong>b</strong>\s*</p>")
        test = "''a'''ab''b'''\n"
        needle = re.compile(expected)
        result = parse(test)
        self.assert_(needle.search(result),
                     'Expected "%(expected)s" but got "%(result)s"' % locals())
       

class EscapeHTMLTestCase(unittest.TestCase):

    def testEscapeInTT(self):
        """ parser.wiki: escape html markup in `tt` """
        test = 'text `<escape>` text\n'
        self._test(test)

    def testEscapeInTT2(self):
        """ parser.wiki: escape html markup in {{{tt}}} """
        test = 'text {{{<escape>}}} text\n'
        self._test(test)

    def testEscapeInPre(self):
        """ parser.wiki: escape html markup in pre """
        test = '''{{{
<escape>
}}}
'''
        self._test(test)
        
    def testEscapeInPreHashbang(self):
        """ parser.wiki: escape html markup in pre with hashbang """
        test = '''{{{#!
<escape>
}}}
'''
        self._test(test)
        
    def testEscapeInPythonCodeArea(self):
        """ parser.wiki: escape html markup in python code area """
        test = '''{{{#!python
#<escape>
}}}
'''
        self._test(test)

    def testEscapeInGetTextMacro(self):
        """ parser.wiki: escape html markup in GetText macro """
        test = "text [[GetText(<escape>)]] text"
        self._test(test)

    def testEscapeInGetTextFormatted(self):
        """ parser.wiki: escape html markup in getText formatted call """
        _ = request.getText
        test = _('<escape>', formatted=1)
        self._test(test)

    def testEscapeInGetTextFormatedLink(self):
        """ parser.wiki: escape html markup in getText formatted call with link """
        _ = request.getText
        test = _('["<escape>"]', formatted=1)
        self._test(test)

    def testEscapeInGetTextUnFormatted(self):
        """ parser.wiki: escape html markup in getText non formatted call """
        _ = request.getText
        test = _('<escape>', formatted=0)
        self._test(test)

    def _test(self, test):
        expected = r'&lt;escape&gt;'
        result = parse(test)
        self.assert_(re.search(expected, result),
                     'Expected "%(expected)s" but got "%(result)s"' % locals())         


class EscapeWikiTableMarkupTestCase(unittest.TestCase):

    def testEscapeInTT(self):
        """ parser.wiki: escape wiki table markup in `tt` """
        test = 'text `||<tablewidth="80"> Table ||` text\n'
        self.do(test)

    def testEscapeInTT2(self):
        """ parser.wiki: escape wiki table markup in {{{tt}}} """
        test = 'text {{{||<tablewidth="80"> Table ||}}} text\n'
        self.do(test)

    def testEscapeInPre(self):
        """ parser.wiki: escape wiki table  markup in pre """
        test = '''{{{
||<tablewidth="80"> Table ||
}}}
'''
        self.do(test)
        
    def testEscapeInPreHashbang(self):
        """ parser.wiki: escape wiki table  markup in pre with hashbang """
        test = '''{{{#!
||<tablewidth="80"> Table ||
}}}
'''
        self.do(test)
        
    def testEscapeInPythonCodeArea(self):
        """ parser.wiki: escape wiki table markup in python code area """
        test = '''{{{#!python
# ||<tablewidth="80"> Table ||
}}}
'''
        self.do(test)

    def do(self, test):
        expected = r'&lt;tablewidth="80"&gt;'
        result = parse(test)
        self.assert_(re.search(expected, result),
                     'Expected "%(expected)s" but got "%(result)s"' % locals())         


class RuleTestCase(unittest.TestCase):
    """ Test rules markup """

    def testNotRule(self):
        """ parser.wiki: --- is no rule """
        result = parse('---')
        expected = '---' # inside <p>
        self.assert_(expected in result,
                     'Expected "%(expected)s" but got "%(result)s"' % locals())

    def testStandardRule(self):
        """ parser.wiki: ---- is standard rule """
        result = parse('----')
        expected = '<hr>'
        self.assert_(expected in result,
                     'Expected "%(expected)s" but got "%(result)s"' % locals())

    def testVariableRule(self):
        """ parser.wiki: ----- rules with size """

        for size in range(5, 11):
            test = '-' * size         
            result = parse(test)
            expected = '<hr class="hr%d">' % (size - 4)
            self.assert_(expected in result,
                     'Expected "%(expected)s" but got "%(result)s"' % locals())

    def testLongRule(self):
        """ parser.wiki: ------------ long rule shortened to hr6 """
        test = '-' * 254        
        result = parse(test)
        expected = '<hr class="hr6">'
        self.assert_(expected in result,
                     'Expected "%(expected)s" but got "%(result)s"' % locals())


class BlockTestCase(unittest.TestCase):
    cases = (
        # test, block start
        ('----\n', '<hr'),
        ('= Heading =\n', '<h2'),
        ('{{{\nPre\n}}}\n', '<pre'),
        ('{{{\n#!python\nPre\n}}}\n', '<div'),
        ('|| Table ||', '<div'),
        (' * unordered list\n', '<ul'),
        (' 1. ordered list\n', '<ol'),
        (' indented text\n', '<ul'),
        )

    def testParagraphBeforeBlock(self):
        """ parser.wiki: paragraph closed before block element """
        text = """XXX
%s
"""
        for test, blockstart in self.cases:
            # We dont test here formatter white space generation
            expected = r'<p>XXX\s*</p>\n+%s' % blockstart
            needle = re.compile(expected, re.MULTILINE)
            result = parse(text % test)
            match = needle.search(result)
            self.assert_(match is not None,
                         'Expected "%(expected)s" but got "%(result)s"' % locals())
            
    def testEmptyLineBeforeBlock(self):
        """ parser.wiki: empty lines before block element ignored
        
        Empty lines separate paragraphs, but should be ignored if a block
        element follow.

        Currently an empty paragraph is created, which make no sense but
        no real harm.
        """
        text = """XXX

%s
"""
        for test, blockstart in self.cases:
            expected = r'<p>XXX\s*</p>\n+%s' % blockstart
            needle = re.compile(expected, re.MULTILINE)
            result = parse(text % test)
            match = needle.search(result)
            self.assert_(match is not None,
                         'Expected "%(expected)s" but got "%(result)s"' % locals())

            

def parse(body):
    """Parse body and return html
    
    Create a page with body, then parse it and format using html formatter
    """
    assert body is not None

    request.reset()

    pg = Page(request, 'ThisPageDoesNotExistsAndWillNeverBeReally')
    pg.set_raw_body(body)

    from MoinMoin.formatter.text_html import Formatter
    pg.formatter = Formatter(request)
    request.formatter = pg.formatter
    pg.formatter.setPage(pg)
    pg.hilite_re = None

    output = []
    
    # Temporarily replace request.write with custom write function that 
    # write into our output object.
    def write_output(text, o=output):
        o.append(text)
    saved_write = request.write
    request.write = write_output
    try:
        Parser(body, request).format(pg.formatter)
    finally:
        request.write = saved_write

    return ''.join(output)
    
