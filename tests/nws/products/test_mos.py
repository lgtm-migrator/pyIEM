"""Test MOS Parsing."""
# pylint: disable=redefined-outer-name

import pytest
from pyiem.nws.products.mos import parser as mosparser
from pyiem.util import get_dbconn, utc, get_test_file


@pytest.fixture
def cursor():
    """Return a database cursor."""
    return get_dbconn("mos").cursor()


def test_mex(cursor):
    """Test that we can parse the Extended GFS MEX."""
    utcnow = utc(2020, 7, 10, 12)
    prod = mosparser(get_test_file("MOS/MEXNC1.txt"), utcnow=utcnow)
    assert len(prod.data) == 4
    inserts = prod.sql(cursor)
    assert inserts == 60


def test_lev(cursor):
    """Test that we can parse the GFS LAMP (LEV stored as LAV)."""
    utcnow = utc(2020, 7, 13, 12, 30)
    prod = mosparser(get_test_file("MOS/LEVUSA.txt"), utcnow=utcnow)
    assert prod.data[0]["model"] == "LAV"
    assert max(prod.data[0]["data"].keys()) == utc(2020, 7, 15, 2)
    assert len(prod.data) == 3
    inserts = prod.sql(cursor)
    assert inserts == 39


def test_lav(cursor):
    """Test that we can parse the GFS LAMP."""
    utcnow = utc(2020, 7, 10, 12, 30)
    prod = mosparser(get_test_file("MOS/LAVUSA.txt"), utcnow=utcnow)
    assert len(prod.data) == 3
    inserts = prod.sql(cursor)
    assert inserts == 75


def test_ecmwf(cursor):
    """Test that we can parse the ECMWF MOS."""
    utcnow = utc(2020, 2, 24, 0)
    prod = mosparser(get_test_file("MOS/ECS.txt"), utcnow=utcnow)
    assert len(prod.data) == 3
    inserts = prod.sql(cursor)
    assert inserts == 63


def test_180125_empty(cursor):
    """Can we parse a MOS product with empty data"""
    utcnow = utc(2018, 1, 26, 1)
    prod = mosparser(get_test_file("MOS/MET_empty.txt"), utcnow=utcnow)
    assert len(prod.data) == 3
    assert len(prod.data[0]["data"].keys()) == 21

    inserts = prod.sql(cursor)
    assert inserts == 42


def test_parse(cursor):
    """MOS type"""
    utcnow = utc(2017, 8, 12, 12)
    prod = mosparser(get_test_file("MOS/METNC1.txt"), utcnow=utcnow)
    assert len(prod.data) == 4
    assert len(prod.data[0]["data"].keys()) == 21

    inserts = prod.sql(cursor)
    assert inserts == (4 * 21)


def test_empty_nbm(cursor):
    """Does an empty product trip us up."""
    utcnow = utc(2018, 11, 7, 17)
    prod = mosparser(get_test_file("MOS/NBSUSA_empty.txt"), utcnow=utcnow)
    assert len(prod.data) == 2

    inserts = prod.sql(cursor)
    assert inserts == 0


def test_nbm_v32(cursor):
    """Can we parse the NBM v3.2 data."""
    utcnow = utc(2020, 2, 19, 12)
    prod = mosparser(get_test_file("MOS/NBSUSA_32.txt"), utcnow=utcnow)
    assert len(prod.data) == 3
    inserts = prod.sql(cursor)
    assert inserts == 69


def test_nbm_v32_station(cursor):
    """Can we parse the NBM v3.2 data."""
    utcnow = utc(2020, 2, 19, 17)
    prod = mosparser(get_test_file("MOS/NBSUSA_32_station.txt"), utcnow=utcnow)
    assert len(prod.data) == 4
    inserts = prod.sql(cursor)
    assert inserts == 92


def test_nbm(cursor):
    """Can we parse the NBM data."""
    utcnow = utc(2018, 11, 7, 15)
    prod = mosparser(get_test_file("MOS/NBSUSA.txt"), utcnow=utcnow)
    assert len(prod.data) == 2

    inserts = prod.sql(cursor)
    assert inserts == (2 * 21)

    cursor.execute(
        """
        SELECT count(*), max(ftime) from t2018
        where model = 'NBS' and station = 'KALM' and runtime = %s
    """,
        (utcnow,),
    )
    row = cursor.fetchone()
    assert row[0] == 21
    assert row[1] == utc(2018, 11, 10, 9)
