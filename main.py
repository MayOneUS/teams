import csv
import functools
import hashlib
import json
import os
import re
import urllib
import urlparse

import jinja2
import markdown
import webapp2
import wtforms
from wtforms.fields.html5 import IntegerField
from wtforms.widgets.html5 import URLInput

from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import db

import config_NOCOMMIT

JINJA = jinja2.Environment(
  loader=jinja2.FileSystemLoader('templates/'),
  extensions=['jinja2.ext.autoescape'],
  autoescape=True)
JINJA.filters["urlencode"] = lambda s: urllib.quote(s, safe="")

YOUTUBE_ID_VALIDATOR = re.compile(r'^[\w\-]+$')
INVALID_SLUG_CHARS = re.compile(r'[^\w-]')
MULTIDASH_RE = re.compile(r'-+')
SLUG_TOKEN_AMOUNT = 2

DEFAULT_TITLE = ""

DEFAULT_DESC = u"""\
I recently joined Lessig's citizen-funded MAYDAY.US campaign, an ambitious \
experiment to win a Congress committed to ending corruption in 2016, and we did something amazing: \
we raised $1 million dollars in 12 days. That's a ton of money, but it's not enough.

We're raising $5 million more by July 4, and I'm writing to my friends and family to \
ask if you can help us get the rest of the way there. If all of us who have supported \
the campaign so far each recruit just five matching pledges, we'd easily hit that goal. \
But I'd like to see if I can recruit ten of my friends to donate. So my question is: \
will you be one of those ten?

"""

PREVIOUS_PLEDGE_DESC = u"""\
I recently joined Lessig's citizen-funded MAYDAY.US campaign, an ambitious \
experiment to win a Congress committed to ending corruption in 2016, and we did something amazing: \
We raised $1 million dollars in 12 days. That's a ton of money, but it's not enough.

We're raising $5 million more by July 4, and I'm writing to my friends and family to \
ask if you can help us get the rest of the way there. If all of us who have supported \
the campaign so far each recruit just five matching pledges, we'd easily hit that goal. \
But I'd like to see if I can recruit ten of my friends to donate. So my question is: \
will you be one of those ten?

{signature}
"""


class BaseHandler(webapp2.RequestHandler):
  def dispatch(self, *args, **kwargs):
    if self.request.host == "my.mayone.us" and self.request.method == "GET":
      self.request.host = "my.mayday.us"
      return self.redirect(self.request.url)
    return webapp2.RequestHandler.dispatch(self, *args, **kwargs)

  @webapp2.cached_property
  def auth_response(self):
    if config_NOCOMMIT.auth_service.requires_https:
      self.request.scheme = "https"
    return config_NOCOMMIT.auth_service.getAuthResponse(
        self.request.cookies.get("auth", ""), self.request.url)

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
    if config_NOCOMMIT.auth_service.requires_https:
      self.request.scheme = "https"
    return config_NOCOMMIT.auth_service.getLogoutLink(self.request.url)

  @property
  def pledge_root_url(self):
    return config_NOCOMMIT.PLEDGE_SERVICE_URL

  def render_template(self, template, **kwargs):
    if self.logged_in:
      data = {
        "logged_in": True,
        "current_user": self.current_user,
        "logout_link": self.logout_link,
        "pledge_root_url": self.pledge_root_url,
        "current_url": self.request.url}
    else:
      data = {
        "logged_in": False,
        "login_links": self.login_links,
        "pledge_root_url": self.pledge_root_url,
        "current_url": self.request.url}
    data.update(kwargs)
    self.response.write(JINJA.get_template(template).render(data))

  def notfound(self):
    self.response.status = 404
    self.render_template("404.html")


class Team(db.Model):
  CURRENT_VERSION = 2

  primary_slug = db.StringProperty()
  title = db.StringProperty(required=True)
  description = db.TextProperty(required=True)

  goal_dollars = db.IntegerProperty()
  youtube_id = db.StringProperty()
  zip_code = db.StringProperty()

  # for use with google.appengine.api.images get_serving_url
  image = db.BlobProperty()
  gravatar = db.StringProperty()

  user_token = db.StringProperty()

  team_version = db.IntegerProperty(default=1)

  creation_time = db.DateTimeProperty(auto_now_add=True)
  modification_time = db.DateTimeProperty(auto_now=True)

  @classmethod
  def create(cls, **kwargs):
    kwargs["team_version"] = cls.CURRENT_VERSION
    team = cls(**kwargs)
    team.put()
    return team


