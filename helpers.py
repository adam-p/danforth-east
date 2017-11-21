# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

"""Helpers that are specific to this application.
"""


import random
import datetime

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


_CSRF_FIELD_NAME = 'csrf-token'


def get_csrf_token(request):
    """Get the current CSRF (cross-site request forgery attack) token from the
    request. If there isn't one, generate one.
    Returns a string.
    """
    cookie_csrf_token = request.cookies.get(_CSRF_FIELD_NAME)

    if not cookie_csrf_token:
        # The prepended string is only to make it a little clearer when debugging.
        cookie_csrf_token = 'csrf' + str(random.getrandbits(128))

    return cookie_csrf_token


def check_csrf(request):
    """Checks that the cross-site request forgery check values are correst in
    the request. Aborts request if not. Does not return a value.
    """

    # It's important to make sure the cookie isn't empty, otherwise the attacker
    # could send the attack-POST before the user hits the page for the first
    # time and gets a cookie.
    cookie_csrf_token = request.cookies.get(_CSRF_FIELD_NAME)
    request_csrf_token = request.get(_CSRF_FIELD_NAME)
    if not cookie_csrf_token or request_csrf_token != cookie_csrf_token:
        logging.error('CSRF mismatch: req csrf=>>%s<<; cookie csrf=>>%s<<',
                      request_csrf_token, cookie_csrf_token)
        webapp2.abort(403, detail='CSRF check fail. Make sure you have cookies enabled. Reload this page and try again.')


def set_csrf_cookie(response, csrf_token):
    """Set the CSRF token as a cookie in the response.
    """
    response.set_cookie(_CSRF_FIELD_NAME, value=csrf_token,
                        #secure=True,  # It would be nice to set this, but it messes up local testing. Since we only allow HTTPS connections, it's probably okay to leave this False...?
                        httponly=True, path='/',
                        expires=datetime.datetime.now()+datetime.timedelta(7))


def latlong_for_record(fields, record_dict):
    """Get a "latitude, longitude" string for the address of the given record.
    `fields` should be config.MEMBER_FIELDS or config.VOLUNTEER_FIELDS -- i.e.,
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

    res = None
    try:
        res = geocoder.reverse(point)
    except Exception, e:
        logging.error('Geocoder exception', exc_info=e)

    if not res:
        return ''

    return res[0].address
