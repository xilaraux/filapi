'''
ADD:
- size restriction
- extension restriction
+ web form for uploading
+ sterams support
+ better web app with progress and buffer
- x-file header support (nginx setup)
- files uploaded by transaction can be uploaded multiple times (move to transaction id instead of hashes)
- refactor code

https://flask.palletsprojects.com/en/1.1.x/patterns/fileuploads/
'''

from time import time
from hashlib import md5
from uuid import uuid4
from sys import getsizeof
from os import makedirs, listdir, rename, remove
from os.path import isfile, join
from sqlite3 import IntegrityError

from filapi.db import get_db

from werkzeug.utils import secure_filename
from flask import Blueprint, request, current_app, redirect, url_for, abort, send_file, safe_join, send_from_directory, jsonify


bp = Blueprint('files', __name__, url_prefix='/files')


def init_app(app):
  app.config['UPLOAD_FOLDER'] = join(app.instance_path, 'files')

  try:
    makedirs(app.config['UPLOAD_FOLDER'])
  except OSError:
    pass


def allowed_file(filename):
  return True


def save_file_to_db(name, size, hash):
  try:
    db = get_db()
    db.execute(
      'INSERT INTO files (name, hash, size)'
      ' VALUES (?, ?, ?)',
      (name, hash, size)
    )
    db.commit()
  except IntegrityError:
    pass


def save_file(folder, file):
  file_bytes = file.read()

  filename = file.filename
  filesize = getsizeof(file_bytes)
  filehash = md5(file_bytes).hexdigest()
  
  with open(join(folder, filehash), 'wb') as f:
    f.write(file_bytes)

  save_file_to_db(filename, filesize, filehash)


def save_transaction_file(folder, transaction):
  transactionID = transaction.get('ID')
  filename = transaction.get('name')
  filesize = transaction.get('size')
  transaction_path = join(folder, transactionID)
  with open(transaction_path, 'rb') as f:
    filehash = md5(f.read()).hexdigest()
  save_path = join(folder, filehash)
  if not isfile(save_path):
    rename(transaction_path, save_path)
    print(f'renamed from {transactionID} to {filehash}')
  else:
    remove(transaction_path)
    print(f'removed {transactionID}')
  save_file_to_db(filename, filesize, filehash)


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
  
  files_info = ['<a href="/files/upload">Upload files</a><br><br>']
  for file in file_list:
    fileurl = url_for('files.download_file', filehash=file['hash'])
    filename = file['name']
    filesize = file['size'] / 1024

    files_info.append(f'<a href="{fileurl}">{filename}</a> ({filesize:.2f} KB)')

  html = '<br>'.join(files_info) or 'empty'

  return html


@bp.route('/upload')
def upload():
  return send_from_directory('templates', 'upload.html')


transactions= dict()
@bp.route('/upload/transaction', methods=('GET', 'POST'))
def upload_transaction():
  if request.method == 'GET':
    return redirect(url_for('files.files'))

  data = request.json
  
  mode = data.get('mode', None)
  file = data.get('file')
  finename = file.get('name')
  filesize = file.get('size')

  transaction = uuid4().hex
  hour = 60 * 60
  expiration = time() + hour

  transactions[transaction] = {
    'ID': transaction,
    'name': finename,
    'size': filesize,
    'exp': expiration,
    'received': 0
  }

  return transaction


@bp.route('/upload/file', methods=('GET', 'POST'))
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


@bp.route('/upload/chunk', methods=('GET', 'POST'))
def upload_chunk():
  if request.method == 'GET':
    return redirect(url_for('files.files'))

  transactionID = request.form.get('ID', None)
  transaction = transactions.get(transactionID, None)

  if not transaction:
    error = {
      'ok': False,
      'status': 500,
      'statusText': 'Transaction does not exist.'
    }
    return jsonify(error)

  if time() >= transaction.get('exp'):
    error = {
      'ok': False,
      'status': 500,
      'statusText': 'Transaction has expiered.'
    }
    return jsonify(error)

  upload_folder = current_app.config['UPLOAD_FOLDER']
  chunk = request.files['chunk'].read()
  
  if isfile(join(upload_folder, transactionID)):
    with open(join(upload_folder, transactionID), 'ab') as f:
      transaction['received'] += len(chunk)
      f.write(chunk)
  else:
    with open(join(upload_folder, transactionID), 'wb') as f:
      transaction['received'] += len(chunk)
      f.write(chunk)

  if transaction['received'] == transaction['size']:
    # print(f'{transaction.get("name")} uploaded')
    save_transaction_file(upload_folder, transaction)

  return jsonify({
    'ok': True,
  })


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
