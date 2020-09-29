# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2020
# MIT License : https://adampritchard.mit-license.org/
#

"""
App entry and Flask routes blueprints gathering.
"""

import logging
from urllib.parse import urlparse
import flask
from flask_wtf.csrf import CSRFProtect, same_origin

import config
import emailer


app = flask.Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
# If log volume ever becomes a problem (which it won't), raise this level if not DEBUG
logging.basicConfig(level=logging.DEBUG)
if config.DEBUG:
    app.debug = True
else:
    app.debug = False


# Add token-based CSRF protection
csrf = CSRFProtect(app)

def additional_csrf_checks():
    """OWASP suggests a defense-in-depth approach to CSRF mitigation.
    https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
    We get the token-base approach from flask_wtf.csrf. Here we're going to some additional checks.
    Calls flask.abort(400) if it doesn't match. Called before every request in this project.

    To be used by blueprints like:
        blueprint_name.before_request(main.additional_csrf_checks)

    If you are running the server behind a proxy, these checks might not work. See:
    https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#identifying-the-target-origin
    """
    if config.DEBUG:
        logging.warning('app.additional_csrf_checks: skipping check due to DEBUG=True')
        return

    if flask.request.method == 'POST':
        # "Use of Custom Request Headers"
        # https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#use-of-custom-request-headers
        if flask.request.headers.get('X-Requested-With') != 'XMLHttpRequest':
            logging.warning('app.additional_csrf_checks: custom header check failed: %s %s', list(flask.request.headers.items()), list(flask.request.values.items()))
            flask.abort(400, description='CSRF: custom header check failed')

        # "Verifying Origin With Standard Headers"
        # https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#verifying-origin-with-standard-headers
        req_target = flask.request.url

        req_initiator = flask.request.origin or flask.request.referrer
        if not req_initiator:
            logging.warning('app.additional_csrf_checks: got empty req_initiator: %s %s', list(flask.request.headers.items()), list(flask.request.values.items()))
            flask.abort(400, description='CSRF: missing Origin and Referer headers')

        if not same_origin(req_target, req_initiator):
            logging.warning('app.additional_csrf_checks: req_target_origin != req_initiator_origin: %s %s %s %s', req_target, req_initiator, list(flask.request.headers.items()), list(flask.request.values.items()))
            flask.abort(400, description='CSRF: request initiator and target origin mismatch')


from auth import auth as auth_blueprint
app.register_blueprint(auth_blueprint)

from admin_site import admin as admin_blueprint
app.register_blueprint(admin_blueprint)

from self_serve import self_serve as self_serve_blueprint, self_serve_tasks as self_serve_tasks_blueprint
app.register_blueprint(self_serve_blueprint)
app.register_blueprint(self_serve_tasks_blueprint)

from tasks import tasks as tasks_blueprint
app.register_blueprint(tasks_blueprint)
