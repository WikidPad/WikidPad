# coding: utf-8
"""Test WikiDocument.

* Test renaming wiki words and updating references via
  WikiDocument.renameWikiWords(renameDict, modifyText).

  Test the following methods to update the text (see UPDATE_METHODS_TO_TEST):

  + ModifyText.advanced
        - recommended method
        - it passes all tests

  + ModifyText.simple
        - simple search & replace
        - it fails tests
        - uncomment in UPDATE_METHODS_TO_TEST to include in test

  The files tests/test_wikis_*_before_rename.txt and
  tests/test_wikis_*_after_rename.txt hold the contents of all test wikis.


"""
import os
import re
import sys

# run from WikidPad directory
wikidpad_dir = os.path.abspath('.')
sys.path.append(wikidpad_dir)
sys.path.append(os.path.join(wikidpad_dir, 'lib'))

from tests.helper import MockWikiDocument, get_text, TESTS_DIR
from Consts import ModifyText


UPDATE_METHODS_TO_TEST = [
    ('advanced', ModifyText.advanced),
    # ('simple', ModifyText.simple),  # uncomment to include (test will fail)
]

test_files = {
    'wikidpad_default_2_0':
        ('test_wikis_wikidpad_default_2_0_before_rename.txt',
         'test_wikis_wikidpad_default_2_0_after_rename.txt'),
}


def parse_test_wikis_text_file(s, wiki_language_name):
    """Return dict. of test wiki content for testing:
    {wikiname: (wikiDoc, renameSeq)}."""
    ans = {}  # {wikiname: (wikiDoc, renameSeq)}

    def error_msg():
        return 'Parse error on line %d section %d: %r' % (
            line_nr, section, line)

    wiki_start = re.compile(r'^= (?P<wikiname>\w+) =+$')
    wiki_end = re.compile(r'^={80}$')
    page_start = re.compile(r'^- (?P<pagename>[/\w]+) -+$')
    page_end = re.compile(r'^-{80}$')
    rename_seq_line = lambda line: '->' in line

    section = 0
    renameSeq = []
    for line_nr, line in enumerate(s.splitlines(True), 1):
        if section == 0:  # outside wiki
            # new wiki?
            m = wiki_start.match(line)
            if m:
                assert len(line.strip()) == 80, error_msg()
                wiki_name = m.group('wikiname')
                wiki_content = {}
                renameSeq = []
                section = 1
                continue

            assert not line.strip(), error_msg()

        elif section == 1:  # inside wiki, outside page
            # new page?
            m = page_start.match(line)
            if m:
                assert len(line.strip()) == 80, error_msg()
                page_name = m.group('pagename')
                page_lines = []
                section = 2
                continue

            # renameSeq?
            if rename_seq_line(line):
                for rename_couple in line.strip().split(','):
                    old_page_name, new_page_name = [
                        s.strip() for s in rename_couple.split('->')]
                    renameSeq.append((old_page_name, new_page_name))
                continue

            # end of wiki?
            m = wiki_end.match(line)
            if m:
                # we now have a complete wiki
                wikidoc = MockWikiDocument(wiki_content, wiki_language_name)
                assert wiki_name not in ans, error_msg()
                ans[wiki_name] = (wikidoc, renameSeq)
                section = 0
                continue

            assert not line.strip(), error_msg()

        elif section == 2:  # inside wiki, inside page
            # end of page?
            m = page_end.match(line)
            if m:
                # we now have a complete page
                page_content = ''.join(page_lines)
                assert page_name not in wiki_content, error_msg()
                wiki_content[page_name] = page_content
                section = 1
                continue

            page_lines.append(line)

    return ans


def load_tests(language_name):
    """Load test wikis from file. Return dict. test:
    {wiki_name: (wikidoc_before, renameSeq, wikidoc_after)}.
    """
    ans = dict()

    before_fn, after_fn = test_files[language_name]

    s = get_text(os.path.join(TESTS_DIR, before_fn))
    wikis_before = parse_test_wikis_text_file(s, language_name)

    s = get_text(os.path.join(TESTS_DIR, after_fn))
    wikis_after = parse_test_wikis_text_file(s, language_name)

    assert len(wikis_before) == len(wikis_after)
    assert list(wikis_before.keys()) == list(wikis_after.keys())

    # pages for which no content was given are considered empty
    # create those empty pages here
    for wiki_name, (wikidoc_before, renameSeq) in wikis_before.items():
        wikidoc_after, _ = wikis_after[wiki_name]

        for word, toWord in renameSeq:
            if not wikidoc_before.isDefinedWikiPageName(word):
                _ = wikidoc_before.createWikiPage(word, content='')
            if not wikidoc_after.isDefinedWikiPageName(toWord):
                _ = wikidoc_after.createWikiPage(toWord, content='')

        ans[wiki_name] = (wikidoc_before, renameSeq, wikidoc_after)

    return ans


def test_renameWikiWords():
    no_method_failed = True

    def err_msg():
        msg = "Method %r language %r: updating text of %r failed"
        msg %= (method_name, language_name, wiki_name)
        return msg

    def wiki_name_nr_sort_key(t):
        wiki_name, _ = t
        try:
            n = int(wiki_name)
        except ValueError:
            return wiki_name
        else:
            return '%050d' % n

    for method_name, modifyText in UPDATE_METHODS_TO_TEST:
        method_failures = []

        for language_name in test_files:
            tests = iter(load_tests(language_name).items())
            for wiki_name, test in sorted(tests, key=wiki_name_nr_sort_key):
                # print u'wiki:', repr(wiki_name)

                wikidoc, renameSeq, wikidoc_after = test
                after = wikidoc_after.getWikiData().wiki_content

                renameDict = dict((oldPageName, newPageName)
                              for oldPageName, newPageName in renameSeq)
                wikidoc.renameWikiWords(renameDict, modifyText)

                result = wikidoc.getWikiData().wiki_content

                if result != after:
                    method_failures.append((language_name, wiki_name))
                    print(err_msg())
                    print(wikidoc)
                # assert result == after, err_msg()

        if method_failures:
            no_method_failed = False
        else:
            print("Method '%s' passed all tests" % method_name)

    assert no_method_failed, "Failures: " + repr(method_failures)  # no one method failed?


if __name__ == '__main__':
    tests = load_tests('wikidpad_default_2_0')
    print(tests['18'][0])
    print(tests['18'][1])
    print(tests['18'][2])
