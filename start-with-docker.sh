#/bin/bash

docker build -t mayone-teams-dev .

docker run -t -i -p 443:443 mayone-teams-dev /develop/.docker-entry.sh
