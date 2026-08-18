#!/usr/bin/env python3
"""Validator for the Cyberpunk Neon VS Code theme.

Rules enforced (each has a stable rule id used by --selftest):

  strict-json         (a) the theme file must parse as strict JSON (no comments,
                          no trailing commas).
  theme-shape             top-level name/type/semanticHighlighting and the three
                          sections must be present and well-formed.
  unknown-color-key   (b) every key under "colors" must exist in the official
                          VS Code color registry (REGISTRY_KEYS below).
  alpha-policy        (c) surfaces are opaque; 8-digit hex is allowed only for
                          keys where VS Code stacks decorations over/under text
                          (ALPHA_ALLOWED_* below). Token and semantic token
                          colors are always 6-digit.
  contrast-floor      (d) WCAG contrast floors, checked on pairs — each
                          foreground against the surface it actually sits on.
  semantic-parity     (e) semanticTokenColors and tokenColors must assign the
                          same color to the same role (PARITY_ROLES below), so
                          LSP-highlighted files match TextMate-highlighted ones.
  ansi-verbatim       (f) the terminal ANSI table must match the canonical
                          Cyberpunk-Neon terminal palette byte for byte.

Registry source (rule b): the official Theme Color reference — the markdown
source `api/references/theme-color.md` of
https://code.visualstudio.com/api/references/theme-color, taken from
https://github.com/microsoft/vscode-docs at commit
31599c6b8a6ca8c46c7a17302954d9aadcc04e17 (extracted 2026-08-18, 910 keys,
one per `- `key`:` bullet).

`--selftest` mutates an in-memory copy of the real theme in several distinct
ways (unknown key, alpha'd token color, comment below the contrast floor,
semantic/TextMate parity break, ANSI table drift, comment-polluted JSON text)
and exits non-zero unless every mutation is caught by the rule that claims to
cover it. A rule that cannot fail is decoration; this proves each one can.

Usage:
    python3 scripts/check_theme.py themes/cyberpunk-neon-color-theme.json
    python3 scripts/check_theme.py --selftest
"""

import copy
import json
import re
import sys
from pathlib import Path

DEFAULT_THEME = Path(__file__).resolve().parent.parent / "themes" / "cyberpunk-neon-color-theme.json"

RULE_JSON = "strict-json"
RULE_SHAPE = "theme-shape"
RULE_REGISTRY = "unknown-color-key"
RULE_ALPHA = "alpha-policy"
RULE_CONTRAST = "contrast-floor"
RULE_PARITY = "semantic-parity"
RULE_ANSI = "ansi-verbatim"

HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")
HEX8 = re.compile(r"^#[0-9a-fA-F]{8}$")

# --- Rule (c): alpha policy -------------------------------------------------
# 8-digit hex is permitted ONLY where VS Code stacks decorations over or under
# text and translucency is functionally correct. Everything else is opaque:
# GlassIt owns window transparency, so theme-side surface alpha buys nothing.
ALPHA_ALLOWED_EXACT = frozenset({
    "editor.selectionBackground",
    "editor.inactiveSelectionBackground",
    "editor.selectionHighlightBackground",
    "editor.wordHighlightBackground",
    "editor.wordHighlightStrongBackground",
    "editor.findMatchBackground",
    "editor.findMatchHighlightBackground",
    "editor.findRangeHighlightBackground",
    "editor.hoverHighlightBackground",
    "editor.lineHighlightBackground",
    "editor.rangeHighlightBackground",
    "editor.foldBackground",
    "editorBracketMatch.background",
    "terminal.selectionBackground",
})
ALPHA_ALLOWED_PREFIXES = (
    "diffEditor.",
    "merge.",
    "minimapSlider.",
    "scrollbarSlider.",
    "editorOverviewRuler.",
    "list.drop",
)

# Deliberately-faint strokes: dim opaque colors whose function is faintness.
# Exempt from contrast floors (and they never appear in the pair lists below).
FAINT_BY_DESIGN = frozenset({
    "editorWhitespace.foreground",
    "editorIndentGuide.background1",
    "editorIndentGuide.activeBackground1",
    "editorRuler.foreground",
})

# --- Rule (d): contrast pairs ----------------------------------------------
PAIRS_45 = [
    ("editor.foreground", "editor.background"),
    ("sideBar.foreground", "sideBar.background"),
    ("statusBar.foreground", "statusBar.background"),
    ("statusBar.debuggingForeground", "statusBar.debuggingBackground"),
    ("statusBar.noFolderForeground", "statusBar.noFolderBackground"),
    ("tab.activeForeground", "tab.activeBackground"),
    ("list.activeSelectionForeground", "list.activeSelectionBackground"),
    ("button.foreground", "button.background"),
    ("badge.foreground", "badge.background"),
    ("activityBarBadge.foreground", "activityBarBadge.background"),
    ("editorLineNumber.activeForeground", "editor.background"),
    ("textLink.foreground", "editor.background"),
    ("textPreformat.foreground", "textCodeBlock.background"),
]
PAIRS_30 = [
    ("editorLineNumber.foreground", "editor.background"),
]

# ANSI entries exempt from the 3.0:1 floor. ansiBlack is background-tier by
# design; ansiBlue shares ansiBlack's exact hex in the canonical palette (the
# source material's quirk — its "blue" slot is the background blue, and the
# usable blue lives in ansiBrightBlue); ansi(Bright)Magenta is the palette's
# verbatim #711c91, mandated by rule (f), which wins over the floor here.
ANSI_CONTRAST_EXEMPT = frozenset({
    "terminal.ansiBlack",
    "terminal.ansiBlue",
    "terminal.ansiMagenta",
    "terminal.ansiBrightMagenta",
})

