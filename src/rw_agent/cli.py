from __future__ import annotations

import sys
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console

from . import __version__
from .client import stream_chat
from .config import get_active_provider, load_config, save_config
from .tools import SYSTEM_PROMPT, run_tool
from .ui import PROMPT_STYLE, SlashCompleter, pick_model, print_banner, run_onboarding


def _format_stats(ttft_ms: int, prompt_tok: int, cached_tok: int, comp_tok: int) -> str:
    parts = [f"{ttft_ms}ms TTFT"]
    if prompt_tok > 0:
        pct = int(round((cached_tok / prompt_tok) * 100)) if cached_tok > 0 else 0
        parts.append(f"{prompt_tok:,} in ({pct}% cached)")
    if comp_tok > 0:
        parts.append(f"{comp_tok:,} out")
    return "▸ " + " · ".join(parts)


def _run_turn(
    console: Console,
    provider: dict[str, Any],
    messages: list[dict[str, Any]],
) -> None:
    model = provider["active_model"]
    base_url = provider["base_url"]
    api_key = provider.get("api_key", "")

    total_prompt = 0
    total_cached = 0
    total_comp = 0
    first_ttft = 0

    while True:
        status = console.status(f"[bright_cyan]Thinking ({model})...[/bright_cyan]", spinner="dots")
        status.start()
        streamed_any_text = False

        def on_first() -> None:
            status.stop()

        def on_token(delta: str) -> None:
            nonlocal streamed_any_text
            if not streamed_any_text:
                streamed_any_text = True
            sys.stdout.write(delta)
            sys.stdout.flush()

        try:
            res = stream_chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                on_first_event=on_first,
                on_token=on_token,
            )
        except Exception as e:
            status.stop()
            console.print(f"\n[red]✗ API error:[/red] {e}")
            return
        finally:
            status.stop()

        if streamed_any_text:
            sys.stdout.write("\n")
            sys.stdout.flush()

        if first_ttft == 0:
            first_ttft = res.ttft_ms
        total_prompt += res.prompt_tokens
        total_cached += res.cached_tokens
        total_comp += res.completion_tokens

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": res.content or None}
        if res.tool_calls:
            assistant_msg["tool_calls"] = res.tool_calls
        messages.append(assistant_msg)

        if not res.tool_calls:
            break

        for tc in res.tool_calls:
            fn = tc.get("function") or {}
            t_name = fn.get("name", "")
            t_args = fn.get("arguments", "{}")
            with console.status(f"[yellow]⚡ {t_name}...[/yellow]", spinner="line"):
                result_text, target, summary = run_tool(t_name, t_args)
            console.print(f"[dim]⚡ {t_name:<5}[/dim] [bright_white]{target}[/bright_white] [dim]({summary})[/dim]")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or "call_0",
                    "content": result_text,
                }
            )

    console.print(f"[dim]{_format_stats(first_ttft, total_prompt, total_cached, total_comp)}[/dim]\n")


def main() -> None:
    console = Console()

    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        console.print(
            "[bold bright_cyan]rw[/bold bright_cyan] — minimal read/write AI agent\n\n"
            "[bold]Usage:[/bold]\n"
            "  rw              Launch interactive agent\n"
            "  rw \"<prompt>\"   Run one-shot prompt\n"
            "  rw --version    Show version\n\n"
            "[bold]Slash commands:[/bold] /model, /new, /provider, /exit"
        )
        return

    if len(sys.argv) == 2 and sys.argv[1] in ("-v", "--version"):
        console.print(f"rw-agent {__version__}")
        return

    cfg = load_config()
    provider = get_active_provider(cfg)

    if provider is None:
        print_banner(console)
        provider = run_onboarding(console, cfg)

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Optional one-shot mode: `rw "read main.py"`
    if len(sys.argv) > 1:
        prompt_text = " ".join(sys.argv[1:]).strip()
        if prompt_text:
            messages.append({"role": "user", "content": prompt_text})
            _run_turn(console, provider, messages)
            return

    print_banner(console, provider["name"], provider["active_model"])

    session = PromptSession(
        completer=SlashCompleter(),
        complete_while_typing=True,
        style=PROMPT_STYLE,
    )

    while True:
        try:
            user_input = session.prompt(HTML("<b><ansicyan>›</ansicyan></b> ")).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            console.print("[dim]bye[/dim]")
            break

        if user_input == "/new":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            console.print("[green]✓[/green] [dim]New chat (context cleared)[/dim]\n")
            continue

        if user_input == "/model":
            models = provider.get("models") or []
            if not models:
                console.print("[yellow]No synced models. Run /provider to re-sync.[/yellow]\n")
                continue
            chosen = pick_model(models, provider.get("active_model", ""))
            if chosen and chosen != provider.get("active_model"):
                provider["active_model"] = chosen
                cfg["providers"][provider["name"]] = provider
                save_config(cfg)
                console.print(f"[green]✓[/green] Model: [bright_cyan]{chosen}[/bright_cyan]\n")
            continue

        if user_input == "/provider":
            provider = run_onboarding(console, cfg)
            print_banner(console, provider["name"], provider["active_model"])
            continue

        if user_input.startswith("/"):
            console.print("[dim]Commands: /model, /new, /provider, /exit[/dim]\n")
            continue

        messages.append({"role": "user", "content": user_input})
        _run_turn(console, provider, messages)


if __name__ == "__main__":
    main()
