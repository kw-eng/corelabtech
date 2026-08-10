import unittest

from services.llm_observability import response_usage


class LlmObservabilityTests(unittest.TestCase):
    def test_extracts_usage_from_response_objects_and_dicts(self):
        self.assertEqual(
            response_usage({"usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}}),
            {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
        )
        self.assertEqual(
            response_usage({"usage": {"prompt_tokens": 3, "completion_tokens": 2}}),
            {"input_tokens": 3, "output_tokens": 2, "total_tokens": None},
        )


if __name__ == "__main__":
    unittest.main()
