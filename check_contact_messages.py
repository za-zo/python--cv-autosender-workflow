import sys

from db import contact_messages


if __name__ == "__main__":
    try:
        if contact_messages.has_active_contact_messages():
            print("More pending contact messages found. Re-triggering...")
            sys.exit(0)
        else:
            print("No more pending contact messages. Stopping.")
            sys.exit(1)
    except Exception as e:
        print(f"Error checking contact messages: {e}")
        sys.exit(1)

