# -*- coding: utf-8 -*-
"""
tests: orchestration script infoView.sh (supervisor, start / stop / status, log rotation,
autostart) with a fake app

IVW_PYTHON points to a small shell script that plays the app (FAKE_MODE: run, exit, crash,
crash_once, stubborn, spam); IVW_LOG_DIR, HOME and DISPLAY are temporary / fake, so the real
logs/ (where the real app may be running), the labwc autostart file and the display are never
touched. Linux only (setsid, pgrep, /proc).
"""
# < imports >----------------------------------------------------------------------------------

# python library
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

# infoView
import infoview.core.config as cfg

# < constants >--------------------------------------------------------------------------------

# the script
DS_SCRIPT = os.path.join(cfg.DS_ROOT_DIR, "infoView.sh")

# the fake app: called as "<fake> <root>/infoView.py" (so pgrep -f infoView.py finds it)
DS_FAKE_APP = r"""#!/bin/bash
case "${FAKE_MODE}" in
    exit)       echo "fake: exit"; exit 0 ;;
    crash)      echo "fake: crash"; exit 3 ;;
    crash_once) if [ ! -f "${FAKE_STATE}" ]; then : > "${FAKE_STATE}"; echo "fake: crash"; exit 3; fi ;;
    stubborn)   trap '' TERM ;;
esac
[ "${FAKE_MODE}" = "stubborn" ] || trap 'echo "fake: TERM"; exit 0' TERM
echo "fake: up"
while true; do
    [ "${FAKE_MODE}" = "spam" ] && echo "fake: some log line to make the log grow ............................"
    sleep 0.05
done
"""

# ---------------------------------------------------------------------------------------------
def _wait_for(f_cond, ff_timeout: float = 10.) -> bool:
    """poll f_cond() until it is true or the time is up"""
    lf_end = time.monotonic() + ff_timeout

    while time.monotonic() < lf_end:
        if f_cond():
            return True
        time.sleep(.1)

    return f_cond()

# < TestScript >-------------------------------------------------------------------------------

@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("setsid") and shutil.which("pgrep"),
                     "needs Linux with setsid and pgrep")
