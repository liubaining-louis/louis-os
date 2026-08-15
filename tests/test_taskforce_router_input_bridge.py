import unittest

from scripts.taskforce_router_input_bridge import bridge


class TaskForceRouterInputBridgeTest(unittest.TestCase):
    def test_adds_taskforce_opportunity_once(self):
        taskforce = {
            "tasks_seen": 2,
            "qualified_count": 1,
            "applications_attempted": 1,
            "accepted_notifications": [],
            "opportunities": [
                {
                    "opportunity_id": "taskforce:t1",
                    "title": "Python API automation",
                    "source_url": "https://www.task-force.app/tasks/t1",
                    "reward_amount": 20,
                }
            ],
        }
        universal = {"opportunities": [{"opportunity_id": "existing", "title": "Existing"}]}
        merged = bridge(taskforce, universal)
        self.assertEqual(len(merged["opportunities"]), 2)
        self.assertEqual(merged["opportunities"][1]["source_id"], "taskforce")
        self.assertTrue(merged["opportunities"][1]["fresh_open_verified"])
        self.assertEqual(merged["taskforce_bridge"]["opportunities_added"], 1)

        merged_again = bridge(taskforce, merged)
        self.assertEqual(len(merged_again["opportunities"]), 2)
        self.assertEqual(merged_again["taskforce_bridge"]["opportunities_added"], 0)

    def test_empty_feed_is_noop(self):
        universal = {"opportunities": [{"opportunity_id": "existing", "title": "Existing"}]}
        merged = bridge({}, universal)
        self.assertEqual(merged["opportunities"], universal["opportunities"])
        self.assertEqual(merged["taskforce_bridge"]["opportunities_added"], 0)


if __name__ == "__main__":
    unittest.main()
