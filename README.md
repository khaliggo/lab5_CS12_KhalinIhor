# Laboratory Work #5 — Working with Signals in Linux

## About the Project

This project is an implementation of **Laboratory Work #5: Working with Signals** for the Linux Operating Systems course. The goal of the work is to gain practical skills in programmatic handling of signals — the traditional mechanism of interaction between the Linux kernel and user processes.

Signals are asynchronous notifications sent to a process by the kernel or another process. They can arrive at any moment, interrupting normal execution. This project explores two fundamental approaches to signal handling:

- **Asynchronous approach** — a signal handler (callback) is registered and invoked automatically upon signal delivery. As per POSIX requirements, handlers must only perform async-signal-safe operations — in practice, this means only setting a boolean flag. All actual logic runs in the main loop after checking the flag.
- **Synchronous approach** — signals are blocked using a signal mask (`pthread_sigmask`) so they queue up without being delivered. The process then explicitly calls `sigwait()` at the right moment to atomically dequeue and handle a specific signal. This gives full control over timing and eliminates race conditions.

The project consists of three independent Python programs, each demonstrating a distinct aspect of signal-based inter-process communication on Linux:

| File | Task | Approach |
|------|------|----------|
| `task1.py` | Timed background notifier using `SIGALRM` | Asynchronous |
| `task2.py` | Daemon-like process with live reconfiguration via `SIGHUP` | Asynchronous |
| `task3.py` | Race-condition-free parent-child synchronisation via `SIGRTMIN` | Synchronous |

All files pass `flake8` with zero errors.

---

## Requirements

- Linux (signals such as `SIGALRM`, `SIGRTMIN`, `SIGHUP` are POSIX/Linux-specific)
- Python 3.8+
- `flake8` (for linting): `pip install flake8`

---

## About the Code

### task1.py — Notifier

**Purpose:** Accept a time interval and a message via CLI. Fork a child process, let the parent exit immediately (freeing the terminal), and have the child print the message after the specified delay using `SIGALRM` and `signal.pause()`.

**Key components:**

| Component | Role |
|-----------|------|
| `argparse` | Parses `-t/--time` (int, default 5) and `-m/--message` (str, default `"Notification!"`) |
| `alarm_fired` | Global boolean flag — the only thing the signal handler is allowed to set |
| `handler(sig, frame)` | Async signal handler for `SIGALRM` — sets `alarm_fired = True` only |
| `child_process(delay, message)` | Registers handler, arms the alarm, blocks on `pause()`, prints message after wakeup |
| `main()` | Parses args, forks, parent calls `sys.exit(0)`, child calls `child_process()` |

**Signals used:**

| Signal | Number | How used |
|--------|--------|----------|
| `SIGALRM` | 14 | Sent by the kernel after `alarm(N)` seconds; wakes the child from `pause()` |

---

### task2.py — Daemon-like Reconfigurable Process

**Purpose:** Simulate a simplified daemon — a background process that reads a config file, outputs a repeated character string at regular intervals, reloads config on `SIGHUP`, and terminates cleanly on `SIGTERM`.

**Config file format (`config.txt`):**
```
r       ← single character (first char of line 1)
5       ← repeat count (line 2, parsed as int)
```
Output per interval: `rrrrr`

**Key components:**

| Component | Role |
|-----------|------|
| `argparse` | Parses `-i/--interval` (float, default 3.0) and `-c/--config` (str, default `"config.txt"`) |
| `flag_reload` | Set to `True` by `handler_sighup` when `SIGHUP` arrives |
| `flag_terminate` | Set to `True` by `handler_sigterm` when `SIGTERM` arrives |
| `handler_sighup(sig, frame)` | Async handler — sets `flag_reload = True` only |
| `handler_sigterm(sig, frame)` | Async handler — sets `flag_terminate = True` only |
| `read_config(path)` | Opens config file, reads char and count, returns `(char, count)` tuple |
| `child_process(interval, config_path)` | Registers both handlers, reads config, runs the main loop |
| `main()` | Validates config exists, forks, parent prints child PID and exits, child runs |

**Signals used:**

| Signal | Number | How used |
|--------|--------|----------|
| `SIGHUP` | 1 | Sent manually with `kill -SIGHUP <pid>`; triggers config reload |
| `SIGTERM` | 15 | Sent manually with `kill -SIGTERM <pid>`; triggers clean shutdown |

**The main loop logic:**
```
while not flag_terminate:
    print(char * count)
    sleep(interval)
    if flag_reload:         ← checked AFTER sleep, not inside handler
        reload config
```
This ensures config is only re-read in the main flow, never inside an async handler.

---

### task3.py — Synchronous Signal Synchronisation

**Purpose:** Solve the post-`fork()` race condition — it is undefined which process runs first after forking. The child performs some initialisation, then signals the parent with `SIGRTMIN`. The parent synchronously waits for this signal before proceeding. With 50% probability the parent then sends `SIGTERM` to the child. The parent collects the child's exit status and reports whether it ended normally or was killed by a signal.