class YoutubeIdField(wtforms.Field):
  widget = URLInput()

  def __init__(self, label=None, validators=None, **kwargs):
    wtforms.Field.__init__(self, label, validators, **kwargs)

  def _value(self):
    if self.data is not None:
      return u"https://www.youtube.com/watch?v=%s" % unicode(self.data)
    else:
      return ''

  def process_formdata(self, valuelist):
    self.data = None
    if valuelist:
      parsed = urlparse.urlparse(valuelist[0])
      if "youtube.com" not in parsed.netloc:
        raise ValueError(self.gettext("Not a valid Youtube URL"))
      video_args = urlparse.parse_qs(parsed.query).get("v")
      if len(video_args) != 1:
        raise ValueError(self.gettext("Not a valid Youtube URL"))
      youtube_id = video_args[0]
      if not YOUTUBE_ID_VALIDATOR.match(youtube_id):
        raise ValueError(self.gettext("Not a valid Youtube URL"))
      self.data = youtube_id


class ZipcodeField(wtforms.Field):
  """
  A text field, except all input is coerced to an integer.  Erroneous input
  is ignored and will not be accepted as a value.
  """
  widget = wtforms.widgets.TextInput()

  def __init__(self, label=None, validators=None, **kwargs):
    wtforms.Field.__init__(self, label, validators, **kwargs)

  def _value(self):
    if self.data is not None:
      return unicode(self.data)
    else:
      return ''

  def process_formdata(self, valuelist):
    self.data = None
    if valuelist:
      try:
        int(valuelist[0])
      except ValueError:
        self.data = None
        raise ValueError(self.gettext('Not a valid integer value'))
      else:
        self.data = valuelist[0]


class TeamForm(wtforms.Form):
  title = wtforms.StringField("Your Name", [
      wtforms.validators.Length(min=1, max=500)], default=DEFAULT_TITLE)
  description = wtforms.TextAreaField("Your Personal Message",
      [wtforms.validators.Length(min=1)],
      default=DEFAULT_DESC.format(title=DEFAULT_TITLE))

  goal_dollars = IntegerField("Goal", [wtforms.validators.optional()])
  youtube_id = YoutubeIdField("Youtube Video URL", [
      wtforms.validators.optional()])
  zip_code = ZipcodeField("Zip Code", [wtforms.validators.optional()])


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

  @staticmethod
  def memcacheKey(user_id, team):
    return repr((str(user_id), str(team.key())))


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
    if self.logged_in:
      return self.redirect("/dashboard")
    return self.redirect("/login")


class NotFoundHandler(BaseHandler):
  def get(self):
    self.notfound()


def isUserAdmin(user_id, team):
  return (memcache.get(AdminToTeam.memcacheKey(user_id, team)) or
          (AdminToTeam.all().filter("team =", team).filter(
              "user =", user_id).get() is not None))


def makeUserAdmin(user_id, team):
  AdminToTeam(user=user_id, team=team).put()
  memcache.add(AdminToTeam.memcacheKey(user_id, team), True, 30)


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
      if isUserAdmin(self.current_user["user_id"], team):
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


class LoginHandler(BaseHandler):
  def get(self):
    if self.logged_in:
      return self.redirect("/dashboard")
    self.render_template("login.html")


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
    self.render_template("new_team.html", form=TeamForm())

  @require_login
  def post(self):
    form = TeamForm(self.request.POST)
    if not form.validate():
      return self.render_template("new_team.html", form=form)
    team = Team.create(title=form.title.data,
                       description=form.description.data,
                       goal_dollars=form.goal_dollars.data,
                       youtube_id=form.youtube_id.data,
                       zip_code=form.zip_code.data)
    # TODO: can i reference a team before putting it in other reference
    # properties? should check
    team.primary_slug = Slug.new(team)
    team.put()
    makeUserAdmin(self.current_user["user_id"], team)
    return self.redirect("/t/%s" % team.primary_slug)


class FromPledgeBaseHandler(BaseHandler):
  def add_to_user(self, team):
    if self.logged_in:
      if not isUserAdmin(self.current_user["user_id"], team):
        makeUserAdmin(self.current_user["user_id"], team)


