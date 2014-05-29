#/bin/bash

docker build -t mayone-teams-dev .

docker run -t -i -p 127.0.0.1:443:443 -p 127.0.0.1:8000:8000 mayone-teams-dev /develop/.docker-entry.sh
