"""
Parser for NWS Climate Report text format
"""
import re
import datetime

from pyiem.nws.product import TextProduct

DATE_RE = re.compile(r"CLIMATE SUMMARY FOR\s+([A-Z]+\s[0-9]+\s+[0-9]{4})")

class CLIException(Exception):
    """ Exception """
    pass

def trace(val):
    """ This value could be T or M, account for it! """
    if val == 'M' or val == 'MM':
        return None
    if val == 'T':
        return 0.0001
    return float(val)

def parse_snowfall(lines, data):
    """ Parse the snowfall data 
WEATHER ITEM   OBSERVED TIME   RECORD YEAR NORMAL DEPARTURE LAST
                VALUE   (LST)  VALUE       VALUE  FROM      YEAR 
                                                  NORMAL
SNOWFALL (IN)
  YESTERDAY        0.0          MM      MM   0.0    0.0      0.0
  MONTH TO DATE    0.0                       0.0    0.0      0.0
  SINCE JUN 1      0.0                       0.0    0.0      0.0
  SINCE JUL 1      0.0                       0.0    0.0      0.0
  SNOW DEPTH       0
    """
    for linenum, line in enumerate(lines):
        line = (line+" ").replace(" T ", "0.0001")
        tokens = line.split()
        if line.startswith("YESTERDAY") or line.startswith("TODAY"):
            data['snow_today'] = trace(tokens[1])
            if len(tokens) == 7 and tokens[2] != 'MM' and tokens[3] != 'MM':
                data['snow_today_record'] = trace(tokens[2])
                data['snow_today_record_years'] = [int(tokens[3]),]
                # Check next line(s) for more years
                while ((linenum+1)<len(lines) and 
                       len(lines[linenum+1].strip()) == 4):
                    data['snow_today_record_years'].append(
                                                    int(lines[linenum+1]))
                    linenum += 1
        elif line.startswith("MONTH TO DATE"):
            data['snow_month'] = trace(tokens[3])
        elif line.startswith("SINCE JUN 1"):
            data['snow_jun1'] = trace(tokens[3])
        elif line.startswith("SINCE JUL 1"):
            data['snow_jul1'] = trace(tokens[3])
        elif line.startswith("SINCE DEC 1"):
            data['snow_dec1'] = trace(tokens[3])

def parse_precipitation(lines, data):
    """ Parse the precipitation data """
    for linenum, line in enumerate(lines):
        # careful here as if T is only value, the trailing space is stripped
        line = (line+" ").replace(" T ", "0.0001")
        numbers = re.findall("(\d\.?\d*)+", line)
        if line.startswith("YESTERDAY") or line.startswith("TODAY"):
            if len(numbers) == 0:
                continue
            data['precip_today'] = float(numbers[0])
            if len(numbers) == 6:
                data['precip_today_normal'] = float(numbers[3])
                data['precip_today_record'] = float(numbers[1])
                data['precip_today_record_years'] = [int(numbers[2]),]
                # Check next line(s) for more years
                while ((linenum+1)<len(lines) and 
                       len(lines[linenum+1].strip()) == 4):
                    data['precip_today_record_years'].append(
                                                    int(lines[linenum+1]))
                    linenum += 1
        elif line.startswith("MONTH TO DATE"):
            data['precip_month'] = float(numbers[0])
            if len(numbers) == 4:
                data['precip_month_normal'] = float(numbers[1])
        elif line.startswith("SINCE JAN 1"):
            data['precip_jan1'] = float(numbers[0])
            if len(numbers) == 4:
                data['precip_jan1_normal'] = float(numbers[1])
        elif line.startswith("SINCE JUL 1"):
            data['precip_jul1'] = float(numbers[0])
            if len(numbers) == 4:
                data['precip_jul1_normal'] = float(numbers[1])
        elif line.startswith("SINCE DEC 1"):
            data['precip_dec1'] = float(numbers[0])
            if len(numbers) == 4:
                data['precip_dec1_normal'] = float(numbers[1])

