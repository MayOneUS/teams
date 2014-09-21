# teams

The backend app that powers [my.mayday.us](my.mayday.us).

Report improvements/bugs at https://github.com/MayOneUS/teams/issues.


## Design Docs

Please see https://github.com/MayOneUS/wiki/wiki/My-SuperPAC-design-doc.


## Setup

1. `cp config_NOCOMMIT_README config_NOCOMMIT.py`
2. download and setup [Google App Engine for Python here](https://developers.google.com/appengine/downloads)
3. Run this app with `dev_appserver.py .`
4. If you want to run [MayOneUS/pledgeservice](https://github.com/MayOneUS/pledgeservice) simultaneously, which you
   will need to for testing submission of forms and other things, run this app on a separate port other than the
   default 8080 to avoid port collisions. This can done by running
   `dev_appserver.py --port SOME_OTHER_FREE_PORT_LIKE_8081 .`.
