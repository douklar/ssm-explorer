"""
Interactive live-filter TUI for SSM Parameter Store.

Uses prompt_toolkit to provide a real-time, keyboard-driven filter UI.

Controls
--------
  Type          Filter parameters live (by ENV name or value, see mode indicator)
  Tab           Toggle filter mode: ENV Name ↔ Value
  ↑ / ↓        Move selection up / down
  Enter         Print the selected parameter's value and exit
  Ctrl+C / Esc  Exit without selecting
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, TypedDict

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style

if TYPE_CHECKING:
    from ssm_explorer.models.parameter import SearchResult, SSMParameter


# ---------------------------------------------------------------------------
# Filter mode
# ---------------------------------------------------------------------------


class FilterMode(Enum):
    NAME = auto()   # filter by ENV variable name
    VALUE = auto()  # filter by parameter value

    def label(self) -> str:
        return "ENV Name" if self is FilterMode.NAME else "Value"

    def toggle(self) -> FilterMode:
        return FilterMode.VALUE if self is FilterMode.NAME else FilterMode.NAME


class _InteractiveState(TypedDict):
    mode: FilterMode
    query: str
    filtered: list[SSMParameter]
    cursor: int
    selected: SSMParameter | None
    done: bool


# ---------------------------------------------------------------------------
# TUI style
# ---------------------------------------------------------------------------

_STYLE = Style.from_dict(
    {
        # chrome
        "header":          "bg:#1e3a5f bold",
        "header.title":    "bg:#1e3a5f #00d7ff bold",
        "header.path":     "bg:#1e3a5f #87ff87",
        "header.hint":     "bg:#1e3a5f #888888",
        "footer":          "bg:#1a1a2e #666666",
        "separator":       "#1e3a5f",
        # mode badge
        "mode.name":       "bg:#005f87 #ffffff bold",
        "mode.value":      "bg:#5f0087 #ffffff bold",
        # search box
        "search.label":    "#888888",
        "search.cursor":   "#00d7ff",
        # list items
        "item.selected":   "bg:#005f87 #ffffff bold",
        "item.normal":     "#cccccc",
        "item.env":        "#ffff87 bold",
        "item.value":      "#cccccc",
        "item.match":      "bg:#875f00 #ffff87 bold",
        "item.type.str":   "#87ff87",
        "item.type.sec":   "#ff5f5f",
        "item.type.list":  "#5fafff",
        "counter":         "#666666",
        "empty":           "#666666 italic",
    }
)


# ---------------------------------------------------------------------------
# Main interactive filter function
# ---------------------------------------------------------------------------


def run_interactive_filter(
    result: SearchResult,
    *,
    initial_mode: FilterMode = FilterMode.NAME,
    conceal: bool = True,
) -> SSMParameter | None:
    """
    Launch the live-filter TUI.

    Presents all parameters from *result* in a scrollable, filterable list.
    Returns the selected SSMParameter when the user presses Enter,
    or None if they exit with Esc / Ctrl+C.

    Args:
        result:       The SearchResult loaded from SSM.
        initial_mode: Starting filter mode (NAME or VALUE). Configurable via
                      filter.default_mode in the config file.
        conceal:      If True, SecureString values are shown concealed in the
                      list (first 4 chars + **** + char count).

    Returns:
        The selected SSMParameter, or None.
    """
    all_params = result.parameters
    # Whether each param's value was actually fetched decrypted
    # (we can tell because the SSMClient sets the raw value)
    decrypted = any(p.is_encrypted and p.value and not p.value.startswith("🔒") for p in all_params)

    # Mutable state shared across callbacks
    state: _InteractiveState = {
        "mode":     initial_mode,
        "query":    "",
        "filtered": list(all_params),
        "cursor":   0,
        "selected": None,
        "done":     False,
    }

    # ------------------------------------------------------------------ #
    # Filtering logic
    # ------------------------------------------------------------------ #

    def _apply_filter(query: str, mode: FilterMode) -> list[SSMParameter]:
        q = query.strip().lower()
        if not q:
            return list(all_params)
        if mode is FilterMode.NAME:
            return [p for p in all_params if q in p.env_variable_name.lower()]
        else:
            return [p for p in all_params if q in p.value.lower()]

    def _clamp_cursor() -> None:
        n = len(state["filtered"])
        state["cursor"] = max(0, min(state["cursor"], n - 1)) if n else 0

    # ------------------------------------------------------------------ #
    # Rendered content builders
    # ------------------------------------------------------------------ #

    def _header_text() -> HTML:
        mode: FilterMode = state["mode"]
        mode_cls = "mode.name" if mode is FilterMode.NAME else "mode.value"
        total = len(all_params)
        shown = len(state["filtered"])
        return HTML(
            f'<header>  🔍  SSM Explorer — Live Filter   '
            f'<header.path>{result.path}</header.path>   '
            f'<header.hint>Profile: {result.profile} • Region: {result.region}</header.hint>'
            f'</header>\n'
            f'  <{mode_cls}> Filter by: {mode.label()} </{mode_cls}>'
            f'  <counter>[{shown}/{total}]</counter>'
            f'  <header.hint>  Tab: toggle mode  •  ↑↓: navigate  •  Enter: select  •  Esc: quit</header.hint>'
        )

    def _search_prompt_text() -> HTML:
        mode: FilterMode = state["mode"]
        mode_cls = "mode.name" if mode is FilterMode.NAME else "mode.value"
        return HTML(
            f'  <{mode_cls}>{mode.label()}</{mode_cls}>'
            f'  <search.label>❯ </search.label>'
        )

    def _list_text() -> HTML:
        params = state["filtered"]
        cursor: int = state["cursor"]

        if not params:
            return HTML('<empty>  No matches found. Try a different query.</empty>\n')

        query = state["query"].strip().lower()
        mode: FilterMode = state["mode"]
        lines: list[str] = []

        for i, p in enumerate(params):
            env = p.env_variable_name

            # Apply conceal logic for value display in the TUI
            raw_val = p.display_value(decrypt=decrypted, conceal=conceal)
            val = raw_val if len(raw_val) <= 60 else raw_val[:57] + "…"

            # Escape HTML special chars so prompt_toolkit doesn't misparse them
            val_safe  = val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            env_safe  = env.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            is_concealed = p.is_encrypted and decrypted and conceal

            type_cls = {
                "String":       "item.type.str",
                "SecureString": "item.type.sec",
                "StringList":   "item.type.list",
            }.get(p.type.value, "item.type.str")
            type_label = {"String": "STR", "SecureString": "SEC 🔒", "StringList": "LST"}.get(
                p.type.value, "STR"
            )

            val_cls = "item.type.sec" if is_concealed else "item.value"

            if i == cursor:
                row_cls = "item.selected"
                prefix = "▶ "
                line = (
                    f'<{row_cls}>{prefix}'
                    f'{env_safe:<30}  {val_safe:<60}  [{type_label}]'
                    f'</{row_cls}>'
                )
            else:
                prefix = "  "
                if query and mode is FilterMode.NAME and query in env.lower():
                    start = env.lower().find(query)
                    end = start + len(query)
                    env_hl = (
                        f'<item.env>{env_safe[:start]}</item.env>'
                        f'<item.match>{env_safe[start:end]}</item.match>'
                        f'<item.env>{env_safe[end:]}</item.env>'
                    )
                else:
                    env_hl = f'<item.env>{env_safe}</item.env>'

                if query and mode is FilterMode.VALUE and query in raw_val.lower() and not is_concealed:
                    start = val_safe.lower().find(query)
                    end = start + len(query)
                    val_hl = (
                        f'<{val_cls}>{val_safe[:start]}</{val_cls}>'
                        f'<item.match>{val_safe[start:end]}</item.match>'
                        f'<{val_cls}>{val_safe[end:]}</{val_cls}>'
                    )
                else:
                    val_hl = f'<{val_cls}>{val_safe}</{val_cls}>'

                line = (
                    f'{prefix}{env_hl}  '
                    f'{val_hl}  '
                    f'<{type_cls}>[{type_label}]</{type_cls}>'
                )

            lines.append(line)

        return HTML("\n".join(lines) + "\n")

    def _column_header_text() -> HTML:
        return HTML(
            '  <header.hint>'
            f'{"ENV VARIABLE":<32}  {"VALUE":<62}  TYPE'
            '</header.hint>'
        )

    def _footer_text() -> HTML:
        p = state["filtered"]
        if p and 0 <= state["cursor"] < len(p):
            param = p[state["cursor"]]
            return HTML(
                f'  Full path: <header.path>{param.name}</header.path>'
                f'  •  Version: {param.version}'
            )
        return HTML('  No selection')

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #

    search_buffer = Buffer(name="search", multiline=False)

    # Update state whenever the search buffer changes
    def _on_text_changed(_buf: Buffer) -> None:
        state["query"] = search_buffer.text
        state["filtered"] = _apply_filter(state["query"], state["mode"])
        _clamp_cursor()
        app.invalidate()

    search_buffer.on_text_changed += _on_text_changed

    layout = Layout(
        HSplit(
            [
                # Top header bar
                Window(
                    content=FormattedTextControl(_header_text),
                    height=2,
                    style="class:header",
                ),
                # Column headers
                Window(
                    content=FormattedTextControl(_column_header_text),
                    height=1,
                ),
                # Search input row
                VSplit(
                    [
                        Window(
                            content=FormattedTextControl(_search_prompt_text),
                            dont_extend_width=True,
                        ),
                        Window(
                            content=BufferControl(buffer=search_buffer),
                            height=1,
                        ),
                    ],
                    height=1,
                ),
                # Thin separator
                Window(height=1, char="─", style="class:separator"),
                # Parameter list (scrollable)
                Window(
                    content=FormattedTextControl(_list_text, focusable=False),
                    height=Dimension(preferred=20, min=5),
                    wrap_lines=False,
                ),
                # Footer / detail bar
                Window(
                    content=FormattedTextControl(_footer_text),
                    height=1,
                    style="class:footer",
                ),
            ]
        ),
        focused_element=search_buffer,
    )

    # ------------------------------------------------------------------ #
    # Key bindings
    # ------------------------------------------------------------------ #

    kb = KeyBindings()

    @kb.add("tab")
    def _toggle_mode(event: object) -> None:
        state["mode"] = state["mode"].toggle()
        state["filtered"] = _apply_filter(state["query"], state["mode"])
        _clamp_cursor()
        app.invalidate()

    @kb.add("up")
    def _cursor_up(event: object) -> None:
        if state["cursor"] > 0:
            state["cursor"] -= 1
        app.invalidate()

    @kb.add("down")
    def _cursor_down(event: object) -> None:
        if state["cursor"] < len(state["filtered"]) - 1:
            state["cursor"] += 1
        app.invalidate()

    @kb.add("enter")
    def _select(event: object) -> None:
        params = state["filtered"]
        if params and 0 <= state["cursor"] < len(params):
            state["selected"] = params[state["cursor"]]
        state["done"] = True
        app.exit()

    @kb.add("escape")
    @kb.add("c-c")
    @kb.add("c-q")
    def _quit(event: object) -> None:
        state["done"] = True
        app.exit()

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #

    app: Application = Application(  # type: ignore[type-arg]
        layout=layout,
        style=_STYLE,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
        refresh_interval=0,
    )

    app.run()
    return state["selected"]
