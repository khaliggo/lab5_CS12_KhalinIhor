import os
import random
import signal
import sys


def child_work(parent_pid):
    print(f"\t[child {os.getpid()}] Started. Performing actions...")
    print(f"\t[child {os.getpid()}] Actions done. Sending SIGRTMIN to parent.")
    os.kill(parent_pid, signal.SIGRTMIN)

    print(f"\t[child {os.getpid()}] Continuing (may be interrupted)...")
    # Unblock SIGTERM so parent can terminate us if it decides to.
    signal.pthread_sigmask(signal.SIG_UNBLOCK, [signal.SIGTERM])
    # Use SIGALRM as a fallback timeout so we don't wait forever.
    signal.signal(signal.SIGALRM, lambda s, f: None)
    signal.alarm(2)
    try:
        signal.pause()
    except InterruptedError:
        pass
    signal.alarm(0)

    print(f"\t[child {os.getpid()}] Finished normally. Exiting with code 0.")
    os._exit(0)


def create_child():
    try:
        pid = os.fork()
    except OSError as err:
        print(f"Fork error: {err}")
        sys.exit(1)
    return pid


def analyze_child_status(pid, status):
    if os.WIFEXITED(status):
        code = os.WEXITSTATUS(status)
        print(f"[parent] Child {pid} exited normally with code {code}.")
    elif os.WIFSIGNALED(status):
        sig = os.WTERMSIG(status)
        print(
            f"[parent] Child {pid} terminated by signal:"
            f" {sig} - {signal.strsignal(sig)}."
        )
    else:
        print(f"[parent] Child {pid} ended with unknown status.")


def main():
    random.seed()
    parent_pid = os.getpid()
    print(f"[parent {parent_pid}] Started.")

    # Block SIGRTMIN before fork so the signal is not missed if child
    # sends it before parent reaches sigwait.
    signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGRTMIN])
    # Block SIGTERM in child until it is ready to receive it.
    signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGTERM])

    pid = create_child()

    if pid == 0:
        # Child: reset SIGTERM to default before our custom unblock.
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        child_work(parent_pid)
    else:
        # Parent: synchronously wait for SIGRTMIN from child.
        print(f"[parent] Child PID: {pid}. Waiting for SIGRTMIN...")
        received = signal.sigwait([signal.SIGRTMIN])
        print(
            f"[parent] Received signal {received}"
            f" ({signal.strsignal(received)}) from child."
        )

        # With 50% probability send SIGTERM to child.
        if random.random() < 0.5:
            print("[parent] Decision (50%): sending SIGTERM to child.")
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                print("[parent] Child already exited before SIGTERM.")
        else:
            print("[parent] Decision (50%): letting child finish normally.")

        # Wait for child and analyze exit status.
        print("[parent] Waiting for child to finish...")
        result_pid, status = os.wait()
        analyze_child_status(result_pid, status)

        sys.exit(0)


if __name__ == "__main__":
    main()
