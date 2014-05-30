import json

from google.appengine.api import urlfetch


class TestPledgeService(object):

  def loadPledgeInfo(self, user_token):
    if user_token == "abcd":
      return {"zip_code": "55555",
              "name": "Test User",
              "pledge_amount_cents": 10000}
    return None


class ProdPledgeService(object):

  def __init__(self, url):
    self.url = url

  def loadPledgeInfo(self, user_token):
    resp = urlfetch.fetch("%s/user-info/%s" % (self.url, user_token),
        follow_redirects=False, validate_certificate=True)
    if resp.status_code == 404:
      return None
    if resp.status_code != 200:
      raise Exception("Unexpected authentication error: %s", resp.content)
    return json.loads(resp.content)["user"]
