# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : https://adampritchard.mit-license.org/
#

"""Helpers that are specific to this application.
"""


from typing import List
import random
import datetime
import logging
import flask
import geopy

import config


def latlong_for_record(fields, record_dict):
    """Get a "latitude, longitude" string for the address of the given record.
    `fields` should be SHEETS.member.fields or SHEETS.volunteer.fields -- i.e.,
    something with appropriate address components.
    Returns empty string if geocoding is not possible.
    """

    if not record_dict.get(fields.street_name.name):
        # If we don't have a street name, just give up
        return ''

    address_components = [
        record_dict.get(fields.street_num.name),
        record_dict.get(fields.street_name.name),
        record_dict.get(fields.city.name) or 'Toronto',
        'Ontario',
        record_dict.get(fields.postal_code.name),
        'Canada',
    ]

    # Get rid of the empty components
    address_components = [component for component in address_components if component]

    address_string = ', '.join(address_components)

    geocoder = geopy.geocoders.GoogleV3(config.GOOGLE_SERVER_API_KEY)

    try:
        location = geocoder.geocode(address_string, region='CA')
    except Exception as e:
        logging.error('geocode failed: %s', exc_info=e)
        return ''

    if not location:
        return ''

    return '%s, %s' % (location.latitude, location.longitude)


def address_from_latlong(latlong: str):
    """Reverse geocode the given latitude and longitude.
    `latlong` must be a string with two floats separated by a comma+space,
    like: "44.842, -84.238".
    Returns empty string on failure.
    """

    if not latlong or not isinstance(latlong, str):
        return ''

    point = latlong.split(', ')

    if len(point) != 2:
        return ''

    geocoder = geopy.geocoders.GoogleV3(config.GOOGLE_SERVER_API_KEY)

    res = None
    try:
        res = geocoder.reverse(point, exactly_one=True)
    except Exception as e:
        logging.error('Geocoder exception', exc_info=e)

    if not res:
        return ''

    return res.address
