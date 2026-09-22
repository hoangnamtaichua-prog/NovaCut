import os
import tempfile
import unittest

import social_workflow
import social_adapters
from unittest.mock import patch


class SocialWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.tmp.close()
        self.old_jobs = social_workflow.JOBS_FILE
        self.old_connections = social_workflow.CONNECTIONS_FILE
        social_workflow.JOBS_FILE = self.tmp.name + ".jobs.json"
        social_workflow.CONNECTIONS_FILE = self.tmp.name + ".connections.json"

    def tearDown(self):
        for path in (self.tmp.name, social_workflow.JOBS_FILE, social_workflow.CONNECTIONS_FILE):
            try:
                os.unlink(path)
            except OSError:
                pass
        social_workflow.JOBS_FILE = self.old_jobs
        social_workflow.CONNECTIONS_FILE = self.old_connections

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


if __name__ == "__main__":
    unittest.main()
