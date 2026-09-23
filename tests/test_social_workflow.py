import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import social_workflow
import social_adapters
import social_tokens
import license_manager
from flask import Flask
from routes.social_publish import social_publish_bp


class SocialWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.tmp.close()
        self.old_jobs = social_workflow.JOBS_FILE
        self.old_connections = social_workflow.CONNECTIONS_FILE
        self.old_tokens = social_tokens.TOKENS_FILE
        self.old_vault_key = social_tokens.VAULT_KEY_FILE

        social_workflow.JOBS_FILE = self.tmp.name + ".jobs.json"
        social_workflow.CONNECTIONS_FILE = self.tmp.name + ".connections.json"
        social_tokens.TOKENS_FILE = self.tmp.name + ".tokens.enc"
        social_tokens.VAULT_KEY_FILE = self.tmp.name + ".vault.key"

        self.app = Flask(__name__)
        self.app.register_blueprint(social_publish_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        for path in (
            self.tmp.name,
            social_workflow.JOBS_FILE,
            social_workflow.CONNECTIONS_FILE,
            social_tokens.TOKENS_FILE,
            social_tokens.VAULT_KEY_FILE,
            social_workflow.JOBS_FILE + ".tmp",
            social_workflow.CONNECTIONS_FILE + ".tmp",
            social_tokens.TOKENS_FILE + ".tmp",
        ):
            try:
                os.unlink(path)
            except OSError:
                pass
        social_workflow.JOBS_FILE = self.old_jobs
        social_workflow.CONNECTIONS_FILE = self.old_connections
        social_tokens.TOKENS_FILE = self.old_tokens
        social_tokens.VAULT_KEY_FILE = self.old_vault_key

    def test_plan_persists_platform_copy(self):
        job = social_workflow.create_publish_plan(self.tmp.name, "Tiêu đề mẫu", ["youtube"], use_ai=False)
        self.assertEqual(job["status"], "READY_FOR_PUBLISH")
        self.assertEqual(social_workflow.get_publish_job(job["job_id"])["job_id"], job["job_id"])
        self.assertTrue(job["platforms"][0]["copy"]["caption"])

    def test_invalid_connection_is_rejected(self):
        with self.assertRaises(ValueError):
            social_workflow.create_publish_plan(self.tmp.name, "Mẫu", ["youtube"], connection_ids=["missing"])

    def test_published_requires_evidence(self):
        job = social_workflow.create_publish_plan(self.tmp.name, "Mẫu", ["youtube"], use_ai=False)
        with self.assertRaises(ValueError):
            social_workflow.update_platform_status(job["job_id"], "youtube", "PUBLISHED")
        self.assertEqual(social_workflow.get_publish_job(job["job_id"])["status"], "READY_FOR_PUBLISH")

    def test_needs_action_is_not_running(self):
        job = social_workflow.create_publish_plan(self.tmp.name, "Mẫu", ["youtube"], use_ai=False)
        updated = social_workflow.update_platform_status(job["job_id"], "youtube", "NEEDS_ACTION")
        self.assertEqual(updated["status"], "NEEDS_ACTION")

    def test_browser_label_cannot_publish_using_global_token(self):
        with patch.object(social_adapters, "publish_youtube") as upload:
            result = social_adapters.publish({}, {"platform_id": "youtube", "status": "READY"})
        upload.assert_not_called()
        self.assertEqual(result.status, "NEEDS_ACTION")

    def test_existing_remote_post_is_not_uploaded_again(self):
        with patch.object(social_adapters, "publish_youtube") as upload:
            result = social_adapters.publish({}, {"platform_id": "youtube", "status": "FAILED", "remote_id": "abc"})
        upload.assert_not_called()
        self.assertEqual(result.remote_id, "abc")

    def test_platform_status_never_publishes_other_platform(self):
        job = social_workflow.create_publish_plan(self.tmp.name, "Mẫu", ["youtube", "facebook"], use_ai=False)
        updated = social_workflow.update_platform_status(job["job_id"], "youtube", "PUBLISHED", "abc", "https://youtu.be/abc")
        self.assertEqual(updated["status"], "IN_PROGRESS")
        self.assertEqual(updated["platforms"][1]["status"], "READY")

    # --- New Tests for Step 13 Features ---

    def test_protected_token_storage_and_encryption(self):
        """Verify tokens are encrypted on disk and decrypted accurately."""
        token_payload = {
            "platform_id": "youtube",
            "access_token": "ya29.secret_token_12345",
            "refresh_token": "1//refresh_secret_67890",
            "expires_at": 9999999999.0,
        }
        conn_id = "test_conn_001"
        social_tokens.save_token(conn_id, token_payload)

        # 1. Decrypted in memory
        loaded = social_tokens.get_token(conn_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["access_token"], "ya29.secret_token_12345")
        self.assertEqual(loaded["refresh_token"], "1//refresh_secret_67890")

        # 2. On disk it is encrypted binary, NOT containing plaintext
        with open(social_tokens.TOKENS_FILE, "rb") as fh:
            raw_disk = fh.read()
        self.assertNotIn(b"ya29.secret_token_12345", raw_disk)
        self.assertNotIn(b"1//refresh_secret_67890", raw_disk)

        # 3. Delete token
        deleted = social_tokens.delete_token(conn_id)
        self.assertTrue(deleted)
        self.assertIsNone(social_tokens.get_token(conn_id))

    def test_pkce_generation_and_state(self):
        """Verify PKCE parameters and CSRF state parameter validation."""
        verifier, challenge = social_tokens.generate_pkce_pair()
        self.assertTrue(len(verifier) >= 43)
        self.assertTrue(len(challenge) >= 43)

        state = social_tokens.create_oauth_state("youtube", verifier)
        self.assertTrue(bool(state))

        # First verify succeeds
        verified = social_tokens.verify_oauth_state(state)
        self.assertIsNotNone(verified)
        self.assertEqual(verified["platform_id"], "youtube")
        self.assertEqual(verified["code_verifier"], verifier)

        # Replayed verify fails (consumed)
        replayed = social_tokens.verify_oauth_state(state)
        self.assertIsNone(replayed)

    def test_update_platform_copy(self):
        """Verify user customization of copy and target connection."""
        job = social_workflow.create_publish_plan(self.tmp.name, "Mẫu", ["youtube"], use_ai=False)
        job_id = job["job_id"]

        updated = social_workflow.update_platform_copy(
            job_id,
            "youtube",
            title="Tiêu đề đã chỉnh sửa",
            caption="Caption tùy biến mới",
            hashtags="#custom #tags",
        )
        self.assertIsNotNone(updated)
        item = updated["platforms"][0]
        self.assertEqual(item["copy"]["title"], "Tiêu đề đã chỉnh sửa")
        self.assertEqual(item["copy"]["caption"], "Caption tùy biến mới")
        self.assertEqual(item["copy"]["hashtags"], "#custom #tags")
        self.assertEqual(item["copy_source"], "user_edited")

    def test_update_platform_copy_published_rejected(self):
        """Published platform copy cannot be modified."""
        job = social_workflow.create_publish_plan(self.tmp.name, "Mẫu", ["youtube"], use_ai=False)
        job_id = job["job_id"]
        social_workflow.update_platform_status(job_id, "youtube", "PUBLISHED", "rem_01", "https://youtu.be/rem_01")

        with self.assertRaises(ValueError):
            social_workflow.update_platform_copy(job_id, "youtube", title="New Title")

    def test_delete_connection_removes_token(self):
        """Deleting a connection cleans up both connection record and token store."""
        conn = social_workflow.save_connection(
            platform_id="youtube",
            account_label="Kênh Xóa",
            capabilities=["manual_browser", "verified_api"],
        )
        cid = conn["connection_id"]
        social_tokens.save_token(cid, {"access_token": "token_abc"})

        self.assertIsNotNone(social_tokens.get_token(cid))
        deleted = social_workflow.delete_connection(cid)
        self.assertTrue(deleted)
        self.assertIsNone(social_tokens.get_token(cid))
        self.assertNotIn(cid, [c["connection_id"] for c in social_workflow.list_connections()])

    def test_verified_api_capability_required_for_publish(self):
        """Publish adapter rejects manual_browser connections and allows verified_api with token."""
        # 1. Manual browser connection
        conn_manual = social_workflow.save_connection(
            platform_id="youtube",
            account_label="Chrome Only",
            capabilities=["manual_browser"],
        )
        job = social_workflow.create_publish_plan(
            self.tmp.name, "Mẫu", ["youtube"], use_ai=False, connection_ids=[conn_manual["connection_id"]]
        )
        item = job["platforms"][0]
        result = social_adapters.publish(job, item)
        self.assertEqual(result.status, "NEEDS_ACTION")
        self.assertIn("OAuth", result.message)

        # 2. Verified API connection with valid token
        conn_verified = social_workflow.save_connection(
            platform_id="youtube",
            account_label="OAuth Verified Channel",
            capabilities=["manual_browser", "verified_api"],
        )
        social_tokens.save_token(conn_verified["connection_id"], {
            "platform_id": "youtube",
            "access_token": "valid_token_xyz",
            "expires_at": 9999999999.0,
        })
        job2 = social_workflow.create_publish_plan(
            self.tmp.name, "Mẫu 2", ["youtube"], use_ai=False, connection_ids=[conn_verified["connection_id"]]
        )
        item2 = job2["platforms"][0]

        with patch.object(social_adapters, "upload_youtube_resumable") as mock_upload:
            mock_upload.return_value = social_adapters.AdapterResult("PUBLISHED", "Thành công", "vid_999", "https://youtu.be/vid_999")
            res2 = social_adapters.publish(job2, item2)
        mock_upload.assert_called_once()
        self.assertEqual(res2.status, "PUBLISHED")
        self.assertEqual(res2.remote_id, "vid_999")

    def test_workflow_routes_require_license(self):
        """License Enforcement Rule: Unlicensed requests must receive 403 Forbidden."""
        with patch.object(license_manager, "check_permission", return_value=(False, "Bản quyền chưa kích hoạt", "UNLICENSED")):
            # POST /api/social/workflow/plan
            resp_plan = self.client.post("/api/social/workflow/plan", json={})
            self.assertEqual(resp_plan.status_code, 403)
            self.assertTrue(resp_plan.get_json().get("license_error"))

            # GET /api/social/workflow/jobs/123
            resp_job = self.client.get("/api/social/workflow/jobs/123")
            self.assertEqual(resp_job.status_code, 403)

            # GET /api/social/workflow/connections
            resp_conn = self.client.get("/api/social/workflow/connections")
            self.assertEqual(resp_conn.status_code, 403)

            # GET /api/social/oauth/start
            resp_oauth = self.client.get("/api/social/oauth/start")
            self.assertEqual(resp_oauth.status_code, 403)


if __name__ == "__main__":
    unittest.main()
