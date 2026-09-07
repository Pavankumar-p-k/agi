"""Optional-dependency-free compatibility hooks for CLI tests/integrations."""


def print_system_msg(*args, **kwargs):
    if args:
        print(*args)
