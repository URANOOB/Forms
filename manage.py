import sys

from dotenv import load_dotenv

from config.environment import configure_settings

if __name__ == "__main__":
    load_dotenv()
    configure_settings(default="config.settings.local")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
