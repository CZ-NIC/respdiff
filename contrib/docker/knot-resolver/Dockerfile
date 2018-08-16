ARG KNOT_BRANCH=2.7

# first build stage, it will not persist in the final image
FROM registry.labs.nic.cz/knot/respdiff/knot-resolver-buildenv:knot-$KNOT_BRANCH as intermediate

# https://docs.docker.com/engine/reference/builder/#understand-how-arg-and-from-interact
ARG SSH_PRIVATE_KEY
ARG GIT_SHA

RUN mkdir /root/.ssh/
RUN echo "${SSH_PRIVATE_KEY}" > /root/.ssh/id_rsa
RUN chmod 0600 /root/.ssh/id_rsa

RUN touch /root/.ssh/known_hosts
RUN ssh-keyscan gitlab.labs.nic.cz >> /root/.ssh/known_hosts

RUN git clone --recursive -j8 https://gitlab.labs.nic.cz/knot/knot-resolver.git /var/opt/knot-resolver
RUN \
	cd /var/opt/knot-resolver; \
	git checkout "${GIT_SHA}" -- || (\
		cd /var/opt; \
		rm -rf /var/opt/knot-resolver; \
		git clone --recursive -j8 git@gitlab.labs.nic.cz:knot/knot-resolver-security.git /var/opt/knot-resolver; \
		cd /var/opt/knot-resolver; \
		git checkout "${GIT_SHA}" --)


# actual image
FROM registry.labs.nic.cz/knot/respdiff/knot-resolver-buildenv:knot-$KNOT_BRANCH
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>

COPY --from=intermediate /var/opt/knot-resolver /var/opt/knot-resolver
WORKDIR /var/opt/knot-resolver

RUN mkdir .install
RUN make PREFIX=/var/opt/knot-resolver/.install LDFLAGS="-Wl,-rpath=/var/opt/knot-resolver/.install/lib"
RUN make install PREFIX=/var/opt/knot-resolver/.install

RUN mkdir /log

CMD /var/opt/knot-resolver/.install/sbin/kresd -c /etc/knot-resolver/kresd.conf -K /etc/knot-resolver/root.keys -v -f 1 /dev/shm >> /log/kresd.log
