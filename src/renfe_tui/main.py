import argparse
import os
import sys

from . import i18n


def main() -> None:
    parser = argparse.ArgumentParser(prog="renfe-tui")
    parser.add_argument("--lang", choices=i18n.LANGS, help="interface language; default: the system's")
    parser.add_argument("--no-anim", action="store_true", help="start without the train animation")
    parser.add_argument("--theme", "--tema", dest="theme", choices=("light", "dark", "claro", "oscuro"),
                        help="colour theme; default: the system's, then the terminal background")
    args = parser.parse_args()
    i18n.set_language(args.lang)

    from .app import RenfeTui
    from .theme import pick

    again = RenfeTui(animate=not args.no_anim, palette=pick(args.theme)).run()
    if again:
        os.execv(sys.executable, [sys.executable, "-m", "renfe_tui", *again])