**Key components:**

| Component | Role |
|-----------|------|
| `pthread_sigmask(SIG_BLOCK, [SIGRTMIN])` | Blocks `SIGRTMIN` **before** fork so the signal cannot be lost if child sends it before parent reaches `sigwait()` |
| `pthread_sigmask(SIG_BLOCK, [SIGTERM])` | Blocks `SIGTERM` before fork so child doesn't receive it before unblocking intentionally |
| `child_work(parent_pid)` | Child's logic: print actions, send `SIGRTMIN` to parent, unblock `SIGTERM`, wait on `pause()` with a 2-second `SIGALRM` fallback |
| `create_child()` | Wraps `os.fork()` with error handling |
| `analyze_child_status(pid, status)` | Decodes `os.wait()` result using `WIFEXITED`/`WIFSIGNALED`/`WEXITSTATUS`/`WTERMSIG` |
| `sigwait([SIGRTMIN])` | Parent blocks here **synchronously** until `SIGRTMIN` is dequeued; returns signal number |
| `random.random() < 0.5` | 50/50 decision to send `SIGTERM` or let child finish normally |
| `os.wait()` | Parent waits for child to fully terminate before reading its exit status |

**Signals used:**

| Signal | Number | How used |
|--------|--------|----------|
| `SIGRTMIN` | 34 | Child → Parent: "I am ready, you may proceed" |
| `SIGTERM` | 15 | Parent → Child: sent with 50% probability after receiving `SIGRTMIN` |
| `SIGALRM` | 14 | Child self-timer: ensures `pause()` returns after 2s even if no `SIGTERM` arrives |

---

## How the Code Works (Detailed)

### task1.py — Step by Step

```
1. parse_args()
      └─ reads -t (delay seconds) and -m (message string) from CLI

2. os.fork()
      ├─ PARENT (pid > 0)
      │     └─ sys.exit(0)  →  terminal is freed immediately
      │
      └─ CHILD (pid == 0)
            ├─ signal.signal(SIGALRM, handler)
            │     └─ registers handler: on SIGALRM → set alarm_fired = True
            │
            ├─ signal.alarm(delay)
            │     └─ asks kernel to deliver SIGALRM after `delay` seconds
            │
            ├─ signal.pause()
            │     └─ process sleeps here, consuming no CPU
            │
            │   ... delay seconds pass, kernel sends SIGALRM ...
            │
            │   handler() is called automatically:
            │     alarm_fired = True
            │
            │   pause() returns
            │
            ├─ if alarm_fired: print(message)
            │     └─ actual print happens here in main flow, not in handler
            │
            └─ os._exit(0)
```

**Why `os._exit()` and not `sys.exit()` in the child?**
After `fork()`, the child inherits Python's internal state including buffered I/O. `sys.exit()` flushes buffers and runs `atexit` handlers, which can cause duplicate output or side effects. `os._exit()` terminates immediately at the OS level, bypassing all Python cleanup.

---

### task2.py — Step by Step

```
1. parse_args()
      └─ reads -i (interval) and -c (config file path)

2. os.path.exists(config) — fails early if config missing

3. os.fork()
      ├─ PARENT (pid > 0)
      │     ├─ print("[parent] Child PID: X. Parent exits.")
      │     └─ sys.exit(0)  →  terminal freed
      │
      └─ CHILD (pid == 0)
            ├─ signal.signal(SIGHUP,  handler_sighup)
            ├─ signal.signal(SIGTERM, handler_sigterm)
            │
            ├─ read_config() → char='r', count=5
            ├─ print("[child X] Started. Config: 'r' x 5")
            │
            └─ MAIN LOOP:
                  while not flag_terminate:
                    │
                    ├─ print("[child X] rrrrr")
                    │
                    ├─ time.sleep(interval)
                    │     ← SIGHUP or SIGTERM may arrive here
                    │       handler sets flag only — sleep continues
                    │       (signal interrupts sleep in CPython,
                    │        but the flag is checked after sleep returns)
                    │
                    └─ if flag_reload:
                          flag_reload = False
                          read_config() again → new char, count
                          print("[child X] Reloaded config: ...")

            └─ (after flag_terminate = True)
                  print("[child X] Received SIGTERM. Exiting.")
                  os._exit(0)
```

**Why only flags in handlers?**
Signal handlers interrupt the process at an arbitrary point. If the handler called `open()` or `print()` and the main code was also inside `open()` or `print()` at that moment, the call would re-enter non-reentrant C library functions — causing deadlocks or data corruption. Setting a plain boolean is always safe.

---

### task3.py — Step by Step

