import Cookie
import hashlib
import json
import logging
import urllib

from google.appengine.api import urlfetch
import webapp2


class TestAuthService(object):

  requires_https = False

  def __init__(self):
    self._logged_in = False
    self._user = None

  def _login(self, name, provider):
    self._logged_in = True
    self._user = {
        "user_id": hashlib.md5("%s:%s" % (provider, name)).hexdigest(),
        "name": name,
        "provider": provider}

  def _logout(self):
    self._logged_in = False

  def _loginLink(self, provider, return_to):
    return "/_testing/auth?%s" % urllib.urlencode({
        "action": "login",
        "provider": provider,
        "return_to": return_to})

  def getAuthResponse(self, auth_token, return_to):
    if not self._logged_in:
      return {
          "logged_in": False,
          "login_links": {
              "google": self._loginLink("google", return_to),
              "facebook": self._loginLink("facebook", return_to),
              "twitter": self._loginLink("twitter", return_to),
              "yahoo": self._loginLink("yahoo", return_to)}}
    return {
      "logged_in": True,
      "user": self._user}

  def getLogoutLink(self, return_to):
    return "/_testing/auth?%s" % urllib.urlencode({
        "action": "logout",
        "return_to": return_to})

  def handlers(self):
    return [webapp2.Route(r'/_testing/auth', TestAuthHandler,
                          defaults={"service": self})]


class TestAuthHandler(webapp2.RequestHandler):
  def get(self, service):
    action = self.request.get("action")
    if action == "logout":
      service._logout()
      return self.redirect(str(self.request.get("return_to")))
    if action == "login":
      return self.response.write("""
        <form method="post">
        Log in to fake {provider}<br/>
        Name: <input type="text" name="user_name" /><br/>
        <input type="submit" />
        </form>
      """.format(provider=self.request.get("provider")))
    raise Exception("unknown action")

  def post(self, service):
    action = self.request.get("action")
    if action == "login":
      service._login(
          self.request.get("user_name"), self.request.get("provider"))
      return self.redirect(str(self.request.get("return_to")))
    raise Exception("unknown action")


class ProdAuthService(object):

  requires_https = True

  def __init__(self, service_url):
    self.url = service_url

  def getAuthResponse(self, auth_token, return_to):
    c = Cookie.SimpleCookie()
    c["auth"] = auth_token
    try:
      resp = urlfetch.fetch(
          "%s/v1/current_user?%s" % (self.url, urllib.urlencode({
              "return_to": return_to})),
          headers={"Cookie": c["auth"].OutputString()},
          follow_redirects=False,
          validate_certificate=True)
      if resp.status_code != 200:
        raise Exception("Unexpected authentication error: %s", resp.content)
      return json.loads(resp.content)
    except Exception:
      logging.exception("failed getting current user, assuming logged out")
      return {"logged_in": False, "login_links": {}}

  def getLogoutLink(self, return_to):
    return "%s/v1/logout?%s" % (self.url, urllib.urlencode({
        "return_to": return_to}))

  def handlers(self):
    return []
