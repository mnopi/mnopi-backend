from models import UserCategory, User, CategorizedDomain, UserCategorization, PageVisited, Search, PluginSession
import opendns
import constants

from tastypie.test import ResourceTestCase
from django.test import TestCase

from pymongo import MongoClient
import datetime
import json

API_URI = {
    'user': '/api/v1/user/',
    'login': '/api/v1/user/login/',
    'page_visited': '/api/v1/page_visited/',
    'html': '/api/v1/page_visited/html/',
    'search_query': '/api/v1/search_query/'
}

class CategorizableResourceTest(TestCase):
    """ Test case with OpenDNS categories loaded """

    def setUp(self):
        super(CategorizableResourceTest, self).setUp()
        for category in opendns.CATEGORIES.values():
            UserCategory.objects.create(name=category, taxonomy="opendns")

class AuthenticableResourceTest(ResourceTestCase):
    """ Test case with authentication capabilities """

    def setUp(self):
        super(AuthenticableResourceTest, self).setUp()

        # Create a user
        self.username = 'alfredo'
        self.password = '1aragon1'
        self.user = User.objects.create_user(self.username, 'alfredo@example.com', self.password)

    def perform_login(self):

        login_data = {
            'username': self.username,
            'key': self.password,
            'is_automatic': False,
            'plugin_version': constants.CURRENT_VERSION
        }
        result = self.api_client.post(API_URI['login'], data=login_data, format='json')
        result_json = json.loads(result.content)
        self.user_resource = result_json['user_resource']
        self.session_key = result_json['session_key']

class ModelsMongoTest(TestCase):
    """ Test case that initializes and destroys a mongodb database for testing purposes """

    from mnopi import models_mongo as test_mongo

    @classmethod
    def setUpClass(cls):
        super(ModelsMongoTest, cls).setUpClass()
        cls.test_mongo.db = MongoClient().mnopi_test

    @classmethod
    def tearDownClass(cls):
        super(ModelsMongoTest, cls).tearDownClass()
        cls.test_mongo.db.drop()




