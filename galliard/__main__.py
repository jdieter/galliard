#!/usr/bin/env python3

import sys

from galliard.app import Galliard


def main():
    """Main entry point for the application"""
    app = Galliard()
    return app.run(sys.argv)


if __name__ == "__main__":
    main()
