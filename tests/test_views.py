# -*- coding: utf-8 -*-

import unittest

from flask import Flask, json, session
from werkzeug.exceptions import BadRequest, Forbidden

import pytest

from coaster.app import load_config_from_file
from coaster.auth import add_auth_attribute, current_auth
from coaster.views import (
    get_current_url,
    get_next_url,
    jsonp,
    requestargs,
    requestform,
    requestquery,
    requires_permission,
)


def index():
    return "index"


def external():
    return "external"


def somewhere():
    return "somewhere"


@requestargs('p1', ('p2', int), ('p3[]', int))
def requestargs_test1(p1, p2=None, p3=None):
    return p1, p2, p3


@requestargs('p1', ('p2', int), 'p3[]')
def requestargs_test2(p1, p2=None, p3=None):
    return p1, p2, p3


@requestquery('p1', ('p2', int), ('p3[]', int))
def requestquery_test(p1, p2=None, p3=None):
    return p1, p2, p3


@requestform('p1', ('p2', int), ('p3[]', int))
def requestform_test(p1, p2=None, p3=None):
    return p1, p2, p3


@requestquery('query1')
@requestform('form1')
def requestcombo_test(query1, form1):
    return query1, form1


@requires_permission('allow-this')
def permission1():
    return 'allowed1'


@requires_permission({'allow-this', 'allow-that'})
def permission2():
    return 'allowed2'


# --- Tests -------------------------------------------------------------------


class TestCoasterViews(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        load_config_from_file(self.app, 'settings.py')
        self.app.add_url_rule('/', 'index', index)
        self.app.add_url_rule('/', 'external', external)
        self.app.add_url_rule('/somewhere', 'somewhere')

    def test_get_current_url(self):
        with self.app.test_request_context('/'):
            assert get_current_url() == '/'

        with self.app.test_request_context('/?q=hasgeek'):
            assert get_current_url() == '/?q=hasgeek'

        self.app.config['SERVER_NAME'] = 'example.com'

        with self.app.test_request_context(
            '/somewhere', environ_overrides={'HTTP_HOST': 'example.com'}
        ):
            assert get_current_url() == '/somewhere'

        with self.app.test_request_context(
            '/somewhere', environ_overrides={'HTTP_HOST': 'sub.example.com'}
        ):
            assert get_current_url() == 'http://sub.example.com/somewhere'

    def test_get_next_url(self):
        with self.app.test_request_context('/?next=http://example.com'):
            assert get_next_url(external=True) == 'http://example.com'
            assert get_next_url() == '/'
            assert get_next_url(default=()) == ()

        with self.app.test_request_context('/'):
            session['next'] = '/external'
            assert get_next_url(session=True) == '/external'

    def test_jsonp(self):
        with self.app.test_request_context('/?callback=callback'):
            kwargs = {'lang': 'en-us', 'query': 'python'}
            r = jsonp(**kwargs)
            response = (
                u'callback({\n  "%s": "%s",\n  "%s": "%s"\n});'
                % ('lang', kwargs['lang'], 'query', kwargs['query'])
            ).encode('utf-8')

            assert response == r.get_data()

        with self.app.test_request_context('/'):
            param1, param2 = 1, 2
            r = jsonp(param1=param1, param2=param2)
            resp = json.loads(r.response[0])
            assert resp['param1'] == param1
            assert resp['param2'] == param2
            r = jsonp({'param1': param1, 'param2': param2})
            resp = json.loads(r.response[0])
            assert resp['param1'] == param1
            assert resp['param2'] == param2
            r = jsonp([('param1', param1), ('param2', param2)])
            resp = json.loads(r.response[0])
            assert resp['param1'] == param1
            assert resp['param2'] == param2

    def test_requestargs(self):
        with self.app.test_request_context('/?p3=1&p3=2&p2=3&p1=1'):
            assert requestargs_test1() == (u'1', 3, [1, 2])

        with self.app.test_request_context('/?p2=2'):
            assert requestargs_test1(p1='1') == (u'1', 2, None)

        with self.app.test_request_context('/?p2=2'):
            assert requestargs_test1(p1='1', p2=3) == (u'1', 3, None)

        with self.app.test_request_context('/?p3=1&p3=2&p2=3&p1=1'):
            assert requestargs_test2() == (u'1', 3, [u'1', u'2'])

        with self.app.test_request_context('/?p2=2&p4=4'):
            with pytest.raises(TypeError):
                requestargs_test1(p4='4')
            with pytest.raises(BadRequest):
                requestargs_test1(p4='4')

        with self.app.test_request_context('/?p3=1&p3=2&p2=3&p1=1'):
            assert requestquery_test() == (u'1', 3, [1, 2])

        with self.app.test_request_context(
            '/', data={'p3': [1, 2], 'p2': 3, 'p1': 1}, method='POST'
        ):
            assert requestform_test() == (u'1', 3, [1, 2])

        with self.app.test_request_context(
            '/', query_string='query1=foo', data={'form1': 'bar'}, method='POST'
        ):
            assert requestcombo_test() == ('foo', 'bar')

        # Calling without a request context works as well
        assert requestargs_test1(p1='1', p2=3, p3=[1, 2]) == ('1', 3, [1, 2])

    def test_requires_permission(self):
        with self.app.test_request_context():

            assert permission1.is_available() is False
            assert permission2.is_available() is False

            with pytest.raises(Forbidden):
                permission1()
            with pytest.raises(Forbidden):
                permission2()

            add_auth_attribute('permissions', set())

            assert permission1.is_available() is False
            assert permission2.is_available() is False

            with pytest.raises(Forbidden):
                permission1()
            with pytest.raises(Forbidden):
                permission2()

            current_auth.permissions.add(
                'allow-that'
            )  # FIXME! Shouldn't this be a frozenset?

            assert permission1.is_available() is False
            assert permission2.is_available() is True

            with pytest.raises(Forbidden):
                permission1()
            assert permission2() == 'allowed2'

            current_auth.permissions.add('allow-this')

            assert permission1.is_available() is True
            assert permission2.is_available() is True

            assert permission1() == 'allowed1'
            assert permission2() == 'allowed2'
