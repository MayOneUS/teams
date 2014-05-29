#/bin/bash

docker build -t mayone-teams-dev .

docker run -t -i mayone-teams-dev /develop/.docker-entry.sh
