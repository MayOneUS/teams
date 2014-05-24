import Cookie
import functools
import json
import logging
import os
import re
import urllib

import jinja2
import markdown
import webapp2

from google.appengine.api import urlfetch
from google.appengine.ext import db

AUTH_SERVICE_PUB = "https://auth.mayone.us"
AUTH_SERVICE_REQ = AUTH_SERVICE_PUB  # "http://172.17.0.2"

JINJA = jinja2.Environment(
  loader=jinja2.FileSystemLoader('templates/'),
  extensions=['jinja2.ext.autoescape'],
  autoescape=True)

YOUTUBE_ID_VALIDATOR = re.compile(r'^[\w\-]+$')
INTEGER_VALIDATOR = re.compile(r'^[0-9]+$')
INVALID_SLUG_CHARS = re.compile(r'[^\w-]')
MULTIDASH_RE = re.compile(r'-+')
SLUG_TOKEN_AMOUNT = 2


class BaseHandler(webapp2.RequestHandler):

  @webapp2.cached_property
  def auth_response(self):
    c = Cookie.SimpleCookie()
    c["auth"] = self.request.cookies.get("auth", "")
    self.request.scheme = "https"
    try:
      resp = urlfetch.fetch(
          "%s/v1/current_user?%s" % (AUTH_SERVICE_REQ, urllib.urlencode({
              "return_to": self.request.url})),
          headers={"Cookie": c["auth"].OutputString()},
          follow_redirects=False,
          validate_certificate=True)
      if resp.status_code != 200:
        raise Exception("Unexpected authentication error: %s", resp.content)
      return json.loads(resp.content)
    except Exception:
      logging.exception("failed getting current user, assuming logged out")
      return {"logged_in": False, "login_links": {}}

  @property
  def logged_in(self):
    return self.auth_response["logged_in"]

  @property
  def current_user(self):
    return self.auth_response.get("user")

  @property
  def login_links(self):
    return self.auth_response.get("login_links") or {}

  @property
  def logout_link(self):
    self.request.scheme = "https"
    return "%s/v1/logout?%s" % (AUTH_SERVICE_PUB, urllib.urlencode({
        "return_to": self.request.url}))

  def render_template(self, template, **kwargs):
    if self.logged_in:
      data = {
        "logged_in": True,
        "current_user": self.current_user,
        "logout_link": self.logout_link}
    else:
      data = {
        "logged_out": False,
        "login_links": self.login_links}
    data.update(kwargs)
    self.response.write(JINJA.get_template(template).render(data))

  def notfound(self):
    self.response.status = 404
    self.render_template("404.html")


class Team(db.Model):
  primary_slug = db.StringProperty()
  title = db.StringProperty(required=True)
  description = db.TextProperty(required=True)

  goal_dollars = db.IntegerProperty()
  youtube_id = db.StringProperty()
  zip_code = db.StringProperty()

  # for use with google.appengine.api.imagesget_serving_url
  image = db.BlobProperty()


class Slug(db.Model):
  # the key is the slug name
  team = db.ReferenceProperty(Team, required=True)

  @staticmethod
  @db.transactional
  def _make(full_slug, team):
    e = Slug.get_by_key_name(full_slug)
    if e is not None:
      return False
    Slug(key_name=full_slug, team=team).put()
    return True

  @staticmethod
  def new(team):
    slug_name = MULTIDASH_RE.sub('-', INVALID_SLUG_CHARS.sub('-', team.title))
    token_amount = SLUG_TOKEN_AMOUNT
    while True:
      slug_prefix = os.urandom(token_amount).encode('hex')
      token_amount += 1
      full_slug = "%s-%s" % (slug_prefix, slug_name)
      if Slug._make(full_slug, team):
        return full_slug


class AdminToTeam(db.Model):
  """This class represents an admin to team relationship, since it's
  many-to-many
  """
  user = db.StringProperty(required=True)  # from current_user["user_id"]
  team = db.ReferenceProperty(Team, required=True)


def require_login(fn):
  @functools.wraps(fn)
  def new_handler(self, *args, **kwargs):
    if not self.logged_in:
      self.redirect("/")
      return
    return fn(self, *args, **kwargs)
  return new_handler


class IndexHandler(BaseHandler):
  def get(self):
    # TODO: shouldn't return all teams, should get list of top n
    self.render_template("index.html", teams=list(Team.all()))


class NotFoundHandler(BaseHandler):
  def get(self):
    self.notfound()


