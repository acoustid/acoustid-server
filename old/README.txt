Acoustid Server
===============

Compile and install a PostgreSQL extension used by the server code:

$ cd postgresql
$ make
$ sudo make install

Compile Java source code:

$ mvn install

Run the server on a development machine:

$ cp conf/acoustid.xml.default conf/acoustid.xml
$ vim conf/acoustid.xml
$ cd server
$ mvn jetty:run

