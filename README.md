# teams

team page service

Please see https://github.com/MayOneUS/wiki/wiki/My-SuperPAC-design-doc


## Quickstart
Make sure you have docker.  If not: see below Installing Docker

Run

    docker run -t -i -v /path/to/checkout:/develop jtolds/mayone-gae /bin/bash

Then inside that new shell

    stunnel4 /etc/stunnel/https.conf
    cd /develop
    npm install
    npm start

Run `docker ps` to find the container id of your running instance, then find
its IP address by running

    docker inspect -f "{{.NetworkSettings.IPAddress}}" container_id

Finally, add the container's IP and `my.mayone.us` to your `/etc/hosts` file.

Now, `https://my.mayone.us` should resolve and display the information in
`markup/index.jade` automatically on change.

For any of the login stuff in backend/ to work, you'll need to set up
https://github.com/MayOneUS/authservice

N.B.: it looks like the GAE dev server's urlfetch service doesn't respect
/etc/hosts? I'm not totally sure - you may need to edit backend/main.py's
AUTH_SERVICE_REQ variable to point to your auth service's IP directly.

## Installing docker
On Mac OSX:
  Install ruby
  
  Install brew
  
  Get VirtualBox
  
  
  Follow the instructions here: http://docs.docker.io/installation/mac/
  
  Make sure you don't miss: 
  
     Configure the Docker OS X Client
     
     Running the Docker daemon via boot2docker
     

  
