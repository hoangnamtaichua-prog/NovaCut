# -*- coding: utf-8 -*-
"""
tests/test_hongguo_challenger.py
Adversarial empirical stress-testing suite for services/hongguo_service.py.
Covers:
1. Concurrency (multi-threaded rapid starts/stops, singleton thread-safety, race resilience)
2. Port collision & Fallback (dummy sockets on 9099 and 8000, cascading port contention)
3. Mock crash & Process recovery (external kill of Java/Python, get_status dead state, forward_request recovery)
4. Win32 Job Object lifecycle & Cleanup idempotency
"""
import os
import sys
import time
import socket
import threading
import unittest
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.hongguo_service import (
    HongguoServiceManager,
    get_service_manager,
    port_is_open,
    port_is_bindable,
    select_available_port,
)


class TestHongguoChallengerConcurrency(unittest.TestCase):
    """Stress-testing concurrency and race conditions."""

    def setUp(self):
        self.mgr = HongguoServiceManager(tool_dir=r"D:\Tool\Hongguo Downloader")

    def tearDown(self):
        self.mgr.stop_services()

    def test_singleton_thread_safety(self):
        """20 threads calling get_service_manager() simultaneously receive the identical singleton instance."""
        instances = []
        barrier = threading.Barrier(20)

        def worker():
            barrier.wait()
            inst = get_service_manager()
            instances.append(inst)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        self.assertEqual(len(instances), 20)
        first_id = id(instances[0])
        for inst in instances:
            self.assertEqual(id(inst), first_id)

    @patch.object(HongguoServiceManager, 'verify_runtime', return_value=(True, ""))
    @patch.object(HongguoServiceManager, 'wait_port', return_value=True)
    @patch.object(HongguoServiceManager, 'check_signer_health')
    @patch.object(HongguoServiceManager, 'check_server_health')
    @patch('subprocess.Popen')
    def test_concurrent_rapid_start_services_no_duplicate_spawns(
        self, mock_popen, mock_srv_health, mock_sign_health, mock_wait, mock_verify
    ):
        """10 threads concurrently calling start_services() must not spawn duplicate processes or deadlock."""
        # First check returns False (not started), after spawn returns True
        state = {"signer_up": False, "server_up": False}

        def sign_health():
            return state["signer_up"]

        def srv_health():
            return state["server_up"]

        mock_sign_health.side_effect = sign_health
        mock_srv_health.side_effect = srv_health

        spawn_calls = []

        def fake_popen(cmd, **kwargs):
            p = MagicMock()
            p.pid = 1000 + len(spawn_calls)
            p.poll.return_value = None
            spawn_calls.append(cmd)
            # simulate process becoming healthy
            if "unidbg" in str(cmd):
                state["signer_up"] = True
            else:
                state["server_up"] = True
            return p

        mock_popen.side_effect = fake_popen

        barrier = threading.Barrier(10)
        results = []

        def worker():
            barrier.wait()
            ok, msg = self.mgr.start_services()
            results.append((ok, msg))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        self.assertEqual(len(results), 10)
        # All threads should report success
        for ok, msg in results:
            self.assertTrue(ok)

        # Crucial empirical check: Exactly 2 processes spawned in total (1 signer + 1 server), not 20!
        self.assertEqual(len(spawn_calls), 2)
        self.assertEqual(len(self.mgr._procs), 2)

    @patch.object(HongguoServiceManager, 'verify_runtime', return_value=(True, ""))
    @patch.object(HongguoServiceManager, 'wait_port', return_value=True)
    @patch.object(HongguoServiceManager, 'check_signer_health', return_value=False)
    @patch.object(HongguoServiceManager, 'check_server_health', return_value=False)
    @patch('subprocess.Popen')
    def test_concurrent_stress_rapid_alternating_start_stop(
        self, mock_popen, mock_srv_health, mock_sign_health, mock_wait, mock_verify
    ):
        """Multiple threads rapidly and simultaneously calling start_services(), stop_services(), and get_status()."""
        def make_proc():
            p = MagicMock()
            p.poll.return_value = None
            p.pid = 999
            return p

        mock_popen.side_effect = lambda *a, **kw: make_proc()

        errors = []
        stop_event = threading.Event()

        def starter():
            while not stop_event.is_set():
                try:
                    self.mgr.start_services()
                except Exception as e:
                    errors.append(f"start: {e}")
                time.sleep(0.005)

        def stopper():
            while not stop_event.is_set():
                try:
                    self.mgr.stop_services()
                except Exception as e:
                    errors.append(f"stop: {e}")
                time.sleep(0.005)

        def reader():
            while not stop_event.is_set():
                try:
                    st = self.mgr.get_status()
                    assert isinstance(st, dict)
                except Exception as e:
                    errors.append(f"status: {e}")
                time.sleep(0.005)

        threads = [
            threading.Thread(target=starter),
            threading.Thread(target=starter),
            threading.Thread(target=stopper),
            threading.Thread(target=stopper),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()

        time.sleep(1.0)
        stop_event.set()

        for t in threads:
            t.join(timeout=5.0)

        # Zero deadlocks or exceptions allowed under race stress
        self.assertEqual(errors, [])
        # Cleanup
        self.mgr.stop_services()
        self.assertEqual(len(self.mgr._procs), 0)


class TestHongguoChallengerPortCollision(unittest.TestCase):
    """Stress-testing port contention, dummy socket conflicts, and fallback port cycling."""

    def setUp(self):
        self.mgr = HongguoServiceManager(tool_dir=r"D:\Tool\Hongguo Downloader")
        self.sockets_to_close = []

    def tearDown(self):
        for s in self.sockets_to_close:
            try:
                s.close()
            except Exception:
                pass
        self.sockets_to_close.clear()
        self.mgr.stop_services()

    def _occupy_port(self, port: int, listen: bool = False) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', port))
        if listen:
            s.listen(1)
        self.sockets_to_close.append(s)
        return s

    def test_port_collision_server_8000_listening_dummy(self):
        """When port 8000 is occupied by a dummy listening socket, server cycles to candidate port 8088."""
        s8000 = self._occupy_port(8000, listen=True)

        # Port 8000 is not bindable
        self.assertFalse(self.mgr.is_port_bindable(8000))
        # Port 8000 is open, but check_server_health fails because dummy is not Hongguo FastAPI
        self.assertFalse(self.mgr.check_server_health())

        selected = self.mgr.select_port("HG_PORT", 8000, self.mgr.DEFAULT_SERVER_CANDIDATES)
        # First available candidate port is 8088
        self.assertEqual(selected, 8088)

    def test_port_collision_server_cascade_multiple_occupied(self):
        """When default 8000 and candidates 8088, 8090 are all occupied, select_port cascades to 8888."""
        s8000 = self._occupy_port(8000, listen=True)
        s8088 = self._occupy_port(8088, listen=True)
        s8090 = self._occupy_port(8090, listen=True)

        selected = self.mgr.select_port("HG_PORT", 8000, self.mgr.DEFAULT_SERVER_CANDIDATES)
        self.assertEqual(selected, 8888)

    def test_port_collision_signer_9099_bound_dummy(self):
        """When port 9099 is occupied by a bound dummy socket, signer cycles to candidate port 8766."""
        s9099 = self._occupy_port(9099, listen=False)

        self.assertFalse(self.mgr.is_port_bindable(9099))
        self.assertFalse(self.mgr.check_signer_health())

        selected = self.mgr.select_port("HG_SIGN_PORT", 9099, self.mgr.DEFAULT_SIGN_CANDIDATES)
        self.assertEqual(selected, 8766)

    def test_port_collision_signer_cascade_multiple_occupied(self):
        """When ports 9099, 8766, 8765 are all occupied, select_port cascades to 9599."""
        s9099 = self._occupy_port(9099, listen=False)
        s8766 = self._occupy_port(8766, listen=False)
        s8765 = self._occupy_port(8765, listen=False)

        selected = self.mgr.select_port("HG_SIGN_PORT", 9099, self.mgr.DEFAULT_SIGN_CANDIDATES)
        # Port 9599 is often in Windows Hyper-V exclusion range [9528-9627], so select_port robustly skips to 9088
        expected = 9599 if port_is_bindable(9599) else 9088
        self.assertEqual(selected, expected)

    def test_port_collision_signer_9099_listening_dummy_limitation(self):
        """Adversarial check: When an alien dummy socket is listening on 9099, check_signer_health() returns True because it only probes TCP connect."""
        s9099 = self._occupy_port(9099, listen=True)
        # An alien listening socket makes check_signer_health return True
        self.assertTrue(self.mgr.check_signer_health())
        # However, is_port_bindable correctly detects port is NOT free
        self.assertFalse(self.mgr.is_port_bindable(9099))

    def test_port_collision_all_candidates_exhausted_fallback_dynamic(self):
        """When default port and ALL candidate ports are occupied, select_port falls back to a free dynamic OS port."""
        candidates = [29091, 29092]
        s_def = self._occupy_port(29090, listen=False)
        s_c1 = self._occupy_port(29091, listen=False)
        s_c2 = self._occupy_port(29092, listen=False)

        dynamic_port = self.mgr.select_port("CUSTOM_TEST_PORT", 29090, candidates)
        self.assertNotIn(dynamic_port, [29090, 29091, 29092])
        self.assertGreater(dynamic_port, 1024)
        self.assertTrue(port_is_bindable(dynamic_port))

    @patch.object(HongguoServiceManager, 'verify_runtime', return_value=(True, ""))
    @patch.object(HongguoServiceManager, 'wait_port', return_value=True)
    @patch('subprocess.Popen')
    def test_start_services_adopts_fallback_ports_under_contention(self, mock_popen, mock_wait, mock_verify):
        """Full start_services() run when 9099 and 8000 are occupied passes candidate ports to processes."""
        # Occupy 9099 (bound, not listening) and 8000 (bound, not listening)
        s9099 = self._occupy_port(9099, listen=False)
        s8000 = self._occupy_port(8000, listen=False)

        captured_envs = []
        captured_cmds = []

        def fake_spawn(cmd, cwd=None, env=None, **kwargs):
            captured_cmds.append(cmd)
            captured_envs.append(env or {})
            p = MagicMock()
            p.pid = 2000 + len(captured_cmds)
            p.poll.return_value = None
            return p

        mock_popen.side_effect = fake_spawn

        ok, msg = self.mgr.start_services()
        self.assertTrue(ok)

        # Check Signer received fallback port 8766
        self.assertEqual(self.mgr.signer_port, 8766)
        sign_cmd = captured_cmds[0]
        self.assertIn("8766", sign_cmd)

        # Check Server received fallback port 8088 and SIGN_SERVER pointing to 8766
        self.assertEqual(self.mgr.server_port, 8088)
        srv_env = captured_envs[1]
        self.assertEqual(srv_env.get("PORT"), "8088")
        self.assertEqual(srv_env.get("SIGN_SERVER"), "http://127.0.0.1:8766")


class TestHongguoChallengerMockCrash(unittest.TestCase):
    """Stress-testing process crash detection, get_status dead-state reflection, and recovery."""

    def setUp(self):
        self.mgr = HongguoServiceManager(tool_dir=r"D:\Tool\Hongguo Downloader")

    def tearDown(self):
        self.mgr.stop_services()

    @patch.object(HongguoServiceManager, 'check_signer_health')
    @patch.object(HongguoServiceManager, 'check_server_health')
    def test_get_status_reflects_signer_crash(self, mock_srv, mock_sign):
        """When Signer process crashes externally, get_status() immediately reflects dead signer state."""
        # Initial: both running
        mock_sign.return_value = True
        mock_srv.return_value = True

        st = self.mgr.get_status()
        self.assertTrue(st["signer_running"])
        self.assertTrue(st["server_running"])

        # Signer killed externally
        mock_sign.return_value = False

        st_after = self.mgr.get_status()
        self.assertFalse(st_after["signer_running"])
        self.assertTrue(st_after["server_running"])

    @patch.object(HongguoServiceManager, 'check_signer_health')
    @patch.object(HongguoServiceManager, 'check_server_health')
    def test_get_status_reflects_server_crash(self, mock_srv, mock_sign):
        """When Server process crashes externally, get_status() immediately reflects dead server state."""
        mock_sign.return_value = True
        mock_srv.return_value = True

        st = self.mgr.get_status()
        self.assertTrue(st["server_running"])

        # Server killed externally
        mock_srv.return_value = False

        st_after = self.mgr.get_status()
        self.assertFalse(st_after["server_running"])
        self.assertTrue(st_after["signer_running"])

    @patch.object(HongguoServiceManager, 'check_server_health')
    @patch.object(HongguoServiceManager, 'start_services')
    @patch('requests.request')
    def test_forward_request_auto_recovers_when_server_dead(self, mock_req, mock_start, mock_srv_health):
        """When server is dead, forward_request() detects it and attempts auto-recovery via start_services()."""
        # Server is dead initially
        mock_srv_health.return_value = False
        mock_start.return_value = (True, "Restarted")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"ok": True}
        mock_req.return_value = mock_resp

        code, body = self.mgr.forward_request("GET", "/dl/status")
        mock_start.assert_called_once()
        self.assertEqual(code, 200)

    @patch.object(HongguoServiceManager, 'check_server_health', return_value=False)
    @patch.object(HongguoServiceManager, 'start_services', return_value=(False, "Failed to boot"))
    def test_forward_request_clean_503_when_recovery_fails(self, mock_start, mock_srv_health):
        """When server is dead and restart fails, forward_request() cleanly returns HTTP 503 error without crashing."""
        code, body = self.mgr.forward_request("GET", "/dl/status")
        self.assertEqual(code, 503)
        self.assertFalse(body["success"])
        self.assertIn("Failed to boot", body["error"])


