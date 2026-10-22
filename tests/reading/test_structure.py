import time
from pathlib import Path

import pytest

from natural_tts.reading.blocks import Block
from natural_tts.reading.structure import (
    blocks,
    looks_like_markdown,
    structured_windows,
)
from natural_tts.segments import Kind

DATA = Path(__file__).with_name("data")


def kinds(items):
    return [b.kind for b in items]


class TestHtml:
    def test_headings_paragraphs_lists_and_quotes(self):
        html = (
            "<h2>Results</h2><p>We found it.</p>"
            "<ul><li>one</li><li>two</li></ul>"
            "<ol><li>first</li><li>second</li></ol>"
            "<blockquote><p>a quote</p></blockquote>"
        )
        out = list(blocks(html, "text/html"))
        assert [(b.kind, b.text) for b in out] == [
            (Kind.HEADING, "Results"),
            (Kind.PROSE, "We found it."),
            (Kind.LIST_ITEM, "one"),
            (Kind.LIST_ITEM, "two"),
            (Kind.LIST_ITEM, "first"),
            (Kind.LIST_ITEM, "second"),
            (Kind.QUOTE, "a quote"),
        ]
        assert out[0].level == 2
        assert [b.ordered_index for b in out[2:6]] == [None, None, 1, 2]

    def test_code_blocks_keep_lines_and_language(self):
        html = (
            '<pre><code class="language-python">def f():\n'
            "    return 1\n</code></pre>"
        )
        (code,) = blocks(html, "text/html")
        assert code.kind is Kind.CODE
        assert code.language == "python"
        assert code.text == "def f():\n    return 1"

    def test_inline_code_links_and_citations_stay_in_the_paragraph(self):
        html = (
            "<p>Run <code>git add -A</code> as shown"
            '<sup><a href="#r1">1</a></sup>, '
            'see <a href="http://x.y/z">the docs</a>.</p>'
        )
        (prose,) = blocks(html, "text/html")
        assert prose.kind is Kind.PROSE
        assert prose.text == "Run `git add -A` as shown [1], see the docs."

    def test_tables_become_rows_with_their_header(self):
        html = (
            "<table><tr><th>Name</th><th>Size</th></tr>"
            "<tr><td>a</td><td>1</td></tr><tr><td>b</td><td>2</td></tr></table>"
        )
        (table,) = blocks(html, "text/html")
        assert table.kind is Kind.TABLE
        assert table.columns == ("Name", "Size")
        assert table.rows == (("a", "1"), ("b", "2"))

    def test_script_style_and_hidden_elements_are_skipped(self):
        html = (
            "<style>.x{}</style><p>Shown.</p><script>hidden()</script>"
            "<noscript>no</noscript><template><p>tpl</p></template>"
        )
        assert [b.text for b in blocks(html, "text/html")] == ["Shown."]

    def test_entities_and_line_breaks(self):
        html = "<p>a &amp; b &lt;c&gt;<br>next line &#8217;s</p>"
        (prose,) = blocks(html, "text/html")
        assert prose.text == "a & b <c>\nnext line ’s"

    def test_first_block_time_does_not_grow_with_the_document(self):
        def first_block_ms(html):
            start = time.perf_counter()
            first = next(blocks(html, "text/html"))
            assert first == Block(Kind.HEADING, "Title", level=1)
            return time.perf_counter() - start

        body = "<p>" + "more words here. " * 20 + "</p>"
        page = "<h1>Title</h1>" + body * 30
        cap = "<h1>Title</h1>" + body * 3000
        assert len(cap) > 1_000_000
        small = min(first_block_ms(page) for _ in range(3))
        large = min(first_block_ms(cap) for _ in range(3))
        assert large < 2.5 * small + 0.01


