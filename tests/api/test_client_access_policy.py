import unittest

from auth.access_policy import can_access_client_record


class ClientAccessPolicyTests(unittest.TestCase):
    def test_operator_can_access_client_session(self):
        self.assertTrue(
            can_access_client_record(
                requesting_role="operator",
                requesting_user_id="OPERATOR_1",
                client_id="CLIENT_1",
            )
        )

    def test_researcher_can_access_client_session(self):
        self.assertTrue(
            can_access_client_record(
                requesting_role="researcher",
                requesting_user_id="RESEARCHER_1",
                client_id="CLIENT_1",
            )
        )

    def test_viewer_can_only_access_own_session(self):
        self.assertTrue(
            can_access_client_record(
                requesting_role="viewer",
                requesting_user_id="CLIENT_1",
                client_id="CLIENT_1",
            )
        )
        self.assertFalse(
            can_access_client_record(
                requesting_role="viewer",
                requesting_user_id="CLIENT_2",
                client_id="CLIENT_1",
            )
        )


if __name__ == "__main__":
    unittest.main()
