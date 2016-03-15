"""util script to call `windrose` package"""
import datetime
import numpy as np
import psycopg2
import os
from pyiem.datatypes import speed
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt  # nopep8
import matplotlib.image as mpimage  # nopep8
from windrose import WindroseAxes  # nopep8
from windrose.windrose import histogram  # nopep8
DATADIR = os.sep.join([os.path.dirname(__file__), 'data'])

WINDUNITS = {
    'mph': {'label': 'miles per hour', 'dbmul': 1.15,
            'bins': (0, 2, 5, 7, 10, 15, 20), 'abbr': 'mph',
            'binlbl': ('2-5', '5-7', '7-10', '10-15', '15-20', '20+')},
    'kts': {'label': 'knots', 'dbmul': 1.0,
            'bins': (0, 2, 5, 7, 10, 15, 20), 'abbr': 'kts',
            'binlbl': ('2-5', '5-7', '7-10', '10-15', '15-20', '20+')},
    'mps': {'label': 'meters per second', 'dbmul': 0.5144,
            'bins': (0, 2, 4, 6, 8, 10, 12), 'abbr': 'm s$^{-1}$',
            'binlbl': ('2-4', '4-6', '6-8', '8-10', '10-12', '12+')},
    'kph': {'label': 'kilometers per hour', 'dbmul': 1.609,
            'bins': (0, 4, 10, 14, 20, 30, 40), 'abbr': '$km h^{-1}$',
            'binlbl': ('4-10', '10-14', '14-20', '20-30', '30-40', '40+')},
}
RAOB_WINDUNITS = {
    'mph': {'label': 'miles per hour', 'dbmul': 1.15,
            'bins': (0, 5, 25, 50, 75, 100, 150), 'abbr': 'mph',
            'binlbl': ('5-25', '25-50', '50-75', '75-100', '100-150', '150+')},
    'kts': {'label': 'knots', 'dbmul': 1.0,
            'bins': (0, 5, 25, 50, 75, 100, 15), 'abbr': 'kts',
            'binlbl': ('5-25', '25-50', '50-75', '75-100', '100-150', '150+')},
    'mps': {'label': 'meters per second', 'dbmul': 0.5144,
            'bins': (0, 5, 10, 15, 25, 50, 75), 'abbr': 'm s$^{-1}$',
            'binlbl': ('5-10', '10-15', '15-25', '25-50', '50-75', '75+')},
    'kph': {'label': 'kilometers per hour', 'dbmul': 1.609,
            'bins': (0, 4, 10, 14, 20, 30, 40), 'abbr': '$km h^{-1}$',
            'binlbl': ('4-10', '10-14', '14-20', '20-30', '30-40', '40+')},
}


def _get_timeinfo(arr, datepart, fullsize):
    """Convert the months/hours array provided into label text and SQL

    Args:
      arr (list): A list of ints
      datepart (str): the part to extract from the database timestamp
      fullsize (int): the size of specifying all dates

    Returns:
      dict with keys `sqltext` and `labeltext`
    """
    sql = ""
    lbl = "All included"
    if len(arr) == 1:
        sql = " and extract(%s from valid) = %s " % (datepart, arr[0])
        lbl = str(tuple(arr))
    elif len(arr) < fullsize:
        sql = (" and extract(%s from valid) in %s "
               ) % (datepart, (str(tuple(arr))).replace("'", ""),)
        lbl = str(tuple(arr))
    return dict(sqltext=sql, labeltext=lbl)


def _get_data(station, cursor, database, sts, ets, monthinfo, hourinfo,
              level):
    """Helper function to get data out of IEM databases

    Args:
      station (str): the station identifier
      cursor (psycopg2): database cursor to use
      database (str): the name of the database to connect to, we assume we can
        then query a table called `alldata`
      sts (datetime): the floor to query data for
      ets (datetime): the ceiling to query data for
      monthinfo (dict): information on how to query for months
      hourinfo (dict): information on how to query for hours
      level (int, optional): in case of RAOB, which pressure level (hPa)

    Returns:
      numpy.array wind speed in knots
      numpy.array wind direction
      datetime of earliest ob
      datetime of latest ob
    """
    # Query observations
    if cursor is None:
        db = psycopg2.connect(database=database, host='iemdb', user='nobody')
        acursor = db.cursor()
    else:
        acursor = cursor
    sql = """SELECT sknt, drct, valid from alldata WHERE station = '%s'
        and valid > '%s' and valid < '%s'
        %s
        %s """ % (station, sts, ets, monthinfo['sqltext'], hourinfo['sqltext'])
    if level is not None:  # HACK!
        acursor.execute("""SET TIME ZONE 'UTC'""")
        sql = """SELECT p.smps * 1.94384, p.drct, f.valid from
        raob_flights f JOIN raob_profile p on (f.fid = p.fid) WHERE
        f.station = '%s' and p.pressure = %s and p.smps is not null
        and p.drct is not null and valid >= '%s' and valid < '%s'
        %s
        %s
        """ % (station, level, sts, ets, monthinfo['sqltext'],
               hourinfo['sqltext'])
        # sys.stderr.write(sql.replace("\n", " "))
    acursor.execute(sql)
    sped = np.zeros((acursor.rowcount,), 'f')
    drct = np.zeros((acursor.rowcount,), 'f')
    minvalid = sts
    maxvalid = ets
    i = 0
    for row in acursor:
        # if row[2].month not in months or row[2].hour not in hours:
        #    continue
        if i == 0:
            minvalid = row[2]
            maxvalid = row[2]
        if row[2] < minvalid:
            minvalid = row[2]
        if row[2] > maxvalid:
            maxvalid = row[2]
        if row[0] is None or row[0] < 3 or row[1] is None or row[1] < 0:
            sped[i] = 0
            drct[i] = 0
        elif row[0] == 0 or row[1] == 0:
            sped[i] = 0
            drct[i] = 0
        else:
            sped[i] = row[0]
            drct[i] = row[1]
        i += 1

    return sped, drct, minvalid, maxvalid


