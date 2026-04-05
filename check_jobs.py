import sys
from db import jobs

if __name__ == "__main__":
    try:
        if jobs.has_active_jobs():
            print("More active jobs found. Re-triggering...")
            sys.exit(0)
        else:
            print("No more active jobs. Stopping.")
            sys.exit(1)
    except Exception as e:
        print(f"Error checking jobs: {e}")
        sys.exit(1)
