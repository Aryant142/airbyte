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

    def start(self, repo_root: Path, fix_spec_script: Path) -> None:
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
            print("Running fix_spec.py to modify specification...")
            subprocess.run([sys.executable, str(fix_spec_script)], check=True, cwd=str(repo_root))

            log_file = repo_root / "specmatic_server.log"
            self.log_file_handle = open(log_file, "w", encoding="utf-8")
            print(f"Starting Specmatic mock server on {self.host}:{self.port} (logging to {log_file})...")
            import os
            # NOTE: Do NOT use CREATE_NEW_PROCESS_GROUP on Windows.
            # With that flag, CTRL_C_EVENT cannot reach the child process.
            # Without it, Java inherits Python's process group, so we can
            # broadcast CTRL_C_EVENT to the whole group to trigger JVM shutdown
            # hooks (which write the Specmatic HTML coverage report).
            creation_flags = 0
            cmd_args = [specmatic_bin, "mock", f"--port={self.port}", f"--host={self.host}"]
            if os.name == 'nt':
                if specmatic_bin.upper().endswith('.CMD'):
                    npm_dir = Path(specmatic_bin).parent
                    jar_path = npm_dir / "node_modules" / "specmatic" / "specmatic.jar"
                    if jar_path.exists() and shutil.which("java"):
                        cmd_args = ["java", "-jar", str(jar_path), "mock", f"--port={self.port}", f"--host={self.host}"]

            self.process = subprocess.Popen(
                cmd_args,
                cwd=str(repo_root),
                stdout=self.log_file_handle,
                stderr=self.log_file_handle,
                text=True,
                shell=False,
                creationflags=creation_flags,
            )

            # Wait for mock server to be ready
            ready_url = f"http://{self.host}:{self.port}/_specmatic/expectations"
            retries = 30
            for i in range(retries):
                if self.process.poll() is not None:
                    raise RuntimeError(f"Specmatic mock server failed to start. Check {log_file} for details.")
                try:
                    # Connection check (non-blocking if server is up, regardless of status code)
                    requests.get(ready_url, timeout=1)
                    print("Specmatic mock server is ready.")
                    return
                except requests.exceptions.ConnectionError:
                    pass
                except requests.RequestException:
                    # Other request exceptions (like bad status code) mean the server is listening!
                    print("Specmatic mock server is ready.")
                    return
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
                if os.name == 'nt':
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
                    time.sleep(0.5)
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
