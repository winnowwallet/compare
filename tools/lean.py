"""Lean 4, read lexically. No tree-sitter grammar parses current Lean: the one in
tree-sitter-language-pack leaves most of Winnow's Lean in error nodes (73% of its bytes at v0.9.5) and
finds half its declarations. So Lean gets the same rule as every other language, applied to tokens
instead of a syntax tree:

- Comments (`--`, nested `/- -/`) are blanked out first, and each string or character literal is reduced
  to its opening quote, keeping line numbers. The quote stays so that `| "a" =>` is an arm with a pattern.
- A Lean file is a sequence of commands, each starting at column 0. A function is a `def`, `instance`,
  `abbrev` or `opaque` command, from its first line (attributes and modifiers included) to the line
  before the next command. Its `where` and `let rec` helpers and its lambdas count toward it, as nested
  functions do everywhere else.
- CC = 1 + each `if` (also `if let`, `else if`), `unless`, `for`, `while`, `repeat`, `catch`, `&&`,
  `||`, and each non-default match arm: an alternative `| pattern =>` of a `match`, a `fun`, or a
  definition by patterns, unless its pattern is only `_` (the wildcard is the default, as in Rust).
  `p1 | p2 =>` is one arm.
- `theorem`, `lemma` and `example` commands are proofs: they are erased when Lean compiles, so they are
  not functions here. They are counted on their own (`proofs`)."""
import re

DECL = re.compile(r'(?:@\[[^\]]*\]\s*)*(?:(?:private|protected|partial|noncomputable|unsafe|nonrec|scoped|local)\s+)*'
                  r'(def|instance|abbrev|opaque|theorem|lemma|example|structure|inductive|class)\b')
# The first word of a line at column 0 that starts a new command (everything else continues one).
COMMAND = re.compile(r'(?:@\[|#|(?:def|instance|abbrev|opaque|theorem|lemma|example|structure|inductive|class|'
                     r'namespace|section|end|open|variable|universe|import|set_option|attribute|macro|macro_rules|'
                     r'syntax|notation|infix|infixl|infixr|prefix|postfix|elab|elab_rules|initialize|'
                     r'builtin_initialize|export|mutual|private|protected|partial|noncomputable|unsafe|nonrec|'
                     r'scoped|local|deriving)\b)')
FUNCTIONS = {'def', 'instance', 'abbrev', 'opaque'}
PROOFS = {'theorem', 'lemma', 'example'}
TOKEN = re.compile(r'&&|\|\|\|?|<\|>|\|>\.|\|>|<\||=>|[A-Za-z_][A-Za-z_0-9!?\'.]*|\S')
BRANCH_WORDS = {'if', 'unless', 'for', 'while', 'repeat', 'catch'}


def blank(text):
    """Comments replaced by spaces, and strings and character literals by their opening quote; newlines kept."""
    out, i, n = [], 0, len(text)

    def keep_lines(s):
        return re.sub(r'[^\n]', ' ', s)

    def quote(s, mark='"'):
        return mark + keep_lines(s[1:])
    while i < n:
        c = text[i]
        if text.startswith('--', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i)); i = j
        elif text.startswith('/-', i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith('/-', j):
                    depth += 1; j += 2
                elif text.startswith('-/', j):
                    depth -= 1; j += 2
                else:
                    j += 1
            out.append(keep_lines(text[i:j])); i = j
        elif c == 'r' and re.match(r'r#*"', text[i:i + 8]) and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] in '_\'')):
            hashes = re.match(r'r(#*)"', text[i:]).group(1)
            end = text.find('"' + hashes, i + 2 + len(hashes))
            j = n if end < 0 else end + 1 + len(hashes)
            out.append(quote(text[i:j])); i = j
        elif c == '"':
            j = string_end(text, i)
            out.append(quote(text[i:j])); i = j
        elif c == "'" and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] in "_'.!?")):
            m = re.match(r"'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]+\}|.)|[^\\'\n])'", text[i:i + 16])
            if m:
                out.append(quote(m.group(0), "'")); i += len(m.group(0))
            else:
                out.append(c); i += 1
        else:
            out.append(c); i += 1
    return ''.join(out)


def string_end(text, i):
    """The index after the string literal opening at text[i]. An interpolated string (`s!"…"`, `m!"…"`,
    `f!"…"`) holds code in braces, and that code may hold strings of its own."""
    n, interpolated = len(text), text[max(0, i - 2):i] in ('s!', 'm!', 'f!')
    j = i + 1
    while j < n and text[j] != '"':
        if text[j] == '\\':
            j += 2
        elif interpolated and text[j] == '{':
            depth, j = 1, j + 1
            while j < n and depth:
                if text[j] == '"':
                    j = string_end(text, j)
                    continue
                depth += text[j] == '{'
                depth -= text[j] == '}'
                j += 1
        else:
            j += 1
    return min(j + 1, n)


def commands(text):
    """(first line, last line, lines) of each column-0 command, 1-based, on blanked text."""
    lines = blank(text).split('\n')
    starts = [k for k, line in enumerate(lines) if line[:1].strip() and COMMAND.match(line)]
    out = []
    for a, b in zip(starts, starts[1:] + [len(lines)]):
        end = b - 1
        while end > a and not lines[end].strip():
            end -= 1
        out.append((a + 1, end + 1, lines[a:end + 1]))
    return out


def complexity(tokens):
    cc, arm, seen_arrow = 1, None, False
    for tok in tokens:
        if tok in BRANCH_WORDS or tok in ('&&', '||'):
            cc += 1
        elif tok == '|':
            if arm is None:
                arm = []  # an alternative starts; a second `|` before its `=>` is an or-pattern
        elif tok == '=>' and arm is not None:
            if any(t not in ('_', ',') for t in arm):
                cc += 1
            arm = None
        elif arm is not None:
            arm.append(tok)
    return cc


def name_of(kind, first_line):
    rest = DECL.match(first_line.strip())
    after = first_line.strip()[rest.end():].strip() if rest else ''
    word = re.match(r'[A-Za-z_][A-Za-z_0-9!?\'.]*', after)
    if word and kind != 'instance':
        return word.group(0)[:60]
    if word and kind == 'instance' and not after.startswith(':'):
        return word.group(0)[:60]
    return f'(instance {after.lstrip(": ").split(":=")[0].split(" where")[0].strip()[:48]})'


def analyze(text):
    """[(cc, lines, name, first line)] for each function, and (proof commands, their non-blank lines)."""
    found, proofs, proof_lines = [], 0, 0
    for start, end, body in commands(text):
        joined = ' '.join(body)
        m = DECL.match(joined.strip())
        if not m:
            continue
        kind = m.group(1)
        if kind in PROOFS:
            proofs += 1
            proof_lines += sum(1 for line in body if line.strip())
        elif kind in FUNCTIONS:
            found.append((complexity(TOKEN.findall(joined)), end - start + 1, name_of(kind, body[0] if DECL.match(body[0].strip()) else joined), start))
    return found, (proofs, proof_lines)
