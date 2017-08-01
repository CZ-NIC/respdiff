FROM cznic/ubuntu:16.04
MAINTAINER Knot DNS <knot-dns@labs.nic.cz>

WORKDIR /root
CMD ["/bin/bash"]

# Docker image `cznic/ubuntu-respdif:16.04` is used for running respdiff tools with unbound running on port 53535 and bind on port 53533
#

RUN LC_ALL=C.UTF-8 add-apt-repository ppa:raphink/augeas -y
RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install unzip wget python3-pip -y

#install unbound
RUN apt-get install unbound unbound-anchor -y
RUN printf "server:\n interface: 127.0.0.1@53535\n use-syslog: yes\nremote-control:\n control-enable: no\n" >> /etc/unbound/unbound.conf


#install bind
RUN apt-get install bind9 -y
RUN printf 'options {\n directory "/var/cache/bind";\n listen-on port 53533 { 127.0.0.1; };\n listen-on-v6 port 53533 { ::1; };\n};\n' > /etc/bind/named.conf.options

#get respdiff
RUN wget https://gitlab.labs.nic.cz/knot/resolver-benchmarking/repository/archive.zip?ref=v2 -O respdiff.zip #fix me when repository is merged
RUN unzip respdiff.zip
RUN cp -R resolver-benchmarking*/response_differences/respdiff /var/opt/respdiff
RUN pip3 install -r resolver-benchmarking*/requirements.txt
RUN rm -rf respdiff.zip resolver-benchmarking*
