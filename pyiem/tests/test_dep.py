"""Test DEP"""
from __future__ import print_function
import os
import datetime

from pyiem import dep


def get_path(name):
    """helper"""
    basedir = os.path.dirname(__file__)
    return "%s/../../data/wepp/%s" % (basedir, name)


def test_cli_fname():
    """Do we get the right climate file names?"""
    res = dep.get_cli_fname(-95.5, 42.5, 0)
    assert res == "/i/0/cli/095x042/095.50x042.50.cli"


def test_yld():
    """Read a slope file"""
    df = dep.read_yld(get_path('yld.txt'))
    assert len(df.index) == 10
    assert abs(df['yield_kgm2'].max() - 0.93) < 0.01


def test_slp():
    """Read a slope file"""
    slp = dep.read_slp(get_path('slp.txt'))
    assert len(slp) == 5
    assert abs(slp[4]['y'][-1] + 8.3) < 0.1


def test_man():
    """Read a management file please"""
    manfile = dep.read_man(get_path('man.txt'))
    assert manfile['nop'] == 5
    assert manfile['nini'] == 2
    assert manfile['nsurf'] == 2
    assert manfile['nwsofe'] == 3
    assert manfile['nrots'] == 1
    assert manfile['nyears'] == 11

    manfile = dep.read_man(get_path('man2.txt'))
    assert manfile['nop'] == 0


def test_ofe():
    """Read an OFE please"""
    df = dep.read_ofe(get_path('ofe.txt'))
    assert abs(df['precip'].max() - 107.56) < 0.01

    df = dep.read_ofe(get_path('ofe2.txt'))
    print(df['sedleave'].sum())
    assert abs(df['sedleave'].sum() - 400257.48) < 0.01


def test_wb():
    """read a WB file please"""
    df = dep.read_wb(get_path('wb.txt'))
    assert abs(df['precip'].max() - 162.04) < 0.01


def test_cli():
    """read a CLI file please"""
    df = dep.read_cli(get_path('cli.txt'))
    assert len(df.index) == 4018


def test_empty():
    """don't error out on an empty ENV"""
    df = dep.read_env(get_path('empty_env.txt'))
    assert df.empty


def test_read():
    """Read a ENV file"""
    df = dep.read_env(get_path('good_env.txt'))
    df2 = df[df['date'] == datetime.datetime(2010, 6, 5)]
    assert len(df2.index) == 1
    row = df2.iloc[0]
    assert row['runoff'] == 86.3


def do_timing():
    """Hack to do timing"""
    sts = datetime.datetime.now()
    dep.read_env(get_path('good_env.txt'))
    ets = datetime.datetime.now()
    print("%.5f reads per second" % (1. / (ets - sts).total_seconds(),))
    # assert 1 == 2
