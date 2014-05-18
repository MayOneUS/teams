import Cookie
import json
import logging
import urllib
import webapp2

from google.appengine.api import urlfetch

AUTH_SERVICE_PUB = "https://auth.mayone.us"
AUTH_SERVICE_REQ = AUTH_SERVICE_PUB  # "http://172.17.0.2"


class BaseHandler(webapp2.RequestHandler):

  @webapp2.cached_property
  def auth_response(self):
    c = Cookie.SimpleCookie()
    c["auth"] = self.request.cookies.get("auth", "")
    self.request.scheme = "https"
    resp = urlfetch.fetch(
        "%s/v1/current_user?%s" % (AUTH_SERVICE_REQ, urllib.urlencode({
            "return_to": self.request.url})),
        headers={"Cookie": c["auth"].OutputString()},
        follow_redirects=False,
        validate_certificate=True)
    if resp.status_code != 200:
      raise Exception("Unexpected authentication error: %s", resp.content)
    return json.loads(resp.content)

  @property
  def logged_in(self):
    return self.auth_response["logged_in"]

  @property
  def current_user(self):
    return self.auth_response.get("user")

  @property
  def login_links(self):
    return self.auth_response.get("login_links")

  @property
  def logout_link(self):
    self.request.scheme = "https"
    return "%s/v1/logout?%s" % (AUTH_SERVICE_PUB, urllib.urlencode({
        "return_to": self.request.url}))


class IndexHandler(BaseHandler):
  def get(self):
    if self.logged_in:
      self.response.write('<a href="%s">logout</a><br/>' % self.logout_link)
      self.response.write(str(self.current_user))
    else:
      self.response.write('<a href="%s">log in via facebook</a><br/>' %
                          self.login_links["facebook"])
      self.response.write('<a href="%s">log in via google</a><br/>' %
                          self.login_links["google"])


app = webapp2.WSGIApplication([
  (r'/.*', IndexHandler)], debug=False)
