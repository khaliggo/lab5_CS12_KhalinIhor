import argparse
import os
import signal
import sys
import time

CONFIG_FILE = "config.txt"

flag_reload = False
flag_terminate = False


def handler_sighup(sig, frame):
    global flag_reload
    flag_reload = True


def handler_sigterm(sig, frame):
    global flag_terminate
    flag_terminate = True


def read_config(path):
    try:
        with open(path, "r") as f:
            lines = f.read().splitlines()
        char = lines[0][0]
        count = int(lines[1])
        return char, count
    except (OSError, IndexError, ValueError) as err:
        print(f"[child] Config read error: {err}")
        os._exit(1)


def child_process(interval, config_path):
    global flag_reload

    signal.signal(signal.SIGHUP, handler_sighup)
    signal.signal(signal.SIGTERM, handler_sigterm)

    char, count = read_config(config_path)
    print(f"[child {os.getpid()}] Started. Config: '{char}' x {count}")

    while not flag_terminate:
        print(f"[child {os.getpid()}] {char * count}")
        time.sleep(interval)

        if flag_reload:
            flag_reload = False
            char, count = read_config(config_path)
            print(
                f"[child {os.getpid()}] Reloaded config:"
                f" '{char}' x {count}"
            )

    print(f"[child {os.getpid()}] Received SIGTERM. Exiting.")
    os._exit(0)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Daemon-like notifier: child process prints a repeated "
            "character from config at a fixed interval."
        )
    )
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=3.0,
        help="Interval in seconds between output lines (default: 3)"
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=CONFIG_FILE,
        help=f"Path to config file (default: {CONFIG_FILE})"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.config):
        print(f"Error: config file '{args.config}' not found.")
        sys.exit(1)

    try:
        pid = os.fork()
    except OSError as err:
        print(f"Fork error: {err}")
        sys.exit(1)

    if pid == 0:
        child_process(args.interval, args.config)
    else:
        print(f"[parent] Child PID: {pid}. Parent exits.")
        sys.exit(0)


if __name__ == "__main__":
    main()
