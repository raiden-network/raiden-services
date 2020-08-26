from raiden_libs import metrics


class TestEnum(metrics.MetricsEnum):
    FOO = "foo"
    BAR = "bar"


def test_metrics_enum():

    # check the str conversion
    assert str(TestEnum.FOO) == "foo"
    assert str(TestEnum.BAR) == "bar"

    # check the camelcase to snakecase conversion for the class name
    assert TestEnum.label_name() == "test_enum"

    # check label dict conversion
    assert TestEnum.FOO.to_label_dict() == {"test_enum": "foo"}  # type: ignore
    assert TestEnum.BAR.to_label_dict() == {"test_enum": "bar"}  # type: ignore