class UserResourceTest(ResourceTestCase):
    """ Login service tests """

    def setUp(self):
        super(UserResourceTest, self).setUp()

        # Create a user
        self.username = 'alfredo'
        self.password = '1aragon1'
        self.user = User.objects.create_user(self.username, 'alfredo@example.com', self.password)

        # Create an already opened session
        self.last_session_key = self.user.new_session()

        # Create an expired session
        self.expired_session_key = self.user.new_session()
        expired_session = PluginSession.objects.get(session_key=self.expired_session_key)
        expired_session.expiration_time -= datetime.timedelta(days=constants.PLUGIN_SESSION_EXPIRY_DAYS + 1)
        expired_session.save()

    def perform_login(self, username, key, is_automatic, plugin_version):
        login_data = {
            'username': username,
            'key': key,
            'is_automatic': is_automatic,
            'plugin_version': plugin_version
        }
        return self.api_client.post(API_URI['login'], data=login_data, format='json')

    def test_correct_password_login(self):
        resp = self.perform_login(username=self.username,
                                  key=self.password,
                                  is_automatic=False,
                                  plugin_version=constants.CURRENT_VERSION)
        self.assertValidJSONResponse(resp)

        deserialized_resp = self.deserialize(resp)
        self.assertKeys(deserialized_resp, ['result', 'session_key', 'user_resource'])
        self.assertEqual(deserialized_resp['result'], 'OK')
        self.assertEqual(deserialized_resp['user_resource'], API_URI['user'] + '%s/' % (self.user.id))

        # Check that a new session has been created
        self.assertEqual(PluginSession.objects.count(), 3)

    def test_correct_session_login(self):
        resp = self.perform_login(username=self.username,
                                  key=self.last_session_key,
                                  is_automatic=True,
                                  plugin_version=constants.CURRENT_VERSION)
        self.assertValidJSONResponse(resp)

        deserialized_resp = self.deserialize(resp)
        self.assertKeys(deserialized_resp, ['result', 'session_key', 'user_resource'])
        self.assertEqual(deserialized_resp['result'], 'OK')
        self.assertEqual(deserialized_resp['session_key'], self.last_session_key)
        self.assertEqual(deserialized_resp['user_resource'], API_URI['user'] + '%s/' % (self.user.id))

    def test_correct_password_login_plus_correct_session_login(self):
        resp = self.perform_login(username=self.username,
                                  key=self.password,
                                  is_automatic=False,
                                  plugin_version=constants.CURRENT_VERSION)
        deserialized_resp = self.deserialize(resp)

        new_resp = self.perform_login(username=self.username,
                                      key=deserialized_resp['session_key'],
                                      is_automatic=True,
                                      plugin_version=constants.CURRENT_VERSION)
        self.assertValidJSONResponse(resp)

        deserialized_new_resp = self.deserialize(new_resp)
        self.assertKeys(deserialized_resp, ['result', 'session_key', 'user_resource'])
        self.assertEqual(deserialized_new_resp['result'], 'OK')
        self.assertEqual(deserialized_resp['user_resource'], API_URI['user'] + '%s/' % (self.user.id))

    def test_incorrect_user_session_login(self):
        resp = self.perform_login(username="pepito",
                                  key=self.last_session_key,
                                  is_automatic=True,
                                  plugin_version=constants.CURRENT_VERSION)
        self.assertValidJSONResponse(resp)

        deserialized_resp = self.deserialize(resp)
        self.assertKeys(deserialized_resp, ['result', 'reason'])
        self.assertEqual(deserialized_resp, {
            'result': 'ERR',
            'reason': "INCORRECT_USER_PASSWORD"
        })

    def test_incorrect_key_session_login(self):
        resp = self.perform_login(username=self.username,
                                  key="1111",
                                  is_automatic=True,
                                  plugin_version=constants.CURRENT_VERSION)
        self.assertValidJSONResponse(resp)

        deserialized_resp = self.deserialize(resp)
        self.assertKeys(deserialized_resp, ['result', 'reason'])
        self.assertEqual(deserialized_resp, {
            'result': 'ERR',
            'reason': "UNEXPECTED_SESSION"
        })

    def test_expired_key_session_login(self):
        resp = self.perform_login(username=self.username,
                                  key=self.expired_session_key,
                                  is_automatic=True,
                                  plugin_version=constants.CURRENT_VERSION)
        self.assertValidJSONResponse(resp)

        deserialized_resp = self.deserialize(resp)
        self.assertKeys(deserialized_resp, ['result', 'reason'])
        self.assertEqual(deserialized_resp, {
            'result': 'ERR',
            'reason': "UNEXPECTED_SESSION"
        })

    def test_client_outdated_password_login(self):
        resp = self.perform_login(username=self.username,
                                  key=self.password,
                                  is_automatic=False,
                                  plugin_version="dummyversion")
        self.assertValidJSONResponse(resp)

        deserialized_resp = self.deserialize(resp)
        self.assertKeys(deserialized_resp, ['result', 'reason'])
        self.assertEqual(deserialized_resp, {
            'result': 'ERR',
            'reason': "CLIENT_OUTDATED"
        })

    def test_client_outdated_session_login(self):
        resp = self.perform_login(username=self.username,
                                  key=self.last_session_key,
                                  is_automatic=True,
                                  plugin_version="dummyversion")
        self.assertValidJSONResponse(resp)

        deserialized_resp = self.deserialize(resp)
        self.assertKeys(deserialized_resp, ['result', 'reason'])
        self.assertEqual(deserialized_resp, {
            'result': 'ERR',
            'reason': "CLIENT_OUTDATED"
        })

    def test_password_error_password_login(self):
        resp = self.perform_login(username=self.username,
                                  key="abcdefghi",
                                  is_automatic=False,
                                  plugin_version=constants.CURRENT_VERSION)
        self.assertValidJSONResponse(resp)

        deserialized_resp = self.deserialize(resp)
        self.assertKeys(deserialized_resp, ['result', 'reason'])
        self.assertEqual(deserialized_resp, {
            'result': 'ERR',
            'reason': "INCORRECT_USER_PASSWORD"
        })

    def test_user_error_password_login(self):
        resp = self.perform_login(username="pepito",
                                  key=self.password,
                                  is_automatic=False,
                                  plugin_version=constants.CURRENT_VERSION)
        self.assertValidJSONResponse(resp)

        deserialized_resp = self.deserialize(resp)
        self.assertKeys(deserialized_resp, ['result', 'reason'])
        self.assertEqual(deserialized_resp, {
            'result': 'ERR',
            'reason': "INCORRECT_USER_PASSWORD"
        })

