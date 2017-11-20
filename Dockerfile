FROM debian:stretch-slim

RUN set -x \
	&& apt-get update \
	&& apt-get install python3-flask python3-yaml
