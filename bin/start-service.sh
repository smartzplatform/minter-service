#!/bin/bash

chmod -R 777 /app/data
/usr/sbin/uwsgi \
	--http-socket :8000 \
        --master \
        --plugin python3 \
	--virtualenv /venv \
        --mount /minter-service=/app/bin/wsgi_app.py --callable app \
        --uid uwsgi --gid uwsgi \
        --die-on-term \
        --processes 4