class TestScript(unittest.TestCase):
    """infoView.sh with a fake app"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        ls_dir = self._tmp.name

        # fake app
        self._s_fake = os.path.join(ls_dir, "fake_python")
        with open(self._s_fake, "w", encoding="utf-8") as l_fp:
            l_fp.write(DS_FAKE_APP)
        os.chmod(self._s_fake, 0o755)

        # temporary logs and home, fake display, fast timings
        self._s_log_dir = os.path.join(ls_dir, "logs")
        self._s_log = os.path.join(self._s_log_dir, "infoView.log")
        self._s_pid = os.path.join(self._s_log_dir, "infoView.pid")

        self._dct_env = {k: v for k, v in os.environ.items() if not k.startswith("IVW_")}
        self._dct_env.update(IVW_PYTHON=self._s_fake, IVW_LOG_DIR=self._s_log_dir, IVW_START_WAIT="0.5",
                             IVW_RESTART_DELAY="0", IVW_STOP_TIMEOUT="3", IVW_LOG_CHECK="1",
                             HOME=ls_dir, DISPLAY=":99", FAKE_MODE="run",
                             FAKE_STATE=os.path.join(ls_dir, "crashed"))

    def tearDown(self):
        # never leave a supervisor behind
        self._sh("stop")
        self._tmp.cleanup()

    def _sh(self, *args, **env) -> subprocess.CompletedProcess:
        """run infoView.sh <args> (extra environment in env)"""
        return subprocess.run(["bash", DS_SCRIPT, *args], env=dict(self._dct_env, **env),
                              capture_output=True, text=True, timeout=60, check=False)

    def _log(self) -> str:
        """log contents"""
        try:
            with open(self._s_log, encoding="utf-8", errors="replace") as l_fp:
                return l_fp.read()
        except FileNotFoundError:
            return ""

    def _app_pid(self) -> int:
        """pid of the fake app (child of the supervisor), 0 if none"""
        with open(self._s_pid, encoding="utf-8") as l_fp:
            ls_spid = l_fp.read().strip()

        l_res = subprocess.run(["pgrep", "-P", ls_spid, "-f", "infoView.py"], capture_output=True, text=True, check=False)
        return int(l_res.stdout.split()[0]) if l_res.stdout.split() else 0

    @staticmethod
    def _alive(fi_pid: int) -> bool:
        """process alive ?"""
        try:
            os.kill(fi_pid, 0)
            return True
        except OSError:
            return False

    def test_start_status_stop(self):
        l_res = self._sh("start")
        self.assertEqual(l_res.returncode, 0, l_res.stderr)
        self.assertIn("started", l_res.stderr)

        # already running: not started twice
        self.assertIn("already running", self._sh("start").stderr)

        l_res = self._sh("status")
        self.assertEqual(l_res.returncode, 0)
        self.assertRegex(l_res.stdout, r"app:\s+pid \d+")
        li_app = self._app_pid()

        # graceful stop: SIGTERM forwarded to the app
        self.assertIn("stopped", self._sh("stop").stderr)
        self.assertFalse(os.path.exists(self._s_pid))
        self.assertTrue(_wait_for(lambda: not self._alive(li_app), 5))
        self.assertIn("stop requested", self._log())
        self.assertIn("fake: TERM", self._log())

        # not running
        self.assertEqual(self._sh("status").returncode, 3)

    def test_normal_exit_not_restarted(self):
        self._sh("start", FAKE_MODE="exit")

        # the supervisor leaves (pid file removed), the app was started once
        self.assertTrue(_wait_for(lambda: not os.path.exists(self._s_pid)))
        self.assertIn("app exited normally", self._log())
        self.assertEqual(self._log().count("starting app"), 1)

    def test_crash_restarted(self):
        self._sh("start", FAKE_MODE="crash_once")

        # crashed once, restarted, now running
        self.assertTrue(_wait_for(lambda: self._log().count("fake: up") == 1))
        self.assertIn("app crashed (rc=3), 1 crash(es)", self._log())
        self.assertEqual(self._sh("status").returncode, 0)

    def test_crash_loop_gives_up(self):
        self._sh("start", FAKE_MODE="crash", IVW_MAX_CRASHES="3")

        self.assertTrue(_wait_for(lambda: not os.path.exists(self._s_pid)))
        self.assertIn("giving up: 3 crashes", self._log())
        self.assertEqual(self._log().count("starting app"), 3)

    def test_forced_stop(self):
        self._sh("start", FAKE_MODE="stubborn")
        li_app = self._app_pid()
        self.assertTrue(li_app)

        # the app ignores SIGTERM: SIGKILL after IVW_STOP_TIMEOUT
        l_res = self._sh("stop", IVW_STOP_TIMEOUT="1")
        self.assertIn("killing", l_res.stderr)
        self.assertTrue(_wait_for(lambda: not self._alive(li_app), 5))
        self.assertIn("forced stop (SIGKILL)", self._log())

    def test_log_rotation_at_start(self):
        os.makedirs(self._s_log_dir)
        with open(self._s_log, "w", encoding="utf-8") as l_fp:
            l_fp.write("old line\n" * 200)

        self._sh("start", FAKE_MODE="exit", IVW_LOG_MAX="1000")

        # renamed to .1, a new log started
        with open(self._s_log + ".1", encoding="utf-8") as l_fp:
            self.assertEqual(l_fp.read().count("old line"), 200)
        self.assertNotIn("old line", self._log())

    def test_log_rotation_while_running(self):
        self._sh("start", FAKE_MODE="spam", IVW_LOG_MAX="2000")

        # the watcher (every IVW_LOG_CHECK = 1 s) copies + truncates the log the app writes to
        self.assertTrue(_wait_for(lambda: os.path.exists(self._s_log + ".1")))
        self.assertGreater(os.path.getsize(self._s_log + ".1"), 2000)

        # the app goes on writing at the new end (append mode): no hole of zero bytes
        time.sleep(.5)
        self.assertNotIn("\0", self._log())
        self.assertIn("fake: some log line", self._log())

    def test_autostart(self):
        ls_file = os.path.join(self._tmp.name, ".config", "labwc", "autostart")

        self.assertIn("autostart on", self._sh("autostart", "on").stderr)
        self.assertIn("already on", self._sh("autostart", "on").stderr)

        with open(ls_file, encoding="utf-8") as l_fp:
            ls_text = l_fp.read()
        self.assertEqual(ls_text.count(f"{DS_SCRIPT} start &"), 1)

        # off: the tag and the command line removed
        self.assertIn("autostart off", self._sh("autostart", "off").stderr)
        with open(ls_file, encoding="utf-8") as l_fp:
            self.assertNotIn("infoView", l_fp.read())
        self.assertIn("already off", self._sh("autostart", "off").stderr)

    def test_logs_and_usage(self):
        os.makedirs(self._s_log_dir)
        with open(self._s_log, "w", encoding="utf-8") as l_fp:
            l_fp.write("a\nb\nc\n")

        self.assertEqual(self._sh("logs", "2").stdout, "b\nc\n")
        self.assertEqual(self._sh("logs", "-x").returncode, 1)

        l_res = self._sh("nonsense")
        self.assertEqual(l_res.returncode, 1)
        self.assertIn("usage: infoView.sh", l_res.stderr)

# < the end >----------------------------------------------------------------------------------
