# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Native API initializer dispatch, with explicit synthetic child returns.

These controls test the native order/error gates only. They neither initialize
the real subsystems nor supply successful returns in the connected boot model.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from penf_probe import ProbeState, CALLER


GATED = (0x602ee808, 0x60314acb, 0x60312c71, 0x6031077e,
         0x602efdbd, 0x602f0161, 0x602f158e, 0x60304b91,
         0x60314f88, 0x602ed49c, 0x60312370, 0x602df1fd,
         0x602ef76f, 0x602f4b2a)
SUFFIX = (0x602ec705, 0x6031168f, 0x602ef7fc)


def dispatch(child_returns):
    state = ProbeState(0x602dc671, 0x80, 12, bytes(16), {})
    seen = []
    hooks = set(GATED+SUFFIX) | {CALLER+7}
    for _ in range(len(hooks)):
        result = state.run(hooks, limit=1000)
        if result['status'] != 'breakpoint':
            raise AssertionError(result)
        pc = state.regs['pc']
        if pc == CALLER+7:
            return state, seen
        seen.append(pc)
        state.return_from_model(child_returns.get(pc, 0))
    raise AssertionError('Dispatcher did not return within bounded call count')


class ApiInitializerTests(unittest.TestCase):
    def test_success_order_and_each_individual_failure_gate(self):
        for failed in (None, *GATED):
            with self.subTest(failed=None if failed is None else hex(failed)):
                state, seen = dispatch({} if failed is None else {failed: 0x8123})
                count = len(GATED) if failed is None else GATED.index(failed)+1
                self.assertEqual(seen, list(GATED[:count]+SUFFIX))
                self.assertEqual(state.regs['d0'], 0 if failed is None else 0x8123)
                self.assertEqual(state.regs['sp'], 0x18018000)

    def test_error_is_halfword_and_suffix_returns_do_not_replace_it(self):
        state, seen = dispatch({GATED[0]: 0x10000, **dict.fromkeys(SUFFIX, 0x8123)})
        self.assertEqual(seen, list(GATED+SUFFIX))
        self.assertEqual(state.regs['d0'], 0)
        state, seen = dispatch({GATED[0]: 0x18023, **dict.fromkeys(SUFFIX, 0)})
        self.assertEqual(seen, [GATED[0], *SUFFIX])
        self.assertEqual(state.regs['d0'], 0x8023)


if __name__ == '__main__':
    unittest.main()
