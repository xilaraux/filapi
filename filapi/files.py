'''
ADD:
- size restriction
- extension restriction
- web for for uploading
- sterams support
- better web app with progress and buffer
- x-file header support

https://flask.palletsprojects.com/en/1.1.x/patterns/fileuploads/
'''

from hashlib import md5
from sys import getsizeof
from os import makedirs, listdir
from os.path import isfile, join
from sqlite3 import IntegrityError

from filapi.db import get_db

from werkzeug.utils import secure_filename
from flask import Blueprint, request, current_app, redirect, url_for, abort, send_file, safe_join


bp = Blueprint('files', __name__, url_prefix='/files')


def init_app(app):
  app.config['UPLOAD_FOLDER'] = join(app.instance_path, 'files')

  try:
    makedirs(app.config['UPLOAD_FOLDER'])
  except OSError:
    pass


def allowed_file(filename):
  return True


def save_file(folder, file):
  file_bytes = file.read()

  filename = file.filename
  filesize = getsizeof(file_bytes)
  filehash = md5(file_bytes).hexdigest()
  
  with open(join(folder, filehash), 'wb') as f:
    f.write(file_bytes)

  try:
    db = get_db()
    db.execute(
      'INSERT INTO files (name, hash, size)'
      ' VALUES (?, ?, ?)',
      (filename, filehash, filesize)
    )
    db.commit()
  except IntegrityError:
    pass


@bp.route('/')
def files():
  '''disply uploaded files with info'''
  # upload_folder = current_app.config['UPLOAD_FOLDER']
  # folder_content = listdir(upload_folder)
  # files = [f for f in folder_content if isfile(join(upload_folder, f))]

  db = get_db()
  file_list = db.execute(
    'SELECT * from files'
  ).fetchall()
  
  files_info = []
  for file in file_list:
    fileurl = url_for('files.download_file', filehash=file['hash'])
    filename = file['name']
    filesize = file['size'] / 1024

    files_info.append(f'<a href="{fileurl}">{filename}</a> ({filesize:.2f} KB)')

  html = '<br>'.join(files_info) or 'empty'

  return html


@bp.route('/upload/', methods=('GET', 'POST'))
def upload_file():
  if request.method == 'GET':
    return redirect(url_for('files.files'))

  upload_folder = current_app.config['UPLOAD_FOLDER']

  if 'file' not in request.files:
    return abort(500)

  file = request.files['file']

  if file.filename == '':
    return abort(501)

  if file and allowed_file(file.filename):
    save_file(upload_folder, file)
    return redirect(url_for('files.files'))


@bp.route('/download/<string:filehash>/')
def download_file(filehash):
  db= get_db()

  # check if exists this hash
  file = db.execute(
    'SELECT name, size'
    ' FROM files'
    ' WHERE hash = ?',
    (filehash,)
  ).fetchone()

  # throw an error
  if file is None:
    return abort(404)

  # or return to client the file
  folder = current_app.config['UPLOAD_FOLDER']
  response = send_file(safe_join(folder, filehash), as_attachment=True, attachment_filename=file['name'])
  # response.headers['x-suggested-filename'] = file['name']
  return response
