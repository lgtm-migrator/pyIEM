"""Center Weather Advisories (CWA)"""
# Stdlib imports
import re
import math

# Third Party
from shapely.geometry import Polygon, LineString, Point

# Local stuff
from pyiem.models.cwa import CWAModel
from pyiem.nws.ugc import str2time
from pyiem.nws.product import TextProduct

LINE3 = re.compile(
    r"(?P<loc>[A-Z1-9]{4}) CWA (?P<ddhhmi>[0-9]{6})\s?(?P<cor>COR)?"
)
LINE4 = re.compile(
    r"(?P<loc>[A-Z1-9]{3,4}) CWA (?P<num>\d+) VALID UNTIL (?P<ddhhmi>[0-9]{6})"
)

FROM_RE = re.compile(
    r"""
(?P<offset>[0-9]+)?
(?P<drct>N|NE|NNE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)?\s?
(?P<loc>[A-Z0-9]{3})
""",
    re.VERBOSE,
)
NM_WIDE = re.compile(r"(\s|\.)(?P<width>\d+)NM WIDE")
DIAMETER = re.compile(r"DIAM (?P<diameter>\d+)NM")
CANCEL_LINE = re.compile("(CNL |CANCEL|ERROR)")


dirs = {
    "NNE": 22.5,
    "ENE": 67.5,
    "NE": 45.0,
    "E": 90.0,
    "ESE": 112.5,
    "SSE": 157.5,
    "SE": 135.0,
    "S": 180.0,
    "SSW": 202.5,
    "WSW": 247.5,
    "SW": 225.0,
    "W": 270.0,
    "WNW": 292.5,
    "NW": 315.0,
    "NNW": 337.5,
    "N": 0,
    "": 0,
}

KM_SM = 1.609347


def go2lonlat(lon0, lat0, direction, displacement):
    """http://stackoverflow.com/questions/7222382"""
    # Radius of the Earth
    R = 6378.1
    # Bearing is 90 degrees converted to radians.
    if isinstance(direction, str):
        direction = dirs.get(direction, 0)
    brng = math.radians(direction)
    # Distance in km
    d = displacement * KM_SM

    # Current lat point converted to radians
    lat1 = math.radians(lat0)
    # Current long point converted to radians
    lon1 = math.radians(lon0)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(d / R)
        + math.cos(lat1) * math.sin(d / R) * math.cos(brng)
    )

    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(d / R) * math.cos(lat1),
        math.cos(d / R) - math.sin(lat1) * math.sin(lat2),
    )

    lat2 = math.degrees(lat2)
    lon2 = math.degrees(lon2)

    return lon2, lat2


def parse_polygon(prod: TextProduct, line: str) -> Polygon:
    """Figure out what the polygon is!"""
    tokens = line.replace("FROM ", "").split("-")
    pts = []
    for token in tokens:
        s = FROM_RE.search(token)
        if s:
            d = s.groupdict()
            if d["offset"] is not None:
                (lon1, lat1) = go2lonlat(
                    prod.nwsli_provider[d["loc"]]["lon"],
                    prod.nwsli_provider[d["loc"]]["lat"],
                    d["drct"],
                    float(d["offset"]),
                )
            else:
                (lon1, lat1) = (
                    prod.nwsli_provider[d["loc"]]["lon"],
                    prod.nwsli_provider[d["loc"]]["lat"],
                )
            pts.append((lon1, lat1))
    if len(pts) == 2:
        # We have a line, uh oh
        res = NM_WIDE.search(prod.unixtext).groupdict()
        # approx
        width_deg = float(res["width"]) / KM_SM / 111.0
        line = LineString(pts)
        right = line.parallel_offset(width_deg / 2, "right", join_style=2)
        left = line.parallel_offset(width_deg / 2, "left", join_style=2)
        poly = Polygon(list(left.coords) + list(right.coords))
    elif len(pts) == 1:
        # We have a point
        res = DIAMETER.search(prod.unixtext).groupdict()
        # approx
        diameter_deg = float(res["diameter"]) / KM_SM / 111.0
        poly = Point(*pts[0]).buffer(diameter_deg / 2)
    else:
        poly = Polygon(pts)
    assert poly.is_valid and not poly.is_empty
    return poly