class TestMarkdown:
    MD = (
        "# Title\n\nSome prose with `code` and more.\n\n"
        "- first\n- second\n\n1. one\n2. two\n\n> quoted\n\n"
        "```python\ndef f(x):\n    return x\n```\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n"
    )

    def test_blocks_in_order(self):
        out = list(blocks(self.MD, None))
        assert kinds(out) == [
            Kind.HEADING,
            Kind.PROSE,
            Kind.LIST_ITEM,
            Kind.LIST_ITEM,
            Kind.LIST_ITEM,
            Kind.LIST_ITEM,
            Kind.QUOTE,
            Kind.CODE,
            Kind.TABLE,
        ]
        assert out[0] == Block(Kind.HEADING, "Title", level=1)
        assert out[1].text == "Some prose with `code` and more."
        assert [b.ordered_index for b in out[2:6]] == [None, None, 1, 2]
        assert (
            out[7].language == "python"
            and out[7].text == "def f(x):\n    return x"
        )
        assert out[8].columns == ("A", "B") and out[8].rows == (("1", "2"),)

    def test_emphasis_markers_are_dropped_from_prose(self):
        (prose,) = blocks("Some **bold** and *em* and __u__ text.", None)
        assert prose.text == "Some bold and em and u text."

    def test_setext_heading_and_tilde_fence(self):
        out = list(blocks("Title\n=====\n\n~~~sh\necho hi\n~~~\n", None))
        assert kinds(out) == [Kind.HEADING, Kind.CODE]
        assert out[1].language == "sh" and out[1].text == "echo hi"

    def test_indented_code_after_a_blank_line(self):
        out = list(blocks("Example:\n\n    x = 1\n    y = 2\n\nDone.", None))
        assert kinds(out) == [Kind.PROSE, Kind.CODE, Kind.PROSE]
        assert out[1].text == "x = 1\ny = 2"

    @pytest.mark.parametrize(
        "text",
        [
            "See item 3.\n2. Then this sentence, which is prose.",
            "Results were clear - not a list - and done.",
            "We used {n = 3} and {p < 0.05} in the model.",
            "A plain paragraph\nwrapped by a PDF\nacross three lines.",
        ],
    )
    def test_prose_is_not_mistaken_for_structure(self, text):
        out = list(blocks(text, None))
        assert kinds(out) == [Kind.PROSE]

    def test_looks_like_markdown(self):
        assert looks_like_markdown(self.MD)
        assert not looks_like_markdown("Just a sentence. Another one.")
        assert looks_like_markdown("- a\n- b\n- c")
        assert not looks_like_markdown("- a single dash line in a PDF paste")

    def test_fence_longer_than_a_window_stays_one_block(self):
        code = "\n".join(f"x{i} = {i}. y{i} = {i}" for i in range(2000))
        text = f"Intro.\n\n```python\n{code}\n```\n\nOutro.\n"
        out = list(blocks(text, None))
        assert kinds(out) == [Kind.PROSE, Kind.CODE, Kind.PROSE]
        assert out[1].text.count("\n") == 1999

    def test_structured_windows_cut_at_blank_lines_outside_fences(self):
        para = "word " * 300 + "\n\n"
        text = para + "```\n" + "line;\n" * 800 + "```\n\n" + para
        wins = list(structured_windows(text, size=2000))
        assert "".join(wins) == text
        assert all(w.count("```") % 2 == 0 for w in wins)
        assert all(len(w) < 6000 for w in wins)

    def test_first_block_time_does_not_grow_with_the_document(self):
        # The first block must cost the same for a page and for the 1 MiB
        # message cap; measured as a ratio so coverage tracing and machine
        # load do not decide the verdict (10.7 vs 14.7 ms plain, 70 vs 74 ms
        # traced, on the owner's machine).
        def first_block_ms(text):
            start = time.perf_counter()
            first = next(blocks(text, None))
            assert first == Block(Kind.HEADING, "Title", level=1)
            return time.perf_counter() - start

        page = "# Title\n\n" + ("Some prose here.\n\n- item\n\n" * 400)
        cap = "# Title\n\n" + ("Some prose here.\n\n- item\n\n" * 45000)
        assert len(cap) > 1_000_000
        small = min(first_block_ms(page) for _ in range(3))
        large = min(first_block_ms(cap) for _ in range(3))
        assert large < 2.5 * small + 0.01


