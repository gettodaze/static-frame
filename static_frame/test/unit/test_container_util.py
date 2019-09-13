import unittest

import numpy as np  # type: ignore


from static_frame.core.container_util import index_from_optional_constructor
from static_frame.core.container_util import matmul

from static_frame import Series
from static_frame import Frame

from static_frame import Index
from static_frame import IndexGO
# from static_frame import IndexDate
# from static_frame import IndexHierarchy
# from static_frame import IndexYearMonth
# from static_frame import IndexYear
from static_frame import IndexSecond
# from static_frame import IndexMillisecond

from static_frame.test.test_case import TestCase



class TestUnit(TestCase):


    def test_index_from_optional_constructor_a(self) -> None:
        idx1 = index_from_optional_constructor([1, 3, 4],
                default_constructor=Index)
        self.assertEqual(idx1.__class__, Index)

        # given a mutable index and an immutable default, get immutable version
        idx2 = index_from_optional_constructor(IndexGO((1, 3, 4)),
                default_constructor=Index)
        self.assertEqual(idx2.__class__, Index)

        # given a mutable index and an immutable default, get immutable version
        idx3 = index_from_optional_constructor(IndexGO((1, 3, 4)),
                default_constructor=IndexGO)
        self.assertEqual(idx3.__class__, IndexGO)

        # given a mutable index and an immutable default, get immutable version
        idx4 = index_from_optional_constructor(
                IndexSecond((1, 3, 4)),
                default_constructor=Index)
        self.assertEqual(idx4.__class__, IndexSecond)


    def test_matmul_a(self) -> None:
        # lhs: frame, rhs: array

        f1 = Frame.from_items((('a', (1, 2, 3)), ('b', (3, 4, 5))),
                index=('x', 'y', 'z'))

        self.assertEqual(
                matmul(f1, [4, 3]).to_pairs(),
                (('x', 13), ('y', 20), ('z', 27))
                )

        self.assertEqual(
                matmul(f1, np.array([4, 3])).to_pairs(),
                (('x', 13), ('y', 20), ('z', 27))
                )


        self.assertEqual(
                matmul(f1, [3, 4]).to_pairs(),
                (('x', 15), ('y', 22), ('z', 29))
                )

        self.assertEqual(
                matmul(f1, np.array([3, 4])).to_pairs(),
                (('x', 15), ('y', 22), ('z', 29))
                )


    def test_matmul_b(self) -> None:
        # lhs: frame, rhs: array

        f1 = Frame.from_items((('a', (1, 2, 3)), ('b', (3, 4, 5))),
                index=('x', 'y', 'z'))

        # get an auto incremented integer columns
        self.assertEqual(
            matmul(f1, np.arange(10).reshape(2, 5)).to_pairs(0),
            ((0, (('x', 15), ('y', 20), ('z', 25))), (1, (('x', 19), ('y', 26), ('z', 33))), (2, (('x', 23), ('y', 32), ('z', 41))), (3, (('x', 27), ('y', 38), ('z', 49))), (4, (('x', 31), ('y', 44), ('z', 57))))
            )

    def test_matmul_c(self) -> None:
        # lhs: frame, rhs: Series, 1D array

        f1 = Frame.from_items((('a', (1, 2, 3)), ('b', (3, 4, 5))),
                index=('x', 'y', 'z'))
        s1 = Series((10, 11), index=('a', 'b'))

        self.assertEqual(matmul(f1, s1).to_pairs(),
                (('x', 43), ('y', 64), ('z', 85)))

        self.assertEqual(matmul(f1, s1.values).to_pairs(),
                (('x', 43), ('y', 64), ('z', 85)))



    def test_matmul_d(self) -> None:
        # lhs: series, rhs: frame

        f1 = Frame.from_items((('a', (1, 2, 3)), ('b', (3, 4, 5))),
                index=('x', 'y', 'z'))

        s1 = Series((3, 4, 2), index=('x', 'y', 'z'))

        self.assertEqual(
            matmul(s1, f1).to_pairs(),
            (('a', 17), ('b', 35))
            )

        # produces a Series indexed 0, 1
        self.assertEqual(matmul(s1, f1.values).to_pairs(),
            ((0, 17), (1, 35)))

    def test_matmul_e(self) -> None:
        # lhs: series, rhs: series

        s1 = Series((3, 4, 2), index=('x', 'y', 'z'))

        s2 = Series((10, 11, 12), index=('x', 'y', 'z'))

        self.assertEqual(matmul(s1, s2), 98)
        self.assertEqual(matmul(s1, s2.values), 98)


    def test_matmul_f(self) -> None:
        # lhs: array 1D, rhs: array 2D, Frame

        f1 = Frame.from_items((('a', (1, 2, 3)), ('b', (3, 4, 5))),
                index=('x', 'y', 'z'))

        self.assertEqual(matmul([3, 4, 5], f1.values).tolist(),
                [26, 50])

        self.assertEqual(matmul([3, 4, 5], f1).to_pairs(),
                (('a', 26), ('b', 50))
                )


    def test_matmul_g(self) -> None:
        # lhs: array 1D, rhs: array 1D, Series

        s1 = Series((3, 4, 2), index=('x', 'y', 'z'))
        self.assertEqual(matmul([10, 11, 12], s1.values), 98)
        self.assertEqual(matmul([10, 11, 12], s1), 98)


    def test_matmul_h(self) -> None:
        # lhs: array 2D, rhs: array 2D, Frame

        f1 = Frame.from_dict(dict(a=(1, 2, 3, 4), b=(5, 6, 7, 8)), index=tuple('wxyz'))
        f2 = Frame.from_dict(dict(p=(1, 2), q=(3, 4), r=(5, 6)), index=tuple('ab'))


        self.assertEqual(matmul(f1.values, f2).to_pairs(0),
                (('p', ((0, 11), (1, 14), (2, 17), (3, 20))), ('q', ((0, 23), (1, 30), (2, 37), (3, 44))), ('r', ((0, 35), (1, 46), (2, 57), (3, 68))))
                )

        self.assertEqual(matmul(f1, f2.values).to_pairs(0),
                ((0, (('w', 11), ('x', 14), ('y', 17), ('z', 20))), (1, (('w', 23), ('x', 30), ('y', 37), ('z', 44))), (2, (('w', 35), ('x', 46), ('y', 57), ('z', 68))))
                )



    def test_matmul_i(self) -> None:
        import itertools as it

        f1 = Frame.from_dict(dict(a=(1, 2), b=(5, 6)), index=tuple('yz'))

        f_container = lambda x: x
        f_values = lambda x: x.values

        for pair in ((f1, f1.T), (f1, f1.loc['y']), (f1['a'], f1), (f1.loc['y'], f1.loc['z'])):
            for x, y in it.combinations((f_container, f_values, f_container, f_values), 2):
                post = matmul(x(pair[0]), y(pair[1])) # type: ignore
                if isinstance(post, (Series, Frame)):
                    self.assertTrue(post.values.tolist(), (pair[0].values @ pair[1].values).tolist())
                elif isinstance(post, np.ndarray):
                    self.assertTrue(post.tolist(), (pair[0].values @ pair[1].values).tolist())


if __name__ == '__main__':
    unittest.main()