"""Tests for src/prompt_linter.py — typo correction and input normalization."""

import unittest
from src.prompt_linter import lint_prompt, _fix_typos, _normalize_unicode, _normalize_whitespace


class TestLintPrompt(unittest.TestCase):
    """Integration tests for the full lint_prompt pipeline."""

    def test_basic_typo_correction(self):
        result = lint_prompt('anlayse teh propmt')
        self.assertEqual(result, 'analyse the prompt')

    def test_preserves_correct_input(self):
        original = 'Create a new REST API endpoint for user authentication'
        self.assertEqual(lint_prompt(original), original)

    def test_empty_input(self):
        self.assertEqual(lint_prompt(''), '')
        self.assertEqual(lint_prompt('   '), '   ')

    def test_none_safety(self):
        # lint_prompt should handle edge cases gracefully
        self.assertEqual(lint_prompt(''), '')

    def test_unicode_normalization(self):
        # Smart quotes → ASCII
        result = lint_prompt('\u201CHello world\u201D')
        self.assertEqual(result, '"Hello world"')

    def test_whitespace_normalization(self):
        result = lint_prompt('fix   the    bug    please')
        self.assertEqual(result, 'fix the bug please')

    def test_preserves_capitalization(self):
        result = lint_prompt('Anlayse the code')
        self.assertEqual(result, 'Analyse the code')

    def test_multiple_typos(self):
        result = lint_prompt('udpate teh fucntion wiht teh new paramter')
        self.assertEqual(result, 'update the function with the new parameter')

    def test_preserves_code_like_content(self):
        # Should not correct words inside paths or code-like content
        result = lint_prompt('refactor the main function')
        self.assertIn('refactor', result)
        self.assertIn('main', result)

    def test_developer_typos(self):
        result = lint_prompt('implment teh databse endpoing')
        self.assertEqual(result, 'implement the database endpoint')


class TestFixTypos(unittest.TestCase):
    """Unit tests for the typo correction function."""

    def test_returns_corrections_list(self):
        _, corrections = _fix_typos('teh propmt')
        self.assertEqual(len(corrections), 2)
        self.assertEqual(corrections[0], ('teh', 'the'))
        self.assertEqual(corrections[1], ('propmt', 'prompt'))

    def test_no_corrections_on_clean_input(self):
        _, corrections = _fix_typos('the prompt is ready')
        self.assertEqual(len(corrections), 0)


class TestNormalizeUnicode(unittest.TestCase):
    """Unit tests for unicode normalization."""

    def test_smart_quotes(self):
        self.assertEqual(_normalize_unicode('\u2018hello\u2019'), "'hello'")
        self.assertEqual(_normalize_unicode('\u201Chello\u201D'), '"hello"')

    def test_em_dash(self):
        self.assertEqual(_normalize_unicode('word\u2014word'), 'word--word')

    def test_ellipsis(self):
        self.assertEqual(_normalize_unicode('wait\u2026'), 'wait...')


class TestNormalizeWhitespace(unittest.TestCase):
    """Unit tests for whitespace normalization."""

    def test_collapses_spaces(self):
        self.assertEqual(_normalize_whitespace('a   b   c'), 'a b c')

    def test_preserves_newlines(self):
        result = _normalize_whitespace('line1\nline2')
        self.assertIn('\n', result)

    def test_collapses_excessive_newlines(self):
        result = _normalize_whitespace('a\n\n\n\n\nb')
        self.assertEqual(result, 'a\n\nb')

    def test_strips_leading_trailing(self):
        self.assertEqual(_normalize_whitespace('  hello  '), 'hello')


if __name__ == '__main__':
    unittest.main()
