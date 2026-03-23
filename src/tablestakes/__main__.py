"""Entry point for `python -m tablestakes`."""

from tablestakes.server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
