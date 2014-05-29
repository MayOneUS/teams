#!/bin/bash

export PATH=$PATH:/google_appengine

stunnel4 /etc/stunnel/https.conf
cd /develop
npm install
npm start
