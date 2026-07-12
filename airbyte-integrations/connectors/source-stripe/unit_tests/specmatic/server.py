# Copyright (c) 2026 Airbyte, Inc., all rights reserved.

import subprocess
import shutil
import sys
from pathlib import Path
import time
import requests

class SpecmaticServer:
    def __init__(self, port: int = 9000, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self.process = None

    def start(self, repo_root: Path, fix_spec_script: Path) -> None:
        specmatic_bin = shutil.which("specmatic")
        if specmatic_bin:
            print("Running fix_spec.py to modify specification...")
            subprocess.run([sys.executable, str(fix_spec_script)], check=True, cwd=str(repo_root))

            print(f"Starting Specmatic mock server on {self.host}:{self.port}...")
            self.process = subprocess.Popen(
                ["specmatic", "mock", f"--port={self.port}", f"--host={self.host}"],
                cwd=str(repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True
            )

            # Wait for mock server to be ready
            ready_url = f"http://{self.host}:{self.port}"
            retries = 30
            for i in range(retries):
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate()
                    raise RuntimeError(f"Specmatic mock server failed to start: {stderr}\n{stdout}")
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
            try:
                # On Windows, kill the process tree to terminate the Java child process too
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], capture_output=True)
            except Exception:
                # Fallback to standard terminate if taskkill is not available or fails
                try:
                    self.process.terminate()
                    self.process.wait()
                except Exception:
                    pass
            self.process = None
            print("Specmatic mock server terminated.")