class TestHongguoChallengerLifecycleIntegrity(unittest.TestCase):
    """Stress-testing Win32 Job Object lifecycle, idempotency, and clean termination."""

    def setUp(self):
        self.mgr = HongguoServiceManager(tool_dir=r"D:\Tool\Hongguo Downloader")

    def tearDown(self):
        self.mgr.stop_services()

    def test_stop_services_idempotent(self):
        """Calling stop_services() multiple consecutive times causes no error."""
        ok1, msg1 = self.mgr.stop_services()
        self.assertTrue(ok1)
        ok2, msg2 = self.mgr.stop_services()
        self.assertTrue(ok2)
        ok3, msg3 = self.mgr.stop_services()
        self.assertTrue(ok3)

    if os.name == 'nt':
        def test_job_object_lifecycle_nt(self):
            """Windows Job Object handle is created and cleanly closed on stop_services()."""
            h1 = self.mgr._init_job_object()
            self.assertIsNotNone(h1)
            # Re-init returns same handle
            h2 = self.mgr._init_job_object()
            self.assertEqual(h1, h2)

            self.mgr.stop_services()
            self.assertIsNone(self.mgr._job_handle)

    def test_process_termination_escalation(self):
        """Unresponsive processes undergo terminate() then kill() escalation during stop_services()."""
        stubborn_proc = MagicMock()
        stubborn_proc.poll.return_value = None  # Pretends it refuses to die
        # wait() raises TimeoutExpired so it escalates to kill()
        import subprocess
        stubborn_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=3.0)

        self.mgr._procs.append(stubborn_proc)
        ok, msg = self.mgr.stop_services()

        self.assertTrue(ok)
        stubborn_proc.terminate.assert_called_once()
        stubborn_proc.kill.assert_called_once()
        self.assertEqual(len(self.mgr._procs), 0)


if __name__ == '__main__':
    unittest.main()
