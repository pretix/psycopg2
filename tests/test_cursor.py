#!/usr/bin/env python

# test_cursor.py - unit test for cursor attributes
#
# Copyright (C) 2010-2011 Daniele Varrazzo  <daniele.varrazzo@gmail.com>
#
# psycopg2 is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# In addition, as a special exception, the copyright holders give
# permission to link this program with the OpenSSL library (or with
# modified versions of OpenSSL that use the same license as OpenSSL),
# and distribute linked combinations including the two.
#
# You must obey the GNU Lesser General Public License in all respects for
# all of the code used other than OpenSSL.
#
# psycopg2 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public
# License for more details.

import time
import psycopg2
import psycopg2.extensions
from psycopg2.extensions import b
from testconfig import dsn
from testutils import unittest, skip_before_postgres

class CursorTests(unittest.TestCase):

    def setUp(self):
        self.conn = psycopg2.connect(dsn)

    def tearDown(self):
        self.conn.close()

    def test_executemany_propagate_exceptions(self):
        conn = self.conn
        cur = conn.cursor()
        cur.execute("create temp table test_exc (data int);")
        def buggygen():
            yield 1//0
        self.assertRaises(ZeroDivisionError,
            cur.executemany, "insert into test_exc values (%s)", buggygen())
        cur.close()

    def test_mogrify_unicode(self):
        conn = self.conn
        cur = conn.cursor()

        # test consistency between execute and mogrify.

        # unicode query containing only ascii data
        cur.execute(u"SELECT 'foo';")
        self.assertEqual('foo', cur.fetchone()[0])
        self.assertEqual(b("SELECT 'foo';"), cur.mogrify(u"SELECT 'foo';"))

        conn.set_client_encoding('UTF8')
        snowman = u"\u2603"

        # unicode query with non-ascii data
        cur.execute(u"SELECT '%s';" % snowman)
        self.assertEqual(snowman.encode('utf8'), b(cur.fetchone()[0]))
        self.assertEqual(("SELECT '%s';" % snowman).encode('utf8'),
            cur.mogrify(u"SELECT '%s';" % snowman).replace(b("E'"), b("'")))

        # unicode args
        cur.execute("SELECT %s;", (snowman,))
        self.assertEqual(snowman.encode("utf-8"), b(cur.fetchone()[0]))
        self.assertEqual(("SELECT '%s';" % snowman).encode('utf8'),
            cur.mogrify("SELECT %s;", (snowman,)).replace(b("E'"), b("'")))

        # unicode query and args
        cur.execute(u"SELECT %s;", (snowman,))
        self.assertEqual(snowman.encode("utf-8"), b(cur.fetchone()[0]))
        self.assertEqual(("SELECT '%s';" % snowman).encode('utf8'),
            cur.mogrify(u"SELECT %s;", (snowman,)).replace(b("E'"), b("'")))

    def test_mogrify_decimal_explodes(self):
        # issue #7: explodes on windows with python 2.5 and psycopg 2.2.2
        try:
            from decimal import Decimal
        except:
            return

        conn = self.conn
        cur = conn.cursor()
        self.assertEqual(b('SELECT 10.3;'),
            cur.mogrify("SELECT %s;", (Decimal("10.3"),)))

    def test_cast(self):
        curs = self.conn.cursor()

        self.assertEqual(42, curs.cast(20, '42'))
        self.assertAlmostEqual(3.14, curs.cast(700, '3.14'))

        try:
            from decimal import Decimal
        except ImportError:
            self.assertAlmostEqual(123.45, curs.cast(1700, '123.45'))
        else:
            self.assertEqual(Decimal('123.45'), curs.cast(1700, '123.45'))

        from datetime import date
        self.assertEqual(date(2011,1,2), curs.cast(1082, '2011-01-02'))
        self.assertEqual("who am i?", curs.cast(705, 'who am i?'))  # unknown

    def test_cast_specificity(self):
        curs = self.conn.cursor()
        self.assertEqual("foo", curs.cast(705, 'foo'))

        D = psycopg2.extensions.new_type((705,), "DOUBLING", lambda v, c: v * 2)
        psycopg2.extensions.register_type(D, self.conn)
        self.assertEqual("foofoo", curs.cast(705, 'foo'))

        T = psycopg2.extensions.new_type((705,), "TREBLING", lambda v, c: v * 3)
        psycopg2.extensions.register_type(T, curs)
        self.assertEqual("foofoofoo", curs.cast(705, 'foo'))

        curs2 = self.conn.cursor()
        self.assertEqual("foofoo", curs2.cast(705, 'foo'))

    def test_weakref(self):
        from weakref import ref
        curs = self.conn.cursor()
        w = ref(curs)
        del curs
        self.assert_(w() is None)

    @skip_before_postgres(8, 2)
    def test_iter_named_cursor_efficient(self):
        curs = self.conn.cursor('tmp')
        # if these records are fetched in the same roundtrip their
        # timestamp will not be influenced by the pause in Python world.
        curs.execute("""select clock_timestamp() from generate_series(1,2)""")
        i = iter(curs)
        t1 = (i.next())[0]  # the brackets work around a 2to3 bug
        time.sleep(0.2)
        t2 = (i.next())[0]
        self.assert_((t2 - t1).microseconds * 1e-6 < 0.1,
            "named cursor records fetched in 2 roundtrips (delta: %s)"
            % (t2 - t1))

    @skip_before_postgres(8, 0)
    def test_iter_named_cursor_default_itersize(self):
        curs = self.conn.cursor('tmp')
        curs.execute('select generate_series(1,50)')
        rv = [ (r[0], curs.rownumber) for r in curs ]
        # everything swallowed in one gulp
        self.assertEqual(rv, [(i,i) for i in range(1,51)])

    @skip_before_postgres(8, 0)
    def test_iter_named_cursor_itersize(self):
        curs = self.conn.cursor('tmp')
        curs.itersize = 30
        curs.execute('select generate_series(1,50)')
        rv = [ (r[0], curs.rownumber) for r in curs ]
        # everything swallowed in two gulps
        self.assertEqual(rv, [(i,((i - 1) % 30) + 1) for i in range(1,51)])


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == "__main__":
    unittest.main()
