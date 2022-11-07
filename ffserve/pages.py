#!python3

import ffmirror.metadb as metadb
# import ffmirror
import os
from pathlib import Path

from itertools import chain
from operator import attrgetter

from flask import (Flask, g, render_template, url_for, request, abort,
                   send_from_directory, redirect, session)
app = Flask('ffserve', instance_relative_config=True)
app.config.from_pyfile('config.cfg')
app.secret_key = "dev"

from . import tasks  # noqa: E402

def template_function(func):
    app.jinja_env.globals[func.__name__] = func
    return func

@template_function
def page_url(pagenum):
    args = request.view_args.copy()
    args.update(request.args)
    args['page'] = pagenum
    return url_for(request.endpoint, **args)

@template_function
def find_story(site, sid):
    ind = g.mirror.get_index(check=False)
    for i in chain(*[i.stories for i in ind.values()]):
        if i['site'] == site and i['id'] == sid:
            return i
    return None

@app.template_filter()
def format_number(n):
    return "{:,}".format(n)

@app.template_filter()
def format_date(n):
    return n.date().isoformat()

@app.template_filter()
def sort_by(slist, order):
    nl = slist.copy()
    nl.sort(key=attrgetter('title'))  # secondary sort for those that matter
    nl.sort(key=attrgetter(order))
    if order in ['updated', 'words']:
        nl.reverse()
    return nl

@app.template_filter()
def stories_present(slist):
    return [i for i in slist if i.download_fn is not None]

@app.before_request
def req_setup():
    g.mirror = metadb.DBMirror(app.config['FF_DIR'], debug=app.config['DEBUG'])
    g.mirror.connect()
    app.config['FAV_DIR'] = os.path.join(app.config['FF_DIR'], '.favs')

def sort_query(aq):
    al = []
    for auth, story in aq.all():
        if len(al) == 0 or al[-1] is not auth:
            al.append(auth)
            auth.query_stories = []
        auth.query_stories.append(story)
    return al

def query_pages(alist):
    """A generator that returns pages (type [metadb.Author]) for the given
    query.

    """
    rv = []
    cp = 0
    page_thres = app.config['PAGE_THRES']
    for i in alist:
        rv.append(i)
        cp += len(i.query_stories)
        if cp >= page_thres:
            yield rv
            rv = []
            cp = 0
    yield rv

@template_function
def get_page(ind, alist):
    """This function returns a page (list of metadb.Author) given its index. Second
    return value is a boolean stating whether requested page is the last one.

    """
    if ind == -1:
        return alist, True
    pl = list(query_pages(alist))
    return pl[ind], ind >= len(pl) - 1

@template_function
def find_author(ao, alist):
    for n, i in enumerate(query_pages(alist)):
        if ao in i:
            return n
    return None

def index():
    pagenum = int(request.args.get('page', 0))
    query = (g.mirror.ds.query(metadb.Author, metadb.Story)
             .options(metadb.joinedload(metadb.Story.tags))
             .filter(metadb.Story.author_id == metadb.Author.id)
             .filter(metadb.Author.in_mirror == True)  # noqa: E712
             .order_by(metadb.func.lower(metadb.Author.name)))
    return render_template('main_index.html', pagenum=pagenum,
                           alist=sort_query(query), tag=None)

@app.route('/')
def frontpage():
    return redirect(url_for('all_authors'))

@app.route('/authorlist')
def all_authors():
    query = (g.mirror.ds.query(metadb.Author).options(
        metadb.joinedload(metadb.Author.stories_written)).
        filter(metadb.Author.in_mirror == True).  # noqa: E712
        order_by(metadb.func.lower(metadb.Author.name)))
    al = query.all()
    return render_template('all_authors.html', alist=al)

@app.route('/list/<author>')
def to_author(author):
    try:
        ao = g.mirror.ds.query(metadb.Author).filter_by(id=author).one()
    except metadb.exc.NoResultFound:
        abort(404)
    query = (g.mirror.ds.query(metadb.Author, metadb.Story)
             .filter(metadb.Story.author_id == metadb.Author.id)
             .filter(metadb.Author.in_mirror == True)  # noqa: E712
             .order_by(metadb.text("lower(name)")))
    page = find_author(ao, sort_query(query))
    if page is not None:
        return redirect(url_for('index', page=page) + '#' + author)
    abort(404)

@app.route('/story/<storyid>')
def story(storyid):
    # if not filepath.endswith('.html'):
    #     abort(404)
    try:
        story = (g.mirror.ds.query(metadb.Story).
                 options(metadb.joinedload(metadb.Story.all_chapters)).
                 filter_by(id=storyid).one())
    except metadb.exc.NoResultFound:
        abort(404)
    if not story.download_fn:
        abort(404)
    md = Path(g.mirror.mdir)
    sd = md / story.download_fn
    if not sd.is_dir():
        abort(404)
    for c in story.all_chapters:
        fp = sd / f"{c.num:04d}.html"
        c.chapter_text = fp.read_text()
    return render_template('view_story.html', story=story)
    # return send_from_directory(app.config['FF_DIR'], filepath,
    #                            mimetype='text/html')

