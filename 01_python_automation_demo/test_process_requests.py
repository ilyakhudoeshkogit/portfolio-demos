import unittest
from process_requests import validate, classify

def row(**kw):
    base = dict(id="1", date="2026-10-20", department="Склад", requester="Иванов И.",
                email="a@b.by", item="Х", qty="2", unit_price="10", priority="normal")
    base.update(kw)
    return base

class T(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(validate(row()), [])
    def test_bad_email(self):
        self.assertIn("некорректный e-mail", validate(row(email="a-at-b.by")))
    def test_negative_qty(self):
        self.assertTrue(validate(row(qty="-4")))
    def test_zero_price(self):
        self.assertTrue(validate(row(unit_price="0")))
    def test_bad_date(self):
        self.assertTrue(validate(row(date="24.10.2026")))
    def test_threshold(self):
        r = classify([row(qty="1", unit_price="600")], 500)[0]
        self.assertEqual(r["status"], "НА_СОГЛАСОВАНИЕ")
        r = classify([row(qty="1", unit_price="500")], 500)[0]
        self.assertEqual(r["status"], "АВТООДОБРЕНА")
    def test_duplicate(self):
        res = classify([row(id="1"), row(id="2")], 500)
        self.assertEqual([r["status"] for r in res], ["АВТООДОБРЕНА", "ДУБЛЬ"])

if __name__ == "__main__":
    unittest.main()
