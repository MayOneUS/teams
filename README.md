# teams

team page service

Please see https://github.com/MayOneUS/wiki/wiki/My-SuperPAC-design-doc


## Quickstart

After checking out the code, run

    cp backend/config_NOCOMMIT_README backend/config_NOCOMMIT.py

Then, run `npm install`.

To start the server, run `npm start` and go to `http://localhost:8080`.
That's it!

If you want to rapidly set up a development environment that already has npm
and dependencies installed using docker, try running

    docker run -t -i -v /path/to/checkout:/develop jtolds/mayone-gae /bin/bash

Then in that new shell

    cd /develop
    npm install
    npm start
