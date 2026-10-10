import unittest
from pathlib import Path

import server.loan.loan as loan

FIXTURE = Path(__file__).parent / "fixtures" / "loan_example.json"


class LoanTest(unittest.TestCase):
    def test_loan_total(self):
        ljp = loan.LoanJsonParser(json_path=FIXTURE)
        self.assertEqual(ljp.principal_paid(), 225)
