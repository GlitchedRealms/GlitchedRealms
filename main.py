from flask import Flask, render_template, session, redirect, url_for, request
from flask_socketio import SocketIO, disconnect
import os
from docker_information import docker_manager
from socket_routes import register_socket_routes  # <- changed name!

app = Flask(__name__)
app.secret_key = os.urandom(24)
sio = SocketIO(app, cors_allowed_origins="*", manage_session=False)
docker_mgr = docker_manager()

register_socket_routes(sio, docker_mgr)

@app.route('/')
def index():
    if 'user_id' in session:
        return render_template("index.html")
    else:
        return render_template("index_not_logged_in.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template("login.html")
    elif request.method == 'POST':
        user_id = request.form.get('username')
        if user_id:
            session['user_id'] = user_id
            return redirect(url_for('index'))
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/terminal/<container_name>')
def terminal(container_name):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))
    container = docker_mgr.find_container_by_logical_name(user_id, container_name)
    if not container or container.status != "running":
        return redirect(url_for('index'))
    return render_template("terminal.html")


sio.run(app, host="0.0.0.0", port=5000)