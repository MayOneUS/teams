import json
import logging

import urllib
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

  def getLeaderboard(self, offset=None, limit=None, orderBy=None):
    return [{"total_cents": 100,
             "num_pledges": 2,
             "team": "ahRkZXZ-bWF5ZGF5LXBhYy10ZWFtc3IRCxIEVGVhbRiAgICAgICACgw"}] * limit

  def updateMailchimp(self, team):
    return None


class ProdPledgeService(object):
  def __init__(self, url):
    self.url = url

  def fetcher(self, url):
    return urlfetch.fetch(url, follow_redirects=False,
                          validate_certificate=True)      
                        
  def poster(self, url, post_data):
    post_data_encoded = urllib.urlencode(post_data)
    return urlfetch.fetch(url, follow_redirects=False,
                          validate_certificate=False, 
                          method=urlfetch.POST, 
                          payload=post_data_encoded,
                          headers={'Content-Type': 'application/x-www-form-urlencoded'}) 

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

  def getLeaderboard(self, offset=None, limit=None, orderBy=None):
    params = {}
    if offset is not None:
      params["offset"] = offset
    if limit is not None:
      params["limit"] = limit
    if orderBy is not None:
      params["orderBy"] = orderBy
    
    resp = self.fetcher("%s/r/leaderboard?%s" % (
        self.url, urllib.urlencode(params)))
    if resp.status_code != 200:
      raise Exception("unexpected leaderboard error %d: %s", resp.status_code,
          resp.content)
    return json.loads(resp.content)["teams"]

  def updateMailchimp(self, team):
    user_info = self.loadPledgeInfo(team.user_token)       
    #logging.info("UT: " + str(team.user_token))
    #logging.info("UI: " + str(user_info))
    if user_info:
      form_fields = {
        "email": user_info['email'],
        "pledgePageSlug": team.primary_slug,
      }
      url="%s/r/subscribe" % self.url
      #logging.info("OK we are posting:" + str(form_fields))      
      result = self.poster(url=url, post_data=form_fields)
      return result
    else:
      return None