class TestCarriers:
    @pytest.mark.parametrize(
        ("text", "language", "code"),
        [
            (
                "A literal block::\n\n    x = 1\n    y = 2\n\nAfter.",
                None,
                "x = 1\ny = 2",
            ),
            (
                ".. code-block:: python\n\n    def f():\n        pass\n\n"
                "After.",
                "python",
                "def f():\n    pass",
            ),
            (
                "\\begin{lstlisting}[language=Python]\nx = 1\n"
                "\\end{lstlisting}",
                "python",
                "x = 1",
            ),
            (
                "\\begin{minted}{bash}\necho hi\n\\end{minted}",
                "bash",
                "echo hi",
            ),
            ("\\begin{verbatim}\nraw text\n\\end{verbatim}", None, "raw text"),
            ("#+BEGIN_SRC python\nx = 1\n#+END_SRC", "python", "x = 1"),
            ("#+begin_example\nplain\n#+end_example", None, "plain"),
            ("[source,python]\n----\nx = 1\n----", "python", "x = 1"),
            ("----\nlisting\n----", None, "listing"),
            (">>> x = 1\n>>> print(x)\n1", "python", "x = 1\nprint(x)\n1"),
            ("In [1]: x = 1\nOut[1]: 1", "python", "x = 1\n1"),
            (
                "$ ls -la\ntotal 0\n$ echo hi\nhi",
                "shell",
                "ls -la\ntotal 0\necho hi\nhi",
            ),
            (
                "#!/usr/bin/env bash\nset -e\necho hi",
                "bash",
                "#!/usr/bin/env bash\nset -e\necho hi",
            ),
        ],
    )
    def test_code_carriers(self, text, language, code):
        out = list(blocks(text, None))
        found = [b for b in out if b.kind is Kind.CODE]
        assert len(found) == 1, kinds(out)
        assert found[0].language == language
        assert found[0].text == code

    def test_diff_hunks_are_code_with_the_file_language(self):
        text = (
            "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n-x = 1\n+x = 2\n y = 3\n"
        )
        (code,) = blocks(text, None)
        assert code.kind is Kind.CODE and code.language == "diff"
        assert code.text == text.strip()

    def test_unfenced_dense_code_is_detected(self):
        text = (
            "int main(void) {\n    int x = 1;\n    if (x) {\n"
            "        return x;\n    }\n    return 0;\n}\n"
        )
        (code,) = blocks(text, None)
        assert code.kind is Kind.CODE and code.language is None

    @pytest.mark.parametrize(
        "text",
        [
            "Prices rose; demand fell: a classic case. The end.",
            "In {n = 3} we found {p < 0.05}: the effect held. Done.",
            "Step one:\n    mix well.\nStep two:\n    bake it.",
        ],
    )
    def test_prose_with_braces_or_colons_is_not_code(self, text):
        assert Kind.CODE not in kinds(blocks(text, None))


class TestRealDocuments:
    def test_this_readme(self):
        out = list(blocks((DATA / "readme.md").read_text(), None))
        assert out[0] == Block(
            Kind.HEADING, "Natural text-to-speech for Ubuntu", level=1
        )
        got = {k: kinds(out).count(k) for k in Kind}
        assert got[Kind.HEADING] >= 10
        assert got[Kind.CODE] >= 3
        assert got[Kind.TABLE] >= 2
        assert got[Kind.LIST_ITEM] >= 8
        fences = [b for b in out if b.kind is Kind.CODE]
        assert any(b.language in {"bash", "toml"} for b in fences)


