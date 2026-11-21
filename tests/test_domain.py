from decimal import Decimal
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate


def test_reroutes_greedy(cases):
    # TRAP-109
    actual, proof = evaluate(cases['reroutes_greedy'])
    assert actual == Decimal('4')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['乙>丙'])) == Decimal('1')


def test_limited_road(cases):
    actual, proof = evaluate(cases['limited_road'])
    assert actual == Decimal('6')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['未满足'])) == Decimal('3')


def test_through_hub(cases):
    actual, proof = evaluate(cases['through_hub'])
    assert actual == Decimal('10')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['调配完成'])) == Decimal('2')


def test_no_route(cases):
    actual, proof = evaluate(cases['no_route'])
    assert actual == Decimal('0')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['未满足'])) == Decimal('2')


def test_more_supply(cases):
    actual, proof = evaluate(cases['more_supply'])
    assert actual == Decimal('1.5')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['未满足'])) == Decimal('0')


def test_capacity_spill(cases):
    actual, proof = evaluate(cases['capacity_spill'])
    assert actual == Decimal('16')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['B>D'])) == Decimal('1')


def test_unknown_station(cases):
    # TRAP-110
    with pytest.raises(DataError) as error:
        evaluate(cases['unknown_station'])
    assert error.value.code == 'CYCLE_ROAD'


def test_station_duplicate(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['station_duplicate'])
    assert error.value.code == 'CYCLE_STATION'


def test_road_duplicate(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['road_duplicate'])
    assert error.value.code == 'CYCLE_ROAD'