def _make_textresult(station, sknt, drct, units, nsector, sname, minvalid,
                     maxvalid, monthinfo, hourinfo, level):
    """Generate a text table of windrose information

    Args:
      station (str): the station identifier
      sknt (list): The wind speed values
      drct (list): the wind direction values
      units (str): the units of the `sknt` values
      nsector (int): number of sectors to divide rose into
      sname (str): the station name
      minvalid (datetime): the minimum observation time
      maxvalid (datetime): the maximum observation time
      monthinfo (dict): information on month limiting
      hourinfo (dict): information on hour limiting
      level (int): in case of RAOB, which level do we care for

    Returns:
      str of information"""
    wu = WINDUNITS[units] if level is None else RAOB_WINDUNITS[units]
    dir_edges, var_bins, table = histogram(drct, sknt,
                                           np.asarray(
                                            wu['bins']),
                                           nsector, normed=True)
    res = ("# Windrose Data Table (Percent Frequency) "
           "for %s (%s)\n"
           ) % (
        sname if sname is not None else "((%s))" % (station, ), station)
    res += "# Observation Count: %s\n" % (len(sknt),)
    res += ("# Period: %s - %s\n"
            ) % (minvalid.strftime("%-d %b %Y"),
                 maxvalid.strftime("%-d %b %Y"))
    res += "# Hour Limiter: %s\n" % (hourinfo['labeltext'],)
    res += "# Month Limiter: %s\n" % (monthinfo['labeltext'],)
    res += "# Wind Speed Units: %s\n" % (wu['label'],)
    if level is not None:
        res += "# RAOB Pressure (hPa) Level: %s\n" % (level,)
    res += ("# Generated %s UTC, contact: akrherz@iastate.edu\n"
            ) % (datetime.datetime.utcnow().strftime("%d %b %Y %H:%M"),)
    res += "# First value in table is CALM\n"
    res += "       ,"
    for j in range(len(var_bins)-1):
        res += " %4.1f-%4.1f," % (var_bins[j],
                                  var_bins[j+1]-0.1)
    res += "\n"
    dir_edges2 = np.concatenate((np.array(dir_edges),
                                 [dir_edges[-1] +
                                  (dir_edges[-1] - dir_edges[-2]), ]))
    for i in range(len(dir_edges2)-1):
        res += "%03i-%03i," % (dir_edges2[i], dir_edges2[i+1])
        for j in range(len(var_bins)-1):
            res += " %9.3f," % (table[j, i], )
        res += "\n"
    return res


