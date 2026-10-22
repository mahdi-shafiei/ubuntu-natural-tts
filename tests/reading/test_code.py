import pytest

from natural_tts.reading.code import read_code, split_identifier

PY = "def get_user_name(x):\n    return x[0]  # fetch first\n"


class TestSplitIdentifier:
    @pytest.mark.parametrize(
        ("name", "words"),
        [
            ("getUserName", ["get", "User", "Name"]),
            ("get_user_name", ["get", "user", "name"]),
            ("kebab-case-name", ["kebab", "case", "name"]),
            ("XMLHttpRequest", ["XML", "Http", "Request"]),
            # Unconventional (JSONFile would be the convention): no rule can
            # place this split without a dictionary, and the research showed
            # no tool exceeds 40% on such cases; the convention wins.
            ("parseJSONfile", ["parse", "JSO", "Nfile"]),
            ("utf8_to_mp3", ["utf8", "to", "mp3"]),
            ("sha256sum", ["sha256", "sum"]),
            ("int32_t", ["int32", "t"]),
            ("XPath", ["XPath"]),
            ("sqlite3_open_v2", ["sqlite", "3", "open", "v", "2"]),
            ("__init__", ["init"]),
            ("iPhoneOS", ["i", "Phone", "OS"]),
            ("HTML", ["HTML"]),
            ("x", ["x"]),
            ("CONSTANT_VALUE", ["CONSTANT", "VALUE"]),
        ],
    )
    def test_splits_on_case_separators_and_digits(self, name, words):
        assert split_identifier(name) == words

    @pytest.mark.parametrize(
        ("name", "words"),
        [
            ("str_len", ["string", "length"]),
            ("cfg_idx", ["config", "index"]),
            ("numPtr", ["number", "pointer"]),
            ("msg_buf", ["message", "buffer"]),
            ("strlen", ["strlen"]),
        ],
    )
    def test_short_unambiguous_abbreviations_are_expanded(self, name, words):
        assert split_identifier(name) == words


class TestLevels:
    def test_level_one_speaks_operators_and_drops_brackets(self):
        assert read_code(PY, language="python", level=1) == [
            "def get user name x",
            "return x zero comment fetch first",
        ]

    def test_level_two_adds_brackets_punctuation_and_indentation(self):
        assert read_code(PY, language="python", level=2) == [
            "def get user name left paren x right paren colon",
            "indent return x left bracket zero right bracket comment fetch "
            "first",
        ]

    def test_level_three_speaks_every_symbol(self):
        code = 'print("Hi, you!")\n'
        assert read_code(code, language="python", level=3) == [
            "print left paren quote Hi comma you bang quote right paren",
        ]

    def test_level_one_keeps_string_contents_as_words(self):
        code = 'print("Hello, world")\n'
        assert read_code(code, language="python", level=1) == [
            "print Hello, world"
        ]

    def test_dedent_is_announced_at_level_two(self):
        code = "if x:\n    y = 1\nz = 2\n"
        assert read_code(code, language="python", level=2) == [
            "if x colon",
            "indent y equals one",
            "dedent z equals two",
        ]

    def test_blank_and_symbol_only_lines_vanish_at_level_one(self):
        code = "int main(void) {\n\n    return 0;\n}\n"
        assert read_code(code, language="c", level=1) == [
            "int main void",
            "return zero",
        ]
        assert read_code(code, language="c", level=2)[-1] == (
            "dedent right brace"
        )


class TestOperatorsAndNumbers:
    @pytest.mark.parametrize(
        ("code", "spoken"),
        [
            ("a == b and c != d", "a equals equals b and c not equals d"),
            ("a <= b >= c", "a less or equal b greater or equal c"),
            ("x += 1; y -= 2", "x plus equals one y minus equals two"),
            ("f = lambda v: v ** 2", "f equals lambda v v star star two"),
            ("p->next = q", "p arrow next equals q"),
            ("a && b || !c", "a and and b or or c"),
            (
                "n = 0x1F + 0.5 + 1_000",
                "n equals hex one F plus zero point five plus one thousand",
            ),
            (
                "ratio = total / count * 100 % 7",
                "ratio equals total slash count star one hundred percent seven",
            ),
            ("obj.method(arg)", "obj dot method arg"),
            ("@decorator", "at decorator"),
        ],
    )
    def test_level_one_operator_words(self, code, spoken):
        assert read_code(code + "\n", language=None, level=1) == [spoken]

    def test_bang_is_spoken_only_at_level_three(self):
        assert read_code("!c\n", language=None, level=3) == ["bang c"]


class TestLanguages:
    def test_shell_comments_and_pipes(self):
        code = "# list files\nls -la | grep foo\n"
        assert read_code(code, language="sh", level=1) == [
            "comment list files",
            "ls minus la grep foo",
        ]
        assert read_code(code, language="sh", level=2)[1] == (
            "ls minus la bar grep foo"
        )

    def test_unknown_language_still_reads(self):
        assert read_code("x = 1\n", language="nosuchlang", level=1) == [
            "x equals one"
        ]

    def test_diff_lines(self):
        diff = (
            "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n-x = 1\n+x = 2\n y = 3\n"
        )
        assert read_code(diff, language="diff", level=1) == [
            "old file x.py",
            "new file x.py",
            "hunk",
            "removed x equals one",
            "added x equals two",
            "y equals three",
        ]

    def test_json(self):
        code = '{"name": "a", "n": 2}\n'
        assert read_code(code, language="json", level=1) == ["name a n two"]
        assert read_code(code, language="json", level=2) == [
            "left brace quote name quote colon quote a quote comma quote n "
            "quote colon two right brace"
        ]


class TestValidation:
    def test_rejects_an_unknown_level(self):
        with pytest.raises(ValueError, match="level"):
            read_code("x\n", language=None, level=4)
