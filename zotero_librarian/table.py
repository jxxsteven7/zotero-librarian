"""One table for two readers: markdown when the output is piped (an agent relays it as is), aligned columns cut to the
terminal width when a human is watching."""
import shutil, sys

HUMAN = sys.stdout.isatty()


def render(headers, rows):
    rows = [[str(c) for c in r] for r in rows]
    if not HUMAN:
        return "| " + " | ".join(headers) + " |\n|" + "---|" * len(headers) + "\n" + "\n".join("| " + " | ".join(r) + " |" for r in rows)
    rows = [[c.replace("`", "") for c in r] for r in rows]
    width = shutil.get_terminal_size((160, 40)).columns
    w = [max([len(h)] + [len(r[i]) for r in rows]) for i, h in enumerate(headers)]
    while sum(w) + 2 * (len(w) - 1) > width and max(w) > 8:          # shrink the widest column until the table fits
        w[w.index(max(w))] -= 1
    cut = lambda s, n: s if len(s) <= n else s[:n - 1] + "…"
    line = lambda r: "  ".join(cut(c, w[i]).ljust(w[i]) for i, c in enumerate(r)).rstrip()
    return "\n".join([line(headers), "  ".join("─" * x for x in w)] + [line(r) for r in rows])
