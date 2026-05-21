import argparse
import os
import signal
import sys

alarm_fired = False


def handler(sig, frame):
    global alarm_fired
    alarm_fired = True


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Notifier: print a message after a delay "
            "in a background child process."
        )
    )
    parser.add_argument(
        "-t", "--time",
        type=int,
        default=5,
        help="Delay in seconds before the message is printed (default: 5)"
    )
    parser.add_argument(
        "-m", "--message",
        type=str,
        default="Notification!",
        help="Message to print after the delay (default: 'Notification!')"
    )
    return parser.parse_args()


def child_process(delay, message):
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(delay)
    signal.pause()
    if alarm_fired:
        print(message)
    os._exit(0)


def main():
    args = parse_args()

    try:
        pid = os.fork()
    except OSError as err:
        print(f"Fork error: {err}")
        sys.exit(1)

    if pid == 0:
        child_process(args.time, args.message)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
