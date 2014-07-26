# -*- coding: utf-8 -*-

#
# Copyright Adam Pritchard 2014
# MIT License : http://adampritchard.mit-license.org/
#

# pylint: disable=E1101,E1103

import logging
import os
from urlparse import urlparse

import webapp2
import webapp2_extras.json
import jinja2
from Crypto.Random import random

from google.appengine.api import users
from google.appengine.ext.webapp.util import login_required
from google.appengine.api import taskqueue

import config
import helpers
import utils
import gapps


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__),
                                                'templates')),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class IndexPage(helpers.BaseHandler):

    def get(self):
        user = users.get_current_user()

        template_values = {
            'user': user,
            'logout_url': users.create_logout_url('/'),
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('index.jinja')
        self.response.write(template.render(template_values))


class NewMemberPage(helpers.BaseHandler):

    @login_required
    def get(self):
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return
        elif not gapps.is_user_authorized(user):
            self.redirect('/bad-user')
            return

        csrf = helpers.create_csrf_token()

        volunteer_interests = gapps.get_volunteer_interests()

        template_values = {
            'FIELDS': config.FIELDS,
            'csrf': csrf,
            'volunteer_interests': volunteer_interests,
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('new-member.jinja')

        self.response.set_cookie('csrf', csrf, path=self.request.path)
        self.response.write(template.render(template_values))

    @login_required
    def post(self):
        """Create the new member.
        '409 Conflict' is thrown if the email address is already associated
        with an existing member.
        """
        helpers.check_csrf(self.request)

        user = users.get_current_user()
        if not user or not gapps.is_user_authorized(user):
            detail = 'user not authorized' if user else 'user not logged in'
            webapp2.abort(401, detail=detail)

        new_member = gapps.member_dict_from_request(self.request,
                                                    user.email(),
                                                    'join')
        join_or_renew = gapps.join_or_renew_member_from_dict(new_member)

        self.response.write('success: %s' % join_or_renew)

        # Queue the welcome email
        taskqueue.add(url='/tasks/new-member-mail', params=new_member)


class RenewMemberPage(helpers.BaseHandler):

    @login_required
    def get(self):
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return
        elif not gapps.is_user_authorized(user):
            self.redirect('/bad-user')
            return

        csrf = helpers.create_csrf_token()

        volunteer_interests = gapps.get_volunteer_interests()

        template_values = {
            'FIELDS': config.FIELDS,
            'csrf': csrf,
            'volunteer_interests': volunteer_interests,
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('renew-member.jinja')

        self.response.set_cookie('csrf', csrf, path=self.request.path)
        self.response.write(template.render(template_values))

    @login_required
    def post(self):
        helpers.check_csrf(self.request)

        user = users.get_current_user()
        if not user or not gapps.is_user_authorized(user):
            detail = 'user not authorized' if user else 'user not logged in'
            webapp2.abort(401, detail=detail)

        renew_member = gapps.member_dict_from_request(self.request,
                                                      user.email(),
                                                      'renew')
        gapps.renew_member_from_dict(renew_member)

        self.response.write('success')

        # Queue the welcome email
        taskqueue.add(url='/tasks/renew-member-mail', params=renew_member)


class BadUserPage(helpers.BaseHandler):

    def get(self):
        user = users.get_current_user()
        if not user:
            self.redirect('/')
            return

        template_values = {
            'user': user,
            'logout_url': users.create_logout_url('/'),
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('bad-user.jinja')
        self.response.write(template.render(template_values))


class AllMembersJson(helpers.BaseHandler):

    # @login_required -- Not using this decorator, since this isn't a web page.
    # Instead we'll check login state in logic and return an error code.
    def get(self):
        user = users.get_current_user()
        if not user or not gapps.is_user_authorized(user):
            detail = 'user not authorized' if user else 'user not logged in'
            webapp2.abort(401, detail=detail)

        all_members = gapps.get_all_members()
        fields = config.fields_to_dict(config.MEMBER_FIELDS)
        res = {'fields': fields, 'members': all_members}

        self.response.headers['Content-Type'] = 'application/json'
        self.response.write(webapp2_extras.json.encode(res))


class AuthorizeUserPage(helpers.BaseHandler):

    @login_required
    def get(self):
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return
        elif not gapps.is_user_authorized(user):
            self.redirect('/bad-user')
            return

        csrf = helpers.create_csrf_token()

        template_values = {
            'FIELDS': config.FIELDS,
            'csrf': csrf,
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('authorize-user.jinja')

        self.response.set_cookie('csrf', csrf, path=self.request.path)
        self.response.write(template.render(template_values))

    @login_required
    def post(self):
        helpers.check_csrf(self.request)

        user = users.get_current_user()
        if not user or not gapps.is_user_authorized(user):
            detail = 'user not authorized' if user else 'user not logged in'
            webapp2.abort(401, detail=detail)

        gapps.authorize_new_user(self.request, user)

        self.response.write('success')


class MapMembersPage(helpers.BaseHandler):

    @login_required
    def get(self):
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))  # pylint: disable=E1101
            return
        elif not gapps.is_user_authorized(user):
            self.redirect('/bad-user')
            return

        template_values = {
            'config': config,
        }
        template = JINJA_ENVIRONMENT.get_template('map-members.jinja')

        self.response.write(template.render(template_values))


app = webapp2.WSGIApplication([  # pylint: disable=C0103
    ('/', IndexPage),
    ('/new-member', NewMemberPage),
    ('/renew-member', RenewMemberPage),
    ('/bad-user', BadUserPage),
    ('/all-members-json', AllMembersJson),
    ('/authorize-user', AuthorizeUserPage),
    ('/map-members', MapMembersPage),
], debug=config.DEBUG)
