#!/usr/local/bin/python
#coding: utf-8

import tornado.httpserver
import tornado.httpclient
import tornado.ioloop
import tornado.options
import tornado.web
import memcache
from lxml import etree
import os, sys, time, hashlib, re
import pprint
import sgmllib
from xml.sax.saxutils import escape as html_escape
import urllib, urlparse
try:
    import simplejson as json
except ImportError:
    import json


from tornado.options import define, options

define("port", default=8001, help="run on the given port", type=int)

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
        ]
        tornado.web.Application.__init__(self, handlers, **settings)

class BaseHandler(tornado.web.RequestHandler):
    def __init__(self, *args, **kwargs):
        super(BaseHandler, self).__init__(*args, **kwargs)

        self.httpclient = tornado.httpclient.AsyncHTTPClient()
        self.url        = None
        self._callback_prefix_stack = list()
        self.context    = dict()
        self.page       = None

    def set_next_callback_prefix(self, prefix, err_handler=None):
        self._callback_prefix_stack.append((prefix, err_handler))

    def get(self):
        self._callback_prefix      = None
        self._callback_err_handler = None

        if len(self._callback_prefix_stack) > 0:
            self._callback_prefix, self._callback_err_handler \
                = self._callback_prefix_stack[0]
            self.url = getattr(self, self._callback_prefix + '_build_url')()
            del self._callback_prefix_stack[0]
        else:
            self.url = self.build_url()

        if isinstance(self.url, list):
            self.fetch_urls()
        else:
            self.fetch_url()

    def build_url(self):
        raise tornado.web.HTTPError(500)

    @tornado.web.asynchronous
    def fetch_url(self):
        if self.mc_time > 0:
            response = self.mc.get(self.mc_key(self.url))
            if response:
                self.response(response)
                return

        if len(self.url) > 1024:
            url, body = self.url.split('?')
            self.httpclient.fetch(url, method='POST', body=body,
                                  callback=self.async_callback(self.response))
        else:
            self.httpclient.fetch(self.url,
                                  callback=self.async_callback(self.response))

    def response(self, response):
        if not isinstance(response, dict):
            response = { 'error':response.error,
                         'body': response.body, }
        if response['error']:
            message_log(response['error'])
            try:
                tree = etree.fromstring(response['body'])
                message_log(response['body'])
            except:
                pass

            if self._callback_err_handler:
                self._callback_err_handler(response['error'])
            else:
                raise tornado.web.HTTPError(500)
        else:
            if self.mc_time > 0:
                self.mc.set(self.mc_key(self.url), response, time=self.mc_time)

            if self._callback_prefix:
                context = getattr(self, self._callback_prefix + '_parse_response')(response)
            else:
                context = self.parse_response(response)

            if isinstance(context, dict):
                self.context = dict(self.context, **context)

        if len(self._callback_prefix_stack) > 0:
            self.get()
        else:
            self.page = self.build_page()
            self.finish()

    def parse_response(self, response):
        raise tornado.web.HTTPError(500)

    def build_page(self):
        return """<?xml version="1.0" encoding="UTF-8"?>
<response status="404"></response>"""

    def finish(self, *args, **kwargs):
        if self.page:
            self.set_header('Content-Type', 'text/xml')
            self.write(self.page)
        super(BaseHandler, self).finish(*args, **kwargs)

    @tornado.web.asynchronous
    def fetch_urls(self, index=0):
        callback_func = lambda response: self.responses(response, index)

        if len(self.url[index]) > 1024:
            url, body = self.url[index].split('?')
            self.httpclient.fetch(url, method='POST', body=body,
                                  callback=self.async_callback(callback_func))
        else:
            self.httpclient.fetch(self.url[index],
                                  callback=self.async_callback(callback_func))

    def responses(self, response, index=0):
        if response.error:
            raise tornado.web.HTTPError(500)

        response = { 'error':response.error,
                     'body': response.body, }

        if self.mc_time > 0:
            self.mc.set(self.mc_key(self.url[index]), response, time=self.mc_time)

        if self._callback_prefix:
            callback_method = self._callback_prefix + '_parse_response'
            context = getattr(self, callback_method)(response, index)
        else:
            context = self.parse_response(response, index)

        if isinstance(context, dict):
            self.context = dict(self.context, **context)

        if len(self.url) - 1 == index:
            if self._callback_prefix:
                callback_method = self._callback_prefix + '_all_complete'
                context = getattr(self, callback_method)()
            else:
                context = self.all_complete()

            if isinstance(context, dict):
                self.context = dict(self.context, **context)
        else:
            self.fetch_urls(index+1)
            return

        if len(self._callback_prefix_stack) > 0:
            self.get()
        else:
            self.page = self.build_page()
            self.finish()

    def all_complete(self):
        pass

class ExampleSingleProxyHandler(BaseHandler):
    def build_url(self):
        querys = set()

        return exampleUrl + '?' + '&'.join([ k + '=' + str(v) for k, v in querys ])

    def parse_response(self, response):
        j = json.load(response['body'])

        # return dictionary
        return parsed_context

    def build_page(self):
        # self.context .. parsed_context

        return response_page

if __name__ == "__main__":
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port, address='127.0.0.1')
    tornado.ioloop.IOLoop.instance().start()