class TestMathBlocks:
    def test_display_latex_in_plain_text(self):
        text = "Before.\n\n$$\\int_0^1 f(x)\\,dx$$\n\nAfter."
        out = list(blocks(text, None))
        assert kinds(out) == [Kind.PROSE, Kind.MATH, Kind.PROSE]
        assert out[1].language == "latex"
        assert out[1].text == "\\int_0^1 f(x)\\,dx"
        assert out[0].text == "Before." and out[2].text == "After."

    def test_equation_environment_and_bracket_display(self):
        text = (
            "\\begin{equation}\na = b\n\\end{equation}\n\n"
            "Then \\[E = mc^2\\] holds."
        )
        out = list(blocks(text, None))
        assert [b.kind for b in out] == [
            Kind.MATH,
            Kind.PROSE,
            Kind.MATH,
            Kind.PROSE,
        ]
        assert out[0].text == "a = b" and out[2].text == "E = mc^2"

    def test_inline_latex_stays_inside_the_paragraph(self):
        (prose,) = blocks("where $x^2 + y^2 = r^2$ holds.", None)
        assert prose.kind is Kind.PROSE and "$x^2 + y^2 = r^2$" in prose.text

    def test_html_math_element_prefers_its_latex_annotation(self):
        html = (
            "<p>Thus</p><math><semantics><mrow><mi>x</mi></mrow>"
            '<annotation encoding="application/x-tex">x^2</annotation>'
            "</semantics></math><p>done.</p>"
        )
        out = list(blocks(html, "text/html"))
        assert kinds(out) == [Kind.PROSE, Kind.MATH, Kind.PROSE]
        assert out[1].language == "latex" and out[1].text == "x^2"

    def test_html_math_without_annotation_is_mathml(self):
        html = '<math alttext="a/b"><mfrac><mi>a</mi><mi>b</mi></mfrac></math>'
        (block,) = blocks(html, "text/html")
        assert block.kind is Kind.MATH and block.language == "latex"
        assert block.text == "a/b"
        html = "<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>"
        (block,) = blocks(html, "text/html")
        assert block.language == "mathml"
        assert block.text == "<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>"

    def test_mathjax_script_tag(self):
        html = '<p>See</p><script type="math/tex">\\frac{a}{b}</script>'
        out = list(blocks(html, "text/html"))
        assert kinds(out) == [Kind.PROSE, Kind.MATH]
        assert out[1].text == "\\frac{a}{b}" and out[1].language == "latex"

    def test_money_is_prose(self):
        (prose,) = blocks("It costs $5 and $10 at most.", None)
        assert prose.kind is Kind.PROSE

    def test_formula_paragraph_from_a_pdf(self):
        text = "Energy is given by\n\nE = mc²\n\nwhere m is mass."
        out = list(blocks(text, None))
        assert kinds(out) == [Kind.PROSE, Kind.MATH, Kind.PROSE]
        assert out[1].language == "unicode" and out[1].text == "E = mc²"
        assert out[2].text == "where m is mass."


class TestTables:
    def test_caption_and_body_row_headers(self):
        html = (
            "<table><caption>Table 2. Results</caption>"
            "<thead><tr><th>Sample</th><th>n</th></tr></thead>"
            "<tbody><tr><th>Control</th><td>12</td></tr>"
            "<tr><th>Treated</th><td></td></tr></tbody></table>"
        )
        (table,) = blocks(html, "text/html")
        assert table.caption == "Table 2. Results"
        assert table.columns == ("Sample", "n")
        assert table.rows == (("Control", "12"), ("Treated", ""))
        assert table.row_headers is True

    def test_plain_html_table_has_no_row_headers(self):
        html = (
            "<table><tr><th>Name</th><th>Size</th></tr>"
            "<tr><td>a</td><td>1</td></tr></table>"
        )
        (table,) = blocks(html, "text/html")
        assert table.row_headers is False and table.caption == ""

    def test_spanning_cells_repeat_their_value(self):
        html = (
            "<table><tr><th>A</th><th>B</th><th>C</th></tr>"
            '<tr><td rowspan="2">x</td><td colspan="2">y</td></tr>'
            "<tr><td>p</td><td>q</td></tr></table>"
        )
        (table,) = blocks(html, "text/html")
        assert table.rows == (("x", "y", "y"), ("x", "p", "q"))

    def test_two_header_rows_join_their_names(self):
        html = (
            "<table><thead>"
            '<tr><th rowspan="2">Model</th><th colspan="2">Score</th></tr>'
            "<tr><th>Dev</th><th>Test</th></tr></thead>"
            "<tbody><tr><td>m1</td><td>1</td><td>2</td></tr></tbody></table>"
        )
        (table,) = blocks(html, "text/html")
        assert table.columns == ("Model", "Score, Dev", "Score, Test")
        assert table.rows == (("m1", "1", "2"),)

    def test_markdown_tables_treat_the_first_column_as_the_row_heading(self):
        md = (
            "| Model | Params |\n|---|---|\n"
            "| GPT-4o | 1.8T |\n| Llama | 70B |\n"
        )
        (table,) = blocks(md, None)
        assert table.row_headers is True and table.caption == ""
        assert table.columns == ("Model", "Params")
        assert table.rows == (("GPT-4o", "1.8T"), ("Llama", "70B"))
