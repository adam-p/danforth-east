# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : https://adampritchard.mit-license.org/
#

"""General utility functions that mostly aren't specific to this application.
"""

import re
import errno
import datetime
import logging

import dateutil.parser
import dateutil.tz

import config


def basic_validator(val, required):
    if required and not val:
        return False

    if val is None:
        return True

    if not isinstance(val, str):
        return False

    return True


def email_validator(val, required):
    if not basic_validator(val, required):
        return False

    if not val:
        return True

    if not re.fullmatch(r'[^@]+@[^@]+\.[^@]+', val):
        return False

    return True


def latlong_validator(val, required):
    if not basic_validator(val, required):
        return False

    if not val:
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
    # We only want the date and not the time (and it needs to be tz-aware).
    return datetime.datetime.now(dateutil.tz.gettz(config.TIMEZONE)).strftime('%Y-%m-%d')


def days_ago(datestring):
    """Returns and integer of the number of days ago the given date was.
    """

    date = dateutil.parser.parse(datestring)
    delta = datetime.datetime.now() - date
    return delta.days
