#!/usr/bin/python

import ffmirror.mirror as mirror
from datetime import datetime
import os, argparse

from flask import Flask, g, render_template, url_for, request
app = Flask('ffserve')

if __name__=='__main__':
    ap = argparse.ArgumentParser(description="Browse an ffmirror archive over the Web")
    ap.add_argument("-d", "--debug", dest="DEBUG", action="store_true", help="Debug in browser", default=False)
    ap.add_argument("--page-thres", dest="PAGE_THRES", type=int, help="Minimum story entries per page", default=100)
    ap.add_argument("-l", "--local", action="store_true", help="Listen only on local interface", default=False)
    ap.add_argument("-p", "--port", type=int, help="HTTP server port", default=5000)
    ap.add_argument("FF_DIR", help="Mirror directory")
    args = ap.parse_args()

app.config.from_object(args)

@app.before_request
def req_setup():
    g.mirror = mirror.FFMirror(app.config['FF_DIR'])
    g.url_for = url_for
    def format_number(n):
        return "{:,}".format(n)
    g.format_number = format_number
    def format_date(n):
        return datetime.fromtimestamp(int(n)).date().isoformat()
    g.format_date = format_date
    def in_page(author, pages):
        for n, i in enumerate(pages):
            if author in i:
                return n
    g.in_page = in_page

def make_pages(ind):
    """This function takes an index (type {author: [story]}) and returns a list of
    pages. A page is a list of authors who will be on that page."""
    page_thres = app.config['PAGE_THRES']
    il = sorted(iter(ind.keys()), key= lambda x: x.lower())
    cl = 0
    ol = []
    lc = 0
    for n,i in enumerate(il):
        cl += len(ind[i])
        if cl >= page_thres:
            cl = 0
            ol.append((lc, n+1))
            lc = n+1
    if len(ol) == 0 or ol[-1][1] != len(il):
        ol.append((lc, len(il)))
    return [il.__getitem__(slice(*i)) for i in ol]

@app.route('/')
def index():
    ind = g.mirror.get_index()
    pagenum = int(request.args.get('page', 0))
    pages = make_pages(ind)
    if pagenum == -1:
        pages = [ [i for sl in pages for i in sl] ]
        pagenum = 0
    return render_template('main_index.html', ind=ind, pages=pages, pagenum=pagenum)

@app.route('/story/<path:filepath>')
def story(filepath):
    if '/../' in filepath or filepath.startswith('../'):
        abort(403)
    fn = os.path.join(app.config['FF_DIR'], filepath)
    with open(fn, 'r') as infile:
        return infile.read()

@app.route('/tag/<path:tagname>')
def tag(tagname):
    ind = g.mirror.get_index()
    pagenum = int(request.args.get('page', 0))
    ind = { k: [i for i in ind[k] if tagname in i['tags']] for k in ind.keys() }
    ind = { k: ind[k] for k in ind.keys() if len(ind[k]) != 0 }
    pages = make_pages(ind)
    if pagenum == -1:
        pages = [ [i for sl in pages for i in sl] ]
        pagenum = 0
    return render_template('main_index.html', ind=ind, pages=pages, pagenum=pagenum, tag=tagname)

if __name__=='__main__':
    host = '127.0.0.1' if args.local else '0.0.0.0'
    app.run(host=host, port=args.port)
