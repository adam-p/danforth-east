# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

"""Helpers that are specific to this application.
"""


import random

import logging
import webapp2
import geopy

import utils
import config


# From https://webapp-improved.appspot.com/guide/exceptions.html
class BaseHandler(webapp2.RequestHandler):
    def handle_exception(self, exception, debug):
        # Log the error.
        logging.critical('BaseHandler exception', exc_info=exception)

        # Set a custom message.
        if hasattr(exception, 'detail') and getattr(exception, 'detail'):
            self.response.write(getattr(exception, 'detail'))

        # If the exception is a HTTPException, use its error code.
        # Otherwise use a generic 500 error code.
        if isinstance(exception, webapp2.HTTPException):
            self.response.set_status(exception.code)
        else:
            self.response.set_status(500)


def create_csrf_token():
    """Generates a token for use in preventing cross-site request forgery
    attacks. Returns a string.
    """
    # The prepended string is only to make it a little clearer when debugging.
    return 'csrf' + str(random.getrandbits(128))


def check_csrf(request):
    """Checks that the cross-site request forgery check values are correst in
    the request. Aborts request if not. Does not return a value.
    """

    # It's important to make sure the cookie isn't empty, otherwise the attacker
    # could send the attack-POST before the user hits the page for the first
    # time and gets a cookie.
    if not request.cookies.get('csrf') or \
       request.get('csrf') != request.cookies.get('csrf'):
        logging.error('CSRF mismatch: req csrf=>>%s<<; cookie csrf=>>%s<<',
                      request.get('csrf'), request.cookies.get('csrf'))
        webapp2.abort(403, detail='CSRF check fail. Make sure you have cookies enabled. Reload this page and try again.')


def latlong_for_member(member_dict):
    """Get a "latitude, longitude" string for the address of the given member.
    Returns empty string if geocoding is not possible.
    """

    if not member_dict.get(config.MEMBER_FIELDS.street_name.name):
        # If we don't have a street name, just give up
        return ''

    address_components = [
        member_dict.get(config.MEMBER_FIELDS.street_num.name),
        member_dict.get(config.MEMBER_FIELDS.street_name.name),
        member_dict.get(config.MEMBER_FIELDS.city.name) or 'Toronto',
        'Ontario',
        member_dict.get(config.MEMBER_FIELDS.postal_code.name),
        'Canada',
    ]

    # Get rid of the empty components
    address_components = [component for component in address_components if component]

    address_string = ', '.join(address_components)

    geocoder = geopy.geocoders.GoogleV3(config.GOOGLE_SERVER_API_KEY)
    location = geocoder.geocode(address_string, region='CA')

    if not location:
        return ''

    return '%s, %s' % (location.latitude, location.longitude)


def address_from_latlong(latlong):
    """Reverse geocode the given latitude and longitude.
    `latlong` must be a string with two floats separated by a comma+space,
    like: "44.842, -84.238".
    Returns empty string on failure.
    """

    if not latlong or type(latlong) not in utils.string_types:
        return ''

    point = latlong.split(', ')

    if len(point) != 2:
        return ''

    geocoder = geopy.geocoders.GoogleV3(config.GOOGLE_SERVER_API_KEY)
    res = geocoder.reverse(point)

    if not res:
        return ''

    return res[0].address
