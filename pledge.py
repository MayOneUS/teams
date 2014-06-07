import json

from google.appengine.api import urlfetch


class TestPledgeService(object):
  def loadPledgeInfo(self, user_token):
    if user_token.startswith("valid"):
      return {"zip_code": "55555",
              "name": "Test User",
              "email": "testuser@example.com",
              "pledge_amount_cents": 10000}
    return None

  def getTeamTotal(self, team):
    return (51800, 7)


class ProdPledgeService(object):
  def __init__(self, url):
    self.url = url

  def fetcher(self, url):
    return urlfetch.fetch(url, follow_redirects=False,
                          validate_certificate=True)

  def loadPledgeInfo(self, user_token):
    resp = self.fetcher("%s/user-info/%s" % (self.url, user_token))
    if resp.status_code == 404:
      return None
    if resp.status_code != 200:
      raise Exception("Unexpected authentication error: %s", resp.content)
    return json.loads(resp.content)["user"]

  def getTeamTotal(self, team):
    resp = self.fetcher("%s/total?team=%s" % (self.url, str(team.key())))
    if resp.status_code != 200:
      raise Exception("unexpected total error %d: %s", resp.status_code,
          resp.content)
    return tuple(map(int,
        resp.content.replace("(", "").replace(")", "").split(",")))
