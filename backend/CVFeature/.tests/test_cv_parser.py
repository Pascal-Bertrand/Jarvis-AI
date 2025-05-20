
import unittest
from src.cv_parser.parser import CVParser

class TestCVParser(unittest.TestCase):

    def setUp(self):
        self.parser = CVParser()

    def test_parse_cv_valid(self):
        # Assuming we have a valid CV file for testing
        cv_file_path = 'path/to/valid_cv.pdf'
        summary = self.parser.parse(cv_file_path)
        self.assertIn('age', summary)
        self.assertIn('gender', summary)
        self.assertIn('work_experience', summary)
        self.assertIn('current_projects', summary)
        self.assertIn('company_resort', summary)

    def test_parse_cv_invalid(self):
        # Test with an invalid CV file
        cv_file_path = 'path/to/invalid_cv.pdf'
        with self.assertRaises(ValueError):
            self.parser.parse(cv_file_path)

    def test_parse_cv_empty(self):
        # Test with an empty CV file
        cv_file_path = 'path/to/empty_cv.pdf'
        summary = self.parser.parse(cv_file_path)
        self.assertEqual(summary, {})

if __name__ == '__main__':
    unittest.main()