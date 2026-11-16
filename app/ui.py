"""
ui.py - Input prompts with validation, and table printing.

Every prompt keeps asking until the user enters a valid value. Typing 'q'
at most prompts cancels the current operation (raises Cancelled), which
returns the user to the menu without changing anything.
"""

import datetime


class Cancelled(Exception):
    """Raised when the user types 'q' to cancel the current operation."""


def _read(prompt):
    value = input(prompt).strip()
    if value.lower() == "q":
        raise Cancelled()
    return value


def prompt_text(prompt, required=True, max_length=160, default=None):
    """Ask for text. Optional fields may be left blank (returns default)."""
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = _read(f"{prompt}{suffix}: ")
        if not value:
            if default is not None or not required:
                return default
            print("  This value is required.")
        elif len(value) > max_length:
            print(f"  Please enter at most {max_length} characters.")
        else:
            return value


def prompt_int(prompt, minimum=None, maximum=None, default=None, allow_blank=False):
    """
    Ask for a whole number within an optional range. With allow_blank,
    pressing Enter returns None.
    """
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = _read(f"{prompt}{suffix}: ")
        if not raw and default is not None:
            return default
        if not raw and allow_blank:
            return None
        try:
            value = int(raw)
        except ValueError:
            print("  Please enter a whole number.")
            continue
        if minimum is not None and value < minimum:
            print(f"  Please enter a number of at least {minimum}.")
        elif maximum is not None and value > maximum:
            print(f"  Please enter a number no greater than {maximum}.")
        else:
            return value


def prompt_money(prompt, minimum=0.0, allow_zero=True, default=None):
    """Ask for a dollar amount and round it to cents."""
    suffix = f" [{default:.2f}]" if default is not None else ""
    while True:
        raw = _read(f"{prompt}{suffix}: ").replace("$", "")
        if not raw and default is not None:
            return default
        try:
            value = round(float(raw), 2)
        except ValueError:
            print("  Please enter an amount such as 4.99.")
            continue
        if value < minimum or (not allow_zero and value == 0):
            print("  Please enter an amount greater than 0." if not allow_zero
                  else f"  Please enter an amount of at least {minimum:.2f}.")
        else:
            return value


def prompt_yes_no(prompt, default=None):
    hint = {True: " [Y/n]", False: " [y/N]", None: " (y/n)"}[default]
    while True:
        raw = _read(f"{prompt}{hint}: ").lower()
        if not raw and default is not None:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please enter y or n.")


def prompt_date(prompt, default=None, allow_blank=False):
    """
    Ask for a date in YYYY-MM-DD format; returns the string. With
    allow_blank, pressing Enter returns None.
    """
    suffix = f" [{default}]" if default else ""
    while True:
        raw = _read(f"{prompt} (YYYY-MM-DD){suffix}: ")
        if not raw and default:
            return default
        if not raw and allow_blank:
            return None
        try:
            return datetime.date.fromisoformat(raw).isoformat()
        except ValueError:
            print("  Please enter a valid date, such as 2026-10-22.")


def choose(title, options):
    """
    Show a numbered list and return the chosen value.
    options is a list of (label, value) pairs.
    """
    if not options:
        raise ValueError("choose() needs at least one option")
    print(f"\n{title}")
    for number, (label, _value) in enumerate(options, start=1):
        print(f"  {number}. {label}")
    index = prompt_int("Choose a number", 1, len(options))
    return options[index - 1][1]


def print_table(rows, columns=None, empty_message="No matching records."):
    """Print rows (sqlite3.Row or tuples) as an aligned text table."""
    rows = list(rows)
    if not rows:
        print(f"\n  {empty_message}")
        return
    if columns is None:
        columns = list(rows[0].keys())
    text_rows = [[_format_cell(value) for value in row] for row in rows]
    widths = [max(len(str(col)), *(len(r[i]) for r in text_rows))
              for i, col in enumerate(columns)]
    print()
    print("  " + "  ".join(str(c).ljust(w) for c, w in zip(columns, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in text_rows:
        print("  " + "  ".join(cell.ljust(w) for cell, w in zip(r, widths)))
    print(f"  ({len(rows)} row{'s' if len(rows) != 1 else ''})")


def _format_cell(value):
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def pause():
    input("\nPress Enter to continue...")
