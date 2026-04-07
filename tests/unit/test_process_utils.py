from src.infrastructure.runtime.process_utils import find_matching_processes


def test_find_matching_processes_collapses_windows_launcher_chain():
    processes = [
        {
            "pid": 1336,
            "parent_pid": 4868,
            "command_line": r"C:\Users\sai\quant\.venv\Scripts\python.exe main.py t0-daemon",
        },
        {
            "pid": 12324,
            "parent_pid": 1336,
            "command_line": (
                r"C:\Users\sai\AppData\Roaming\uv\python\cpython-3.12.3-windows-x86_64-none"
                r"\python.exe main.py t0-daemon"
            ),
        },
    ]

    matches = find_matching_processes(processes, ("main.py t0-daemon",))

    assert [process["pid"] for process in matches] == [1336]


def test_find_matching_processes_keeps_independent_instances():
    processes = [
        {
            "pid": 1336,
            "parent_pid": 4868,
            "command_line": r"C:\Users\sai\quant\.venv\Scripts\python.exe main.py t0-daemon",
        },
        {
            "pid": 2336,
            "parent_pid": 5868,
            "command_line": r"C:\Users\sai\quant\.venv\Scripts\python.exe main.py t0-daemon",
        },
    ]

    matches = find_matching_processes(processes, ("main.py t0-daemon",))

    assert [process["pid"] for process in matches] == [1336, 2336]
