from pathfinding_service.model.channel_view import FeeSchedule
from raiden.utils.typing import FeeAmount as FA, TokenAmount as TA


def test_basic_fee():
    flat_schedule = FeeSchedule(flat=FA(2))
    assert flat_schedule.fee(TA(10), capacity=TA(0)) == FA(2)

    prop_schedule = FeeSchedule(proportional=0.01)
    assert prop_schedule.fee(TA(40), capacity=TA(0)) == FA(0)
    assert prop_schedule.fee(TA(60), capacity=TA(0)) == FA(1)
    assert prop_schedule.fee(TA(1000), capacity=TA(0)) == FA(10)

    combined_schedule = FeeSchedule(flat=FA(2), proportional=0.01)
    assert combined_schedule.fee(TA(60), capacity=TA(0)) == FA(3)


def test_imbalance_penalty():
    v_schedule = FeeSchedule(
        imbalance_penalty=[[TA(0), TA(10)], [TA(50), TA(0)], [TA(100), TA(10)]]
    )
    assert v_schedule.fee(capacity=TA(0), amount=TA(50)) == FA(-10)
    assert v_schedule.fee(capacity=TA(50), amount=TA(50)) == FA(10)
    assert v_schedule.fee(capacity=TA(0), amount=TA(10)) == FA(-2)
    assert v_schedule.fee(capacity=TA(10), amount=TA(10)) == FA(-2)
    assert v_schedule.fee(capacity=TA(0), amount=TA(20)) == FA(-4)
    assert v_schedule.fee(capacity=TA(40), amount=TA(20)) == FA(0)
