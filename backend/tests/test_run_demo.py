"""The terminal demo refuses a budget the intake form would refuse."""
import argparse

import pytest

import run_demo


def test_the_budget_must_be_above_zero():
    assert run_demo.positive_amount("250000") == 250000
    for bad in ("0", "-5", "nan", "lots"):
        with pytest.raises(argparse.ArgumentTypeError):
            run_demo.positive_amount(bad)
