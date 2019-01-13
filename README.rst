This is a Flask web app that interacts with ffmirror to allow you to view a
local fanfiction mirror over the Web. It fulfills the same purpose as the
now-obsolete server.py in ffmirror.

You can install it via poetry using ``poetry install``. ffmirror is a
dependency. After installation, copy the ``config.cfg.default`` under
``instance`` to the name ``config.cfg``, and set the proper path to your
ffmirror archive. Then you can use the ``flask run`` command to run it as a
development server.

If you want to deploy it publicly, flask can do that, but I question your
priorities.