# --- Rule (f): canonical terminal palette, verbatim -------------------------
ANSI_TABLE = {
    "terminal.background": "#000b1e",
    "terminal.foreground": "#0abdc6",
    "terminal.ansiBlack": "#123e7c",
    "terminal.ansiRed": "#ff0000",
    "terminal.ansiGreen": "#d300c4",
    "terminal.ansiYellow": "#f57800",
    "terminal.ansiBlue": "#123e7c",
    "terminal.ansiMagenta": "#711c91",
    "terminal.ansiCyan": "#0abdc6",
    "terminal.ansiWhite": "#d7d7d5",
    "terminal.ansiBrightBlack": "#1c61c2",
    "terminal.ansiBrightRed": "#ff0000",
    "terminal.ansiBrightGreen": "#d300c4",
    "terminal.ansiBrightYellow": "#f57800",
    "terminal.ansiBrightBlue": "#00ff00",
    "terminal.ansiBrightMagenta": "#711c91",
    "terminal.ansiBrightCyan": "#0abdc6",
    "terminal.ansiBrightWhite": "#d7d7d5",
}

# --- Rule (e): semantic role -> mirror TextMate scope -----------------------
PARITY_ROLES = {
    "keyword": "keyword",
    "function": "entity.name.function",
    "method": "entity.name.function",
    "type": "entity.name.type",
    "class": "entity.name.class",
    "interface": "entity.name.interface",
    "enum": "entity.name.enum",
    "enumMember": "constant.other",
    "variable": "variable",
    "parameter": "variable.parameter",
    "property": "variable.other.property",
    "string": "string",
    "number": "constant.numeric",
    "comment": "comment",
    "namespace": "entity.name.namespace",
    "decorator": "entity.name.function.decorator",
    "macro": "entity.name.function.macro",
}


def relative_luminance(hex6):
    def channel(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r = channel(int(hex6[1:3], 16))
    g = channel(int(hex6[3:5], 16))
    b = channel(int(hex6[5:7], 16))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex6, bg_hex6):
    lf, lb = relative_luminance(fg_hex6), relative_luminance(bg_hex6)
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi + 0.05) / (lo + 0.05)


def alpha_allowed(key):
    return key in ALPHA_ALLOWED_EXACT or key.startswith(ALPHA_ALLOWED_PREFIXES)


