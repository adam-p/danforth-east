# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2020
# MIT License : https://adampritchard.mit-license.org/
#

"""
Flask routes for user authentication-related processing.
Auth is done with Google Sign-in.
"""

from typing import Optional
import logging
import flask
import flask_login
from google.oauth2 import id_token
from google.auth.transport import requests

import config
import gapps

import main
login_manager = flask_login.LoginManager()
login_manager.init_app(main.app)


auth = flask.Blueprint('auth', __name__)

auth.before_request(main.additional_csrf_checks)

class User(flask_login.UserMixin):
    pass


@login_manager.user_loader
def user_loader(email: str) -> Optional[User]:
    """Create a User object from the given email. Returns None if the user is not found --
    which means it is not authorized.
    """
    if not gapps.is_user_authorized(email):
        logging.warning(f"auth.user_loader: user not authorized: {email}")
        return None

    logging.debug(f"auth.user_loader: loading {email}")
    user = User()
    user.id = email
    return user


@login_manager.unauthorized_handler
def unauthorized_handler():
    """Called when a `login_required` route is hit but the user isn't yet authorized.
    """
    return flask.redirect(flask.url_for('auth.login'))


@auth.route('/login')
def login():
    """The login page.
    """
    return flask.render_template('login.jinja', app_config=config)


@auth.route('/tokensignin', methods=['POST'])
def token_signin():
    """Authorize user with a submitted Google auth token. (Or don't if the token is bad
    or the user is not authorized.)
    """
    response_401 = flask.make_response('You are not an authorized user. Please contact your administrator.', 401)

    idtoken = flask.request.values.get('idtoken')
    if not idtoken:
        logging.warning('auth.token_signin: no idtoken')
        return response_401

    try:
        idinfo = id_token.verify_oauth2_token(idtoken, requests.Request(), config.GOOGLE_SIGNIN_CLIENT_ID)
    except ValueError:
        logging.warning('auth.token_signin: invalid idtoken')
        return response_401

    user = user_loader(idinfo['email'])
    if not user:
        logging.warning(f'auth.token_signin: user not authorized: {idinfo["email"]}')
        return response_401

    flask_login.login_user(user, remember=True)
    return flask.make_response(user.id, 200)


@auth.route('/logout')
@flask_login.login_required
def logout():
    """Log the user out.
    """
    logging.info(f'logging out {flask_login.current_user.id}')
    flask_login.logout_user()
    return flask.render_template('logout.jinja', app_config=config)
