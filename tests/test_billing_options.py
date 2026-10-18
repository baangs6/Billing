import pytest
from billing_options import due_date, manual_rounding


def test_dates_and_signed_rounding():
    assert due_date('2026-10-02', '', 30) == '2026-11-01'
    assert due_date('2026-10-02', '2026-12-01', 30) == '2026-12-01'
    assert manual_rounding('-0.49') == -49
    assert manual_rounding('1.00') == 100
    for value in ['NaN','Infinity','-1.01','0.001','junk']:
        with pytest.raises(ValueError): manual_rounding(value)
    with pytest.raises(ValueError): due_date('2026-10-02','2026-10-01')