def parse_product(prod: TextProduct) -> CWAModel:
    """Do the parsing we need for the data model."""
    lines = prod.unixtext.replace("\001\n", "").split("\n")
    # This is not tenable at the moment
    for ln in [4, 5]:
        if CANCEL_LINE.match(lines[ln]):
            return None
    # Could fail, but this is a requirement anyway
    res3 = LINE3.match(lines[2]).groupdict()
    issue = str2time(res3["ddhhmi"], prod.valid)
    # Could fail, but this is a requirement anyway
    res4 = LINE4.match(lines[3]).groupdict()
    expire = str2time(res4["ddhhmi"], prod.valid)
    # parse the polygon, perhaps lines[5] has more points for the polygon :/
    test = lines[5].split()[0]
    # if length of test is 3 or starts with a number
    nrstart = 5
    content = lines[4]
    if len(test) == 3 or test[3] == "-" or test[0].isdigit():
        content = " ".join(lines[4:6])
        nrstart = 6
    poly = parse_polygon(prod, content)
    narrative = " ".join(lines[nrstart:]).replace("=", "").strip()
    return CWAModel(
        center=res4["loc"],
        issue=issue,
        expire=expire,
        geom=poly,
        is_corrected=(res3["cor"] is not None),
        narrative=narrative,
        num=int(res4["num"]),
    )


class CWAProduct(TextProduct):
    """
    Represents a Center Weather Advsiory (CWA) product.
    """

    def __init__(
        self, text, utcnow=None, ugc_provider=None, nwsli_provider=None
    ):
        """constructor"""
        TextProduct.__init__(self, text, utcnow, ugc_provider, nwsli_provider)
        self.data = parse_product(self)
        # Need to do our faked AFOS, so other things work below
        self.afos = f"CWA{self.source[1:]}"

    def sql(self, txn):
        """Do SQL related stuff that is required"""
        data = self.data
        if data is None:
            return
        if data.is_corrected:
            txn.execute(
                "DELETE from cwas where issue = %s and num = %s and "
                "center = %s",
                (data.issue, data.num, data.center),
            )
            if txn.rowcount == 0:
                self.warnings.append("Corrected CWA updated no rows")
        txn.execute(
            "INSERT into cwas (issue, expire, center, num, narrative, "
            "product_id, geom) VALUES (%s, %s, %s, %s, %s, %s, "
            "ST_GeomFromText(%s, 4326))",
            (
                data.issue,
                data.expire,
                data.center,
                data.num,
                data.narrative,
                self.get_product_id(),
                data.geom.wkt,
            ),
        )

    def get_jabbers(self, _uri, _uri2=None):
        """Return the Jabber for this sigmet"""
        data = self.data
        if data is None:
            return []
        apurl = (
            "https://mesonet.agron.iastate.edu/plotting/auto/plot/226/"
            f"network:CWSU::cwsu:{data.center}::num:{data.num}::"
            f"issue:{data.issue:%Y-%m-%d%%20%H%M}::_r:t.png"
        )
        texturl = (
            "https://mesonet.agron.iastate.edu/"
            f"p.php?pid={self.get_product_id()}"
        )
        till = f"{data.expire:%-d %b %H%M}Z"
        text = (
            f"{data.center} issues CWA {data.num} till {till} ... "
            f"{data.narrative} {texturl}"
        )
        html = (
            f'<p>{data.center} issues <a href="{texturl}">CWA {data.num}</a>'
            f" till {till}<br/>{data.narrative}</p>"
        )
        channels = ["CWA...", f"CWA{data.center}"]
        xtra = {
            "channels": ",".join(channels),
            "twitter": text,
            "twitter_media": apurl,
        }

        return [(text, html, xtra)]


def parser(text, utcnow=None, ugc_provider=None, nwsli_provider=None):
    """Helper function"""
    return CWAProduct(text, utcnow, ugc_provider, nwsli_provider)
