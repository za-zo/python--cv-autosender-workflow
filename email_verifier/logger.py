"""
Logger for terminal output with colors.
"""


class Logger:
    COLORS = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "gray": "\033[90m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }

    @staticmethod
    def color(text: str, color: str) -> str:
        code = Logger.COLORS.get(color, "")
        return f"{code}{text}{Logger.COLORS['reset']}"

    @staticmethod
    def header(email: str):
        print(f"\n{'─' * 65}")
        print(f"  {Logger.color('▶', 'cyan')} {Logger.color(email, 'bold')}")
        print(f"{'─' * 65}")

    @staticmethod
    def step(number: int, name: str, passed: bool, message: str):
        icon = Logger.color("✓", "green") if passed else Logger.color("✗", "red")
        label = Logger.color(f"[Step {number}]", "cyan")
        name_s = Logger.color(f"{name:<26}", "white")
        detail = Logger.color(message, "green") if passed else Logger.color(message, "red")
        print(f"   {label} {icon}  {name_s} {detail}")

    @staticmethod
    def skip(number: int, name: str, reason: str):
        label = Logger.color(f"[Step {number}]", "cyan")
        name_s = Logger.color(f"{name:<26}", "gray")
        reason = Logger.color(f"— {reason}", "gray")
        print(f"   {label} -  {name_s} {reason}")

    @staticmethod
    def footer(valid: bool, reason: str):
        if valid:
            result = Logger.color("✅  VALID   → Generate AI message + Send Gmail", "green")
        else:
            result = Logger.color("❌  SKIPPED → 0 token consumed, 0 Gmail quota used", "red")
        print(f"\n   {Logger.color('Result:', 'bold')} {result}")
        print(f"   {Logger.color('Reason:', 'bold')} {Logger.color(reason, 'gray')}")

    @staticmethod
    def summary(total: int, valid: int, skipped: int):
        savings = round(skipped / total * 100) if total > 0 else 0
        print(f"\n{Logger.color('═' * 65, 'cyan')}")
        print(Logger.color("  SUMMARY", "bold"))
        print(Logger.color("─" * 65, "cyan"))
        print(f"  {'Total checked':<25} {Logger.color(str(total), 'white')}")
        print(f"  {'Valid (processed)':<25} {Logger.color(str(valid), 'green')}")
        print(f"  {'Skipped (blocked)':<25} {Logger.color(str(skipped), 'red')}")
        print(f"  {'Savings':<25} {Logger.color(str(savings) + '%', 'yellow')}  <- tokens + Gmail quota saved")
        print(Logger.color("═" * 65, "cyan") + "\n")