def parse_temperature(lines, data):
    """ Here we parse a temperature section
WEATHER ITEM   OBSERVED TIME   RECORD YEAR NORMAL DEPARTURE LAST
                VALUE   (LST)  VALUE       VALUE  FROM      YEAR
                                                  NORMAL
..................................................................
TEMPERATURE (F)
 YESTERDAY
  MAXIMUM         89    309 PM 101    1987  85      4       99
  MINIMUM         63    545 AM  51    1898  67     -4       69
  AVERAGE         76                        76      0       84
    """
    for linenum, line in enumerate(lines):
        numbers = re.findall("\d+", line)
        if line.startswith("MAXIMUM"):
            data['temperature_maximum'] = float(numbers[0])
            tokens = re.findall("([0-9]{3,4} [AP]M)", line)
            if len(tokens) == 1:
                data['temperature_maximum_time'] = tokens[0]
            if len(numbers) == 7: # we know this
                data['temperature_maximum_record'] = int(numbers[2])
                data['temperature_maximum_record_years'] = [int(numbers[3]),]
                data['temperature_maximum_normal'] = int(numbers[4])
                # Check next line(s) for more years
                while ((linenum+1)<len(lines) and 
                       len(lines[linenum+1].strip()) == 4):
                    data['temperature_maximum_record_years'].append(
                                                    int(lines[linenum+1]))
                    linenum += 1
        if line.startswith("MINIMUM"):
            data['temperature_minimum'] = float(numbers[0])
            tokens = re.findall("([0-9]{3,4} [AP]M)", line)
            if len(tokens) == 1:
                data['temperature_minimum_time'] = tokens[0]
            if len(numbers) == 7: # we know this
                data['temperature_minimum_record'] = int(numbers[2])
                data['temperature_minimum_record_years'] = [int(numbers[3]),]
                data['temperature_minimum_normal'] = int(numbers[4])
                while ((linenum+1)<len(lines) and 
                       len(lines[linenum+1].strip()) == 4):
                    data['temperature_minimum_record_years'].append(
                                                    int(lines[linenum+1]))
                    linenum += 1

class CLIProduct( TextProduct ):
    """
    Represents a Storm Prediction Center Mesoscale Convective Discussion
    """

    def __init__(self, text):
        """ constructor """
        TextProduct.__init__(self, text)
        self.data = None
        self.cli_valid = None
        if self.wmo[:2] != 'CD':
            print 'Product %s skipped due to wrong header' % (
                                                    self.get_product_id(),)
            return
        self.cli_valid = self.parse_cli_valid()
        # If we failed above
        if self.cli_valid is not None:
            self.data = self.parse_data()
        
    def parse_data(self):
        """ Actually do the parsing of this silly format """
        data = {}
        pos = self.unixtext.find("TEMPERATURE (F)")
        if pos == -1:
            pos = self.unixtext.find("TEMPERATURE")
            if pos == -1:
                raise CLIException('Failed to find TEMPERATURE (F), aborting')

        # Strip extraneous spaces
        meat = "\n".join([l.strip() for l in self.unixtext[pos:].split("\n")])
        sections = meat.split("\n\n")
        for section in sections:
            lines = section.split("\n")
            if lines[0] in ["TEMPERATURE (F)", 'TEMPERATURE']:
                parse_temperature(lines, data)
            elif lines[0] in ['PRECIPITATION (IN)', 'PRECIPITATION']:
                parse_precipitation(lines, data)
            elif lines[0] in ['SNOWFALL (IN)', 'SNOWFALL']:
                parse_snowfall(lines, data)

        return data

    def parse_cli_valid(self):
        """ Figure out when this product is valid for """
        tokens = DATE_RE.findall( self.unixtext.replace("\n", " ") )
        if len(tokens) == 1:
            if len(tokens[0].split()[0]) == 3:
                myfmt = '%b %d %Y'
            else:
                myfmt = '%B %d %Y'
            return datetime.datetime.strptime(tokens[0], myfmt)
        else:
            # Known sources of bad data...
            if self.source in ['PKMR', 'NSTU', 'PTTP', 'PTKK']:
                return None
            raise CLIException('Could not find date valid in %s' % (
                                                self.get_product_id(),))

def parser(text, utcnow=None, ugc_provider=None, nwsli_provider=None):
    """ Provide back CLI objects based on the parsing of this text """
    return CLIProduct( text )