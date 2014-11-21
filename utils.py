# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

"""General utility functions that mostly aren't specific to this application.
"""

import re
import errno
import datetime
import logging

from google.appengine.api import mail
import pytz
import dateutil.parser

import config


_no_spaces_re = re.compile('[^\w-]')


def title_to_name(title):
    """When a spreadsheet is accessed using the "list-based feed" API, it
    converts column names to all lowercase in the resulting dict.
    """
    return _no_spaces_re.sub('', title).lower()


string_types = (str, unicode) if str is bytes else (str, bytes)


def email_validator(val, required):
    if required and not val:
        return False

    if type(val) not in string_types:
        return False

    if not val and not required:
        return True

    return mail.is_email_valid(val)


def basic_validator(val, required):
    if required and not val:
        return False

    if type(val) not in string_types:
        return False

    return True


def latlong_validator(val, required):
    if required and not val:
        return False

    if type(val) not in string_types:
        return False

    if not val and not required:
        return True

    latlong = val.split(', ')

    if len(latlong) != 2:
        return False

    try:
        latitude = float(latlong[0])
        longitude = float(latlong[1])
    except ValueError:
        return False

    return latitude > -180.0 and latitude < 180.0 and \
           longitude > -180.0 and longitude < 180.0


def current_datetime():
    """Returns string of current datetime.
    """
    #return datetime.datetime.now(pytz.timezone(config.TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S')
    # We only want the date and not the time.
    return datetime.datetime.now(pytz.timezone(config.TIMEZONE)).strftime('%Y-%m-%d')


def days_ago(datestring):
    """Returns and integer of the number of days ago the given date was.
    """

    date = dateutil.parser.parse(datestring)
    delta = datetime.datetime.now() - date
    return delta.days
