# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2020
# MIT License : https://adampritchard.mit-license.org/
#

"""
Flask routes for the admin member management site.
"""

import logging
import flask
import flask_login

import config
import helpers
import gapps
import main


admin = flask.Blueprint('admin', __name__)

admin.before_request(main.additional_csrf_checks)


@admin.route('/')
def index():
    """The main page, with links to everything else.
    """
    return flask.render_template('index.jinja', app_config=config)

@admin.route('/new-member', methods=['GET'])
@flask_login.login_required
def new_member():
    """Show the page where a new member can be added.
    """
    volunteer_interests = gapps.get_volunteer_interests()
    skills_categories = gapps.get_skills_categories()

    resp = flask.make_response(flask.render_template(
        'new-member.jinja',
        app_config=config,
        volunteer_interests=volunteer_interests,
        skills_categories=skills_categories))

    return resp

@admin.route('/new-member', methods=['POST'])
@flask_login.login_required
def submit_new_member():
    """Create the new member.
    '409 Conflict' is thrown if the email address is already associated
    with an existing member.
    """
    user_email = flask_login.current_user.id

    new_member = gapps.member_dict_from_request(flask.request,
                                                user_email,
                                                'join')
    join_or_renew = gapps.join_or_renew_member_from_dict(new_member)

    if join_or_renew == 'join':
        # Enqueue the welcome email
        gapps.enqueue_task('/tasks/new-member-mail', new_member)
    # else the member already existed and we're going to email. This is especially
    # important because App Engine 500s even after a successful member creation. We don't
    # want a retry to spam the member.

    return f'success: {join_or_renew}'

@admin.route('/renew-member', methods=['GET'])
@flask_login.login_required
def renew_member():
    """Show the page where a member can be renewed.
    """
    volunteer_interests = gapps.get_volunteer_interests()
    skills_categories = gapps.get_skills_categories()

    resp = flask.make_response(flask.render_template(
        'renew-member.jinja',
        app_config=config,
        volunteer_interests=volunteer_interests,
        skills_categories=skills_categories))

    return resp

@admin.route('/renew-member', methods=['POST'])
@flask_login.login_required
def submit_renew_member():
    """Processing the member renewal form.
    """
    user_email = flask_login.current_user.id

    renew_member = gapps.member_dict_from_request(flask.request,
                                                  user_email,
                                                  'renew')

    gapps.renew_member_from_dict(renew_member)

    # Enqueue the renewal email
    gapps.enqueue_task('/tasks/renew-member-mail', renew_member)

    return 'success'

@admin.route('/all-members-json', methods=['GET'])
@flask_login.login_required
def all_members_json():
    """Fetch a list of all members. This is to be called via XHR from the admin site pages.
    """
    all_members = gapps.get_all_members()
    fields = config.fields_to_dict(config.SHEETS.member.fields)
    res = {'fields': fields, 'members': all_members}

    return flask.make_response(flask.jsonify(res))

@admin.route('/authorize-user', methods=['GET'])
@flask_login.login_required
def authorize_user():
    """Show the page for adding a new admin user.
    """
    resp = flask.make_response(flask.render_template(
        'authorize-user.jinja',
        app_config=config))

    return resp

@admin.route('/authorize-user', methods=['POST'])
@flask_login.login_required
def submit_authorize_user():
    """Process the form to add a new admin user.
    """
    current_user_email = flask_login.current_user.id
    gapps.authorize_new_user(flask.request, current_user_email)

    return 'success'

@admin.route('/map-members', methods=['GET'])
@flask_login.login_required
def map_members():
    """Show a map of all members.
    """
    resp = flask.make_response(flask.render_template(
        'map-members.jinja',
        app_config=config))

    return resp
