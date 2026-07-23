# Copyright (c) 2026 Airbyte, Inc., all rights reserved.

import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests


class SpecmaticServer:
    def __init__(self, port: int = 9000, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self.process = None

    def start(self, repo_root: Path) -> None:
        # Check if a Specmatic mock server is already running on this port
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect((self.host, self.port))
            # Port is busy, meaning a server is already running!
            print(f"Specmatic mock server is already running on {self.host}:{self.port}. Reusing the existing server.")
            self.process = None
            return
        except Exception:
            # Port is free, proceed with spawning a new mock server process
            pass

        specmatic_bin = shutil.which("specmatic")
        if specmatic_bin:
            log_file = repo_root / "specmatic_server.log"
            self.log_file_handle = open(log_file, "w", encoding="utf-8")
            print(f"Starting Specmatic mock server on {self.host}:{self.port} (logging to {log_file})...")
            import os

            # NOTE: Do NOT use CREATE_NEW_PROCESS_GROUP on Windows.
            # With that flag, CTRL_C_EVENT cannot reach the child process.
            # Without it, Java inherits Python's process group, so we can
            # broadcast CTRL_C_EVENT to the whole group to trigger JVM shutdown
            # hooks (which write the Specmatic HTML coverage report).
            # Locate specmatic.yaml relative to repo_root or parent directories
            config_file = repo_root / "specmatic.yaml"
            if not config_file.exists():
                for parent in repo_root.parents:
                    if (parent / "specmatic.yaml").exists():
                        config_file = parent / "specmatic.yaml"
                        break

            creation_flags = 0
            cmd_args = [specmatic_bin, "mock", f"--port={self.port}", f"--host={self.host}", "--config", str(config_file)]

            # Find specmatic.jar to launch Java process directly on all platforms.
            # Direct Java execution ensures SIGINT reaches the JVM process directly so JVM shutdown hooks run and write Specmatic reports.
            java_bin = shutil.which("java")
            if java_bin:
                jar_candidates = []
                bin_path = Path(specmatic_bin).resolve()
                jar_candidates.append(bin_path.parent / "node_modules" / "specmatic" / "specmatic.jar")
                jar_candidates.append(bin_path.parent.parent / "lib" / "node_modules" / "specmatic" / "specmatic.jar")
                jar_candidates.append(bin_path.parent.parent / "node_modules" / "specmatic" / "specmatic.jar")
                try:
                    npm_root = subprocess.check_output(["npm", "root", "-g"], text=True, timeout=5).strip()
                    if npm_root:
                        jar_candidates.append(Path(npm_root) / "specmatic" / "specmatic.jar")
                except Exception:
                    pass

                for jar_path in jar_candidates:
                    if jar_path.exists():
                        cmd_args = [
                            java_bin,
                            "-jar",
                            str(jar_path),
                            "mock",
                            f"--port={self.port}",
                            f"--host={self.host}",
                            "--config",
                            str(config_file),
                        ]
                        print(f"Launching Specmatic via direct Java command: {' '.join(cmd_args)}")
                        break

            self.process = subprocess.Popen(
                cmd_args,
                cwd=str(repo_root),
                stdout=self.log_file_handle,
                stderr=self.log_file_handle,
                text=True,
                shell=False,
                creationflags=creation_flags,
            )

            # Wait for mock server to be ready using socket connection to avoid sending unhandled HTTP requests
            import socket

            retries = 30
            for i in range(retries):
                if self.process.poll() is not None:
                    raise RuntimeError(f"Specmatic mock server failed to start. Check {log_file} for details.")
                try:
                    with socket.create_connection((self.host, self.port), timeout=1):
                        print("Specmatic mock server is ready.")
                        return
                except (OSError, ConnectionRefusedError):
                    pass
                time.sleep(0.5)

            # If we timeout
            if self.process:
                self.stop()
            raise RuntimeError(f"Specmatic mock server failed to start on port {self.port}")
        else:
            print("Specmatic executable not found. Assuming Specmatic server is running externally.")

    def stop(self) -> None:
        if self.process:
            print("Terminating Specmatic mock server...")
            import os
            import signal

            graceful = False
            try:
                if os.name == "nt":
                    # Java shares Python's process group (no CREATE_NEW_PROCESS_GROUP).
                    # Temporarily suppress Python's own SIGINT so only Java handles it.
                    # CTRL_C_EVENT to process group 0 = broadcast to entire shared group.
                    old_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
                    try:
                        os.kill(0, signal.CTRL_C_EVENT)
                    finally:
                        signal.signal(signal.SIGINT, old_handler)
                else:
                    os.kill(self.process.pid, signal.SIGINT)

                # Wait up to 15 seconds for the JVM to run shutdown hooks and exit
                for _ in range(30):
                    if self.process.poll() is not None:
                        graceful = True
                        break
                    try:
                        time.sleep(0.5)
                    except KeyboardInterrupt:
                        # CTRL_C_EVENT we sent was also delivered to Python at the OS
                        # level (we share the same process group). Swallow it here so
                        # the poll loop can complete and pytest exits cleanly.
                        pass
            except Exception as e:
                print(f"Graceful shutdown signal failed: {e}")

            if graceful:
                print("Specmatic mock server stopped gracefully (report written).")
            else:
                # Fallback to forceful termination if still alive
                if self.process and self.process.poll() is None:
                    try:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], capture_output=True)
                        print("Forcefully terminated Specmatic mock server via taskkill (report may NOT be written).")
                    except Exception:
                        try:
                            self.process.terminate()
                            self.process.wait()
                        except Exception:
                            pass
            self.process = None
            if hasattr(self, "log_file_handle") and self.log_file_handle:
                try:
                    self.log_file_handle.close()
                except Exception:
                    pass
            print("Specmatic mock server terminated.")