class NewFromPledgeHandler(FromPledgeBaseHandler):
  def get(self, user_token):
    team = Team.all().filter('user_token =', user_token).get()
    if team is None:
      user_info = config_NOCOMMIT.pledge_service.loadPledgeInfo(user_token)
      if user_info is None:
        return self.notfound()
      user_pledge_dollars = int(user_info["pledge_amount_cents"]) / 100
      goal_dollars = user_pledge_dollars * 10
      if user_info["name"]:
        signature = "_Thank you,_\n\n_%s_" % user_info["name"]
      else:
        signature = "Thank you!"
      title = user_info["name"] or DEFAULT_TITLE
      form = TeamForm(data={
          "goal_dollars": str(goal_dollars),
          "title": title,
          "zip_code": str(user_info["zip_code"] or ""),
          "description": PREVIOUS_PLEDGE_DESC.format(
              pledge_dollars=user_pledge_dollars,
              signature=signature,
              title=title)})
    else:
      self.add_to_user(team)
      form = TeamForm(obj=team)
    self.render_template("new_from_pledge.html", form=form)

  def post(self, user_token):
    team = Team.all().filter('user_token =', user_token).get()
    if team is None:
      # just make sure this pledge exists
      user_info = config_NOCOMMIT.pledge_service.loadPledgeInfo(user_token)
      if user_info is None:
        return self.notfound()
    form = TeamForm(self.request.POST, team)
    if not form.validate():
      return self.render_template("new_from_pledge.html", form=form)
    if team is None:
      gravatar = "https://secure.gravatar.com/avatar/%s?%s" % (
        hashlib.md5(user_info['email'].lower()).hexdigest(),
        urllib.urlencode({'s': str('120')}))
      team = Team.create(title=form.title.data,
                         description=form.description.data,
                         zip_code=form.zip_code.data,
                         user_token=user_token,
                         gravatar=gravatar)
    else:
      form.populate_obj(team)
    self.add_to_user(team)
    team.primary_slug = Slug.new(team)
    team.put()
    if self.logged_in:
      return self.redirect("/t/%s" % team.primary_slug)
    return self.redirect("/dashboard/add_admin_from_pledge/%s" % user_token)


class AddAdminFromPledgeHandler(FromPledgeBaseHandler):
  def get(self, user_token):
    team = Team.all().filter('user_token =', user_token).get()
    if team is None:
      return self.notfound()
    if not self.logged_in:
      return self.render_template("add_admin_login.html", team=team)
    self.add_to_user(team)
    return self.redirect("/t/%s" % team.primary_slug)


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
    self.render_template("edit_team.html", form=TeamForm(obj=team))

  # require_login unneeded because we do the checking ourselves with validate
  def post(self, slug):
    team, _, is_admin = self.validate(slug)
    if team is None:
      return
    if not is_admin:
      return self.redirect("/t/%s" % team.primary_slug)
    form = TeamForm(self.request.POST, team)
    if not form.validate():
      return self.render_template("edit_team.html", form=form)
    form.populate_obj(team)
    team.primary_slug = Slug.new(team)
    team.put()
    self.redirect("/t/%s" % team.primary_slug)


class AdminHandler(webapp2.RequestHandler):
  def render_template(self, template, **data):
    self.response.write(JINJA.get_template(template).render(data))


class SiteAdminIndex(AdminHandler):
  def get(self):
    self.render_template("site_admin.html")


class SiteAdminCSV(AdminHandler):
  def get(self):
    self.response.headers.add_header("Content-Type", "text/csv")
    self.response.headers.add_header("Content-Disposition",
        "attachment; filename=teams.csv;")
    out = csv.DictWriter(self.response,
        ["key", "title", "slug", "url", "zip_code", "user_token",
         "user_token_name", "user_token_email", "crtime", "mtime", "version",
         "dollars", "pledges"])
    out.writeheader()
    for team in Team.all():
      dollars, pledges = config_NOCOMMIT.pledge_service.getTeamTotal(team)
      if team.user_token:
        user_info = config_NOCOMMIT.pledge_service.loadPledgeInfo(
            team.user_token)
        user_token_name = user_info["name"]
        user_token_email = user_info["email"]
      else:
        user_token_name = None
        user_token_email = None
      out.writerow({
          "key": str(team.key()),
          "title": team.title,
          "slug": team.primary_slug,
          "url": "%s/t/%s" % (self.request.application_url, team.primary_slug),
          "zip_code": team.zip_code,
          "user_token": team.user_token,
          "user_token_name": user_token_name,
          "user_token_email": user_token_email,
          "crtime": team.creation_time,
          "mtime": team.modification_time,
          "version": team.team_version,
          "dollars": dollars,
          "pledges": pledges})

app = webapp2.WSGIApplication(config_NOCOMMIT.auth_service.handlers() + [
  (r'/t/([^/]+)/?', TeamHandler),
  (r'/t/([^/]+)/edit?', EditTeamHandler),
  (r'/login/?', LoginHandler),
  (r'/dashboard/?', DashboardHandler),
  (r'/dashboard/new/?', NewTeamHandler),
  (r'/dashboard/new_from_pledge/(\w+)', NewFromPledgeHandler),
  (r'/dashboard/add_admin_from_pledge/(\w+)', AddAdminFromPledgeHandler),
  (r'/site-admin/?', SiteAdminIndex),
  (r'/site-admin/csv/?', SiteAdminCSV),
  (r'/?', IndexHandler),
  (r'.*', NotFoundHandler)], debug=False)