```
1. random.seed()
   parent_pid = os.getpid()

2. pthread_sigmask(SIG_BLOCK, [SIGRTMIN])
      └─ SIGRTMIN now queued, not delivered — cannot be missed

3. pthread_sigmask(SIG_BLOCK, [SIGTERM])
      └─ child inherits this mask after fork — SIGTERM won't kill it prematurely

4. os.fork()
      │
      ├─ CHILD (pid == 0)
      │     ├─ signal(SIGTERM, SIG_DFL)
      │     │     └─ restore default action so SIGTERM actually kills when unblocked
      │     │
      │     ├─ print("Performing actions...")
      │     ├─ print("Actions done. Sending SIGRTMIN to parent.")
      │     │
      │     ├─ os.kill(parent_pid, SIGRTMIN)
      │     │     └─ signal goes into parent's queue (parent has it blocked)
      │     │
      │     ├─ pthread_sigmask(SIG_UNBLOCK, [SIGTERM])
      │     │     └─ now SIGTERM can be delivered to child
      │     │
      │     ├─ signal.alarm(2)          ← fallback: wake up in 2s regardless
      │     ├─ signal.pause()           ← sleep: waiting for SIGTERM or SIGALRM
      │     │
      │     │   CASE A: parent sends SIGTERM
      │     │     └─ SIGTERM delivered → SIG_DFL action → child process killed
      │     │
      │     │   CASE B: parent does not send SIGTERM
      │     │     └─ SIGALRM fires after 2s → pause() returns
      │     │
      │     ├─ signal.alarm(0)          ← cancel alarm if still running
      │     ├─ print("Finished normally. Exiting with code 0.")
      │     └─ os._exit(0)
      │
      └─ PARENT (pid > 0)
            ├─ print("Child PID: X. Waiting for SIGRTMIN...")
            │
            ├─ sigwait([SIGRTMIN])
            │     └─ parent BLOCKS here synchronously
            │        dequeues SIGRTMIN when it arrives
            │        returns 34 (SIGRTMIN number)
            │
            ├─ print("Received signal 34 (Real-time signal 0) from child.")
            │
            ├─ random.random() < 0.5 ?
            │     ├─ YES: os.kill(pid, SIGTERM)
            │     │         └─ print("sending SIGTERM to child.")
            │     └─ NO:  print("letting child finish normally.")
            │
            ├─ os.wait()
            │     └─ blocks until child exits or is killed
            │        returns (child_pid, raw_status)
            │
            └─ analyze_child_status():
                  WIFEXITED(status)  → "exited normally with code 0"
                  WIFSIGNALED(status) → "terminated by signal: 15 - Terminated"
```

**Why block signals before `fork()` and not after?**
After `fork()`, both processes run concurrently. If the child were scheduled first and sent `SIGRTMIN` before the parent reached `sigwait()`, and `SIGRTMIN` were not blocked, the signal would be delivered to the parent with no handler — default action kills it. By blocking before `fork()`, the signal queues silently until `sigwait()` explicitly dequeues it, regardless of scheduling order.

---

## Running the Programs

### task1.py

```bash
# Custom delay and message
python3 task1.py -t 4 -m "Hello from background!"

# Default values (5 seconds, "Notification!")
python3 task1.py
```

**Expected output** (terminal returns immediately, message appears after delay):
```
$                              ← terminal free at once
Hello from background!         ← appears after 4 seconds
```

---

### task2.py

```bash
# Step 1 — create config file
echo -e "r\n5" > config.txt

# Step 2 — start the program (interval 2 seconds)
python3 task2.py -i 2 -c config.txt
```
```
[parent] Child PID: 1234. Parent exits.
[child 1234] Started. Config: 'r' x 5
[child 1234] rrrrr
[child 1234] rrrrr
```

```bash
# Step 3 — change config and send SIGHUP to reload
echo -e "x\n8" > config.txt
kill -SIGHUP 1234
```
```
[child 1234] Reloaded config: 'x' x 8
[child 1234] xxxxxxxx
```

```bash
# Step 4 — terminate the process
kill -SIGTERM 1234
```
```
[child 1234] Received SIGTERM. Exiting.
```

---

### task3.py

```bash
# Run multiple times to observe both outcomes
python3 task3.py
python3 task3.py
python3 task3.py
```

**Output — child terminated by signal (50% chance):**
```
[parent 1001] Started.
[child 1002] Started. Performing actions...
[child 1002] Actions done. Sending SIGRTMIN to parent.
[child 1002] Continuing (may be interrupted)...
[parent] Child PID: 1002. Waiting for SIGRTMIN...
[parent] Received signal 34 (Real-time signal 0) from child.
[parent] Decision (50%): sending SIGTERM to child.
[parent] Waiting for child to finish...
[parent] Child 1002 terminated by signal: 15 - Terminated.
```

**Output — child finishes normally (50% chance):**
```
[parent 1003] Started.
[child 1004] Started. Performing actions...
[child 1004] Actions done. Sending SIGRTMIN to parent.
[child 1004] Continuing (may be interrupted)...
[parent] Child PID: 1004. Waiting for SIGRTMIN...
[parent] Received signal 34 (Real-time signal 0) from child.
[parent] Decision (50%): letting child finish normally.
[parent] Waiting for child to finish...
[child 1004] Finished normally. Exiting with code 0.
[parent] Child 1004 exited normally with code 0.
```