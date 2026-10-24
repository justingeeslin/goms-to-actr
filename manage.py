#!/usr/bin/env python3
"""Django management entry point for the optional conversion server."""
import os
import sys


if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'goms_to_actr.web.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