def _make_plot(station, sknt, drct, units, nsector, rmax, hours, months,
               sname, minvalid, maxvalid, level):
    """Generate a matplotlib windrose plot

    Args:
      station (str): station identifier
      sknt (list): list of wind obs
      drct (list): list of wind directions
      units (str): units of wind speed
      nsector (int): number of bins to use for windrose
      rmax (float): radius of the plot
      hours (list): hour limit for plot
      month (list): month limit for plot
      sname (str): station name
      minvalid (datetime): minimum observation time
      maxvalid (datetime): maximum observation time
      level (int): RAOB level in hPa of interest

    Returns:
      matplotlib.Figure
    """
    # Generate figure
    fig = plt.figure(figsize=(7, 7), dpi=80, facecolor='w', edgecolor='w')
    rect = [0.15, 0.15, 0.7, 0.7]
    ax = WindroseAxes(fig, rect, axisbg='w')
    fig.add_axes(ax)
    wu = WINDUNITS[units] if level is None else RAOB_WINDUNITS[units]
    ax.bar(drct, sknt, normed=True, bins=wu['bins'], opening=0.8,
           edgecolor='white', nsector=nsector, rmax=rmax)
    handles = []
    for p in ax.patches_list:
        color = p.get_facecolor()
        handles.append(plt.Rectangle((0, 0), 0.1, 0.3,
                                     facecolor=color, edgecolor='black'))
    l = fig.legend(handles, wu['binlbl'], loc=(0.01, 0.01),
                   ncol=6,
                   title='Wind Speed [%s]' % (wu['abbr'],),
                   mode=None, columnspacing=0.9, handletextpad=0.45)
    plt.setp(l.get_texts(), fontsize=10)
    # Now we put some fancy debugging info on the plot
    tlimit = "Time Domain: "
    if len(hours) == 24 and len(months) == 12:
        tlimit = "All Year"
    if len(hours) < 24:
        if len(hours) > 4:
            tlimit += "%s-%s" % (
                    datetime.datetime(2000, 1, 1, hours[0]).strftime("%-I %p"),
                    datetime.datetime(2000, 1, 1, hours[-1]).strftime("%-I %p")
                                 )
        else:
            for h in hours:
                tlimit += "%s," % (
                    datetime.datetime(2000, 1, 1, h).strftime("%-I %p"),)
    if len(months) < 12:
        for h in months:
            tlimit += "%s," % (datetime.datetime(2000, h, 1).strftime("%b"),)
    label = """[%s] %s%s
Windrose Plot [%s]
Period of Record: %s - %s""" % (
        station, sname if sname is not None else "((%s))" % (station, ),
        "" if level is None else " @%s hPa" % (level, ),
        tlimit,
        minvalid.strftime("%d %b %Y"), maxvalid.strftime("%d %b %Y"))
    plt.gcf().text(0.14, 0.99, label, va='top')
    plt.gcf().text(0.96, 0.11, (
        "Stats\nn: %s\nCalm: %.1f%%\nAvg Speed: %.1f %s"
        ) % (np.shape(sknt)[0],
             np.sum(np.where(sknt < 2., 1., 0.)) / np.shape(sknt)[0] * 100.,
             np.average(sknt), wu['abbr']), ha='right')
    plt.gcf().text(0.01, 0.11, "Generated: %s" % (
                   datetime.datetime.now().strftime("%d %b %Y"),),
                   verticalalignment="bottom")
    # Make a logo
    im = mpimage.imread('%s/%s' % (DATADIR, 'logo.png'))

    plt.figimage(im, 10, 625)

    return fig


def windrose(station, database='asos', months=np.arange(1, 13),
             hours=np.arange(0, 24), sts=datetime.datetime(1970, 1, 1),
             ets=datetime.datetime(2050, 1, 1), units="mph", nsector=36,
             justdata=False, rmax=None, cursor=None, sname=None,
             sknt=None, drct=None, level=None):
    """Utility function that generates a windrose plot

    Args:
      station (str): station identifier to search database for
      database (str,optional): database name to look for data within
      months (list,optional): optional list of months to limit plot to
      hours (list,optional): optional list of hours to limit plot to
      sts (datetime,optional): start datetime
      ets (datetime,optional): end datetime
      units (str,optional): units to plot values as
      nsector (int,optional): number of bins to devide the windrose into
      justdata (boolean,optional): if True, write out the data only
      cursor (psycopg2.cursor,optional): provide a database cursor to run the
        query against.
      sname (str,optional): The name of this station, if not specified it will
        default to the ((`station`)) identifier
      sknt (list,optional): A list of wind speeds in knots already generated
      drct (list,optional): A list of wind directions (deg N) already generated
      level (int,optional): In case of RAOB, which level interests us (hPa)

    Returns:
      matplotlib.Figure instance or textdata
    """
    monthinfo = _get_timeinfo(months, 'month', 12)
    hourinfo = _get_timeinfo(hours, 'hour', 24)

    if sknt is None or drct is None:
        (sknt, drct, minvalid, maxvalid) = _get_data(station, cursor, database,
                                                     sts, ets, monthinfo,
                                                     hourinfo, level)
    sknt = speed(sknt, 'KT').value(units.upper())
    if justdata:
        return _make_textresult(station, sknt, drct, units, nsector, sname,
                                minvalid, maxvalid, monthinfo, hourinfo, level)
    if len(sknt) < 5 or np.max(sknt) < 1:
        fig = plt.figure(figsize=(6, 7), dpi=80, facecolor='w', edgecolor='w')
        fig.text(0.17, 0.89, 'Not enough data available to generate plot')
        return fig


    return _make_plot(station, sknt, drct, units, nsector, rmax, hours, months,
                      sname, minvalid, maxvalid, level)
