import unittest
from datetime import timezone
from app.domain import interval, overlaps, validate_resource
from app.security import issue, verify


class DomainTests(unittest.TestCase):
    def test_timezone_normalized(self):
        a,b=interval('2026-11-01T10:00:00+03:00','2026-11-01T11:00:00+03:00')
        self.assertEqual(a.hour,7)
        self.assertEqual(a.tzinfo,timezone.utc)

    def test_rejects_naive_or_invalid_intervals(self):
        for a,b in [('2026-11-01T10:00:00','2026-11-01T11:00:00'),
                    ('2026-11-01T10:00:00Z','2026-11-01T10:00:00Z'),
                    ('2026-11-01T10:00:00Z','2026-11-01T09:00:00Z'),
                    ('2026-11-01T10:00:00Z','2026-11-01T19:00:00Z')]:
            with self.subTest(a=a,b=b),self.assertRaises(ValueError): interval(a,b)

    def test_adjacent_allowed_and_overlap_detected(self):
        self.assertFalse(overlaps(1,2,2,3))
        self.assertTrue(overlaps(1,3,2,4))
        self.assertTrue(overlaps(1,5,2,3))

    def test_room_capacity_required(self):
        for capacity in [None,0,-1,True]:
            with self.subTest(capacity=capacity),self.assertRaises(ValueError):
                validate_resource('rooms',{'name':'101','capacity':capacity})
        validate_resource('rooms',{'name':'101','capacity':20})

    def test_equipment_no_capacity(self):
        validate_resource('equipment',{'name':'Projector'})

    def test_resource_name(self):
        for name in ['', ' ', 'x'*201]:
            with self.assertRaises(ValueError): validate_resource('equipment',{'name':name})

    def test_token_round_trip(self):
        token=issue('alice','student',key='test-key',now=100)
        self.assertEqual(verify(token,key='test-key',now=101)['sub'],'alice')

    def test_token_tamper(self):
        token=issue('alice','student',key='test-key',now=100)
        with self.assertRaises(ValueError): verify(token+'x',key='test-key',now=101)
        with self.assertRaises(ValueError): verify(token,key='other-key',now=101)

    def test_token_expired(self):
        token=issue('alice','student',key='test-key',now=100)
        with self.assertRaises(ValueError): verify(token,key='test-key',now=3700)

    def test_malformed_token(self):
        for token in ['', '.', 'abc', 'a.b.c']:
            with self.subTest(token=token),self.assertRaises(ValueError): verify(token,key='key')

if __name__=='__main__': unittest.main()
