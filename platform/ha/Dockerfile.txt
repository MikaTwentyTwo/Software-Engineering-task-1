FROM alpine:3.22
RUN apk add --no-cache haproxy keepalived socat iproute2 gettext
COPY start.sh /usr/local/bin/start-ha
COPY haproxy.cfg.template /etc/haproxy/haproxy.cfg.template
RUN sed -i 's/\r$//' /usr/local/bin/start-ha /etc/haproxy/haproxy.cfg.template \
    && chmod 755 /usr/local/bin/start-ha
ENTRYPOINT ["/bin/sh", "/usr/local/bin/start-ha"]