def semantic_foreground(value):
    """A semanticTokenColors value is either "#rrggbb" or a style object."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("foreground")
    return None


def check_shape(theme):
    fails = []
    if theme.get("name") != "Cyberpunk Neon":
        fails.append((RULE_SHAPE, 'top-level "name" must be "Cyberpunk Neon"'))
    if theme.get("type") != "dark":
        fails.append((RULE_SHAPE, 'top-level "type" must be "dark"'))
    if theme.get("semanticHighlighting") is not True:
        fails.append((RULE_SHAPE, '"semanticHighlighting" must be true'))
    for section, kind in (("colors", dict), ("tokenColors", list), ("semanticTokenColors", dict)):
        if not isinstance(theme.get(section), kind):
            fails.append((RULE_SHAPE, f'"{section}" must be a {kind.__name__}'))
    return fails


def check_registry(theme):
    fails = []
    for key in theme.get("colors", {}):
        if key not in REGISTRY_KEYS:
            fails.append((RULE_REGISTRY, f'"{key}" is not in the VS Code color registry'))
    return fails


def check_alpha(theme):
    fails = []
    for key, value in theme.get("colors", {}).items():
        if not isinstance(value, str) or not (HEX6.match(value) or HEX8.match(value)):
            fails.append((RULE_ALPHA, f'"{key}": "{value}" is not #rrggbb or #rrggbbaa'))
            continue
        if HEX8.match(value) and not alpha_allowed(key):
            fails.append((RULE_ALPHA, f'"{key}": "{value}" carries alpha but is not a stacking-decoration key'))
    for i, entry in enumerate(theme.get("tokenColors", [])):
        fg = entry.get("settings", {}).get("foreground")
        if fg is not None and not HEX6.match(fg):
            fails.append((RULE_ALPHA, f'tokenColors[{i}] ("{entry.get("name", "?")}"): foreground "{fg}" must be opaque 6-digit hex'))
    for key, value in theme.get("semanticTokenColors", {}).items():
        fg = semantic_foreground(value)
        if fg is not None and not HEX6.match(fg):
            fails.append((RULE_ALPHA, f'semanticTokenColors "{key}": foreground "{fg}" must be opaque 6-digit hex'))
    return fails


def check_contrast(theme):
    fails = []
    colors = theme.get("colors", {})

    def color6(key):
        v = colors.get(key)
        return v if isinstance(v, str) and HEX6.match(v) else None

    def check_pair(fg_key, bg_key, floor, label):
        fg, bg = color6(fg_key), color6(bg_key)
        if fg is None or bg is None:
            fails.append((RULE_CONTRAST, f"{label}: missing or non-opaque {fg_key} / {bg_key}"))
            return
        ratio = contrast_ratio(fg, bg)
        if ratio < floor:
            fails.append((RULE_CONTRAST, f"{label}: {fg_key} {fg} vs {bg_key} {bg} is {ratio:.2f}:1, floor {floor}:1"))

    for fg_key, bg_key in PAIRS_45:
        check_pair(fg_key, bg_key, 4.5, "workbench pair")
    for fg_key, bg_key in PAIRS_30:
        check_pair(fg_key, bg_key, 3.0, "workbench pair")

    editor_bg = color6("editor.background")
    terminal_bg = color6("terminal.background")
    if editor_bg is None or terminal_bg is None:
        fails.append((RULE_CONTRAST, "editor.background / terminal.background missing or non-opaque"))
        return fails

    for i, entry in enumerate(theme.get("tokenColors", [])):
        fg = entry.get("settings", {}).get("foreground")
        if fg is None or not HEX6.match(fg):
            continue  # alpha policy reports malformed values
        scopes = entry.get("scope", [])
        if isinstance(scopes, str):
            scopes = [scopes]
        is_comment = any("comment" in s for s in scopes)
        floor = 3.0 if is_comment else 4.5
        ratio = contrast_ratio(fg, editor_bg)
        if ratio < floor:
            fails.append((RULE_CONTRAST, f'tokenColors[{i}] ("{entry.get("name", "?")}"): {fg} vs editor.background is {ratio:.2f}:1, floor {floor}:1'))

    for key, value in theme.get("semanticTokenColors", {}).items():
        fg = semantic_foreground(value)
        if fg is None or not HEX6.match(fg):
            continue
        floor = 3.0 if "comment" in key.lower() else 4.5
        ratio = contrast_ratio(fg, editor_bg)
        if ratio < floor:
            fails.append((RULE_CONTRAST, f'semanticTokenColors "{key}": {fg} vs editor.background is {ratio:.2f}:1, floor {floor}:1'))

    for key in ANSI_TABLE:
        if not key.startswith("terminal.ansi") or key in ANSI_CONTRAST_EXEMPT:
            continue
        fg = color6(key)
        if fg is None:
            continue  # ansi-verbatim reports missing entries
        ratio = contrast_ratio(fg, terminal_bg)
        if ratio < 3.0:
            fails.append((RULE_CONTRAST, f"{key} {fg} vs terminal.background is {ratio:.2f}:1, floor 3.0:1"))

    return fails


def check_parity(theme):
    fails = []
    entries = theme.get("tokenColors", [])
    semantic = theme.get("semanticTokenColors", {})

    def textmate_color(scope):
        found = []
        for entry in entries:
            scopes = entry.get("scope", [])
            if isinstance(scopes, str):
                scopes = [scopes]
            if scope in scopes:
                found.append(entry.get("settings", {}).get("foreground"))
        return found

    for role, scope in PARITY_ROLES.items():
        sem_fg = semantic_foreground(semantic.get(role))
        if sem_fg is None:
            fails.append((RULE_PARITY, f'semanticTokenColors is missing "{role}"'))
            continue
        tm_colors = [c for c in textmate_color(scope) if c]
        if not tm_colors:
            fails.append((RULE_PARITY, f'no tokenColors entry covers scope "{scope}" (mirror of semantic "{role}")'))
            continue
        if len(set(c.lower() for c in tm_colors)) > 1:
            fails.append((RULE_PARITY, f'scope "{scope}" appears with conflicting colors {tm_colors}'))
            continue
        if sem_fg.lower() != tm_colors[0].lower():
            fails.append((RULE_PARITY, f'"{role}": semantic {sem_fg} != TextMate {tm_colors[0]} (scope "{scope}")'))
    return fails


def check_ansi(theme):
    fails = []
    colors = theme.get("colors", {})
    for key, expected in ANSI_TABLE.items():
        actual = colors.get(key)
        if not isinstance(actual, str) or actual.lower() != expected:
            fails.append((RULE_ANSI, f'{key} must be {expected} verbatim, found {actual!r}'))
    return fails


def run_checks(theme):
    fails = []
    fails += check_shape(theme)
    fails += check_registry(theme)
    fails += check_alpha(theme)
    fails += check_contrast(theme)
    fails += check_parity(theme)
    fails += check_ansi(theme)
    return fails


def load_strict(path):
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def main_check(path):
    try:
        theme = load_strict(path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL [{RULE_JSON}] {path}: {exc}")
        return 1
    fails = run_checks(theme)
    for rule, message in fails:
        print(f"FAIL [{rule}] {message}")
    if fails:
        print(f"\n{len(fails)} failure(s) in {path}")
        return 1
    n_colors = len(theme["colors"])
    n_tokens = len(theme["tokenColors"])
    n_semantic = len(theme["semanticTokenColors"])
    print(f"OK: {path}")
    print(f"  {n_colors} workbench colors, all present in the registry ({len(REGISTRY_KEYS)} known keys)")
    print(f"  {n_tokens} tokenColors entries, {n_semantic} semantic token rules")
    print("  alpha policy, contrast floors, semantic parity, ANSI table: all pass")
    return 0


def main_selftest(path):
    try:
        base = load_strict(path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"selftest needs a valid theme to mutate; {path} failed to load: {exc}")
        return 1
    if run_checks(base):
        print(f"selftest needs a passing theme to mutate; {path} has failures (run the plain check)")
        return 1

    def fired(theme, rule):
        return any(r == rule for r, _ in run_checks(theme))

    mutations = []

    def mutation(description, rule, mutate):
        theme = copy.deepcopy(base)
        mutate(theme)
        mutations.append((description, rule, fired(theme, rule)))

    mutation(
        "invented color key editor.hologramGlow",
        RULE_REGISTRY,
        lambda t: t["colors"].__setitem__("editor.hologramGlow", "#ff00ff"),
    )

    def alpha_token(theme):
        for entry in theme["tokenColors"]:
            scopes = entry.get("scope", [])
            if "string" in (scopes if isinstance(scopes, list) else [scopes]):
                entry["settings"]["foreground"] = "#f5780080"
                return
        raise AssertionError("no string entry to mutate")

    mutation("token color with alpha (#f5780080 on strings)", RULE_ALPHA, alpha_token)

    def darken_comment(theme):
        for entry in theme["tokenColors"]:
            scopes = entry.get("scope", [])
            if "comment" in (scopes if isinstance(scopes, list) else [scopes]):
                entry["settings"]["foreground"] = "#123e7c"
                return
        raise AssertionError("no comment entry to mutate")

    mutation("comment darkened to #123e7c (~1.9:1, below the 3.0 floor)", RULE_CONTRAST, darken_comment)

    mutation(
        "semantic keyword recolored to #f57800 while TextMate keyword stays #ea00d9",
        RULE_PARITY,
        lambda t: t["semanticTokenColors"].__setitem__("keyword", "#f57800"),
    )

    mutation(
        "terminal.ansiGreen drifted to #00ff00 (table says #d300c4)",
        RULE_ANSI,
        lambda t: t["colors"].__setitem__("terminal.ansiGreen", "#00ff00"),
    )

    text = Path(path).read_text(encoding="utf-8")
    polluted = text.replace("{", "{ // strict JSON permits no comments", 1)
    try:
        json.loads(polluted)
        json_caught = False
    except json.JSONDecodeError:
        json_caught = True
    mutations.append(("theme text polluted with a // comment", RULE_JSON, json_caught))

    ok = True
    for description, rule, caught in mutations:
        if caught:
            print(f"CAUGHT [{rule}] {description}")
        else:
            print(f"MISSED [{rule}] {description} — rule cannot fail, checker is decorative")
            ok = False
    print(f"\nselftest: {sum(c for _, _, c in mutations)}/{len(mutations)} mutations caught")
    return 0 if ok else 1


def main(argv):
    args = [a for a in argv[1:] if a != "--selftest"]
    selftest = "--selftest" in argv[1:]
    path = Path(args[0]) if args else DEFAULT_THEME
    return main_selftest(path) if selftest else main_check(path)


# Rule (b) registry: see the docstring for source and commit.
REGISTRY_KEYS = frozenset("""
actionBar.toggledBackground
activityBar.activeBackground
activityBar.activeBorder
activityBar.activeFocusBorder
activityBar.background
activityBar.border
activityBar.dropBorder
activityBar.foreground
activityBar.inactiveForeground
activityBarBadge.background
activityBarBadge.foreground
activityBarTop.activeBackground
activityBarTop.activeBorder
activityBarTop.background
activityBarTop.dropBorder
activityBarTop.foreground
activityBarTop.inactiveForeground
activityErrorBadge.background
activityErrorBadge.foreground
activityWarningBadge.background
activityWarningBadge.foreground
agentSessionReadIndicator.foreground
agentSessionSelectedBadge.border
agentSessionSelectedUnfocusedBadge.border
agentStatusIndicator.background
aiCustomizationManagement.sashBorder
badge.background
badge.foreground
banner.background
banner.foreground
banner.iconForeground
breadcrumb.activeSelectionForeground
breadcrumb.background
breadcrumb.focusForeground
breadcrumb.foreground
breadcrumbPicker.background
button.background
button.border
button.foreground
button.hoverBackground
button.secondaryBackground
button.secondaryBorder
button.secondaryForeground
button.secondaryHoverBackground
button.separator
chart.axis
chart.guide
chart.line
charts.blue
charts.foreground
charts.green
charts.lines
charts.orange
charts.purple
charts.red
charts.yellow
chat.avatarBackground
chat.avatarForeground
chat.checkpointSeparator
chat.editedFileForeground
chat.linesAddedForeground
chat.linesRemovedForeground
chat.requestBackground
chat.requestBorder
chat.requestBubbleBackground
chat.requestBubbleHoverBackground
chat.requestCodeBorder
chat.slashCommandBackground
chat.slashCommandForeground
chat.thinkingShimmer
chatManagement.sashBorder
checkbox.background
checkbox.border
checkbox.disabled.background
checkbox.disabled.foreground
checkbox.foreground
checkbox.selectBackground
checkbox.selectBorder
commandCenter.activeBackground
commandCenter.activeBorder
commandCenter.activeForeground
commandCenter.background
commandCenter.border
commandCenter.debuggingBackground
commandCenter.foreground
commandCenter.inactiveBorder
commandCenter.inactiveForeground
commentsView.resolvedIcon
commentsView.unresolvedIcon
contrastActiveBorder
contrastBorder
debugConsole.errorForeground
debugConsole.infoForeground
debugConsole.sourceForeground
debugConsole.warningForeground
debugConsoleInputIcon.foreground
debugExceptionWidget.background
debugExceptionWidget.border
debugIcon.breakpointCurrentStackframeForeground
debugIcon.breakpointDisabledForeground
debugIcon.breakpointForeground
debugIcon.breakpointStackframeForeground
debugIcon.breakpointUnverifiedForeground
debugIcon.continueForeground
debugIcon.disconnectForeground
debugIcon.pauseForeground
debugIcon.restartForeground
debugIcon.startForeground
debugIcon.stepBackForeground
debugIcon.stepIntoForeground
debugIcon.stepOutForeground
debugIcon.stepOverForeground
debugIcon.stopForeground
debugTokenExpression.boolean
debugTokenExpression.error
debugTokenExpression.name
debugTokenExpression.number
debugTokenExpression.string
debugTokenExpression.type
debugTokenExpression.value
debugToolBar.background
debugToolBar.border
debugView.exceptionLabelBackground
debugView.exceptionLabelForeground
debugView.stateLabelBackground
debugView.stateLabelForeground
debugView.valueChangedHighlight
descriptionForeground
diffEditor.border
diffEditor.diagonalFill
diffEditor.insertedLineBackground
diffEditor.insertedTextBackground
diffEditor.insertedTextBorder
diffEditor.move.border
diffEditor.moveActive.border
diffEditor.removedLineBackground
diffEditor.removedTextBackground
diffEditor.removedTextBorder
diffEditor.unchangedCodeBackground
diffEditor.unchangedRegionBackground
diffEditor.unchangedRegionForeground
diffEditor.unchangedRegionShadow
diffEditorGutter.insertedLineBackground
diffEditorGutter.removedLineBackground
diffEditorOverview.insertedForeground
diffEditorOverview.removedForeground
disabledForeground
dropdown.background
dropdown.border
dropdown.foreground
dropdown.listBackground
editor.background
editor.compositionBorder
editor.findMatchBackground
editor.findMatchBorder
editor.findMatchForeground
editor.findMatchHighlightBackground
editor.findMatchHighlightBorder
editor.findMatchHighlightForeground
editor.findRangeHighlightBackground
editor.findRangeHighlightBorder
editor.focusedStackFrameHighlightBackground
editor.foldBackground
editor.foldPlaceholderForeground
editor.foreground
editor.hoverHighlightBackground
editor.inactiveLineHighlightBackground
editor.inactiveSelectionBackground
editor.inlineValuesBackground
editor.inlineValuesForeground
editor.lineHighlightBackground
editor.lineHighlightBorder
editor.linkedEditingBackground
editor.placeholder.foreground
editor.rangeHighlightBackground
editor.rangeHighlightBorder
editor.selectionBackground
editor.selectionForeground
editor.selectionHighlightBackground
editor.selectionHighlightBorder
editor.snippetFinalTabstopHighlightBackground
editor.snippetFinalTabstopHighlightBorder
editor.snippetTabstopHighlightBackground
editor.snippetTabstopHighlightBorder
editor.stackFrameHighlightBackground
editor.symbolHighlightBackground
editor.symbolHighlightBorder
editor.wordHighlightBackground
editor.wordHighlightBorder
editor.wordHighlightStrongBackground
editor.wordHighlightStrongBorder
editor.wordHighlightTextBackground
editor.wordHighlightTextBorder
editorActionList.background
editorActionList.focusBackground
editorActionList.focusForeground
editorActionList.foreground
editorBracketHighlight.foreground1
editorBracketHighlight.foreground2
editorBracketHighlight.foreground3
editorBracketHighlight.foreground4
editorBracketHighlight.foreground5
editorBracketHighlight.foreground6
editorBracketHighlight.unexpectedBracket.foreground
editorBracketMatch.background
editorBracketMatch.border
editorBracketMatch.foreground
editorBracketPairGuide.activeBackground1
editorBracketPairGuide.activeBackground2
editorBracketPairGuide.activeBackground3
editorBracketPairGuide.activeBackground4
editorBracketPairGuide.activeBackground5
editorBracketPairGuide.activeBackground6
editorBracketPairGuide.background1
editorBracketPairGuide.background2
editorBracketPairGuide.background3
editorBracketPairGuide.background4
editorBracketPairGuide.background5
editorBracketPairGuide.background6
editorCodeLens.foreground
editorCommentsWidget.rangeActiveBackground
editorCommentsWidget.rangeBackground
editorCommentsWidget.replyInputBackground
editorCommentsWidget.resolvedBorder
editorCommentsWidget.unresolvedBorder
editorCursor.background
editorCursor.foreground
editorError.background
editorError.border
editorError.foreground
editorGhostText.background
editorGhostText.border
editorGhostText.foreground
editorGroup.border
editorGroup.dropBackground
editorGroup.dropIntoPromptBackground
editorGroup.dropIntoPromptBorder
editorGroup.dropIntoPromptForeground
editorGroup.emptyBackground
editorGroup.focusedEmptyBorder
editorGroupHeader.border
editorGroupHeader.noTabsBackground
editorGroupHeader.tabsBackground
editorGroupHeader.tabsBorder
editorGutter.addedBackground
editorGutter.addedSecondaryBackground
editorGutter.background
editorGutter.commentDraftGlyphForeground
editorGutter.commentGlyphForeground
editorGutter.commentRangeForeground
editorGutter.commentUnresolvedGlyphForeground
editorGutter.deletedBackground
editorGutter.deletedSecondaryBackground
editorGutter.foldingControlForeground
editorGutter.itemBackground
editorGutter.itemGlyphForeground
editorGutter.modifiedBackground
editorGutter.modifiedSecondaryBackground
editorHint.border
editorHint.foreground
editorHoverWidget.background
editorHoverWidget.border
editorHoverWidget.foreground
editorHoverWidget.highlightForeground
editorHoverWidget.statusBarBackground
editorIndentGuide.activeBackground
editorIndentGuide.activeBackground1
editorIndentGuide.activeBackground2
editorIndentGuide.activeBackground3
editorIndentGuide.activeBackground4
editorIndentGuide.activeBackground5
editorIndentGuide.activeBackground6
editorIndentGuide.background
editorIndentGuide.background1
editorIndentGuide.background2
editorIndentGuide.background3
editorIndentGuide.background4
editorIndentGuide.background5
editorIndentGuide.background6
editorInfo.background
editorInfo.border
editorInfo.foreground
editorInlayHint.background
editorInlayHint.foreground
editorInlayHint.parameterBackground
editorInlayHint.parameterForeground
editorInlayHint.typeBackground
editorInlayHint.typeForeground
editorLightBulb.foreground
editorLightBulbAi.foreground
editorLightBulbAutoFix.foreground
editorLineNumber.activeForeground
editorLineNumber.dimmedForeground
editorLineNumber.foreground
editorLink.activeForeground
editorMarkerNavigation.background
editorMarkerNavigationError.background
editorMarkerNavigationError.headerBackground
editorMarkerNavigationInfo.background
editorMarkerNavigationInfo.headerBackground
editorMarkerNavigationWarning.background
editorMarkerNavigationWarning.headerBackground
editorMinimap.inlineChatInserted
editorMultiCursor.primary.background
editorMultiCursor.primary.foreground
editorMultiCursor.secondary.background
editorMultiCursor.secondary.foreground
editorOverviewRuler.addedForeground
editorOverviewRuler.background
editorOverviewRuler.border
editorOverviewRuler.bracketMatchForeground
editorOverviewRuler.commentDraftForeground
editorOverviewRuler.commentForeground
editorOverviewRuler.commentUnresolvedForeground
editorOverviewRuler.commonContentForeground
editorOverviewRuler.currentContentForeground
editorOverviewRuler.deletedForeground
editorOverviewRuler.errorForeground
editorOverviewRuler.findMatchForeground
editorOverviewRuler.incomingContentForeground
editorOverviewRuler.infoForeground
editorOverviewRuler.inlineChatInserted
editorOverviewRuler.inlineChatRemoved
editorOverviewRuler.modifiedForeground
editorOverviewRuler.rangeHighlightForeground
editorOverviewRuler.selectionHighlightForeground
editorOverviewRuler.warningForeground
editorOverviewRuler.wordHighlightForeground
editorOverviewRuler.wordHighlightStrongForeground
editorOverviewRuler.wordHighlightTextForeground
editorPane.background
editorRuler.foreground
editorStickyScroll.background
editorStickyScroll.border
editorStickyScroll.shadow
editorStickyScrollGutter.background
editorStickyScrollHover.background
editorSuggestWidget.background
editorSuggestWidget.border
editorSuggestWidget.focusHighlightForeground
editorSuggestWidget.foreground
editorSuggestWidget.highlightForeground
editorSuggestWidget.selectedBackground
editorSuggestWidget.selectedForeground
editorSuggestWidget.selectedIconForeground
editorSuggestWidgetStatus.foreground
editorUnicodeHighlight.background
editorUnicodeHighlight.border
editorUnnecessaryCode.border
editorUnnecessaryCode.opacity
editorWarning.background
editorWarning.border
editorWarning.foreground
editorWhitespace.foreground
editorWidget.background
editorWidget.border
editorWidget.foreground
editorWidget.resizeBorder
errorForeground
extensionBadge.remoteBackground
extensionBadge.remoteForeground
extensionButton.background
extensionButton.border
extensionButton.foreground
extensionButton.hoverBackground
extensionButton.prominentBackground
extensionButton.prominentForeground
extensionButton.prominentHoverBackground
extensionButton.separator
extensionIcon.preReleaseForeground
extensionIcon.privateForeground
extensionIcon.sponsorForeground
extensionIcon.starForeground
extensionIcon.verifiedForeground
focusBorder
foreground
gauge.background
gauge.border
gauge.errorBackground
gauge.errorForeground
gauge.foreground
gauge.warningBackground
gauge.warningForeground
git.blame.editorDecorationForeground
gitDecoration.addedResourceForeground
gitDecoration.conflictingResourceForeground
gitDecoration.deletedResourceForeground
gitDecoration.ignoredResourceForeground
gitDecoration.modifiedResourceForeground
gitDecoration.renamedResourceForeground
gitDecoration.stageDeletedResourceForeground
gitDecoration.stageModifiedResourceForeground
gitDecoration.submoduleResourceForeground
gitDecoration.untrackedResourceForeground
icon.foreground
inlineChat.background
inlineChat.border
inlineChat.foreground
inlineChat.shadow
inlineChatDiff.inserted
inlineChatDiff.removed
inlineChatInput.background
inlineChatInput.border
inlineChatInput.focusBorder
inlineChatInput.placeholderForeground
inlineEdit.gutterIndicator.background
inlineEdit.gutterIndicator.primaryBackground
inlineEdit.gutterIndicator.primaryBorder
inlineEdit.gutterIndicator.primaryForeground
inlineEdit.gutterIndicator.secondaryBackground
inlineEdit.gutterIndicator.secondaryBorder
inlineEdit.gutterIndicator.secondaryForeground
inlineEdit.gutterIndicator.successfulBackground
inlineEdit.gutterIndicator.successfulBorder
inlineEdit.gutterIndicator.successfulForeground
inlineEdit.modifiedBackground
inlineEdit.modifiedBorder
inlineEdit.modifiedChangedLineBackground
inlineEdit.modifiedChangedTextBackground
inlineEdit.originalBackground
inlineEdit.originalBorder
inlineEdit.originalChangedLineBackground
inlineEdit.originalChangedTextBackground
inlineEdit.tabWillAcceptModifiedBorder
inlineEdit.tabWillAcceptOriginalBorder
input.background
input.border
input.foreground
input.placeholderForeground
inputOption.activeBackground
inputOption.activeBorder
inputOption.activeForeground
inputOption.hoverBackground
inputValidation.errorBackground
inputValidation.errorBorder
inputValidation.errorForeground
inputValidation.infoBackground
inputValidation.infoBorder
inputValidation.infoForeground
inputValidation.warningBackground
inputValidation.warningBorder
inputValidation.warningForeground
interactive.activeCodeBorder
interactive.inactiveCodeBorder
keybindingLabel.background
keybindingLabel.border
keybindingLabel.bottomBorder
keybindingLabel.foreground
keybindingTable.headerBackground
keybindingTable.rowsBackground
list.activeSelectionBackground
list.activeSelectionForeground
list.activeSelectionIconForeground
list.deemphasizedForeground
list.dropBackground
list.dropBetweenBackground
list.errorForeground
list.filterMatchBackground
list.filterMatchBorder
list.focusAndSelectionOutline
list.focusBackground
list.focusForeground
list.focusHighlightForeground
list.focusOutline
list.highlightForeground
list.hoverBackground
list.hoverForeground
list.inactiveFocusBackground
list.inactiveFocusOutline
list.inactiveSelectionBackground
list.inactiveSelectionForeground
list.inactiveSelectionIconForeground
list.invalidItemForeground
list.warningForeground
listFilterWidget.background
listFilterWidget.noMatchesOutline
listFilterWidget.outline
listFilterWidget.shadow
markdownAlert.caution.foreground
markdownAlert.important.foreground
markdownAlert.note.foreground
markdownAlert.tip.foreground
markdownAlert.warning.foreground
mcpIcon.starForeground
menu.background
menu.border
menu.foreground
menu.selectionBackground
menu.selectionBorder
menu.selectionForeground
menu.separatorBackground
menubar.selectionBackground
menubar.selectionBorder
menubar.selectionForeground
merge.border
merge.commonContentBackground
merge.commonHeaderBackground
merge.currentContentBackground
merge.currentHeaderBackground
merge.incomingContentBackground
merge.incomingHeaderBackground
mergeEditor.change.background
mergeEditor.change.word.background
mergeEditor.changeBase.background
mergeEditor.changeBase.word.background
mergeEditor.conflict.handled.minimapOverViewRuler
mergeEditor.conflict.handledFocused.border
mergeEditor.conflict.handledUnfocused.border
mergeEditor.conflict.input1.background
mergeEditor.conflict.input2.background
mergeEditor.conflict.unhandled.minimapOverViewRuler
mergeEditor.conflict.unhandledFocused.border
mergeEditor.conflict.unhandledUnfocused.border
mergeEditor.conflictingLines.background
minimap.background
minimap.chatEditHighlight
minimap.errorHighlight
minimap.findMatchHighlight
minimap.foregroundOpacity
minimap.infoHighlight
minimap.selectionHighlight
minimap.selectionOccurrenceHighlight
minimap.warningHighlight
minimapGutter.addedBackground
minimapGutter.deletedBackground
minimapGutter.modifiedBackground
minimapSlider.activeBackground
minimapSlider.background
minimapSlider.hoverBackground
multiDiffEditor.background
multiDiffEditor.border
multiDiffEditor.headerBackground
notebook.cellBorderColor
notebook.cellEditorBackground
notebook.cellHoverBackground
notebook.cellInsertionIndicator
notebook.cellStatusBarItemHoverBackground
notebook.cellToolbarSeparator
notebook.editorBackground
notebook.focusedCellBackground
notebook.focusedCellBorder
notebook.focusedEditorBorder
notebook.inactiveFocusedCellBorder
notebook.inactiveSelectedCellBorder
notebook.outputContainerBackgroundColor
notebook.outputContainerBorderColor
notebook.selectedCellBackground
notebook.selectedCellBorder
notebook.symbolHighlightBackground
notebookEditorOverviewRuler.runningCellForeground
notebookScrollbarSlider.activeBackground
notebookScrollbarSlider.background
notebookScrollbarSlider.hoverBackground
notebookStatusErrorIcon.foreground
notebookStatusRunningIcon.foreground
notebookStatusSuccessIcon.foreground
notificationCenter.border
notificationCenterHeader.background
notificationCenterHeader.foreground
notificationLink.foreground
notificationToast.border
notifications.background
notifications.border
notifications.foreground
notificationsErrorIcon.foreground
notificationsInfoIcon.foreground
notificationsWarningIcon.foreground
outputView.background
outputViewStickyScroll.background
panel.background
panel.border
panel.dropBorder
panelInput.border
panelSection.border
panelSection.dropBackground
panelSectionHeader.background
panelSectionHeader.border
panelSectionHeader.foreground
panelStickyScroll.background
panelStickyScroll.border
panelStickyScroll.shadow
panelTitle.activeBorder
panelTitle.activeForeground
panelTitle.border
panelTitle.inactiveForeground
panelTitleBadge.background
panelTitleBadge.foreground
peekView.border
peekViewEditor.background
peekViewEditor.matchHighlightBackground
peekViewEditor.matchHighlightBorder
peekViewEditorGutter.background
peekViewEditorStickyScroll.background
peekViewEditorStickyScrollGutter.background
peekViewResult.background
peekViewResult.fileForeground
peekViewResult.lineForeground
peekViewResult.matchHighlightBackground
peekViewResult.selectionBackground
peekViewResult.selectionForeground
peekViewTitle.background
peekViewTitleDescription.foreground
peekViewTitleLabel.foreground
pickerGroup.border
pickerGroup.foreground
ports.iconRunningProcessForeground
problemsErrorIcon.foreground
problemsInfoIcon.foreground
problemsWarningIcon.foreground
profileBadge.background
profileBadge.foreground
profiles.sashBorder
progressBar.background
quickInput.background
quickInput.foreground
quickInputList.focusBackground
quickInputList.focusForeground
quickInputList.focusIconForeground
quickInputTitle.background
radio.activeBackground
radio.activeBorder
radio.activeForeground
radio.inactiveBackground
radio.inactiveBorder
radio.inactiveForeground
radio.inactiveHoverBackground
sash.hoverBorder
scmGraph.foreground1
scmGraph.foreground2
scmGraph.foreground3
scmGraph.foreground4
scmGraph.foreground5
scmGraph.historyItemBaseRefColor
scmGraph.historyItemHoverAdditionsForeground
scmGraph.historyItemHoverDefaultLabelBackground
scmGraph.historyItemHoverDefaultLabelForeground
scmGraph.historyItemHoverDeletionsForeground
scmGraph.historyItemHoverLabelForeground
scmGraph.historyItemRefColor
scmGraph.historyItemRemoteRefColor
scrollbar.background
scrollbar.shadow
scrollbarSlider.activeBackground
scrollbarSlider.background
scrollbarSlider.hoverBackground
search.resultsInfoForeground
searchEditor.findMatchBackground
searchEditor.findMatchBorder
searchEditor.textInputBorder
selection.background
settings.checkboxBackground
settings.checkboxBorder
settings.checkboxForeground
settings.dropdownBackground
settings.dropdownBorder
settings.dropdownForeground
settings.dropdownListBorder
settings.focusedRowBackground
settings.focusedRowBorder
settings.headerBorder
settings.headerForeground
settings.modifiedItemIndicator
settings.numberInputBackground
settings.numberInputBorder
settings.numberInputForeground
settings.rowHoverBackground
settings.sashBorder
settings.settingsHeaderHoverForeground
settings.textInputBackground
settings.textInputBorder
settings.textInputForeground
sideBar.background
sideBar.border
sideBar.dropBackground
sideBar.foreground
sideBarActivityBarTop.border
sideBarSectionHeader.background
sideBarSectionHeader.border
sideBarSectionHeader.foreground
sideBarStickyScroll.background
sideBarStickyScroll.border
sideBarStickyScroll.shadow
sideBarTitle.background
sideBarTitle.border
sideBarTitle.foreground
sideBySideEditor.horizontalBorder
sideBySideEditor.verticalBorder
simpleFindWidget.sashBorder
statusBar.background
statusBar.border
statusBar.debuggingBackground
statusBar.debuggingBorder
statusBar.debuggingForeground
statusBar.focusBorder
statusBar.foreground
statusBar.noFolderBackground
statusBar.noFolderBorder
statusBar.noFolderForeground
statusBarItem.activeBackground
statusBarItem.compactHoverBackground
statusBarItem.errorBackground
statusBarItem.errorForeground
statusBarItem.errorHoverBackground
statusBarItem.errorHoverForeground
statusBarItem.focusBorder
statusBarItem.hoverBackground
statusBarItem.hoverForeground
statusBarItem.offlineBackground
statusBarItem.offlineForeground
statusBarItem.offlineHoverBackground
statusBarItem.offlineHoverForeground
statusBarItem.prominentBackground
statusBarItem.prominentForeground
statusBarItem.prominentHoverBackground
statusBarItem.prominentHoverForeground
statusBarItem.remoteBackground
statusBarItem.remoteForeground
statusBarItem.remoteHoverBackground
statusBarItem.remoteHoverForeground
statusBarItem.warningBackground
statusBarItem.warningForeground
statusBarItem.warningHoverBackground
statusBarItem.warningHoverForeground
symbolIcon.arrayForeground
symbolIcon.booleanForeground
symbolIcon.classForeground
symbolIcon.colorForeground
symbolIcon.constantForeground
symbolIcon.constructorForeground
symbolIcon.enumeratorForeground
symbolIcon.enumeratorMemberForeground
symbolIcon.eventForeground
symbolIcon.fieldForeground
symbolIcon.fileForeground
symbolIcon.folderForeground
symbolIcon.functionForeground
symbolIcon.interfaceForeground
symbolIcon.keyForeground
symbolIcon.keywordForeground
symbolIcon.methodForeground
symbolIcon.moduleForeground
symbolIcon.namespaceForeground
symbolIcon.nullForeground
symbolIcon.numberForeground
symbolIcon.objectForeground
symbolIcon.operatorForeground
symbolIcon.packageForeground
symbolIcon.propertyForeground
symbolIcon.referenceForeground
symbolIcon.snippetForeground
symbolIcon.stringForeground
symbolIcon.structForeground
symbolIcon.textForeground
symbolIcon.typeParameterForeground
symbolIcon.unitForeground
symbolIcon.variableForeground
tab.activeBackground
tab.activeBorder
tab.activeBorderTop
tab.activeForeground
tab.activeModifiedBorder
tab.border
tab.dragAndDropBorder
tab.hoverBackground
tab.hoverBorder
tab.hoverForeground
tab.inactiveBackground
tab.inactiveForeground
tab.inactiveModifiedBorder
tab.lastPinnedBorder
tab.selectedBackground
tab.selectedBorderTop
tab.selectedForeground
tab.unfocusedActiveBackground
tab.unfocusedActiveBorder
tab.unfocusedActiveBorderTop
tab.unfocusedActiveForeground
tab.unfocusedActiveModifiedBorder
tab.unfocusedHoverBackground
tab.unfocusedHoverBorder
tab.unfocusedHoverForeground
tab.unfocusedInactiveBackground
tab.unfocusedInactiveForeground
tab.unfocusedInactiveModifiedBorder
terminal.ansiBlack
terminal.ansiBlue
terminal.ansiBrightBlack
terminal.ansiBrightBlue
terminal.ansiBrightCyan
terminal.ansiBrightGreen
terminal.ansiBrightMagenta
terminal.ansiBrightRed
terminal.ansiBrightWhite
terminal.ansiBrightYellow
terminal.ansiCyan
terminal.ansiGreen
terminal.ansiMagenta
terminal.ansiRed
terminal.ansiWhite
terminal.ansiYellow
terminal.background
terminal.border
terminal.dropBackground
terminal.findMatchBackground
terminal.findMatchBorder
terminal.findMatchHighlightBackground
terminal.findMatchHighlightBorder
terminal.foreground
terminal.hoverHighlightBackground
terminal.inactiveSelectionBackground
terminal.initialHintForeground
terminal.selectionBackground
terminal.selectionForeground
terminal.tab.activeBorder
terminalCommandDecoration.defaultBackground
terminalCommandDecoration.errorBackground
terminalCommandDecoration.successBackground
terminalCommandGuide.foreground
terminalCursor.background
terminalCursor.foreground
terminalOverviewRuler.border
terminalOverviewRuler.cursorForeground
terminalOverviewRuler.findMatchForeground
terminalStickyScroll.background
terminalStickyScroll.border
terminalStickyScrollHover.background
terminalSymbolIcon.aliasForeground
terminalSymbolIcon.argumentForeground
terminalSymbolIcon.branchForeground
terminalSymbolIcon.commitForeground
terminalSymbolIcon.fileForeground
terminalSymbolIcon.flagForeground
terminalSymbolIcon.folderForeground
terminalSymbolIcon.inlineSuggestionForeground
terminalSymbolIcon.methodForeground
terminalSymbolIcon.optionForeground
terminalSymbolIcon.optionValueForeground
terminalSymbolIcon.pullRequestDoneForeground
terminalSymbolIcon.pullRequestForeground
terminalSymbolIcon.remoteForeground
terminalSymbolIcon.stashForeground
terminalSymbolIcon.symbolText
terminalSymbolIcon.symbolicLinkFileForeground
terminalSymbolIcon.symbolicLinkFolderForeground
terminalSymbolIcon.tagForeground
testing.coverCountBadgeBackground
testing.coverCountBadgeForeground
testing.coveredBackground
testing.coveredBorder
testing.coveredGutterBackground
testing.iconErrored
testing.iconErrored.retired
testing.iconFailed
testing.iconFailed.retired
testing.iconPassed
testing.iconPassed.retired
testing.iconQueued
testing.iconQueued.retired
testing.iconSkipped
testing.iconSkipped.retired
testing.iconUnset
testing.iconUnset.retired
testing.message.error.badgeBackground
testing.message.error.badgeBorder
testing.message.error.badgeForeground
testing.message.error.lineBackground
testing.message.info.decorationForeground
testing.message.info.lineBackground
testing.messagePeekBorder
testing.messagePeekHeaderBackground
testing.peekBorder
testing.peekHeaderBackground
testing.runAction
testing.uncoveredBackground
testing.uncoveredBorder
testing.uncoveredBranchBackground
testing.uncoveredGutterBackground
textBlockQuote.background
textBlockQuote.border
textCodeBlock.background
textLink.activeForeground
textLink.foreground
textPreformat.background
textPreformat.border
textPreformat.foreground
textSeparator.foreground
titleBar.activeBackground
titleBar.activeForeground
titleBar.border
titleBar.inactiveBackground
titleBar.inactiveForeground
toolbar.activeBackground
toolbar.hoverBackground
toolbar.hoverOutline
tree.inactiveIndentGuidesStroke
tree.indentGuidesStroke
tree.tableColumnsBorder
tree.tableOddRowsBackground
walkThrough.embeddedEditorBackground
walkthrough.stepTitle.foreground
welcomePage.background
welcomePage.progress.background
welcomePage.progress.foreground
welcomePage.tileBackground
welcomePage.tileBorder
welcomePage.tileHoverBackground
widget.border
widget.shadow
window.activeBorder
window.inactiveBorder
""".split())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