@app.route('/tag/<path:tagname>')
def tag(tagname):
    order = request.args.get('sort', 'updated')
    page = int(request.args.get('page', 0))
    page_count = app.config['PAGE_THRES']
    to = g.mirror.ds.query(metadb.Tag).filter_by(name=tagname).one()
    query = (g.mirror.ds.query(metadb.Story, metadb.Author)
             .options(metadb.joinedload(metadb.Story.tags))
             .filter(metadb.Story.tags.contains(to))
             .filter(metadb.Story.author_id == metadb.Author.id)
             .filter(metadb.Author.in_mirror == True))  # noqa: E712
    num_stories = query.count()
    last_page = num_stories // page_count
    sl = (query.order_by(sorts[order]).
          limit(page_count).offset(page * page_count).all())
    return render_template('all_stories.html', listing=sl, page=page,
                           last_page=last_page)
    # return render_template('main_index.html', pagenum=pagenum,
    #                        alist=sort_query(query), tag=tagname)

@app.route('/favs/<author>')
def favs(author):
    order = request.args.get('sort', 'updated')
    try:
        ao = g.mirror.ds.query(metadb.Author).filter_by(id=author).one()
    except metadb.exc.NoResultFound:
        abort(404)
    g.mirror.sync_author(ao)
    ao = (g.mirror.ds.query(metadb.Author)
          .options(  # metadb.joinedload(metadb.Author.fav_stories)
                     # .joinedload('author'),
              metadb.joinedload(metadb.Author.fav_stories)
              .joinedload('tags'),
              metadb.joinedload(metadb.Author.stories_written)
              .joinedload('tags'))
          .filter_by(id=author).one())
    return render_template('favorites.html', ao=ao, order=order)

@app.route('/favorite/<sid>')
def favorite(sid):
    try:
        so = g.mirror.ds.query(metadb.Story).filter_by(id=sid).one()
    except metadb.exc.NoResultFound:
        abort(404)
    sfn = os.path.join('.favs', so.unique_filename())
    if so.download_time is None or so.updated > so.download_time:
        t = tasks.download_fav.delay(sid, sfn, app.config['DEBUG'])
        return redirect(url_for('wait_for_fav', task_id=t.id))
    return redirect(url_for('story', filepath=sfn))

@app.route('/download_fav/<task_id>')
def wait_for_fav(task_id):
    t = tasks.download_fav.AsyncResult(task_id)
    if t.state == 'SUCCESS':
        r = t.result
        return redirect(url_for('story', filepath=r['url']))
    elif t.state == 'FAILURE':
        t.get()  # to reraise exception and let debugger get it
    else:
        return render_template('wait_for_fav.html')
    # mod = ffmirror.sites[so.archive]
    # md = so.get_metadata()
    # story_url = mod.get_story_url(md)
    # author_url = mod.get_user_url(md)
    # # TODO make a prettier error page for this
    # abort(502, description=f"Could not download story " +
    #       f"{story_url} " +
    #       f"(author {author_url})")


sorts = {
    'title': metadb.Story.title, 'author': metadb.Author.name,
    'category': metadb.Story.category, 'words': metadb.Story.words.desc(),
    'updated': metadb.Story.updated.desc()
}

@app.route('/all_stories')
def all_stories():
    order = request.args.get('sort', 'updated')
    page_count = app.config['PAGE_THRES']
    page = int(request.args.get('page', 0))
    num_stories = (g.mirror.ds.query(metadb.Story, metadb.Author).
                   filter(metadb.Story.author_id == metadb.Author.id).
                   filter(metadb.Author.in_mirror == True).count())
    all_stories = (g.mirror.ds.query(metadb.Story, metadb.Author).
                   options(metadb.joinedload(metadb.Story.tags)).
                   filter(metadb.Story.author_id == metadb.Author.id).
                   filter(metadb.Author.in_mirror == True))  # noqa: E712
    last_page = num_stories // page_count
    sl = (all_stories.order_by(sorts[order]).
          limit(page_count).offset(page * page_count).all())
    return render_template('all_stories.html', listing=sl, page=page,
                           last_page=last_page)

@app.route("/refresh_test")
def refresh_test():
    task_id = session.get('task')
    if task_id is None:
        t = tasks.long_task.delay()
        session['task'] = t.id
        message = "New task: " + t.id
    else:
        t = tasks.long_task.AsyncResult(task_id)
        if t.state == 'PENDING':
            message = f"Task {t.id} is pending"
        elif t.state == 'PROGRESS':
            di = dict(t.info)
            message = di['status']
        else:
            rv = t.get()
            message = f"State: {t.state}, got: " + str(rv)
            session.pop('task')
    return render_template("test.html", message=message)
