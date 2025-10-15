FROM fedora:latest
LABEL org.opencontainers.image.authors="Knot Resolver <knot-resolver@labs.nic.cz>"

# Knot DNS (build), Knot Resolver (build + runtime) dependencies
RUN dnf install -y \
	git \
	automake \
	make \
	libtool \
	gcc \
	gcc-c++ \
	lua-socket-compat \
	lua-sec-compat \
	'pkgconfig(cmocka)' \
	'pkgconfig(gnutls)' \
	'pkgconfig(libedit)' \
	'pkgconfig(libidn2)' \
	'pkgconfig(libknot)' \
	'pkgconfig(libzscanner)' \
	'pkgconfig(libdnssec)' \
	'pkgconfig(libsystemd)' \
	'pkgconfig(libuv)' \
	'pkgconfig(liburcu)' \
	'pkgconfig(luajit)' \
	'pkgconfig(lmdb)'

# Make Knot DNS
RUN git clone -b 2.6 --depth=1 https://gitlab.nic.cz/knot/knot-dns.git /tmp/knot
WORKDIR /tmp/knot
RUN autoreconf -if
RUN ./configure --disable-static --enable-fastparser --disable-documentation
RUN make
RUN make install
RUN ldconfig

# Make Knot Resolver
RUN git clone --recursive -j8 https://gitlab.nic.cz/knot/knot-resolver.git /var/opt/knot-resolver
WORKDIR /var/opt/knot-resolver
RUN git checkout v2.4.0
RUN mkdir .install
RUN make PREFIX=/var/opt/knot-resolver/.install LDFLAGS="-Wl,-rpath=/var/opt/knot-resolver/.install/lib"
RUN make install PREFIX=/var/opt/knot-resolver/.install

CMD /var/opt/knot-resolver/.install/sbin/kresd -c /etc/knot-resolver/kresd.conf -v /dev/shm