class TeamBaseHandler(BaseHandler):
  def validate(self, slug):
    s = Slug.get_by_key_name(slug)
    if s is None:
      self.notfound()
      return None, False, False
    team = s.team
    if team is None:
      self.notfound()
      return None, False, False
    primary = True
    if team.primary_slug and team.primary_slug != slug:
      primary = False
    is_admin = False
    if self.logged_in:
      if AdminToTeam.all().filter("team =", team).filter(
          "user =", self.current_user["user_id"]).get() is not None:
        is_admin = True
    return team, primary, is_admin


class TeamHandler(TeamBaseHandler):
  def get(self, slug):
    team, primary, is_admin = self.validate(slug)
    if team is None:
      return
    if not primary:
      return self.redirect("/t/%s" % team.primary_slug, permanent=True)
    if is_admin:
      edit_url = "/t/%s/edit" % team.primary_slug
    else:
      edit_url = None
    self.render_template(
        "show_team.html", team=team, edit_url=edit_url,
        description_rendered=markdown.markdown(
            jinja2.escape(team.description)))


class DashboardHandler(BaseHandler):
  @require_login
  def get(self):
    teams = [a.team for a in
             AdminToTeam.all().filter('user =',
                self.current_user["user_id"])]
    self.render_template("dashboard.html", teams=teams)


class NewTeamHandler(BaseHandler):
  @require_login
  def get(self):
    self.render_template("new_team.html")

  @require_login
  def post(self):
    # TODO: this is horrible. should use WTForms or something and
    # NOT COPY PASTE
    title = self.request.get("title")
    description = self.request.get("description")
    goal_dollars = self.request.get("goal_dollars") or None
    if goal_dollars:
      goal_dollars = int(goal_dollars)
    youtube_id = self.request.get("youtube_id") or None
    if youtube_id and not YOUTUBE_ID_VALIDATOR.match(youtube_id):
      raise Exception("invalid youtube id")
    zip_code = self.request.get("zip_code") or None
    if zip_code and not INTEGER_VALIDATOR.match(zip_code):
      raise Exception("invalid zip_code")
    team = Team(title=title, description=description,
                goal_dollars=goal_dollars, youtube_id=youtube_id,
                zip_code=zip_code)
    team.put()
    # TODO: can i reference a team before putting it in other reference
    # properties? should check
    AdminToTeam(user=self.current_user["user_id"], team=team).put()
    team.primary_slug = Slug.new(team)
    team.put()
    self.redirect("/t/%s" % team.primary_slug)


class EditTeamHandler(TeamBaseHandler):
  # require_login unneeded because we do the checking ourselves with validate
  def get(self, slug):
    team, primary, is_admin = self.validate(slug)
    if team is None:
      return
    if not primary:
      return self.redirect("/t/%s/edit" % team.primary_slug, permanent=True)
    if not is_admin:
      return self.redirect("/t/%s" % team.primary_slug)
    self.render_template("edit_team.html", team=team)

  # require_login unneeded because we do the checking ourselves with validate
  def post(self, slug):
    team, _, is_admin = self.validate(slug)
    if team is None:
      return
    if not is_admin:
      return self.redirect("/t/%s" % team.primary_slug)

    # TODO: this is horrible. should use WTForms or something and
    # NOT COPY PASTE
    team.title = self.request.get("title")
    team.description = self.request.get("description")
    goal_dollars = self.request.get("goal_dollars") or None
    if goal_dollars:
      team.goal_dollars = int(goal_dollars)
    else:
      team.goal_dollars = None
    youtube_id = self.request.get("youtube_id") or None
    if youtube_id and not YOUTUBE_ID_VALIDATOR.match(youtube_id):
      raise Exception("invalid youtube id")
    team.youtube_id = youtube_id
    zip_code = self.request.get("zip_code") or None
    if zip_code and not INTEGER_VALIDATOR.match(zip_code):
      raise Exception("invalid zip_code")
    team.zip_code = zip_code
    team.primary_slug = Slug.new(team)
    team.put()
    self.redirect("/t/%s" % team.primary_slug)


app = webapp2.WSGIApplication([
  (r'/t/([^/]+)/?', TeamHandler),
  (r'/t/([^/]+)/edit?', EditTeamHandler),
  (r'/dashboard/?', DashboardHandler),
  (r'/dashboard/new/?', NewTeamHandler),
  (r'/?', IndexHandler),
  (r'.*', NotFoundHandler)], debug=False)
