"""Project-lock contention uses temporary files and real independent processes."""

from __future__ import annotations

import errno
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from sprite_pipeline.storage.locking import ProjectBusyError, ProjectLock


class ProjectLockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = Path(temporary.name) / "pipeline.json"

    def assert_available_from_another_thread(self, lock):
        results = []

        def acquire():
            try:
                with lock:
                    results.append("acquired")
            except BaseException as error:
                results.append(error)

        thread = threading.Thread(target=acquire, daemon=True)
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive(), "A failed acquisition leaked the local lock")
        self.assertEqual(results, ["acquired"])

    def holder(self):
        script = (
            "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
            "from sprite_pipeline.storage.locking import ProjectLock\n"
            "with ProjectLock(Path(sys.argv[2])):\n"
            " print('locked', flush=True)\n"
            " sys.stdin.readline()\n"
        )
        child = subprocess.Popen(
            [sys.executable, "-c", script, str(TOOLS), str(self.config)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def close():
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)

        self.addCleanup(close)
        self.assertEqual(child.stdout.readline().strip(), "locked")
        return child

    def test_short_cross_process_contention_waits_then_enters_without_manual_retry(self):
        child = self.holder()
        lock = ProjectLock(self.config, timeout=2)

        def release_on_contention(_delay):
            child.stdin.write("release\n")
            child.stdin.flush()
            self.assertEqual(child.wait(timeout=5), 0)

        # The first OS lock attempt really fails. Release the real holder only
        # when the implementation elects to wait instead of reporting failure.
        with patch("sprite_pipeline.storage.locking.time.sleep", side_effect=release_on_contention):
            with lock:
                self.assertEqual(lock.depth, 1)
        self.assertIsNone(lock.handle)

    def test_cross_process_timeout_does_not_enter_or_leak_the_local_lock(self):
        child = self.holder()
        lock = ProjectLock(self.config, timeout=0.05)
        with self.assertRaises(ProjectBusyError):
            with lock:
                self.fail("A competing writer must not enter the critical section")
        self.assertEqual(lock.depth, 0)
        self.assertIsNone(lock.handle)
        child.stdin.write("release\n")
        child.stdin.flush()
        self.assertEqual(child.wait(timeout=5), 0)
        self.assert_available_from_another_thread(lock)

    def test_another_thread_has_the_same_bounded_wait_and_keeps_the_owner_handle(self):
        lock = ProjectLock(self.config, timeout=0.05)
        ready, release = threading.Event(), threading.Event()

        def hold():
            with lock:
                ready.set()
                release.wait(timeout=5)

        thread = threading.Thread(target=hold)
        thread.start()
        try:
            self.assertTrue(ready.wait(timeout=2))
            with self.assertRaises(ProjectBusyError):
                with lock:
                    self.fail("The timeout must also apply within the server process")
            self.assertEqual(lock.depth, 1)
            self.assertFalse(lock.handle.closed)
        finally:
            release.set()
            thread.join(timeout=6)
        self.assertFalse(thread.is_alive())
        with lock:
            self.assertEqual(lock.depth, 1)

    def test_reentrant_acquisition_keeps_the_outer_file_lock(self):
        lock = ProjectLock(self.config, timeout=0)
        with lock:
            handle = lock.handle
            with lock:
                self.assertEqual(lock.depth, 2)
                self.assertIs(lock.handle, handle)
            self.assertEqual(lock.depth, 1)
            self.assertFalse(handle.closed)
        self.assertTrue(handle.closed)

    def test_non_contention_os_error_is_preserved_and_acquisition_can_be_retried(self):
        lock = ProjectLock(self.config, timeout=0.05)
        error = OSError(errno.EINVAL, "invalid lock operation")
        with patch.object(lock, "_lock_once", side_effect=error):
            with self.assertRaises(OSError) as caught:
                with lock:
                    self.fail("A failed lock operation must not enter")
        self.assertIs(caught.exception, error)
        self.assertIsNone(lock.handle)
        self.assert_available_from_another_thread(lock)

    def test_initialization_failure_closes_the_handle_and_releases_the_local_lock(self):
        lock = ProjectLock(self.config, timeout=0.05)
        with patch("sprite_pipeline.storage.locking.os.fstat", side_effect=OSError("stat failed")):
            with self.assertRaisesRegex(OSError, "stat failed"):
                with lock:
                    self.fail("Initialization must finish before entering")
        self.assertIsNone(lock.handle)
        self.assert_available_from_another_thread(lock)

    def test_os_lock_wait_uses_time_left_after_local_acquisition(self):
        self.holder()
        lock = ProjectLock(self.config, timeout=0.1)
        local_lock = lock.thread
        clock, waits = [0.0], []

        def acquire_local(*, timeout):
            acquired = local_lock.acquire(timeout=timeout)
            clock[0] += 0.08
            return acquired

        def wait(delay):
            waits.append(delay)
            clock[0] += delay

        # Keep the real OS lock contended; advance a controlled clock to account
        # for time spent waiting for the local RLock without a timing-sensitive test.
        with (
            patch.object(lock, "thread") as thread,
            patch("sprite_pipeline.storage.locking.time.monotonic", side_effect=lambda: clock[0]),
            patch("sprite_pipeline.storage.locking.time.sleep", side_effect=wait),
        ):
            thread.acquire.side_effect = acquire_local
            thread.release.side_effect = local_lock.release
            with self.assertRaises(ProjectBusyError):
                with lock:
                    self.fail("The local wait must not grant a second full timeout")
        self.assertAlmostEqual(sum(waits), 0.02)


if __name__ == "__main__":
    unittest.main()
