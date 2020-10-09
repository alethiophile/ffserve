#!python3

from .pages import app, metadb
import celery

queue = celery.Celery(app.name)
queue.conf.update(
    broker_url='redis://127.0.0.1:6379/0',
    result_backend='redis://127.0.0.1:6379/0'
)

@queue.task
def download_fav(sid, rfn, dbg):
    mirror = metadb.DBMirror(app.config['FF_DIR'], debug=dbg)
    mirror.connect()
    so = mirror.ds.query(metadb.Story).filter_by(id=sid).one()
    mirror.story_to_archive(so, rfn=rfn,
                            silent=not dbg)
    return {'url': rfn}
