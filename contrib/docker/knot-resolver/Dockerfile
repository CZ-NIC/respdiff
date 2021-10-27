ARG KNOT_BRANCH=3.1

# first build stage, it will not persist in the final image
FROM registry.nic.cz/knot/respdiff/knot-resolver-buildenv:knot-$KNOT_BRANCH as intermediate
ENV DEBIAN_FRONTEND=noninteractive

# https://docs.docker.com/engine/reference/builder/#understand-how-arg-and-from-interact
ARG SSH_PRIVATE_KEY
ARG GIT_SHA

RUN mkdir /root/.ssh/
RUN echo "${SSH_PRIVATE_KEY}" > /root/.ssh/id_rsa
RUN chmod 0600 /root/.ssh/id_rsa

RUN touch /root/.ssh/known_hosts
RUN ssh-keyscan gitlab.nic.cz >> /root/.ssh/known_hosts

RUN git clone --recursive -j8 https://gitlab.nic.cz/knot/knot-resolver.git /var/opt/knot-resolver
RUN \
	cd /var/opt/knot-resolver; \
	(git checkout "${GIT_SHA}" -- && git submodule update) || (\
		cd /var/opt; \
		rm -rf /var/opt/knot-resolver; \
		git clone --recursive -j8 git@gitlab.nic.cz:knot/security/knot-resolver.git /var/opt/knot-resolver; \
		cd /var/opt/knot-resolver; \
		git checkout "${GIT_SHA}" --; \
		git submodule update)


# actual image
FROM registry.nic.cz/knot/respdiff/knot-resolver-buildenv:knot-$KNOT_BRANCH
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>
ARG MESONARGS
ARG CFLAGS
ENV DEBIAN_FRONTEND=noninteractive

COPY --from=intermediate /var/opt/knot-resolver /var/opt/knot-resolver
WORKDIR /var/opt/knot-resolver

RUN mkdir .install
RUN meson build_respdiff --prefix=/var/opt/knot-resolver/.install --default-library=static ${MESONARGS}
RUN ninja -C build_respdiff install

RUN mkdir /log

COPY kresd.entrypoint.sh /

ENTRYPOINT ["/kresd.entrypoint.sh"]