class PageVisitedResourceTest(AuthenticableResourceTest, CategorizableResourceTest):
    """
    Page visited service tests

    Avoid doing many calls to perform_page_visited as they are very slow (query to opendns)
    """

    def setUp(self):
        super(PageVisitedResourceTest, self).setUp()
        self.perform_login()

    def perform_page_visited(self, url, user_resource=None, session_key=None):

        if user_resource is None:
            user_resource = self.user_resource
        if session_key is None:
            session_key = self.session_key

        page_visited_data = {
            'user_resource': user_resource,
            'session_key': session_key,
            'url': url
        }
        return self.api_client.post(API_URI['page_visited'], data=page_visited_data, format='json')

    def test_no_user(self):
        resp = self.perform_page_visited(url="http://www.lol.com",
                                         user_resource="/api/v1/user/18/",
                                         session_key=self.session_key)
        self.assertHttpUnauthorized(resp)

    def test_invalid_session_key(self):
        resp = self.perform_page_visited(url="http://www.lol.com",
                                         user_resource=self.user_resource,
                                         session_key=self.session_key + "a")
        self.assertHttpUnauthorized(resp)

    def test_no_url(self):
        resp = self.perform_page_visited(url="")
        self.assertHttpBadRequest(resp)

    def test_add_page_added(self):
        resp = self.perform_page_visited(url="http://www.lol.com")
        self.assertHttpOK(resp)

        num_pages = PageVisited.objects.filter(user=self.user, page_visited="http://www.lol.com").count()
        self.assertEqual(num_pages, 1)

        resp = self.perform_page_visited(url="http://lol.com")
        self.assertHttpOK(resp)

        num_pages = PageVisited.objects.filter(user=self.user).count()
        self.assertEqual(num_pages, 2)

    def test_two_domains_added(self):
        resp = self.perform_page_visited(url="http://www.lol.com")
        self.assertHttpOK(resp)

        domains = CategorizedDomain.objects.filter(domain="www.lol.com").count()
        self.assertEqual(domains, 1)

        resp = self.perform_page_visited(url="http://lol.com")
        self.assertHttpOK(resp)

        domains = CategorizedDomain.objects.filter(domain="lol.com").count()
        self.assertEqual(domains, 1)

    def test_domains_repeated(self):
        resp = self.perform_page_visited(url="http://www.lol.com")
        self.assertHttpOK(resp)

        resp = self.perform_page_visited(url="http://www.lol.com/2")
        self.assertHttpOK(resp)

        domains = CategorizedDomain.objects.filter(domain="www.lol.com").count()
        self.assertEqual(domains, 1)

    def test_categorized_domain(self):
        resp = self.perform_page_visited(url="http://www.lol.com")
        self.assertHttpOK(resp)

        domain = CategorizedDomain.objects.get(domain="www.lol.com")
        self.assertEqual([x.name for x in domain.categories.all()], ['Humor'])

    def test_categorized_domain_multiple_categories(self):
        resp = self.perform_page_visited(url="http://stackoverflow.com")
        self.assertHttpOK(resp)

        domain = CategorizedDomain.objects.get(domain="stackoverflow.com")
        self.assertEqual(set([x.name for x in domain.categories.all()]),
                         set(['Software/Technology', 'Research/Reference', 'Forums/Message boards']))

    def test_user_categorization(self):
        resp = self.perform_page_visited(url="http://stackoverflow.com")
        self.assertHttpOK(resp)

        categories = CategorizedDomain.objects.get(domain="stackoverflow.com").categories.all()
        for cat in categories:
            user_cat = UserCategorization.objects.get(user=self.user, category=cat)
            self.assertEqual(user_cat.weigh, 1)

        resp = self.perform_page_visited(url="http://stackoverflow.com")
        self.assertHttpOK(resp)

        categories = CategorizedDomain.objects.get(domain="stackoverflow.com").categories.all()
        for cat in categories:
            user_cat = UserCategorization.objects.get(user=self.user, category=cat)
            self.assertEqual(user_cat.weigh, 2)

