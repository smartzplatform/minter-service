FROM centos:latest as build
RUN yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm \
	&& yum install -y python34 python34-pip python34-devel nodejs npm \
	&& yum groups install -y 'Development Tools' \
	&& yum clean all \
	&& rm -rf /var/cache/yum

WORKDIR /app
COPY ./ /app

RUN python3 -m venv /venv \
	&& /venv/bin/pip3 install -r requirements.txt --no-cache-dir
RUN npm install --prefix /app --only=dev

RUN /app/bin/test_wrapper.sh 
RUN rm -f /app/bin/test_wrapper.sh
RUN /app/bin/deploy /deploy


FROM centos:latest

WORKDIR /app
COPY --from=build /deploy /app
COPY --from=build /venv /venv

RUN yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm \
	&& yum install -y python34 uwsgi uwsgi-plugin-python3 \
	&& yum clean all \
	&& rm -rf /var/cache/yum \
	&& mv /app/bin/shell /usr/local/bin

VOLUME [ "/app/data", "/app/conf/minter.conf" ]

# start app
CMD [ "/app/bin/start-service.sh" ]

