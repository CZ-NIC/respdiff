FROM registry.labs.nic.cz/knot/respdiff/knot-resolver-buildenv
ARG GIT_SHA
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>

RUN git clone --recursive -j8 https://gitlab.labs.nic.cz/knot/knot-resolver.git /var/opt/knot-resolver
WORKDIR /var/opt/knot-resolver
RUN git checkout $GIT_SHA
RUN mkdir .install
RUN make PREFIX=/var/opt/knot-resolver/.install LDFLAGS="-Wl,-rpath=/var/opt/knot-resolver/.install/lib"
RUN make install PREFIX=/var/opt/knot-resolver/.install

CMD /var/opt/knot-resolver/.install/sbin/kresd -c /etc/knot-resolver/kresd.conf -K /etc/knot-resolver/root.keys -v /dev/shm
