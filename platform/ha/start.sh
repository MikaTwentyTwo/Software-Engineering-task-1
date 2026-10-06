#!/bin/sh
set -eu

: "${LB_NAME:?Missing LB_NAME}"
: "${LOCAL_IP:?Missing LOCAL_IP}"
: "${PEER_IP:?Missing PEER_IP}"
: "${PRIORITY:?Missing PRIORITY}"

envsubst '${LB_NAME}' \
    < /etc/haproxy/haproxy.cfg.template \
    > /etc/haproxy/haproxy.cfg

mkdir -p /etc/keepalived
cat > /etc/keepalived/keepalived.conf <<EOF
global_defs {
    router_id ${LB_NAME}
    enable_script_security
    script_user root
}

vrrp_script check_haproxy {
    script "/bin/pidof haproxy"
    interval 2
    fall 2
    rise 2
}

vrrp_instance CAMPUS_VIP {
    state BACKUP
    interface eth0
    virtual_router_id 51
    priority ${PRIORITY}
    advert_int 1

    unicast_src_ip ${LOCAL_IP}
    unicast_peer {
        ${PEER_IP}
    }

    virtual_ipaddress {
        192.168.49.250/24 dev eth0
    }

    track_script {
        check_haproxy
    }
}
EOF

haproxy -c -f /etc/haproxy/haproxy.cfg
haproxy -db -f /etc/haproxy/haproxy.cfg &
haproxy_pid=$!

keepalived --dont-fork --log-console \
    --use-file=/etc/keepalived/keepalived.conf &
keepalived_pid=$!

cleanup() {
    kill "$haproxy_pid" "$keepalived_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' TERM INT

while kill -0 "$haproxy_pid" 2>/dev/null &&
      kill -0 "$keepalived_pid" 2>/dev/null; do
    sleep 2
done

exit 1