class HtmlVisitedResourceTest(AuthenticableResourceTest, ModelsMongoTest):
    """ Html visited service tests """

    def setUp(self):
        super(HtmlVisitedResourceTest, self).setUp()
        self.perform_login()


    def perform_html_visited(self, url, html_code, user_resource=None, session_key=None):

        if user_resource is None:
            user_resource = self.user_resource
        if session_key is None:
            session_key = self.session_key

        html_visited_data = {
            'user_resource': user_resource,
            'session_key': session_key,
            'url': url,
            'html_code': html_code
        }
        return self.api_client.post(API_URI['html'], data=html_visited_data, format='json')

    #TODO: SEGUIR PRO AQUI

class SearchQueryResourceTest(AuthenticableResourceTest):
    """ Test case for search engines queries """

    def setUp(self):
        super(SearchQueryResourceTest, self).setUp()
        self.perform_login()

    def perform_search_query(self, search_query, search_results, user_resource=None, session_key=None):

        if user_resource is None:
            user_resource = self.user_resource
        if session_key is None:
            session_key = self.session_key

        search_query_data = {
            'user_resource': user_resource,
            'session_key': session_key,
            'search_query': search_query,
            'search_results': search_results
        }
        return self.api_client.post(API_URI['search_query'], data=search_query_data, format='json')

    ######################
    # Parameters checks
    ######################
    def test_user_empty(self):
        resp = self.perform_search_query(search_query="lolazos",
                                         search_results="http://lol.com",
                                         user_resource="",
                                         session_key=self.session_key)
        self.assertHttpUnauthorized(resp)

    def test_no_authenticated_user(self):
        resp = self.perform_search_query(search_query="lolazos",
                                         search_results="http://lol.com",
                                         user_resource="/api/v1/user/18/",
                                         session_key=self.session_key)
        self.assertHttpUnauthorized(resp)

    def test_session_key(self):
        resp = self.perform_search_query(search_query="lolazos",
                                         search_results="http://lol.com",
                                         user_resource=self.user_resource,
                                         session_key=self.session_key+"a")
        self.assertHttpUnauthorized(resp)

    def test_no_query(self):
        resp = self.perform_search_query(search_query="",
                                         search_results="http://lol.com",
                                         user_resource=self.user_resource,
                                         session_key=self.session_key)
        self.assertHttpBadRequest(resp)

    def test_no_search_results(self):
        resp = self.perform_search_query(search_query="lolazo",
                                         search_results="",
                                         user_resource=self.user_resource,
                                         session_key=self.session_key)
        self.assertHttpBadRequest(resp)

    ######################
    # Behaviour checks
    ######################
    def test_search_done(self):
        resp = self.perform_search_query(search_query="lolazo",
                                         search_results="http://lol.com")
        self.assertHttpCreated(resp)